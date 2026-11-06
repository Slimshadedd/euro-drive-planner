"""DFDS short-sea crossings: Dover <-> Calais, Dover <-> Dunkirk, Newhaven <-> Dieppe.

DFDS's public search widget exposes a `booking-url` endpoint that turns route + date + vehicle +
passengers into a booking-page link. Opening that link in the browser lists the departures with
"from" prices straight away - no vehicle registration or personal details needed. We read the
cheapest price from the page text.

* Dover pages list both Calais and Dunkirk sailings, so one visit prices both routes.
* Newhaven - Dieppe uses DFDS's older booking site, which auto-advances to a fares list.
* Newcastle - Amsterdam and Rosslare - Dunkirk are not collected: their first price excludes the
  compulsory cabin, so it would understate the real cost (the estimate includes a cabin).
"""
from __future__ import annotations

import datetime as dt
import logging
import re

from .. import net
from ..crossings import Party
from .base import Collector, CollectorBlocked, Quote, new_page, save_debug

log = logging.getLogger(__name__)

SITE = "https://www.dfds.com"
SEARCH_API = "https://travel-search-prod.dfds-pax-web.com/api/booking-url"

# our route id -> (DFDS route code, departure port name, arrival port name as shown on the site)
ROUTES = {
    "dfds-dover-calais":         ("GBDVR-FRCQF", "Dover", "Calais"),
    "dfds-dover-calais#rev":     ("FRCQF-GBDVR", "Calais", "Dover"),
    "dfds-dover-dunkirk":        ("GBDVR-FRDKK", "Dover", "Dunkirk"),
    "dfds-dover-dunkirk#rev":    ("FRDKK-GBDVR", "Dunkirk", "Dover"),
    "dfds-newhaven-dieppe":      ("GBNHV-FRDPE", "Newhaven", "Dieppe"),
    "dfds-newhaven-dieppe#rev":  ("FRDPE-GBNHV", "Dieppe", "Newhaven"),
}
# Dover pages show both French ports - map (from, to) port names back to our route ids.
BY_PORTS = {(f, t): rid for rid, (_, f, t) in ROUTES.items()}

VEHICLE = {  # our vehicle kind -> (DFDS vehicle code, trailer code)
    "car": ("CAR", None),
    "van": ("PVANM", None),        # van up to 6m
    "campervan": ("MCVM", None),   # motorhome up to 7m
    "car_caravan": ("CAR", "CAMB"),
}

# "00:35\nDover\n03:15\nCalais\nDuration: 1h40min\nfrom\n£103.00"  (new booking site)
NEW_RE = re.compile(r"^(\d\d:\d\d)\n([^\n]+)\n(\d\d:\d\d)\n([^\n]+)\nDuration:[^\n]*\nfrom\n£([\d,]+(?:\.\d\d)?)", re.M)
# "17:00 - Newhaven - Dieppe\n£73.50"  (legacy booking site)
OLD_RE = re.compile(r"^(\d\d:\d\d) - ([^\n-]+?) - ([^\n]+)\n£([\d,]+(?:\.\d\d)?)", re.M)


class DFDS(Collector):
    operator = "DFDS"
    route_ids = set(ROUTES)
    robots_url = f"{SITE}/robots.txt"
    paths_used = [f"{SITE}/en-gb/passenger-ferries/yourbooking", f"{SITE}/en-gb/passenger-ferries/booking"]

    async def collect(self, browser, route: dict, date: dt.date, party: Party) -> list[Quote]:
        code, _, _ = ROUTES[route["id"]]
        vcode, trailer = VEHICLE.get(party.vehicle, ("CAR", None))
        params = {"locale": "en-gb", "routeCode": code, "vehicleCode": vcode,
                  "outboundDate": date.isoformat(), "isOneway": "true",
                  "adults": party.adults, "currency": "GBP"}
        if trailer:
            params["trailerCode"] = trailer
        if party.children:
            params["children"] = party.children
            params["childrenAges"] = ",".join(["8"] * party.children)
        r = await net.get(SEARCH_API, params=params)
        path = r.json().get("url")
        if not path:
            raise RuntimeError("DFDS search API returned no booking link")

        ctx, pg = await new_page(browser)
        try:
            resp = await pg.goto(f"{SITE}/{path.lstrip('/')}", wait_until="domcontentloaded", timeout=60000)
            if resp and resp.status in (403, 429):
                raise CollectorBlocked(f"HTTP {resp.status}")
            try:  # cookie banner: "Reject all cookies" keeps only strictly necessary ones
                await pg.get_by_role("button", name="Reject all cookies").click(timeout=10000)
            except Exception:  # noqa: BLE001
                pass
            text = ""
            for _ in range(40):  # wait up to ~20s for departures to render
                await pg.wait_for_timeout(500)
                text = await pg.inner_text("body")
                if NEW_RE.search(text) or OLD_RE.search(text) or "no departures" in text.lower():
                    break
            quotes = _parse(text, route["id"], date)
            if not quotes:
                await save_debug(pg, f"dfds-{code}")
                raise RuntimeError("no prices found on the DFDS page (site flow may have changed)")
            return quotes
        except CollectorBlocked:
            raise
        except Exception:
            await save_debug(pg, f"dfds-{code}")
            raise
        finally:
            await ctx.close()


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _parse(text: str, route_id: str, date: dt.date) -> list[Quote]:
    best: dict[str, tuple[float, str]] = {}
    count: dict[str, int] = {}

    def add(rid, price, dep):
        count[rid] = count.get(rid, 0) + 1
        if rid not in best or price < best[rid][0]:
            best[rid] = (price, dep)

    for dep, frm, _arr, to, price in NEW_RE.findall(text):
        rid = BY_PORTS.get((frm.strip(), to.strip()))
        if rid:
            add(rid, _num(price), dep)
    if not best:
        for dep, frm, to, price in OLD_RE.findall(text):
            rid = BY_PORTS.get((frm.strip(), to.strip())) or route_id
            add(rid, _num(price), dep)
    return [Quote(rid, date, p, "GBP", departure=d,
                  detail=f"Cheapest of {count[rid]} DFDS departures")
            for rid, (p, d) in best.items()]


if __name__ == "__main__":  # manual test: python -m app.collectors.dfds 2026-12-05
    import asyncio
    import json
    import sys

    from playwright.async_api import async_playwright

    async def _main():
        async with async_playwright() as p:
            b = await p.chromium.launch(channel="msedge", headless=True)
            d = dt.date.fromisoformat(sys.argv[1])
            for rid in ("dfds-dover-calais", "dfds-newhaven-dieppe#rev"):
                qs = await DFDS().collect(b, {"id": rid}, d, Party())
                print(rid, json.dumps([q.__dict__ for q in qs], default=str))
            await b.close()
        await net.close()

    asyncio.run(_main())
