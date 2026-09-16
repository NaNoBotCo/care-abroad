"""worldmap.py — one projection, shared by every map on the site.

A world map that colours countries by a rate has to be equal-area or it lies: on the
Mercator every chart reads as "the rich north is enormous", and the north is where the
patients come from, not where they go. So every map here is drawn in Equal Earth
(Šavrič, Patterson and Jenny, 2018) — equal-area, and shaped closely enough to Robinson
that a reader recognises the world.

    fit = fit_world(load(), width=900)
    x, y = project(lon, lat, fit)

For a close-up — one city, one region — fit_bbox() keeps the same projection and simply
crops to the box, so a hub map and the world map agree about where things are.

Areas are true: a square kilometre takes the same ink anywhere on this map.
Shapes are not: Equal Earth stretches high latitudes east-west and squashes them
north-south, which is the price every equal-area projection pays.
"""
from __future__ import annotations

import math
from pathlib import Path

from common import GEO, jload

A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
_R3_2 = math.sqrt(3) / 2


def _equal_earth(lon: float, lat: float, lon0: float = 0.0) -> tuple[float, float]:
    """Equal Earth, in projected units where the equator runs about 2.7 wide per radian.
    y is negated because SVG counts down and the globe counts up."""
    lam = math.radians(((lon - lon0 + 180) % 360) - 180)
    phi = math.radians(max(-89.999, min(89.999, lat)))
    th = math.asin(_R3_2 * math.sin(phi))
    t2 = th * th
    den = 3 * (9 * A4 * t2 ** 4 + 7 * A3 * t2 ** 3 + 3 * A2 * t2 + A1)
    x = 2 * math.sqrt(3) * lam * math.cos(th) / den
    y = A4 * th ** 9 + A3 * th ** 7 + A2 * th ** 3 + A1 * th
    return x, -y


def load() -> dict:
    return jload(GEO / "countries.json")


def fit_world(geo: dict, width: float, pad: float = 6.0, lon0: float = 0.0,
              lat_range: tuple[float, float] = (-58.0, 84.0)) -> dict:
    """Scale the whole world into `width` pixels. Antarctica is cropped off the bottom by
    default — nobody in this directory flies there for a knee — and the caption says so."""
    xs = [_equal_earth(lon, 0, lon0)[0] for lon in (lon0 - 180 + 0.001, lon0 + 180 - 0.001)]
    ys = [_equal_earth(0, lat_range[1], lon0)[1], _equal_earth(0, lat_range[0], lon0)[1]]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    k = (width - 2 * pad) / (x1 - x0)
    return {"k": k, "x0": x0, "y0": y0, "pad": pad, "lon0": lon0,
            "w": width, "h": (y1 - y0) * k + 2 * pad, "crop": lat_range}


def fit_bbox(minlon: float, minlat: float, maxlon: float, maxlat: float,
             width: float, pad: float = 6.0, lon0: float | None = None) -> dict:
    """The same projection, cropped to a box — a country, a city and its neighbours."""
    if lon0 is None:
        lon0 = (minlon + maxlon) / 2
    corners = [_equal_earth(lo, la, lon0) for lo in (minlon, maxlon, (minlon + maxlon) / 2)
               for la in (minlat, maxlat, (minlat + maxlat) / 2)]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    k = (width - 2 * pad) / (x1 - x0) if x1 > x0 else 1.0
    return {"k": k, "x0": x0, "y0": y0, "pad": pad, "lon0": lon0,
            "w": width, "h": (y1 - y0) * k + 2 * pad, "crop": (minlat, maxlat)}


def project(lon: float, lat: float, fit: dict) -> tuple[float, float]:
    x, y = _equal_earth(lon, lat, fit["lon0"])
    return (x - fit["x0"]) * fit["k"] + fit["pad"], (y - fit["y0"]) * fit["k"] + fit["pad"]


def country_paths(geo: dict, fit: dict, only: set | None = None):
    """(iso2, name, svg path) per country, rings already simplified on disk."""
    out = []
    for c in geo["countries"]:
        if only is not None and c["iso"] not in only:
            continue
        d = []
        for ring in c["rings"]:
            pts = []
            last = None
            for lon, lat in ring:
                x, y = project(lon, lat, fit)
                # a ring that wraps the antimeridian would otherwise draw a bar across
                # the whole map; break it instead
                if last is not None and abs(x - last) > fit["w"] * 0.55:
                    pts.append(None)
                last = x
                pts.append((x, y))
            seg = []
            for p in pts:
                if p is None:
                    if len(seg) > 2:
                        d.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in seg) + "Z")
                    seg = []
                else:
                    seg.append(p)
            if len(seg) > 2:
                d.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in seg) + "Z")
        if d:
            out.append((c["iso"], c["name"], "".join(d)))
    return out


def graticule(fit: dict, step: int = 30) -> str:
    """Meridians and parallels, so a reader can see the projection bending."""
    d = []
    lo0 = fit["lon0"]
    for lon in range(-180, 181, step):
        pts = [project(lon, lat, fit) for lat in range(int(fit["crop"][0]), int(fit["crop"][1]) + 1, 5)]
        if any(abs(p[0] - q[0]) > fit["w"] * 0.5 for p, q in zip(pts, pts[1:])):
            continue
        d.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts))
    for lat in range(-60, 91, step):
        if not (fit["crop"][0] <= lat <= fit["crop"][1]):
            continue
        pts = [project(lon, lat, fit) for lon in range(-180, 181, 5)]
        segs, cur = [], [pts[0]]
        for p, q in zip(pts, pts[1:]):
            if abs(q[0] - p[0]) > fit["w"] * 0.5:
                segs.append(cur)
                cur = []
            cur.append(q)
        segs.append(cur)
        for s in segs:
            if len(s) > 1:
                d.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in s))
    return " ".join(d)


def arc(lon1: float, lat1: float, lon2: float, lat2: float, fit: dict, n: int = 48) -> str:
    """A great-circle path between two points, sampled and projected — the line a plane
    actually flies, not the straight line a flat map draws. Returns "" if it would wrap."""
    r = math.radians
    f1, l1, f2, l2 = r(lat1), r(lon1), r(lat2), r(lon2)
    d = 2 * math.asin(math.sqrt(math.sin((f2 - f1) / 2) ** 2 +
                                math.cos(f1) * math.cos(f2) * math.sin((l2 - l1) / 2) ** 2))
    if d < 1e-9:
        return ""
    pts = []
    for i in range(n + 1):
        t = i / n
        a = math.sin((1 - t) * d) / math.sin(d)
        b = math.sin(t * d) / math.sin(d)
        x = a * math.cos(f1) * math.cos(l1) + b * math.cos(f2) * math.cos(l2)
        y = a * math.cos(f1) * math.sin(l1) + b * math.cos(f2) * math.sin(l2)
        z = a * math.sin(f1) + b * math.sin(f2)
        lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
        lon = math.degrees(math.atan2(y, x))
        pts.append(project(lon, lat, fit))
    for p, q in zip(pts, pts[1:]):
        if abs(q[0] - p[0]) > fit["w"] * 0.5:
            return ""
    return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts)


def bbox_of(geo: dict, iso: str):
    for c in geo["countries"]:
        if c["iso"] == iso:
            xs = [p[0] for ring in c["rings"] for p in ring]
            ys = [p[1] for ring in c["rings"] for p in ring]
            return min(xs), min(ys), max(xs), max(ys)
    return None
