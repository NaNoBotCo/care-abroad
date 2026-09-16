"""The rules this project would rather find broken here than on a page.

    python3 -m unittest discover -s tests
"""
from __future__ import annotations

import json
import math
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from common import GEO, HARVEST, NODES, TYPES, haversine_km, jload, load_nodes, load_sources, load_vocab  # noqa: E402
import validate as V  # noqa: E402
import worldmap  # noqa: E402

RECS = load_nodes()
SOURCES = load_sources()
ISO = re.compile(r"^[A-Z]{2}$")
CUR = re.compile(r"^[A-Z]{3}$")
DATEISH = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


class TestValidator(unittest.TestCase):
    def test_every_record_passes(self):
        self.assertEqual(V.validate_all(quiet=True), 0, "run tools/validate.py to see what broke")


class TestPrices(unittest.TestCase):
    def rows(self):
        for r in RECS:
            for i, p in enumerate(r.get("prices", [])):
                yield r, i, p

    def test_a_price_carries_a_date_a_currency_and_a_source(self):
        for r, i, p in self.rows():
            with self.subTest(rec=r["id"], i=i):
                self.assertTrue(DATEISH.match(str(p.get("as_of", ""))))
                self.assertTrue(CUR.match(p.get("currency", "")))
                self.assertIn(p.get("source", ""), SOURCES)

    def test_a_range_runs_upward(self):
        for r, i, p in self.rows():
            if p.get("amount") is not None and p.get("amount_high") is not None:
                with self.subTest(rec=r["id"], i=i):
                    self.assertGreaterEqual(p["amount_high"], p["amount"])

    def test_a_price_names_a_country_that_exists(self):
        known = {c["iso"] for c in jload(GEO / "countries.json")["countries"]}
        for r, i, p in self.rows():
            with self.subTest(rec=r["id"], i=i):
                self.assertTrue(ISO.match(p.get("country", "")))
                self.assertIn(p["country"], known)


class TestLegality(unittest.TestCase):
    def test_a_reading_names_an_instrument_and_a_date(self):
        for r in RECS:
            for i, lg in enumerate(r.get("legality", [])):
                with self.subTest(rec=r["id"], i=i):
                    self.assertTrue(DATEISH.match(str(lg.get("as_of", ""))))
                    self.assertIn(lg.get("source", ""), SOURCES)
                    if lg["status"] not in ("no-data", "unregulated"):
                        self.assertTrue(lg.get("instrument"), "a status with no instrument named")


class TestTags(unittest.TestCase):
    def test_a_tag_is_never_a_guess(self):
        """The tiers a tag may carry. A reader may act on a tag, so tradition and
        inference are refused here even though they are fine in prose."""
        for r in RECS:
            for i, t in enumerate(r.get("tags", [])):
                with self.subTest(rec=r["id"], i=i):
                    self.assertNotIn(t.get("tier"), ("tradition", "inference"))
                    self.assertIn(t.get("source", ""), SOURCES)


class TestVoice(unittest.TestCase):
    def test_no_banned_words_outside_quotation_marks(self):
        for r in RECS:
            for fname, txt in V.text_fields(r):
                clean = re.sub(r'[“"][^”"]{0,400}[”"]', "X", txt or "")
                with self.subTest(rec=r["id"], field=fname):
                    self.assertIsNone(V.BANNED.search(clean))
                    self.assertIsNone(V.PUFF.search(clean))

    def test_no_second_person_advice_in_the_journey(self):
        """The pathway records describe what happens. A sentence telling a reader what to
        do about their own body belongs to a clinician who has seen them."""
        bad = re.compile(r"\byou (?:should|must|need to|ought to|will want)\b", re.I)
        for r in RECS:
            if r["type"] != "pathway":
                continue
            for fname, txt in V.text_fields(r):
                with self.subTest(rec=r["id"], field=fname):
                    self.assertIsNone(bad.search(txt or ""))


class TestKin(unittest.TestCase):
    def test_kin_points_somewhere_real_and_not_at_itself(self):
        """Under BUILD_DRAFT an unwritten target is tolerated, the same way validate.py
        tolerates it, so the suite can run while a batch is still being drafted."""
        ids = {r["id"] for r in RECS}
        missing = []
        for r in RECS:
            for k in r.get("kin", []):
                with self.subTest(rec=r["id"], to=k["to"]):
                    self.assertNotEqual(k["to"], r["id"])
                if k["to"] not in ids:
                    missing.append(f'{r["id"]} -> {k["to"]}')
        if missing and not V.DRAFT:
            self.fail(f"{len(missing)} kin targets do not exist: " + ", ".join(sorted(set(missing))[:20]))

    def test_a_kin_sentence_says_something(self):
        for r in RECS:
            for k in r.get("kin", []):
                with self.subTest(rec=r["id"], to=k["to"]):
                    self.assertGreater(len(k["as"].split()), 3, "a kin line is a sentence, not a label")
                    self.assertNotIn(k["as"].strip().lower(), ("see also", "related", "related to"))


class TestGeo(unittest.TestCase):
    def test_a_point_is_on_the_planet(self):
        for r in RECS:
            g = r.get("geo")
            if not g:
                continue
            with self.subTest(rec=r["id"]):
                self.assertTrue(-90 <= g["lat"] <= 90)
                self.assertTrue(-180 <= g["lon"] <= 180)
                self.assertNotEqual((round(g["lat"]), round(g["lon"])), (0, 0), "null island")

    def test_a_point_lands_in_the_country_it_claims(self):
        """Point-in-polygon against the same outlines the maps are drawn from. A coarse
        1:50m outline is used here rather than the 1:110m one the maps draw from, because
        at 1:110m Singapore has no polygon and a point in Geneva falls in France."""
        from common import country_by_geo
        for r in RECS:
            g = r.get("geo")
            iso = (r.get("facets") or {}).get("iso2") or (r.get("address") or {}).get("country")
            if not g or not iso or g.get("precision") in ("country", "region"):
                continue
            hit = country_by_geo(g["lat"], g["lon"], detail=True)
            if hit is None or hit == iso:
                continue
            # A border town is the normal case here, not an error: Los Algodones is a few
            # hundred metres from Arizona and the Nicosia point straddles a line the
            # outlines draw differently. Accept anything within 20 km of the claimed
            # country's own coastline or frontier.
            with self.subTest(rec=r["id"]):
                self.assertLess(_km_to_country(g["lat"], g["lon"], iso), 20.0,
                                f"{r['id']} says {iso}, the outline says {hit}")


def _km_to_country(lat: float, lon: float, iso: str) -> float:
    """Shortest great-circle distance from a point to any vertex of that country's
    outline. Vertices, not edges, so it over-estimates slightly on a long straight
    frontier — which is the safe direction for a tolerance test."""
    geo = jload(GEO / "countries-detail.json") if (GEO / "countries-detail.json").exists() \
        else jload(GEO / "countries.json")
    best = 9e9
    for c in geo["countries"]:
        if c["iso"] != iso:
            continue
        for ring in c["rings"]:
            for lo, la in ring:
                d = haversine_km(lat, lon, la, lo)
                if d < best:
                    best = d
    return best


class TestProjection(unittest.TestCase):
    def test_equal_earth_puts_the_equator_where_it_belongs(self):
        geo = jload(GEO / "countries.json")
        fit = worldmap.fit_world(geo, 900)
        x0, y0 = worldmap.project(0, 0, fit)
        self.assertAlmostEqual(x0, 900 / 2, delta=1.5)
        xw, _ = worldmap.project(-179.9, 0, fit)
        xe, _ = worldmap.project(179.9, 0, fit)
        self.assertAlmostEqual(xw, fit["pad"], delta=2)
        self.assertAlmostEqual(xe, 900 - fit["pad"], delta=2)

    def test_north_is_up(self):
        geo = jload(GEO / "countries.json")
        fit = worldmap.fit_world(geo, 900)
        _, y_north = worldmap.project(0, 60, fit)
        _, y_south = worldmap.project(0, -30, fit)
        self.assertLess(y_north, y_south)

    def test_equal_area_holds(self):
        """The property the projection is chosen for: two patches of equal area on the
        globe take equal area on the page. Sampled at the equator and at 55 degrees."""
        geo = jload(GEO / "countries.json")
        fit = worldmap.fit_world(geo, 900)

        def patch(lat):
            d = 2.0
            # a lat/lon box of this size covers cos(lat) times the area of one on the equator
            p = [worldmap.project(lo, la, fit) for lo, la in
                 ((0, lat), (d, lat), (d, lat + d), (0, lat + d))]
            a = abs(sum(p[i][0] * p[(i + 1) % 4][1] - p[(i + 1) % 4][0] * p[i][1] for i in range(4))) / 2
            return a / math.cos(math.radians(lat + d / 2))
        self.assertAlmostEqual(patch(0) / patch(55), 1.0, delta=0.04)


class TestDistance(unittest.TestCase):
    def test_a_known_great_circle(self):
        # London Heathrow to Bangkok Suvarnabhumi, about 9,550 km
        self.assertAlmostEqual(haversine_km(51.47, -0.4543, 13.69, 100.75), 9550, delta=120)


class TestHarvests(unittest.TestCase):
    def test_world_bank_rows_are_country_codes(self):
        p = HARVEST / "worldbank.json"
        if not p.exists():
            self.skipTest("no World Bank harvest on disk")
        wb = jload(p)
        for key, ind in wb["indicators"].items():
            for iso in ind["values"]:
                with self.subTest(indicator=key, iso=iso):
                    self.assertTrue(ISO.match(iso))

    def test_every_value_carries_its_year(self):
        p = HARVEST / "worldbank.json"
        if not p.exists():
            self.skipTest("no World Bank harvest on disk")
        for key, ind in jload(p)["indicators"].items():
            for iso, v in ind["values"].items():
                with self.subTest(indicator=key, iso=iso):
                    self.assertIsInstance(v["year"], int)
                    self.assertTrue(1960 <= v["year"] <= 2030)

    def test_the_rate_table_is_dated(self):
        p = HARVEST / "rates.json"
        if not p.exists():
            self.skipTest("no rate table on disk")
        d = jload(p)
        self.assertTrue(d.get("fetched_at"))
        self.assertGreater(len(d["per_usd"]), 50)
        self.assertEqual(d["per_usd"]["USD"], 1)


class TestVocab(unittest.TestCase):
    def test_every_type_has_a_folder_and_an_entry(self):
        entries = {e["key"] for e in load_vocab("types")["entries"]}
        self.assertEqual(entries, set(TYPES))
        for t in TYPES:
            self.assertTrue((NODES / t).exists(), f"data/nodes/{t}/ is missing")

    def test_market_points_are_on_the_planet(self):
        for m in load_vocab("markets")["entries"]:
            with self.subTest(market=m["iso"]):
                self.assertTrue(-90 <= m["lat"] <= 90)
                self.assertTrue(-180 <= m["lon"] <= 180)
                self.assertTrue(CUR.match(m["currency"]))


if __name__ == "__main__":
    unittest.main()
