"""Build a compact Europe-only country polygon file from Natural Earth 1:50m.

Usage: python tools/build_countries.py <ne_50m_admin_0_countries.geojson> <out.json>
"""
import json, sys

BBOX = (-25.0, 34.0, 45.0, 72.0)  # lon_min, lat_min, lon_max, lat_max


def in_bbox(ring):
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    return not (max(xs) < BBOX[0] or min(xs) > BBOX[2] or max(ys) < BBOX[1] or min(ys) > BBOX[3])


def main(src, dst):
    data = json.load(open(src, encoding="utf-8"))
    out = []
    for f in data["features"]:
        p = f["properties"]
        code = p.get("ISO_A2_EH") or p.get("ISO_A2")
        if not code or code == "-99":
            continue
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        keep = []
        for poly in polys:
            if in_bbox(poly[0]):
                keep.append([[[round(x, 3), round(y, 3)] for x, y in ring] for ring in poly])
        if keep:
            out.append({"code": code, "name": p.get("NAME"), "polygons": keep})
    json.dump(out, open(dst, "w", encoding="utf-8"), separators=(",", ":"))
    print(len(out), "countries:", ",".join(sorted(c["code"] for c in out)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
