"""harvest_worldbank.py — the country-level series the choropleths are drawn from.

The World Bank's open data API, no key, CC BY 4.0. One request per indicator for every
country, most recent non-null year per country kept, the year kept beside the value
because a 2019 figure and a 2023 figure are not the same fact.

    python3 tools/harvest_worldbank.py                 # every indicator below
    python3 tools/harvest_worldbank.py --only beds
    python3 tools/harvest_worldbank.py --from 2010

Writes data/harvest/worldbank.json. Each indicator carries its own code, name, unit,
licence and fetch date, and data/nodes/dataset/*.json is where a reader is told what the
series counts and what it leaves out.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HARVEST, jdump  # noqa: E402

API = "https://api.worldbank.org/v2"
LICENSE = "CC BY 4.0"
LICENSE_URL = "https://datacatalog.worldbank.org/public-licenses#cc-by"

INDICATORS = {
    "spend_pc": ("SH.XPD.CHEX.PC.CD", "Current health expenditure per person", "current US$"),
    "spend_gdp": ("SH.XPD.CHEX.GD.ZS", "Current health expenditure", "% of GDP"),
    "oop": ("SH.XPD.OOPC.CH.ZS", "Out-of-pocket share of health spending", "% of current health expenditure"),
    "doctors": ("SH.MED.PHYS.ZS", "Physicians", "per 1,000 people"),
    "nurses": ("SH.MED.NUMW.P3", "Nurses and midwives", "per 1,000 people"),
    "beds": ("SH.MED.BEDS.ZS", "Hospital beds", "per 1,000 people"),
    "life": ("SP.DYN.LE00.IN", "Life expectancy at birth", "years"),
    "gdp_pc": ("NY.GDP.PCAP.CD", "GDP per person", "current US$"),
    "population": ("SP.POP.TOTL", "Population", "people"),
    "arrivals": ("ST.INT.ARVL", "Inbound visitor arrivals", "people a year"),
    "receipts": ("ST.INT.RCPT.CD", "Inbound travel receipts", "current US$"),
}

# Two of the World Bank's own series titles use a word this project's style rules keep out
# of its prose. The label on the button is ours; the publisher's title travels with it so
# the series can still be found by the name its publisher gives it.
PUBLISHER_TITLE = {
    "arrivals": "International tourism, number of arrivals",
    "receipts": "International tourism, receipts (current US$)",
}


_REAL: set = set()


def real_countries() -> set:
    """The World Bank's own list of what is a country. Its indicator endpoint returns
    aggregates — income groups, regions, the euro area — alongside countries, and several
    of them wear two-letter codes that collide with real ones: XN is "Lower middle income"
    here and northern Cyprus on this site's map. An aggregate is the row whose region id
    is NA, so that is the test, rather than a hand-kept list of codes to drop."""
    global _REAL
    if _REAL:
        return _REAL
    url = f"{API}/country?format=json&per_page=400"
    with urllib.request.urlopen(url, timeout=120) as r:
        body = json.loads(r.read().decode("utf-8"))
    for row in body[1]:
        if (row.get("region") or {}).get("id") != "NA":
            _REAL.add(row["iso2Code"].upper())
    return _REAL


def fetch(code: str, since: int) -> list:
    rows, page = [], 1
    while True:
        url = (f"{API}/country/all/indicator/{code}?format=json&per_page=8000"
               f"&date={since}:{time.strftime('%Y')}&page={page}")
        with urllib.request.urlopen(url, timeout=120) as r:
            body = json.loads(r.read().decode("utf-8"))
        if not isinstance(body, list) or len(body) < 2 or body[1] is None:
            break
        rows += body[1]
        meta = body[0]
        if page >= meta.get("pages", 1):
            break
        page += 1
        time.sleep(0.3)
    return rows


def latest(rows: list) -> dict:
    """Most recent year with a value, per country. Aggregates — the Bank's own regions and
    income groups — come back on the same endpoint wearing two-letter codes, and are
    dropped against its own country list rather than by eye."""
    real = real_countries()
    out: dict = {}
    for r in rows:
        iso2 = (r.get("country", {}) or {}).get("id", "")
        if len(iso2) != 2 or not iso2.isalpha() or r.get("value") is None:
            continue
        if real and iso2.upper() not in real:
            continue
        y = int(r["date"])
        cur = out.get(iso2.upper())
        if cur is None or y > cur["year"]:
            out[iso2.upper()] = {"value": r["value"], "year": y,
                                 "name": (r.get("country", {}) or {}).get("value", "")}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--from", dest="since", type=int, default=2010)
    a = ap.parse_args()
    path = HARVEST / "worldbank.json"
    have = json.loads(path.read_text()) if path.exists() else {"indicators": {}}
    want = a.only or list(INDICATORS)
    for key in want:
        code, name, unit = INDICATORS[key]
        print(f"  {key:11s} {code} …", end=" ", flush=True)
        rows = fetch(code, a.since)
        vals = latest(rows)
        have["indicators"][key] = {
            "code": code, "name": name, "unit": unit,
            "source": "World Bank Open Data", "license": LICENSE, "license_url": LICENSE_URL,
            "url": f"https://data.worldbank.org/indicator/{code}",
            "publisher_title": PUBLISHER_TITLE.get(key),
            "fetched_at": time.strftime("%Y-%m-%d"), "since": a.since,
            "countries": len(vals),
            "years": sorted({v["year"] for v in vals.values()}),
            "values": dict(sorted(vals.items())),
        }
        print(f"{len(vals)} countries")
        time.sleep(0.4)
    have["fetched_at"] = time.strftime("%Y-%m-%d")
    have["note"] = ("Most recent year with a value, per country, per indicator. The year "
                    "travels with the value: a chart that puts a 2019 figure beside a 2023 "
                    "one without saying so is drawing two different worlds.")
    jdump(have, path, indent=None)
    print(f"wrote {path} — {path.stat().st_size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
