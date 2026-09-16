#!/usr/bin/env python3
"""fetch_wiki.py — the verification corpus a drafting agent reads before it writes.

Plain-text copies of the Wikipedia articles this set cites, one file per article, each
carrying its title, URL and fetch date at the top. An agent reads these first and reaches
for the live web only when a fact is not in them.

    python3 tools/fetch_wiki.py <out-dir>

MediaWiki caps a full-text extract at one article per request, so this walks them one at
a time with a pause. Sixty-odd articles take about a minute.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

API = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "buffalo-wings-build/0.1 (https://wichaa.net; nan@motdang.net) python-urllib"}

TITLES = """Buffalo wing|Anchor Bar|Duff's Famous Wings|Frank's RedHot|Hot chicken|Mumbo sauce|Mild sauce|
Old Bay Seasoning|Korean fried chicken|Jerk (cooking)|Harold's Chicken Shack|Wingstop|Buffalo Wild Wings|Hooters|
Bonchon Chicken|Wing Bowl|National Buffalo Wing Festival|Beef on weck|Garbage plate|Chicken riggies|
Blue cheese dressing|Ranch dressing|Lemon pepper|Calvin Trillin|Prince's Hot Chicken Shack|Hattie B's Hot Chicken|
Joey Chestnut|Chicken nugget|National Chicken Council|Deep frying|Mozzarella sticks|Chicken and waffles|
Crystal Hot Sauce|Cayenne pepper|Hot sauce|Scoville scale|Air fryer|Chicken as food|Poultry|Buffalo, New York|
Rochester, New York|Celery|Hot honey|Teriyaki|Gochujang|Sriracha|Louisiana-style hot sauce|Tabasco sauce|Texas Pete|
Sweet chili sauce|Super Bowl|Fried chicken|Soul food|American Chinese cuisine|La Nova Pizzeria|Chicken wing|
Chicken fingers|Pizza Hut|Popeyes|Zaxby's|Carolina Reaper"""


def main(out_dir: str) -> int:
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    titles = [t.strip() for t in TITLES.replace("\n", "").split("|") if t.strip()]
    got, missing = [], []
    for t in titles:
        q = {"action": "query", "prop": "extracts|info", "explaintext": 1, "format": "json",
             "redirects": 1, "inprop": "url", "titles": t}
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q), headers=UA)
        try:
            d = json.load(urllib.request.urlopen(req, timeout=60))
        except Exception as e:  # noqa: BLE001
            missing.append(f"{t} ({e})")
            continue
        for pid, pg in d["query"]["pages"].items():
            if int(pid) < 0 or not pg.get("extract"):
                missing.append(pg.get("title") or t)
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", pg["title"].lower()).strip("-")
            (out / f"{slug}.txt").write_text(
                f"TITLE: {pg['title']}\nURL: {pg['fullurl']}\nFETCHED: {time.strftime('%Y-%m-%d')}\n\n{pg['extract']}\n",
                encoding="utf-8")
            got.append(pg["title"])
        time.sleep(0.35)
    print(f"{len(got)} fetched into {out} · {len(missing)} missing: {missing}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1]))
