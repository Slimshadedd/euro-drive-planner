"""Eurotunnel LeShuttle (Folkestone <-> Calais).

Flow: home page (cookie preferences -> necessary only) -> booking deep link for the date ->
vehicle "type and size" (no registration / make / model needed) -> the outbound page, whose
quote API response we read. The fare is per vehicle (up to 9 people), so party size doesn't matter.
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from ..crossings import Party
from .base import Collector, CollectorBlocked, Quote, new_page, save_debug

log = logging.getLogger(__name__)

BASE = "https://www.leshuttle.com"
CATEGORY = {"car": "CAR", "car_caravan": "CAR", "van": "BIG", "campervan": "CAM"}


class LeShuttle(Collector):
    operator = "LeShuttle"
    # Outbound only: the Calais->Folkestone flow requires ticking a journey confirmation box,
    # which this tool deliberately does not do, so that direction uses the estimate.
    route_ids = {"leshuttle-folkestone-coquelles"}
    robots_url = f"{BASE}/robots.txt"
    paths_used = [f"{BASE}/uk-en", f"{BASE}/booking/trip-details"]

    async def collect(self, browser, route: dict, date: dt.date, party: Party) -> list[Quote]:
        direction = "CA" if route["id"].endswith("#rev") else "FO"
        ctx, pg = await new_page(browser)
        quote_json: dict = {}
        calendar_json: dict = {}

        async def on_response(r):
            if "nextus-api" not in r.url:
                return
            try:
                if "/ExactViewQuote" in r.url:
                    quote_json.update(await r.json())
                elif "/CalendarView" in r.url:
                    calendar_json.update(await r.json())
            except Exception:  # noqa: BLE001
                pass

        pg.on("response", on_response)
        try:
            resp = await pg.goto(f"{BASE}/uk-en", wait_until="domcontentloaded", timeout=45000)
            if resp and resp.status in (403, 429):
                raise CollectorBlocked(f"HTTP {resp.status}")
            try:  # cookie banner: open preferences and confirm the default (necessary only)
                await pg.click("#onetrust-pc-btn-handler", timeout=15000)
                await pg.get_by_role("button", name="Confirm My Choices").first.click(timeout=10000)
            except Exception:  # noqa: BLE001 - banner may not appear
                pass
            await pg.goto(f"{BASE}/booking/trip-details?df={direction}&bm=en-GB&od={date.isoformat()}"
                          f"&ow=true&op={max(party.adults + party.children, 1)}&rp=1",
                          wait_until="domcontentloaded", timeout=45000)
            await pg.wait_for_selector("text=Vehicle details", timeout=30000)
            await pg.get_by_role("button", name="make and model").click(timeout=15000)
            await pg.get_by_role("button", name="type and size").first.click(timeout=15000)
            cat = CATEGORY.get(party.vehicle, "CAR")
            await _click_input(pg, f"input[name=vd-ts-cat][value={cat}]")
            await pg.wait_for_timeout(800)
            if cat == "CAR":
                await _click_input(pg, "#vd-cat-height-low")
            await _click_input(pg, "#vd-fuel-con")
            towing = party.vehicle == "car_caravan"
            await _click_input(pg, "#vd-roof-rear-yes" if towing else "#vd-roof-rear-no")
            await pg.get_by_role("button", name="Continue").click()
            for _ in range(60):
                if quote_json:
                    break
                await pg.wait_for_timeout(500)
            if not quote_json:
                await save_debug(pg, f"leshuttle-{direction}")
        except Exception:
            await save_debug(pg, f"leshuttle-{direction}")
            raise
        finally:
            await ctx.close()

        if not quote_json:
            raise RuntimeError("no quote data returned (site flow may have changed)")
        return _parse(route["id"], date, quote_json, calendar_json)


async def _click_input(pg, selector: str) -> None:
    await pg.locator(selector).evaluate("e => (e.closest('label') || e).click()")


def _parse(route_id: str, date: dt.date, quote: dict, calendar: dict) -> list[Quote]:
    cur = quote.get("currencyCode", "GBP")
    best = None
    count = 0
    for slot in (quote.get("outboundJourney") or {}).get("slots", []):
        for m in slot.get("missions", []):
            for t in m.get("ticketTypes", []):
                if t.get("description") == "Standard" and t.get("available") == "Yes":
                    count += 1
                    if best is None or t["price"] < best[0]:
                        best = (t["price"], m["dateTime"])
    quotes = []
    if best:
        dep = best[1][11:16]
        quotes.append(Quote(route_id, date, float(best[0]), cur, departure=dep,
                            detail=f"Cheapest Standard ticket of {count} available departures"))
    # The calendar strip gives 'from' prices for neighbouring days - cache those too.
    for d in ((calendar.get("outboundJourney") or {}).get("dates") or []):
        day = dt.date.fromisoformat(d["date"][:10])
        if day != date and d.get("fromPrice"):
            quotes.append(Quote(route_id, day, float(d["fromPrice"]), cur,
                                detail="'From' price from LeShuttle calendar"))
    if not quotes:
        raise RuntimeError("no available departures found for this date")
    return quotes


if __name__ == "__main__":  # manual test: python -m app.collectors.leshuttle 2026-12-05
    import asyncio
    import sys

    from playwright.async_api import async_playwright

    async def _main():
        async with async_playwright() as p:
            b = await p.chromium.launch(channel="msedge", headless=True)
            d = dt.date.fromisoformat(sys.argv[1])
            for rid in ("leshuttle-folkestone-coquelles",):
                qs = await LeShuttle().collect(b, {"id": rid}, d, Party())
                print(rid, json.dumps([q.__dict__ for q in qs[:3]], default=str))
            await b.close()

    asyncio.run(_main())
