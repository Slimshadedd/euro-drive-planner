"""Brittany Ferries (UK <-> France / Spain).

The booking site's "choose sailing" step loads fares from a public JSON endpoint
(`/api/bebop/v1/crossing/prices`) that answers a plain request: route ports, dates, passengers and a
generic vehicle size. No browser or session is needed. The registration is the site's own placeholder
"TBC"; no personal details are sent.

The response flags sailings where a cabin is compulsory (overnight / Spain) and includes the
cheapest such cabin, so we add it - matching the estimates, which include a basic cabin.
"""
from __future__ import annotations

import datetime as dt
import logging

from .. import net
from ..crossings import Party
from .base import Collector, NoSailings, Quote, Unsupported

log = logging.getLogger(__name__)

SITE = "https://www.brittany-ferries.co.uk"
PRICES_API = f"{SITE}/api/bebop/v1/crossing/prices"

_OUT = {  # our route id -> (departure port code, arrival port code)
    "bf-portsmouth-caen": ("GBPME", "FROUI"),
    "bf-portsmouth-cherbourg": ("GBPME", "FRCER"),
    "bf-portsmouth-stmalo": ("GBPME", "FRSML"),
    "bf-plymouth-roscoff": ("GBPLY", "FRROS"),
    "bf-portsmouth-santander": ("GBPME", "ESSDR"),
    "bf-portsmouth-bilbao": ("GBPME", "ESBIO"),
    "bf-plymouth-santander": ("GBPLY", "ESSDR"),
}
ROUTES = {**_OUT, **{f"{k}#rev": (b, a) for k, (a, b) in _OUT.items()}}

VEHICLE = {  # our vehicle kind -> (API type, height cm, length cm)
    "car": ("CAR", 183, 500),
    "van": ("VAN", 250, 600),
    "campervan": ("MINIBUS", 300, 700),
}


class BrittanyFerries(Collector):
    operator = "Brittany Ferries"
    route_ids = set(ROUTES)
    robots_url = f"{SITE}/robots.txt"
    paths_used = [PRICES_API]
    needs_browser = False

    async def collect(self, browser, route: dict, date: dt.date, party: Party) -> list[Quote]:
        if party.vehicle not in VEHICLE:
            raise Unsupported(f"vehicle '{party.vehicle}' not supported by this collector")
        dep, arr = ROUTES[route["id"]]
        vtype, h, l = VEHICLE[party.vehicle]
        start = max(date - dt.timedelta(days=3), dt.date.today())
        body = {
            "bookingReference": None,
            "pets": {"smallDogs": 0, "largeDogs": 0, "cats": 0},
            "passengers": {"adults": party.adults, "children": party.children, "infants": 0},
            "vehicle": {"type": vtype, "registrations": ["TBC"], "height": h, "length": l,
                        "extras": {"rearMountedBikeCarrier": False}},
            "departurePort": dep, "arrivalPort": arr, "disability": None, "direction": "outbound",
            "fromDate": f"{start.isoformat()}T00:00:00",
            "toDate": f"{(date + dt.timedelta(days=3)).isoformat()}T23:59:59",
        }
        r = await net.post(PRICES_API, json=body)
        quotes = parse(route["id"], r.json())
        if not quotes:
            raise NoSailings("no bookable sailings within 3 days of this date")
        if not any(q.travel_date == date for q in quotes):
            # Spain routes don't sail daily: price the requested date with the nearest sailing.
            near = min(quotes, key=lambda q: (abs((q.travel_date - date).days), q.price))
            quotes.append(Quote(route["id"], date, near.price, near.currency, departure=near.departure,
                                detail=f"No sailing on {date:%a %d %b}; nearest is {near.travel_date:%a %d %b}. "
                                       + (near.detail or "")))
        return quotes


def parse(route_id: str, data: dict) -> list[Quote]:
    cur = data.get("currency", "GBP")
    out = []
    for day in data.get("crossings", []):
        best = None
        n = 0
        for p in day.get("prices", []):
            cp = p.get("crossingPrices") or {}
            std = (cp.get("standardPrice") or {}).get("amount")
            if std is None or cp.get("full"):
                continue
            price = float(std)
            cabin = ""
            if cp.get("isAccommodationMandatory"):
                extra = sum(c["price"]["amount"] * c.get("quantity", 1) for c in cp.get("cabinsIncluded", []))
                price += extra
                cabin = f" incl. compulsory cabin £{extra:.0f}" if extra else ""
            n += 1
            dep = (cp.get("departureDateTime") or {}).get("time")
            if best is None or price < best[0]:
                best = (price, dep, cabin)
        if best:
            out.append(Quote(route_id, dt.date.fromisoformat(day["date"]), round(best[0], 2), cur,
                             departure=best[1],
                             detail=f"Cheapest of {n} Brittany Ferries sailings (Standard){best[2]}"))
    return out


if __name__ == "__main__":  # manual test: python -m app.collectors.brittany 2026-12-05
    import asyncio
    import json
    import sys

    async def _main():
        d = dt.date.fromisoformat(sys.argv[1])
        for rid in ("bf-portsmouth-caen", "bf-portsmouth-santander", "bf-plymouth-roscoff#rev"):
            qs = await BrittanyFerries().collect(None, {"id": rid}, d, Party())
            print(rid, json.dumps([q.__dict__ for q in qs if q.travel_date == d], default=str))
        await net.close()

    asyncio.run(_main())
