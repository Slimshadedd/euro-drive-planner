"""FastAPI app: JSON API + serves the built React frontend."""
from __future__ import annotations

import datetime as dt
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import cache, collectors, costs, crossings, net, planner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app):
    yield
    await net.close()


app = FastAPI(title="Euro Drive Planner", lifespan=lifespan)


# ---------------------------------------------------------------- models
class PlaceIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str = ""


class PlanIn(BaseModel):
    origin: PlaceIn
    destination: PlaceIn
    date: dt.date
    return_date: dt.date | None = None  # set for a return journey (destination -> origin)
    adults: int = Field(2, ge=1, le=9)
    children: int = Field(0, ge=0, le=8)
    vehicle: Literal["car", "van", "campervan", "car_caravan"] = "car"
    fuel: Literal["petrol", "diesel"] = "petrol"
    mpg: float = Field(45.0, ge=10, le=120)
    mode: Literal["cheapest", "fastest", "balanced"] = "cheapest"
    value_of_time: float = Field(10.0, ge=0, le=500)
    currency: Literal["GBP", "EUR"] = "GBP"
    avoid_tolls: bool = False
    live_fares: bool = True
    max_results: int = Field(6, ge=1, le=12)


class ManualFareIn(BaseModel):
    route_id: str
    date: dt.date
    price: float = Field(gt=0, lt=10000)
    currency: Literal["GBP", "EUR"] = "GBP"
    adults: int = 2
    children: int = 0
    vehicle: Literal["car", "van", "campervan", "car_caravan"] = "car"


# ---------------------------------------------------------------- API
@app.get("/api/geocode")
async def geocode(q: str = Query(min_length=2, max_length=120)):
    """Place search (Photon / OpenStreetMap), limited to Europe."""
    key = f"geocode:{q.lower().strip()}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    r = await net.get("https://photon.komoot.io/api/",
                      params={"q": q, "limit": 7, "lang": "en", "bbox": "-25,34,45,72"})
    out = []
    for f in r.json().get("features", []):
        p = f["properties"]; lon, lat = f["geometry"]["coordinates"]
        name = p.get("name") or p.get("street") or ""
        parts = [name, p.get("city") if p.get("city") != name else None, p.get("state"), p.get("country")]
        out.append({"lat": lat, "lon": lon, "label": ", ".join(x for x in parts if x),
                    "short": name, "type": p.get("osm_value")})
    cache.put(key, out, 30 * 86400)
    return out


@app.post("/api/plan")
async def plan(body: PlanIn):
    """Plan a one-way trip, or a return trip when `return_date` is given.

    A return is planned as two independent one-way journeys (out and back), because operators
    price returns as two singles and the cheapest crossing can differ by direction and date.
    The response is the outbound plan, plus `return_plan` for the way back.
    """
    if body.date < dt.date.today():
        raise HTTPException(400, "Travel date is in the past.")
    if body.return_date and body.return_date < body.date:
        raise HTTPException(400, "Return date is before the outbound date.")
    origin = planner.Place(**body.origin.model_dump())
    dest = planner.Place(**body.destination.model_dump())

    def request(a, b, date):
        return planner.PlanRequest(
            origin=a, destination=b, date=date,
            party=crossings.Party(adults=body.adults, children=body.children, vehicle=body.vehicle),
            vehicle=costs.Vehicle(kind=body.vehicle, fuel=body.fuel, mpg=body.mpg),
            mode=body.mode, value_of_time=body.value_of_time, currency=body.currency,
            avoid_tolls=body.avoid_tolls, live_fares=body.live_fares, max_results=body.max_results,
        )

    try:
        out = await planner.plan(request(origin, dest, body.date), live_fetch=collectors.fetch_live)
        out["date"] = body.date.isoformat()
        if body.return_date:
            back = await planner.plan(request(dest, origin, body.return_date), live_fetch=collectors.fetch_live)
            back["date"] = body.return_date.isoformat()
            out["return_plan"] = back
        return out
    except Exception as e:  # noqa: BLE001
        logging.exception("plan failed")
        raise HTTPException(502, f"Planning failed: {e}") from e


@app.get("/api/crossings")
async def list_crossings(date: dt.date | None = None):
    d = date or dt.date.today() + dt.timedelta(days=21)
    fx = await costs.fx_rates()
    live_ids = collectors.supported_route_ids()
    out = []
    for r in crossings.routes():
        p = crossings.ports()
        f = crossings.fare(r, d, crossings.Party(), fx)
        out.append({"id": r["id"], "operator": r["operator"], "from": p[r["from"]]["name"],
                    "to": p[r["to"]]["name"], "duration_min": r["duration_min"],
                    "overnight": r.get("overnight", False), "live_supported": r["id"] in live_ids,
                    "fare_gbp": round(f["eur"] * fx.get("GBP", 0.87), 2), "fare_source": f["source"]})
    return {"date": d.isoformat(), "crossings": out, "as_of": crossings.network()["as_of"]}


@app.post("/api/fares/manual")
async def manual_fare(body: ManualFareIn):
    """Record a quote you got yourself (e.g. from a booking site); used like a live fare for 6h."""
    if not any(r["id"] == body.route_id for r in crossings.routes()):
        raise HTTPException(404, "Unknown crossing")
    party = crossings.Party(adults=body.adults, children=body.children, vehicle=body.vehicle)
    cache.put_fare(body.route_id, body.date.isoformat(), party.profile, body.price, body.currency,
                   None, crossings.MANUAL_MARK)
    return {"ok": True}


@app.get("/api/collectors")
async def collector_status():
    return {"collectors": collectors.status(), "log": cache.recent_collector_log(30)}


@app.get("/api/health")
async def health():
    return {"ok": True}


# ---------------------------------------------------------------- frontend
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        f = FRONTEND / path
        if path and f.is_file() and FRONTEND in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(FRONTEND / "index.html")
