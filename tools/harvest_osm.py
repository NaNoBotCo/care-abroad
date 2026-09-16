"""harvest_osm.py — every named hospital, clinic and dental surgery around each hub.

OpenStreetMap through Overpass, ODbL 1.0 (share-alike: the attribution and the licence
travel with the rows, on the page and in the API). One query per hub record, a radius the
hub itself names, saved after each hub so a kill keeps what it already fetched.

    python3 tools/harvest_osm.py                  # every hub record
    python3 tools/harvest_osm.py --resume         # only hubs not already on disk
    python3 tools/harvest_osm.py --hubs bangkok,istanbul
    python3 tools/harvest_osm.py --radius 25      # override every hub's radius, km

What a row is: a point OpenStreetMap carries on the fetch date, with whatever tags a
mapper typed. It is not a recommendation, not an accreditation, and not a claim the place
treats foreign patients. A hospital missing from the map is missing from the map.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HARVEST, NODES, jdump, jload, slugify  # noqa: E402

ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter"]
UA = "care-abroad/1.0 (static directory build; contact via the site)"
KEEP = ("name", "name:en", "int_name", "operator", "operator:type", "healthcare",
        "healthcare:speciality", "amenity", "emergency", "beds", "website", "contact:website",
        "phone", "contact:phone", "opening_hours", "addr:city", "addr:street", "addr:housenumber",
        "addr:postcode", "addr:country", "wheelchair", "start_date", "wikidata", "wikipedia",
        "brand", "religion", "lgbtq", "lgbtq:signed")

Q = """[out:json][timeout:240];
(
  nwr["amenity"="hospital"]["name"](around:{r},{lat},{lon});
  nwr["amenity"="clinic"]["name"](around:{r},{lat},{lon});
  nwr["amenity"="dentist"]["name"](around:{r},{lat},{lon});
  nwr["healthcare"~"^(hospital|clinic|centre|dentist|fertility_clinic|rehabilitation|laboratory)$"]["name"](around:{r},{lat},{lon});
);
out center tags;"""


def overpass(query: str) -> dict:
    last = None
    for ep in ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    ep, data=urllib.parse.urlencode({"data": query}).encode(),
                    headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.loads(r.read().decode("utf-8"))
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                last = e
                time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Overpass refused every endpoint: {last}")


def hubs() -> list[dict]:
    out = []
    for p in sorted((NODES / "hub").glob("*.json")):
        d = jload(p)
        g = d.get("geo") or {}
        if g.get("lat") is None:
            continue
        out.append({"id": d["id"], "name": d["names"]["name"], "lat": g["lat"], "lon": g["lon"],
                    "iso2": (d.get("facets") or {}).get("iso2", ""),
                    "radius_km": (d.get("facets") or {}).get("radius_km") or 15})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--hubs", default="")
    ap.add_argument("--radius", type=float, default=0)
    a = ap.parse_args()
    path = HARVEST / "osm-facilities.json"
    have = jload(path) if path.exists() else {"hubs": {}, "places": []}
    want = hubs()
    if a.hubs:
        pick = {x.strip() for x in a.hubs.split(",")}
        want = [h for h in want if h["id"] in pick]
    if a.resume:
        want = [h for h in want if h["id"] not in have.get("hubs", {})]
    if not want:
        print("nothing to fetch — every hub is already on disk (or no hub record carries geo)")
        return 0
    seen = {p["osm_id"] for p in have.get("places", [])}
    for h in want:
        r_km = a.radius or h["radius_km"]
        q = Q.format(r=int(r_km * 1000), lat=h["lat"], lon=h["lon"])
        print(f"  {h['name']:28s} r={r_km:g} km …", end=" ", flush=True)
        try:
            body = overpass(q)
        except RuntimeError as e:
            print("failed:", e)
            continue
        n = 0
        for el in body.get("elements", []):
            t = el.get("tags", {})
            name = t.get("name") or ""
            if not name:
                continue
            oid = f"{el['type'][0]}{el['id']}"
            if oid in seen:
                continue
            c = el.get("center") or el
            if c.get("lat") is None:
                continue
            seen.add(oid)
            have["places"].append({
                "osm_id": oid, "hub": h["id"], "iso2": (t.get("addr:country") or h["iso2"]).upper()[:2],
                "name": name, "slug": slugify(name)[:60] or oid,
                "lat": round(c["lat"], 5), "lon": round(c["lon"], 5),
                "tags": {k: v for k, v in t.items() if k in KEEP},
            })
            n += 1
        have["hubs"][h["id"]] = {"fetched_at": time.strftime("%Y-%m-%d"), "radius_km": r_km, "rows": n}
        have.update({
            "source": "OpenStreetMap contributors", "license": "ODbL 1.0",
            "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
            "attribution": "© OpenStreetMap contributors",
            "osm_base": "https://www.openstreetmap.org/",
            "fetched_at": time.strftime("%Y-%m-%d"),
            "query": re.sub(r"\s+", " ", Q).strip(),
            "count": len(have["places"]),
        })
        jdump(have, path, indent=None)
        print(f"{n} new · {len(have['places'])} total")
        time.sleep(3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
