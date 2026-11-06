"""Live fare collector framework.

Each operator collector drives the operator's public booking pages in a headless browser
(the locally installed Microsoft Edge via Playwright), reads the fare the site shows for a
date / vehicle, and stores it in the fare cache. Ground rules every collector follows:

* only operators whose robots.txt permits the pages used (checked at runtime too);
* cookie banners: only strictly-necessary cookies are allowed;
* no logins, no CAPTCHA solving, no bot-detection workarounds - if a site blocks us we
  stop and the planner falls back to estimated fares;
* one browser, one page at a time, with pauses between requests.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path

from .. import cache, net
from ..crossings import Party

log = logging.getLogger(__name__)


@dataclass
class Quote:
    route_id: str
    travel_date: dt.date
    price: float
    currency: str
    departure: str | None = None
    detail: str | None = None


class CollectorBlocked(Exception):
    """The site refused automated access (403, challenge page, robots.txt)."""


class NoSailings(Exception):
    """The operator has no bookable sailings on/near the date; the crossing is hidden from results."""


class Unsupported(Exception):
    """This collector can't price this request (e.g. vehicle type); quietly use the estimate."""


class Collector:
    operator: str = ""
    route_ids: set[str] = set()       # crossing ids (including '#rev' for return direction)
    robots_url: str = ""
    paths_used: list[str] = []         # URLs fetched, checked against robots.txt
    needs_browser: bool = True         # False = plain HTTP requests only

    def handles(self, route_id: str) -> bool:
        return route_id in self.route_ids

    async def allowed(self) -> bool:
        key = f"robots:{self.robots_url}"
        hit = cache.get(key)
        if hit is None:
            try:
                r = await net.client().get(self.robots_url)
                text = r.text if r.status_code == 200 else ""
                hit = {"status": r.status_code, "text": text}
            except Exception as e:  # noqa: BLE001
                hit = {"status": 0, "text": "", "error": str(e)}
            cache.put(key, hit, 86400)
        if hit["status"] in (401, 403):
            return False
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(hit["text"].splitlines())
        return all(rp.can_fetch(net.USER_AGENT, u) for u in self.paths_used)

    async def collect(self, browser, route: dict, date: dt.date, party: Party) -> list[Quote]:
        raise NotImplementedError


async def new_page(browser):
    ctx = await browser.new_context(locale="en-GB", viewport={"width": 1280, "height": 1400})
    return ctx, await ctx.new_page()


DEBUG_DIR = Path(__file__).resolve().parents[2] / "var" / "debug"


async def save_debug(page, name: str) -> None:
    """Save a screenshot + page text when a collector fails, to help fix broken flows."""
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)
        (DEBUG_DIR / f"{name}.txt").write_text(page.url + "\n\n" + await page.inner_text("body"), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def store(quotes: list[Quote], party: Party) -> None:
    for q in quotes:
        cache.put_fare(q.route_id, q.travel_date.isoformat(), party.profile, q.price, q.currency,
                       q.departure, q.detail)


async def polite_pause() -> None:
    await asyncio.sleep(2.0)


def now() -> float:
    return time.time()
