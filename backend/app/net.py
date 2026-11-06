"""Shared HTTP client.

Forces IPv4 (some networks, including the one this was built on, have broken IPv6
routes to the public OSM services) and applies a polite per-host rate limit.
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

import httpx

USER_AGENT = "euro-drive-planner/0.1 (personal trip planner; local use)"

# Minimum seconds between requests to the same host (public services ask for <= 1 req/s).
_HOST_INTERVAL = {
    "nominatim.openstreetmap.org": 1.1,
    "photon.komoot.io": 0.3,
    "router.project-osrm.org": 0.5,
    "valhalla1.openstreetmap.de": 0.6,
}
_DEFAULT_INTERVAL = 0.5

_client: httpx.AsyncClient | None = None
_locks: dict[str, asyncio.Lock] = {}
_last: dict[str, float] = {}


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=2),
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(45.0, connect=10.0),
            follow_redirects=True,
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _throttle(url: str) -> None:
    host = urlparse(url).hostname or ""
    lock = _locks.setdefault(host, asyncio.Lock())
    async with lock:
        wait = _HOST_INTERVAL.get(host, _DEFAULT_INTERVAL) - (time.monotonic() - _last.get(host, 0.0))
        if wait > 0:
            await asyncio.sleep(wait)
        _last[host] = time.monotonic()


async def get(url: str, **kw) -> httpx.Response:
    await _throttle(url)
    r = await client().get(url, **kw)
    r.raise_for_status()
    return r


async def post(url: str, **kw) -> httpx.Response:
    await _throttle(url)
    r = await client().post(url, **kw)
    r.raise_for_status()
    return r
