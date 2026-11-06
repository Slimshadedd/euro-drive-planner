"""Geography helpers: country lookup, landmass classification, distances, polyline decoding."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


class _Country:
    __slots__ = ("code", "name", "polys")  # polys: list of (bbox, rings)

    def __init__(self, code, name, polygons):
        self.code, self.name = code, name
        self.polys = []
        for poly in polygons:
            outer = poly[0]
            xs = [p[0] for p in outer]; ys = [p[1] for p in outer]
            self.polys.append(((min(xs), min(ys), max(xs), max(ys)), poly))

    def contains(self, lon: float, lat: float) -> bool:
        for (x0, y0, x1, y1), rings in self.polys:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and _in_ring(lon, lat, rings[0]):
                if not any(_in_ring(lon, lat, hole) for hole in rings[1:]):
                    return True
        return False


def _in_ring(x: float, y: float, ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


@lru_cache(maxsize=1)
def _countries() -> list[_Country]:
    raw = json.load(open(DATA / "countries_geo.json", encoding="utf-8"))
    return [_Country(c["code"], c["name"], c["polygons"]) for c in raw]


def country_at(lat: float, lon: float, hint: str | None = None) -> str | None:
    """ISO alpha-2 code of the country containing the point, or None (sea / outside data)."""
    cs = _countries()
    if hint:
        for c in cs:
            if c.code == hint and c.contains(lon, lat):
                return hint
    for c in cs:
        if c.contains(lon, lat):
            return c.code
    return None


def nearest_country(lat: float, lon: float) -> str | None:
    """Country at the point, or the closest country vertex if the point is just offshore."""
    c = country_at(lat, lon)
    if c:
        return c
    best, best_d = None, 1e18
    for ctry in _countries():
        for (x0, y0, x1, y1), rings in ctry.polys:
            if x0 - 1 <= lon <= x1 + 1 and y0 - 1 <= lat <= y1 + 1:
                for x, y in rings[0]:
                    d = (x - lon) ** 2 + (y - lat) ** 2
                    if d < best_d:
                        best, best_d = ctry.code, d
    return best


def landmass(lat: float, lon: float, country: str | None) -> str:
    """'GB' (Great Britain), 'IE' (island of Ireland incl. NI) or 'EU' (mainland Europe)."""
    if country == "IE":
        return "IE"
    if country == "GB" or country in ("IM", "JE", "GG"):
        # Northern Ireland is part of GB in the polygon data but on the island of Ireland.
        if lon < -5.35 and 54.0 <= lat <= 55.4:
            return "IE"
        return "GB"
    return "EU"


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def decode_polyline(s: str, precision: int = 6) -> list[tuple[float, float]]:
    """Decode a Google-style encoded polyline into [(lat, lon), ...]."""
    coords, idx, lat, lon, f = [], 0, 0, 0, 10 ** precision
    while idx < len(s):
        for which in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[idx]) - 63; idx += 1
                result |= (b & 0x1F) << shift; shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lat / f, lon / f))
    return coords


def simplify(points: list[tuple[float, float]], min_km: float) -> list[tuple[float, float]]:
    """Drop points closer than min_km to the previously kept point (cheap thinning for map display)."""
    if len(points) < 3:
        return points
    out = [points[0]]
    for p in points[1:-1]:
        if haversine_km(out[-1][0], out[-1][1], p[0], p[1]) >= min_km:
            out.append(p)
    out.append(points[-1])
    return out
