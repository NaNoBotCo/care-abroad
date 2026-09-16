"""fetch_geo.py — the country outlines the maps are drawn from.

Natural Earth, Admin 0 countries, 1:110m, public domain. Fetched once and kept in
data/geo/countries.json: every country with an ISO 3166-1 alpha-2 code, rings simplified
to about twenty kilometres, coordinates to 2 decimal places. That is coarse on purpose —
these maps are 900 pixels wide and a coastline drawn finer than a pixel costs bandwidth
and buys nothing. Run it again only to refresh.

    python3 tools/fetch_geo.py
    python3 tools/fetch_geo.py --detail    # the 1:50m file, for the close-up maps
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GEO, jdump  # noqa: E402

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
CREDIT = "Natural Earth, Admin 0 – Countries (public domain)"
SITE = "https://www.naturalearthdata.com/downloads/"

# Natural Earth leaves iso_a2 as "-99" for a handful of places: France and Norway (their
# codes sit on the dependency rows), Kosovo, Somaliland, northern Cyprus. Patch the ones
# a reader of this directory would look for by name.
BY_NAME = {"France": "FR", "Norway": "NO", "Kosovo": "XK", "Somaliland": "XS",
           "N. Cyprus": "XN", "Northern Cyprus": "XN"}


def _perp(p, a, b) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return ((x - (x1 + t * dx)) ** 2 + (y - (y1 + t * dy)) ** 2) ** 0.5


def simplify(pts: list, tol: float) -> list:
    """Douglas-Peucker, iterative so a long coastline does not blow the stack."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        far, d = -1, tol
        for k in range(i + 1, j):
            dk = _perp(pts[k], pts[i], pts[j])
            if dk > d:
                far, d = k, dk
        if far > 0:
            keep[far] = True
            stack.append((i, far))
            stack.append((far, j))
    return [p for p, k in zip(pts, keep) if k]


def rings_of(geom: dict) -> list:
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [poly[0] for poly in geom["coordinates"]]
    return []


def main(detail=False) -> int:
    url = BASE + ("ne_50m_admin_0_countries.geojson" if detail else "ne_110m_admin_0_countries.geojson")
    tol = 0.05 if detail else 0.2
    min_ring = 0.15 if detail else 0.45
    dp = 3 if detail else 2
    print(f"fetching {url}")
    with urllib.request.urlopen(url, timeout=300) as r:
        gj = json.loads(r.read().decode("utf-8"))
    out = []
    for f in gj["features"]:
        p = f["properties"]
        iso = (p.get("ISO_A2_EH") or p.get("iso_a2") or p.get("ISO_A2") or "").strip()
        name = p.get("NAME") or p.get("name") or ""
        if iso in ("", "-99"):
            iso = BY_NAME.get(name, "")
        if len(iso) != 2:
            continue
        rings = []
        for ring in rings_of(f["geometry"]):
            xs = [c[0] for c in ring]
            ys = [c[1] for c in ring]
            if max(xs) - min(xs) < min_ring and max(ys) - min(ys) < min_ring:
                continue
            s = simplify([(round(c[0], dp), round(c[1], dp)) for c in ring], tol)
            if len(s) > 3:
                rings.append([[x, y] for x, y in s])
        if not rings:
            continue
        hit = next((c for c in out if c["iso"] == iso), None)
        if hit:
            hit["rings"] += rings
            continue
        out.append({"iso": iso, "name": name,
                    "iso3": p.get("ADM0_A3") or p.get("iso_a3") or "",
                    "region": p.get("SUBREGION") or p.get("subregion") or "",
                    "rings": rings})
    out.sort(key=lambda c: c["iso"])
    path = GEO / ("countries-detail.json" if detail else "countries.json")
    jdump({"source": CREDIT, "url": SITE, "fetched_from": url,
           "coords": f"[lon, lat], {dp} dp, Douglas-Peucker at {tol}°",
           "countries": out}, path, indent=None)
    kb = path.stat().st_size / 1024
    print(f"wrote {len(out)} countries, {sum(len(r) for c in out for r in c['rings'])} points, {kb:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--detail" in sys.argv))
