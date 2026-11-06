"""Turn a routed road leg into money: fuel, distance tolls, vignettes and special tolls (EUR)."""
from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import cache, geo, net

log = logging.getLogger(__name__)
DATA = Path(__file__).resolve().parent / "data"

# Fallback FX rates (units per 1 EUR) if the ECB feed can't be reached.
FALLBACK_FX = {"EUR": 1.0, "GBP": 0.87, "USD": 1.10, "CHF": 0.94}

# Toll multipliers by vehicle type (French/Spanish/Italian class 2 is roughly 1.5x class 1).
TOLL_CLASS = {"car": 1.0, "van": 1.55, "campervan": 1.55, "car_caravan": 1.5}
LITRES_PER_100KM_AT_1_MPG = 282.481  # UK (imperial) mpg -> L/100km
FUELS = ("petrol", "diesel")


@lru_cache(maxsize=1)
def country_data() -> dict:
    return json.load(open(DATA / "countries.json", encoding="utf-8"))


async def fx_rates() -> dict[str, float]:
    """Daily ECB reference rates (per 1 EUR). Cached for 12 hours."""
    hit = cache.get("fx:ecb")
    if hit:
        return hit
    try:
        r = await net.get("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml")
        root = ET.fromstring(r.text)
        rates = {"EUR": 1.0}
        for el in root.iter():
            if el.get("currency") and el.get("rate"):
                rates[el.get("currency")] = float(el.get("rate"))
        cache.put("fx:ecb", rates, 12 * 3600)
        return rates
    except Exception as e:  # noqa: BLE001
        log.warning("ECB FX fetch failed (%s); using fallback rates", e)
        return FALLBACK_FX


@dataclass
class Vehicle:
    kind: str = "car"            # car | van | campervan | car_caravan
    fuel: str = "petrol"         # petrol | diesel (used for the headline total)
    mpg: float = 45.0            # UK miles per gallon

    @property
    def l_per_100km(self) -> float:
        return LITRES_PER_100KM_AT_1_MPG / max(self.mpg, 1.0)


def _cinfo(code: str) -> dict:
    cd = country_data()
    return cd["countries"].get(code) or cd["default"]


def energy_price_eur(code: str, fuel: str) -> float:
    return _cinfo(code).get(fuel, country_data()["default"][fuel])


def leg_cost(leg: dict, vehicle: Vehicle) -> dict:
    """Cost breakdown in EUR for one routed road leg (output of routing.route)."""
    fuel = tolls = vignettes = 0.0
    fuel_by_type = {f: 0.0 for f in FUELS}
    items: list[dict] = []
    per_country = []
    cls = TOLL_CLASS.get(vehicle.kind, 1.0)
    for code, e in leg["countries"].items():
        road_km = e["km"] - e.get("ferry_km", 0.0)
        info = _cinfo(code)
        litres = road_km * vehicle.l_per_100km / 100.0
        by_type = {ft: litres * energy_price_eur(code, ft) for ft in FUELS}
        for ft in FUELS:
            fuel_by_type[ft] += by_type[ft]
        f = by_type[vehicle.fuel]
        t = e["toll_km"] * info.get("toll_per_km", 0.0) * cls
        fuel += f; tolls += t
        per_country.append({
            "country": code, "name": info.get("name", code), "km": round(e["km"], 1),
            "toll_km": round(e["toll_km"], 1), "fuel_eur": round(f, 2), "toll_eur": round(t, 2),
            "litres": round(litres, 1),
            "petrol_price_eur": energy_price_eur(code, "petrol"),
            "diesel_price_eur": energy_price_eur(code, "diesel"),
        })
        vig = info.get("vignette")
        if vig and e.get("motorway_km", 0) > 2.0:
            price = vig["price"]  # same for all vehicles up to 3.5 t
            vignettes += price
            items.append({"kind": "vignette", "country": code, "label": vig["label"], "eur": price})
    for sp in country_data().get("special_tolls", []):
        if _passes_near(leg["geometry"], sp["lat"], sp["lon"], sp["radius_km"]):
            price = sp["price"] * cls
            tolls += price
            items.append({"kind": "special_toll", "country": sp["country"], "label": sp["name"], "eur": price})
    per_country.sort(key=lambda x: -x["km"])
    return {"fuel_eur": round(fuel, 2),
            "fuel_by_type_eur": {k: round(v, 2) for k, v in fuel_by_type.items()},
            "tolls_eur": round(tolls, 2),
            "vignettes_eur": round(vignettes, 2), "items": items, "per_country": per_country}


def _passes_near(geometry, lat, lon, radius_km) -> bool:
    for la, lo in geometry:
        if abs(la - lat) < 0.1 and abs(lo - lon) < 0.15 and geo.haversine_km(la, lo, lat, lon) <= radius_km:
            return True
    return False


def rough_road_cost_eur(km: float, landmass: str, vehicle: Vehicle) -> float:
    """Cheap estimate for screening candidates before detailed routing."""
    ref = {"GB": "GB", "IE": "IE", "EU": "FR"}[landmass]
    fuel = km * vehicle.l_per_100km / 100.0 * energy_price_eur(ref, vehicle.fuel)
    toll_guess = km * (0.045 if landmass == "EU" else 0.0) * TOLL_CLASS.get(vehicle.kind, 1.0)
    return fuel + toll_guess
