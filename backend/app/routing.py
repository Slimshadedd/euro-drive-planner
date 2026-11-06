"""Road routing via public OpenStreetMap routing services.

* OSRM (router.project-osrm.org) distance tables - fast screening of many port combinations.
* Valhalla (valhalla1.openstreetmap.de) detailed routes - geometry plus which stretches are
  toll roads / motorways, which we split per country for fuel, toll and vignette costing.
"""
from __future__ import annotations

import logging

from . import cache, geo, net

log = logging.getLogger(__name__)

OSRM = "https://router.project-osrm.org"
VALHALLA = "https://valhalla1.openstreetmap.de"
ROUTE_TTL = 30 * 86400

Point = tuple[float, float]  # (lat, lon)


def _k(p: Point) -> str:
    return f"{p[0]:.4f},{p[1]:.4f}"


async def table(points: list[Point]) -> tuple[list[list[float | None]], list[list[float | None]]]:
    """All-pairs driving distance (km) and duration (s) between points. None = unreachable."""
    key = "osrm-table:" + ";".join(_k(p) for p in points)
    hit = cache.get(key)
    if hit:
        return hit["km"], hit["s"]
    coords = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in points)
    r = await net.get(f"{OSRM}/table/v1/driving/{coords}", params={"annotations": "distance,duration"})
    d = r.json()
    if d.get("code") != "Ok":
        raise RuntimeError(f"OSRM table failed: {d.get('message')}")
    km = [[(x / 1000.0 if x is not None else None) for x in row] for row in d["distances"]]
    s = d["durations"]
    cache.put(key, {"km": km, "s": s}, ROUTE_TTL)
    return km, s


async def route(a: Point, b: Point, avoid_tolls: bool = False) -> dict:
    """Detailed route a->b. Returns distance_km, duration_s, geometry and per-country breakdown:
    countries = {CC: {"km", "toll_km", "motorway_km"}}, plus has_ferry/has_toll flags."""
    key = f"route:{_k(a)}:{_k(b)}:{int(avoid_tolls)}"
    hit = cache.get(key)
    if hit:
        return hit
    try:
        res = await _valhalla(a, b, avoid_tolls)
    except Exception as e:  # noqa: BLE001 - fall back to OSRM on any Valhalla problem
        log.warning("Valhalla failed (%s); falling back to OSRM", e)
        res = await _osrm_route(a, b)
    cache.put(key, res, ROUTE_TTL)
    return res


async def _valhalla(a: Point, b: Point, avoid_tolls: bool) -> dict:
    body = {
        "locations": [{"lat": a[0], "lon": a[1]}, {"lat": b[0], "lon": b[1]}],
        "costing": "auto",
        "costing_options": {"auto": {"use_ferry": 0.0, "use_tolls": 0.0 if avoid_tolls else 0.5}},
        "units": "kilometers",
        "directions_type": "maneuvers",
    }
    r = await net.post(f"{VALHALLA}/route", json=body)
    trip = r.json()["trip"]
    shape: list[Point] = []
    flags: list[tuple[bool, bool, bool]] = []  # per shape segment: (toll, motorway, ferry)
    for leg in trip["legs"]:
        pts = geo.decode_polyline(leg["shape"], 6)
        seg_flags = [(False, False, False)] * max(len(pts) - 1, 0)
        for m in leg["maneuvers"]:
            f = (bool(m.get("toll")), bool(m.get("highway")),
                 bool(m.get("ferry")) or m.get("travel_type") == "ferry")
            for i in range(m["begin_shape_index"], min(m["end_shape_index"], len(seg_flags))):
                seg_flags[i] = f
        shape.extend(pts); flags.extend(seg_flags + [(False, False, False)])
    s = trip["summary"]
    return _breakdown(shape, flags[: max(len(shape) - 1, 0)], s["length"], s["time"],
                      engine="valhalla", has_ferry=s.get("has_ferry", False))


async def _osrm_route(a: Point, b: Point) -> dict:
    coords = f"{a[1]:.5f},{a[0]:.5f};{b[1]:.5f},{b[0]:.5f}"
    r = await net.get(f"{OSRM}/route/v1/driving/{coords}",
                      params={"overview": "full", "geometries": "polyline6", "steps": "true"})
    d = r.json()
    if d.get("code") != "Ok":
        raise RuntimeError(f"No road route found ({d.get('message', d.get('code'))})")
    rt = d["routes"][0]
    shape: list[Point] = []
    flags: list[tuple[bool, bool, bool]] = []
    for leg in rt["legs"]:
        for st in leg["steps"]:
            pts = geo.decode_polyline(st["geometry"], 6)
            cls = set()
            for it in st.get("intersections", []):
                cls |= set(it.get("classes", []))
            f = ("toll" in cls, "motorway" in cls, "ferry" in cls or st.get("mode") == "ferry")
            if shape and pts and pts[0] == shape[-1]:
                pts = pts[1:]
            elif shape and pts:
                flags.append(f)
            shape.extend(pts)
            flags.extend([f] * max(len(pts) - 1, 0))
    return _breakdown(shape, flags[: max(len(shape) - 1, 0)], rt["distance"] / 1000.0,
                      rt["duration"], engine="osrm",
                      has_ferry=any(f[2] for f in flags))


def _breakdown(shape: list[Point], flags, total_km: float, total_s: float, engine: str,
               has_ferry: bool) -> dict:
    countries: dict[str, dict[str, float]] = {}
    current = geo.nearest_country(*shape[0]) if shape else None
    since_check = 1e9
    measured = 0.0
    for i in range(len(shape) - 1):
        (la1, lo1), (la2, lo2) = shape[i], shape[i + 1]
        d = geo.haversine_km(la1, lo1, la2, lo2)
        since_check += d
        if since_check >= 2.0:  # re-check the country every ~2 km
            c = geo.country_at((la1 + la2) / 2, (lo1 + lo2) / 2, hint=current)
            if c:
                current = c
            since_check = 0.0
        toll, mway, ferry = flags[i] if i < len(flags) else (False, False, False)
        e = countries.setdefault(current or "??", {"km": 0.0, "toll_km": 0.0, "motorway_km": 0.0, "ferry_km": 0.0})
        e["km"] += d
        if toll:
            e["toll_km"] += d
        if mway:
            e["motorway_km"] += d
        if ferry:
            e["ferry_km"] += d
        measured += d
    scale = total_km / measured if measured > 0 else 1.0
    for e in countries.values():
        for k in e:
            e[k] = round(e[k] * scale, 2)
    return {
        "engine": engine,
        "distance_km": round(total_km, 2),
        "duration_s": round(total_s),
        "countries": countries,
        "has_ferry": has_ferry,
        "geometry": [[round(la, 5), round(lo, 5)] for la, lo in geo.simplify(shape, 0.4)],
    }
