"""Ferry / shuttle crossings: static network data, fare estimates, and live-fare lookup."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import cache

DATA = Path(__file__).resolve().parent / "data"
LIVE_FARE_MAX_AGE_S = 6 * 3600
MANUAL_MARK = "Entered by you"

# Vehicle surcharge on ferry fares (vans/campervans/caravans are priced as larger vehicles).
VEHICLE_FARE_MULT = {"car": 1.0, "van": 1.45, "campervan": 1.6, "car_caravan": 1.8}


@dataclass
class Party:
    adults: int = 2
    children: int = 0
    vehicle: str = "car"

    @property
    def profile(self) -> str:
        """Cache key for live fares: fares depend on vehicle and party size."""
        return f"{self.vehicle}-a{self.adults}-c{self.children}"


@lru_cache(maxsize=1)
def network() -> dict:
    return json.load(open(DATA / "crossings.json", encoding="utf-8"))


def ports() -> dict:
    return network()["ports"]


def routes(include_reverse: bool = True) -> list[dict]:
    """All crossings; each listed route is bookable in both directions."""
    out = []
    for r in network()["routes"]:
        out.append({**r, "direction": "out"})
        if include_reverse:
            out.append({**r, "from": r["to"], "to": r["from"], "direction": "return",
                        "id": r["id"] + "#rev"})
    return out


def season(d: dt.date) -> str:
    m = d.month
    # Christmas / New Year getaway and Easter-ish school holidays count as high.
    if (m == 12 and d.day >= 18) or (m == 1 and d.day <= 3):
        return "high"
    if m in (7, 8):
        return "high"
    if m in (4, 5, 6, 9, 10):
        return "mid"
    return "low"


def estimate_fare_gbp(route: dict, d: dt.date, party: Party) -> float:
    base = route["fare"][season(d)]
    if d.weekday() in (4, 5):  # Fri/Sat departures are typically dearer
        base *= 1.10
    base *= VEHICLE_FARE_MULT.get(party.vehicle, 1.0)
    extra_people = max(0, party.adults - 2) + 0.5 * party.children
    base += extra_people * route.get("per_extra_adult", 0)
    return round(base, 2)


def mark_no_sailing(route_id: str, d: dt.date) -> None:
    cache.put(f"nosail:{route_id}:{d.isoformat()}", True, LIVE_FARE_MAX_AGE_S)


def no_sailing(route_id: str, d: dt.date) -> bool:
    return bool(cache.get(f"nosail:{route_id}:{d.isoformat()}"))


def fare(route: dict, d: dt.date, party: Party, fx: dict[str, float]) -> dict:
    """Best known fare in EUR: a recent live quote if one was collected, else the estimate."""
    live = cache.get_fare(route["id"], d.isoformat(), party.profile, LIVE_FARE_MAX_AGE_S)
    if live:
        eur = live["price"] / fx.get(live["currency"], 1.0)
        source = "manual" if live["detail"] == MANUAL_MARK else "live"
        return {"eur": round(eur, 2), "source": source, "currency": live["currency"],
                "original_price": live["price"], "departure": live["departure"],
                "detail": live["detail"], "fetched_at": live["fetched_at"]}
    gbp = estimate_fare_gbp(route, d, party)
    return {"eur": round(gbp / fx.get("GBP", 0.87), 2), "source": "estimate", "currency": "GBP",
            "original_price": gbp, "season": season(d)}
