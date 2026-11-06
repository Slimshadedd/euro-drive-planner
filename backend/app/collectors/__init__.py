"""Registry and runner for live fare collectors."""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging

from .. import cache
from ..crossings import LIVE_FARE_MAX_AGE_S, Party
from .base import Collector, CollectorBlocked, NoSailings, Unsupported, polite_pause, store
from ..crossings import mark_no_sailing, no_sailing
from .brittany import BrittanyFerries
from .dfds import DFDS
from .leshuttle import LeShuttle

log = logging.getLogger(__name__)

COLLECTORS: list[Collector] = [LeShuttle(), DFDS(), BrittanyFerries()]
_run_lock = asyncio.Lock()  # one collection run (and one headless browser) at a time


def supported_route_ids() -> set[str]:
    return {rid for c in COLLECTORS for rid in c.route_ids}


def status() -> list[dict]:
    return [{"operator": c.operator, "routes": sorted(c.route_ids)} for c in COLLECTORS]


def _fresh(route_id: str, date: dt.date, party: Party) -> bool:
    return cache.get_fare(route_id, date.isoformat(), party.profile, LIVE_FARE_MAX_AGE_S) is not None


async def fetch_live(routes: list[dict], date: dt.date, party: Party, timeout_s: float = 150) -> dict:
    """Collect live fares for the given crossings (skipping fresh cache hits). Never raises."""
    todo = []
    for r in routes:
        col = next((c for c in COLLECTORS if c.handles(r["id"])), None)
        if col and not _fresh(r["id"], date, party) and not no_sailing(r["id"], date):
            todo.append((col, r))
    report = {"collected": [], "failed": [], "warnings": [], "no_sailing": []}
    if not todo:
        return report
    # Plain-HTTP collectors first (fast), browser ones after.
    todo.sort(key=lambda t: t[0].needs_browser)
    try:
        await asyncio.wait_for(_run(todo, date, party, report), timeout=timeout_s)
    except asyncio.TimeoutError:
        report["warnings"].append("Live fare collection timed out; some fares are estimates.")
    return report


@contextlib.asynccontextmanager
async def _browser_session(needed: bool):
    if not needed:
        yield None
        return
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        try:
            yield browser
        finally:
            await browser.close()


async def _run(todo, date, party, report):
    async with _run_lock, _browser_session(any(c.needs_browser for c, _ in todo)) as browser:
        for col, route in todo:
            rid, d = route["id"], date.isoformat()
            if _fresh(rid, date, party):  # e.g. a DFDS Dover page already priced this route
                report["collected"].append(rid)
                continue
            if not await col.allowed():
                msg = f"{col.operator}: robots.txt / access policy does not allow collection"
                report["warnings"].append(msg)
                cache.log_collector(col.operator, rid, d, False, msg)
                continue
            try:
                quotes = await col.collect(browser, route, date, party)
                store(quotes, party)
                report["collected"].append(rid)
                cache.log_collector(col.operator, rid, d, True, f"{len(quotes)} quotes")
            except NoSailings as e:
                mark_no_sailing(rid, date)
                report["no_sailing"].append(_label(route))
                cache.log_collector(col.operator, rid, d, True, f"no sailings: {e}")
            except Unsupported as e:
                cache.log_collector(col.operator, rid, d, False, f"unsupported: {e}")
            except CollectorBlocked as e:
                report["failed"].append(rid)
                report["warnings"].append(f"{col.operator} blocked automated access ({e}); using its estimate.")
                cache.log_collector(col.operator, rid, d, False, f"blocked: {e}")
            except Exception as e:  # noqa: BLE001
                log.warning("collector %s failed for %s: %r", col.operator, rid, e)
                report["failed"].append(rid)
                reason = str(e) if isinstance(e, RuntimeError) and str(e) else type(e).__name__
                report["warnings"].append(f"No live {col.operator} fare for {_label(route)} ({reason}); using estimate.")
                cache.log_collector(col.operator, rid, d, False, repr(e))
            if col.needs_browser:
                await polite_pause()


def _label(route: dict) -> str:
    from ..crossings import ports

    p = ports()
    return f"{p[route['from']]['name']} → {p[route['to']]['name']}" if "from" in route else route["id"]
