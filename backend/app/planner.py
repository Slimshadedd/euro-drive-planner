"""Find the cheapest / fastest ways to drive between two places, including sea crossings.

The network is three landmasses (Great Britain, the island of Ireland, mainland Europe)
joined by ferry / shuttle crossings. A journey is: drive -> crossing -> drive [-> crossing -> drive].

1. Screening: one OSRM distance table per landmass gives road km/time between the origin,
   the destination and every port, so every crossing combination can be priced roughly.
2. Refinement: the best candidates get detailed routes (per-country fuel, tolls, vignettes)
   and their crossing fares (live if collected, otherwise estimated), then are re-ranked.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import itertools
import logging
from dataclasses import dataclass, field

from . import costs, crossings, geo, routing

log = logging.getLogger(__name__)

LANDMASS_NAMES = {"GB": "Great Britain", "IE": "Ireland", "EU": "mainland Europe"}
SCREEN_KEEP = 12


@dataclass
class Place:
    lat: float
    lon: float
    label: str = ""


@dataclass
class PlanRequest:
    origin: Place
    destination: Place
    date: dt.date
    party: crossings.Party = field(default_factory=crossings.Party)
    vehicle: costs.Vehicle = field(default_factory=costs.Vehicle)
    mode: str = "cheapest"                # cheapest | fastest | balanced
    value_of_time: float = 10.0           # display currency per hour (balanced mode)
    currency: str = "GBP"
    avoid_tolls: bool = False
    max_results: int = 6
    live_fares: bool = False


def _score(mode: str, money: float, seconds: float, vot: float) -> float:
    if mode == "fastest":
        return seconds
    if mode == "balanced":
        return money + seconds / 3600.0 * vot
    return money


async def plan(req: PlanRequest, live_fetch=None) -> dict:
    fx = await costs.fx_rates()
    cur = req.currency if req.currency in fx else "EUR"
    rate = fx[cur]  # display units per EUR
    vot_eur = req.value_of_time / rate

    o_c = geo.nearest_country(req.origin.lat, req.origin.lon)
    d_c = geo.nearest_country(req.destination.lat, req.destination.lon)
    o_lm = geo.landmass(req.origin.lat, req.origin.lon, o_c)
    d_lm = geo.landmass(req.destination.lat, req.destination.lon, d_c)
    warnings: list[str] = []

    ports = crossings.ports()
    all_routes = crossings.routes()

    # ---- landmass sequences ------------------------------------------------------------
    if o_lm == d_lm:
        sequences = [[o_lm]]
    else:
        sequences = [[o_lm, d_lm]]
        for mid in ("GB", "IE", "EU"):
            if mid not in (o_lm, d_lm):
                sequences.append([o_lm, mid, d_lm])

    # ---- screening tables (one per landmass) -----------------------------------------------
    needed = {lm for seq in sequences for lm in seq}
    node_points: dict[str, list[tuple[str, tuple[float, float]]]] = {}
    for lm in needed:
        pts = [(pid, (p["lat"], p["lon"])) for pid, p in ports.items() if p["landmass"] == lm]
        if lm == o_lm:
            pts.insert(0, ("@O", (req.origin.lat, req.origin.lon)))
        if lm == d_lm:
            pts.insert(0, ("@D", (req.destination.lat, req.destination.lon)))
        node_points[lm] = pts

    tables = {}
    for lm, pts in node_points.items():
        km, s = await routing.table([p for _, p in pts])
        idx = {pid: i for i, (pid, _) in enumerate(pts)}
        tables[lm] = (idx, km, s)

    def road(lm: str, a: str, b: str):
        idx, km, s = tables[lm]
        if a == b:
            return 0.0, 0.0
        x, y = km[idx[a]][idx[b]], s[idx[a]][idx[b]]
        return (x, y) if x is not None and y is not None else None

    # ---- enumerate candidate journeys ----------------------------------------------------
    candidates = []
    for seq in sequences:
        if len(seq) == 1:
            r = road(seq[0], "@O", "@D")
            if r:
                candidates.append({"crossings": [], "screen_km": [r[0]], "screen_s": r[1],
                                   "road_eur": costs.rough_road_cost_eur(r[0], seq[0], req.vehicle)})
            continue
        hops = []
        for a, b in zip(seq, seq[1:]):
            hops.append([r for r in all_routes
                         if ports[r["from"]]["landmass"] == a and ports[r["to"]]["landmass"] == b])
        for combo in itertools.product(*hops):
            stops = ["@O"]
            for cr in combo:
                stops += [cr["from"], cr["to"]]
            stops.append("@D")
            total_eur = total_s = 0.0
            kms = []
            ok = True
            for i, lm in enumerate(seq):
                r = road(lm, stops[2 * i], stops[2 * i + 1])
                if r is None:
                    ok = False
                    break
                kms.append(r[0])
                total_eur += costs.rough_road_cost_eur(r[0], lm, req.vehicle)
                total_s += r[1]
            if not ok:
                continue
            for cr in combo:
                total_s += (cr["duration_min"] + cr["checkin_min"]) * 60
            candidates.append({"crossings": list(combo), "screen_km": kms,
                               "screen_s": total_s, "road_eur": total_eur})

    if not candidates:
        return {"options": [], "warnings": ["No drivable route found between these places."],
                "currency": cur}

    # ---- live fares for every crossing that has a collector (before shortlisting, so a live
    #      fare that beats its estimate can still make the shortlist) -------------------------
    if req.live_fares and live_fetch:
        wanted = {cr["id"]: cr for c in candidates for cr in c["crossings"]}
        try:
            report = await live_fetch(list(wanted.values()), req.date, req.party)
            warnings.extend(report.get("warnings", []))
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Live fare collection failed: {e}")

    # Drop crossings the operator says have no sailings near this date.
    def sails(cr):
        return not crossings.no_sailing(cr["id"], req.date)
    gone = sorted({f"{ports[cr['from']]['name']} → {ports[cr['to']]['name']}"
                   for c in candidates for cr in c["crossings"] if not sails(cr)})
    if gone:
        warnings.append("Not sailing within 3 days of this date (left out): " + ", ".join(gone) + ".")
    candidates = [c for c in candidates if all(sails(cr) for cr in c["crossings"])]
    if not candidates:
        return {"options": [], "warnings": warnings + ["No crossings are sailing around this date."],
                "currency": cur}

    for c in candidates:
        c["screen_eur"] = c["road_eur"] + sum(crossings.fare(cr, req.date, req.party, fx)["eur"]
                                              for cr in c["crossings"])
        c["screen_score"] = _score(req.mode, c["screen_eur"], c["screen_s"], vot_eur)
    keep = sorted(candidates, key=lambda c: c["screen_score"])[:SCREEN_KEEP]
    # Always include the very cheapest and very fastest so the comparison is honest.
    for extra in (min(candidates, key=lambda c: c["screen_eur"]), min(candidates, key=lambda c: c["screen_s"])):
        if extra not in keep:
            keep.append(extra)

    # ---- detailed routing ------------------------------------------------------------------
    point_of = {"@O": (req.origin.lat, req.origin.lon), "@D": (req.destination.lat, req.destination.lon)}
    point_of.update({pid: (p["lat"], p["lon"]) for pid, p in ports.items()})
    leg_keys = set()
    for c in keep:
        stops = _stops(c)
        for i in range(0, len(stops), 2):
            if stops[i] != stops[i + 1]:
                leg_keys.add((stops[i], stops[i + 1]))
    sem = asyncio.Semaphore(3)
    legs: dict[tuple[str, str], dict] = {}

    async def fetch(k):
        async with sem:
            try:
                legs[k] = await routing.route(point_of[k[0]], point_of[k[1]], req.avoid_tolls)
            except Exception as e:  # noqa: BLE001
                log.warning("route %s failed: %s", k, e)

    await asyncio.gather(*(fetch(k) for k in leg_keys))

    label = {"@O": req.origin.label or "Start", "@D": req.destination.label or "Destination"}
    label.update({pid: p["name"] for pid, p in ports.items()})

    options = []
    for c in keep:
        opt = _build_option(c, legs, label, req, fx, rate)
        if opt:
            opt["score"] = _score(req.mode, opt["_eur"], opt["duration_s"], vot_eur)
            options.append(opt)
    options.sort(key=lambda o: o["score"])
    ranked = _dedupe(options)
    options = ranked[: req.max_results]
    # Always show the overall cheapest and fastest options so the trade-off is visible.
    for best in (min(ranked, key=lambda o: o["_eur"], default=None),
                 min(ranked, key=lambda o: o["duration_s"], default=None)):
        if best is not None and best not in options:
            options = options[: req.max_results - 1] + [best] if len(options) >= req.max_results else options + [best]
    if options:
        cheapest = min(o["_eur"] for o in options)
        fastest = min(o["duration_s"] for o in options)
        for o in options:
            o["is_cheapest"] = o["_eur"] == cheapest
            o["is_fastest"] = o["duration_s"] == fastest
            o["extra_vs_cheapest"] = round((o["_eur"] - cheapest) * rate, 2)
            del o["_eur"]
    ferry_legs = sorted({f"{l['from']} → {l['to']}" for o in options for l in o["legs"]
                         if l["type"] == "road" and l.get("includes_ferry")})
    if ferry_legs:
        warnings.append("The road route for " + ", ".join(ferry_legs) + " includes a short ferry the router "
                        "couldn't avoid (e.g. a river crossing); its fare isn't included.")

    return {
        "currency": cur,
        "fx_per_eur": rate,
        "origin": {"country": o_c, "landmass": LANDMASS_NAMES[o_lm]},
        "destination": {"country": d_c, "landmass": LANDMASS_NAMES[d_lm]},
        "mode": req.mode,
        "candidates_considered": len(candidates),
        "options": options,
        "warnings": warnings,
    }


def _stops(c) -> list[str]:
    stops = ["@O"]
    for cr in c["crossings"]:
        stops += [cr["from"], cr["to"]]
    return stops + ["@D"]


def _build_option(c, legs, label, req: PlanRequest, fx, rate) -> dict | None:
    stops = _stops(c)
    out_legs = []
    fuel = tolls = fares = 0.0
    fuel_by_type = {f: 0.0 for f in costs.FUELS}
    litres = 0.0
    vignettes: dict[str, dict] = {}
    specials: dict[str, dict] = {}
    dist = dur = 0.0
    for i in range(0, len(stops), 2):
        a, b = stops[i], stops[i + 1]
        if a != b:
            leg = legs.get((a, b))
            if not leg:
                return None
            lc = costs.leg_cost(leg, req.vehicle)
            fuel += lc["fuel_eur"]
            for ft in costs.FUELS:
                fuel_by_type[ft] += lc["fuel_by_type_eur"][ft]
            litres += sum(p["litres"] for p in lc["per_country"])
            tolls += lc["tolls_eur"]
            for it in lc["items"]:
                (vignettes if it["kind"] == "vignette" else specials)[it["country"] + it["label"]] = it
            dist += leg["distance_km"]
            dur += leg["duration_s"]
            out_legs.append({
                "type": "road", "from": label[a], "to": label[b],
                "distance_km": leg["distance_km"], "duration_s": leg["duration_s"],
                "fuel": round(lc["fuel_eur"] * rate, 2),
                "tolls": round(lc["tolls_eur"] * rate, 2),
                "per_country": [{**p, "fuel": round(p["fuel_eur"] * rate, 2), "toll": round(p["toll_eur"] * rate, 2),
                                 "petrol_price": round(p["petrol_price_eur"] * rate, 3),
                                 "diesel_price": round(p["diesel_price_eur"] * rate, 3)}
                                for p in lc["per_country"]],
                "items": [{**it, "amount": round(it["eur"] * rate, 2)} for it in lc["items"]],
                "geometry": leg["geometry"], "engine": leg["engine"],
                "includes_ferry": bool(leg.get("has_ferry")),
            })
        cidx = i // 2
        if cidx < len(c["crossings"]):
            cr = c["crossings"][cidx]
            f = crossings.fare(cr, req.date, req.party, fx)
            fares += f["eur"]
            dur += (cr["duration_min"] + cr["checkin_min"]) * 60
            p_from, p_to = crossings.ports()[cr["from"]], crossings.ports()[cr["to"]]
            out_legs.append({
                "type": "crossing", "id": cr["id"], "operator": cr["operator"], "kind": cr["type"],
                "from": p_from["name"], "to": p_to["name"],
                "geometry": [[p_from["lat"], p_from["lon"]], [p_to["lat"], p_to["lon"]]],
                "duration_min": cr["duration_min"], "checkin_min": cr["checkin_min"],
                "overnight": cr.get("overnight", False), "booking_url": cr["booking_url"],
                "fare": round(f["eur"] * rate, 2), "fare_source": f["source"],
                "fare_detail": {k: v for k, v in f.items() if k not in ("eur",)},
            })
    vig_total = sum(v["eur"] for v in vignettes.values())
    # Special tolls were already added into `tolls` per leg; vignettes are de-duplicated per trip.
    total = fuel + tolls + vig_total + fares
    non_fuel = tolls + vig_total + fares
    crossings_used = [l for l in out_legs if l["type"] == "crossing"]
    if crossings_used:
        title = " + ".join(f"{l['from']} → {l['to']}" for l in crossings_used)
        subtitle = " + ".join(f"{l['operator']}" for l in crossings_used)
    else:
        title, subtitle = "Drive direct", "No sea crossing needed"
    return {
        "title": title, "subtitle": subtitle,
        "total": round(total * rate, 2),
        "breakdown": {"fuel": round(fuel * rate, 2), "tolls": round(tolls * rate, 2),
                      "vignettes": round(vig_total * rate, 2), "crossings": round(fares * rate, 2)},
        "fuel_compare": {ft: {"fuel": round(fuel_by_type[ft] * rate, 2),
                              "total": round((fuel_by_type[ft] + non_fuel) * rate, 2)}
                         for ft in costs.FUELS},
        "litres": round(litres, 1),
        "vignettes": [{**v, "amount": round(v["eur"] * rate, 2)} for v in vignettes.values()],
        "distance_km": round(dist, 1), "duration_s": round(dur),
        "all_fares_live": bool(crossings_used) and all(l["fare_source"] == "live" for l in crossings_used),
        "legs": out_legs, "_eur": total,
    }


def _dedupe(options: list[dict]) -> list[dict]:
    seen, out = set(), []
    for o in options:
        key = (o["title"], o["subtitle"])
        if key not in seen:
            seen.add(key)
            out.append(o)
    return out
