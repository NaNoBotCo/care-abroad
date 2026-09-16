#!/usr/bin/env python3
"""build.py — records + harvests → build/api (JSON) + build/searchdocs.json + search tables.

Order: validate → enrich → join → write. Nothing is written if validation fails.

Outputs (all regenerated, never hand-edited):
  build/api/nodes.json         every enriched record
  build/api/<type>/<id>.json   one per record
  build/api/index.json         directory: id, type, name, region, facets, blurb
  build/api/countries.json     one row per country: the records on it, the World Bank
                               series, the prices, the accreditations
  build/api/facilities.json    curated facilities + the OpenStreetMap harvest
  build/api/prices.json        every published price, flattened, converted at a dated rate
  build/api/legality.json      the procedure × jurisdiction matrix
  build/api/kin.json           every directed kin edge, plus auto backlinks
  build/api/vocab/*.json       regions, types, facets, tags, recognizers, markets
  build/api/sources.json       the source registry (merged)
  build/api/coverage.json      scope as an object: what is in, what is not, where rows come from
  build/searchdocs.json        one document per record
  data/search/care.thesaurus.json

    python3 tools/build.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BUILD, DATA, GEO, SOURCES, TIER_LABEL, TYPES, haversine_km, jdump,  # noqa: E402
                    jload, load_harvest, load_nodes, load_sources, load_vocab)
from validate import validate_all  # noqa: E402

SEARCH_DIR = DATA / "search"
API = BUILD / "api"
TAGS = {e["key"]: e for e in load_vocab("tags").get("entries", [])}
RECOG = {e["key"]: e for e in load_vocab("recognizers").get("entries", [])}


def merge_sources() -> dict:
    """sources.json + every data/sources/new-*.json, de-duplicated by id, written back."""
    base = jload(SOURCES)
    have = {s["id"] for s in base["sources"]}
    added = 0
    done = SOURCES.parent / "merged"
    for p in sorted(SOURCES.parent.glob("new-*.json")):
        d = jload(p)
        for s in d.get("sources", []):
            if s.get("id") and s["id"] not in have:
                base["sources"].append(s)
                have.add(s["id"])
                added += 1
        # moved rather than deleted: a drafting agent may still be appending to its own
        # file, and a batch that watches its register vanish mid-run cannot tell a merge
        # from a loss
        done.mkdir(exist_ok=True)
        p.replace(done / p.name)
    if added:
        base["sources"].sort(key=lambda s: s["id"])
        jdump(base, SOURCES)
        print(f"merged {added} new sources into sources.json")
    return {s["id"]: s for s in base["sources"]}


def blurb(r: dict, n=220) -> str:
    w = r["text"]["what"].strip()
    if len(w) <= n:
        return w
    head = w[:n]
    if ". " in head and len(head.rsplit(". ", 1)[0]) > 60:
        return head.rsplit(". ", 1)[0] + "."
    return head.rsplit(" ", 1)[0].rstrip(",;:—-") + "…"


def tier_for(rec: dict, path: str) -> dict:
    prov = rec.get("provenance", {})
    best = None
    for p, v in prov.get("fields", {}).items():
        if path == p or path.startswith(p + "."):
            if best is None or len(p) > len(best[0]):
                best = (p, v)
    return best[1] if best else prov.get("default", {})


def enrich(r: dict, by_id: dict, sources: dict, regions: dict) -> dict:
    out = {k: v for k, v in r.items() if not k.startswith("_")}
    out["blurb"] = blurb(out)
    out["region_terms"] = [dict(regions.get(k) or {"key": k, "name": k}) for k in out["region"]]
    out["kin_out"] = []
    for k in out.get("kin", []):
        t = by_id.get(k["to"])
        if t:
            out["kin_out"].append({"to": k["to"], "type": t["type"], "name": t["names"]["name"],
                                   "as": k["as"], "rel": k.get("rel", "kin")})
    out["source_list"] = [dict(sources[s], id=s) for s in out.get("sources", []) if s in sources]
    out["tiers"] = {p: tier_for(out, p) for p in ("text.what", "text.story", "text.how", "text.today",
                                                  "etymology", "geo", "address", "prices", "legality", "metrics")
                    if p.split(".")[0] in out and (len(p.split(".")) == 1 or p.split(".")[1] in out[p.split(".")[0]])}
    out["primary_image"] = next((im for im in out.get("images", []) if im.get("primary")),
                                (out.get("images") or [None])[0])
    out["tag_facts"] = [dict(TAGS.get(t["tag"], {"key": t["tag"], "label": t["tag"], "icon": ""}),
                             **{"source": t["source"], "note": t.get("note", ""),
                                "tier": t.get("tier", "cited"), "url": t.get("url", "")})
                        for t in out.get("tags", [])]
    out["recognition_facts"] = [dict(RECOG.get(x["by"], {"key": x["by"], "label": x["by"]}),
                                     **{"what": x["what"], "year": x.get("year"),
                                        "valid_until": x.get("valid_until"), "source": x["source"],
                                        "url": x.get("url", "")})
                                for x in out.get("recognitions", [])]
    out["acclaim"] = len({x["by"] for x in out.get("recognitions", [])})
    return out


def backlinks(recs: list[dict]):
    by_id = {r["id"]: r for r in recs}
    for r in recs:
        r["kin_in"] = []
    for r in recs:
        for k in r["kin_out"]:
            t = by_id.get(k["to"])
            if t:
                t["kin_in"].append({"from": r["id"], "type": r["type"], "name": r["names"]["name"],
                                    "as": k["as"], "rel": k["rel"]})


# ------------------------------------------------------------------ money

def price_rows(recs: list[dict], rates: dict | None) -> dict:
    """Every price on every record, flattened into one table, converted at ONE dated rate.

    The conversion is arithmetic, not a claim: a lira price from 2019 shown in 2026
    dollars is what that number converts to today, which is not what the patient paid.
    Each row carries both dates so a reader can see the gap."""
    per_usd = (rates or {}).get("per_usd", {})
    rate_date = (rates or {}).get("rate_date", "")
    rows = []
    for r in recs:
        for i, p in enumerate(r.get("prices", [])):
            k = per_usd.get(p["currency"])
            lo, hi = p.get("amount"), p.get("amount_high")
            rows.append({
                "key": f'{r["id"]}#{i}', "on": r["id"], "on_type": r["type"],
                "procedure": p.get("procedure"), "facility": p.get("facility"),
                "country": p["country"], "city": p.get("city", ""),
                "amount": lo, "amount_high": hi, "currency": p["currency"],
                "usd": round(lo / k, 0) if (k and lo is not None) else None,
                "usd_high": round(hi / k, 0) if (k and hi is not None) else None,
                "as_of": str(p["as_of"]), "rate_date": rate_date if k else "",
                "kind": p["kind"], "includes": p.get("includes", []), "excludes": p.get("excludes", []),
                "source": p["source"], "url": p.get("url", ""), "note": p.get("note", ""),
                "tier": p.get("tier", "cited"),
            })
    # the same published number carried on two records counts twice on every chart, so
    # say so rather than let the total drift
    seen: dict = {}
    for r in rows:
        k = (r["procedure"], r["country"], r["amount"], r["amount_high"], r["currency"],
             r["source"], r["as_of"])
        seen.setdefault(k, []).append(r["on"])
    for k, on in seen.items():
        if len(on) > 1:
            print(f"warn  the same price ({k[2]:,.0f} {k[4]} for {k[0]}, {k[5]}) sits on "
                  f"{len(on)} records: {', '.join(on)}")
    rows.sort(key=lambda x: (x["procedure"] or "zz", x["usd"] if x["usd"] is not None else 9e12))
    return {"built": time.strftime("%Y-%m-%d"), "count": len(rows),
            "rate_date": rate_date, "rate_source": (rates or {}).get("url", ""),
            "note": ("One row per published price. `kind` says what sort of number it is: a "
                     "package price off a hospital's own page, a list price, a national "
                     "tariff, an insurer's reimbursement, a survey figure, or a range a "
                     "provider quotes. Dollars are the row's own currency put through one "
                     "rate table dated above."),
            "prices": rows}


def legality_matrix(recs: list[dict]) -> dict:
    """Every legality row, by subject and jurisdiction. The subject is the record that
    carries the row — a procedure or a rule."""
    rows = []
    for r in recs:
        for lg in r.get("legality", []):
            rows.append({"subject": r["id"], "subject_type": r["type"], "subject_name": r["names"]["name"],
                         "country": lg["country"], "status": lg["status"],
                         "conditions": lg.get("conditions", ""), "instrument": lg.get("instrument", ""),
                         "as_of": str(lg["as_of"]), "source": lg["source"], "url": lg.get("url", ""),
                         "note": lg.get("note", "")})
    subjects = sorted({r["subject"] for r in rows})
    countries = sorted({r["country"] for r in rows})
    return {"built": time.strftime("%Y-%m-%d"), "subjects": subjects, "countries": countries,
            "count": len(rows),
            "statuses": {"lawful": "lawful for a visitor", "lawful-with-conditions": "lawful, with conditions named in the row",
                         "residents-only": "lawful, but not for a non-resident", "unlawful": "prohibited",
                         "unregulated": "no instrument either way", "no-data": "nobody here has read the law"},
            "note": ("A row is a reading of one named instrument on one date. Law moves; a row "
                     "older than its country's last reform is wrong, and the date is printed "
                     "beside every cell so a reader can see how old it is. Nothing here is "
                     "legal advice."),
            "rows": rows}


# ------------------------------------------------------------------ places

def facilities_table(recs: list[dict], osm: dict | None) -> dict:
    """Curated facility records and the OSM harvest in one table. A curated facility that
    also exists in OSM keeps the curated row and gains the osm_id."""
    rows = []
    curated_names: dict = {}
    for r in recs:
        if r["type"] != "facility":
            continue
        g = r.get("geo") or {}
        a = r.get("address") or {}
        f = r.get("facets") or {}
        m = r.get("metrics") or {}
        rows.append({
            "id": r["id"], "name": r["names"]["name"], "iso2": f.get("iso2") or a.get("country"),
            "city": a.get("city", ""), "area": a.get("area", ""),
            "lat": g.get("lat"), "lon": g.get("lon"), "curated": True, "url": f"hospital/{r['id']}/",
            "blurb": r["blurb"], "tier": tier_for(r, "text.what").get("tier"), "osm_id": None,
            "ownership": f.get("ownership"), "beds": m.get("beds") or f.get("beds"),
            "founded": f.get("founded"), "specialty": f.get("specialty") or [],
            "draws": f.get("draws") or [],
            "tags": sorted({t["tag"] for t in r.get("tags", [])}),
            "accredited_by": sorted({x["by"] for x in r.get("recognitions", [])}),
            "acclaim": r.get("acclaim", 0),
            "prices": len(r.get("prices", [])),
            "image": (r.get("primary_image") or {}).get("file"),
        })
        curated_names[_norm(r["names"]["name"])] = rows[-1]
        for al in r["names"].get("aliases", []):
            curated_names[_norm(al)] = rows[-1]
    n_osm = 0
    for p in (osm or {}).get("places", []):
        t = p["tags"]
        hit = curated_names.get(_norm(p["name"]))
        if hit and hit["lat"] is not None and haversine_km(hit["lat"], hit["lon"], p["lat"], p["lon"]) < 4:
            hit["osm_id"] = p["osm_id"]
            continue
        kind = t.get("healthcare") or t.get("amenity") or ""
        rows.append({
            "id": "osm-" + p["slug"], "name": p["name"], "iso2": p.get("iso2") or "",
            "city": t.get("addr:city", ""), "area": "", "lat": p["lat"], "lon": p["lon"],
            "curated": False, "url": None, "blurb": "", "tier": "harvested", "osm_id": p["osm_id"],
            "hub": p.get("hub"), "kind": kind, "ownership": t.get("operator:type"),
            "beds": int(t["beds"]) if str(t.get("beds", "")).isdigit() else None,
            "founded": t.get("start_date"), "specialty": [s for s in (t.get("healthcare:speciality") or "").split(";") if s],
            "draws": [], "tags": (["lgbtq-friendly"] if (t.get("lgbtq") or "").lower() in ("welcome", "primary", "only") else []),
            "accredited_by": [], "acclaim": 0, "prices": 0, "image": None,
            "website": t.get("website") or t.get("contact:website"), "phone": t.get("phone") or t.get("contact:phone"),
            "operator": t.get("operator"), "wheelchair": t.get("wheelchair"),
        })
        n_osm += 1
    rows.sort(key=lambda x: ((x["iso2"] or "ZZ"), x["name"].lower()))
    return {"built": time.strftime("%Y-%m-%d"), "count": len(rows),
            "curated": len(rows) - n_osm, "harvested": n_osm,
            "harvest": {k: (osm or {}).get(k) for k in ("source", "license", "license_url",
                                                        "attribution", "fetched_at", "osm_base", "query")} if osm else None,
            "facilities": rows}


def _norm(s: str) -> str:
    s = s.lower().replace("&", "and").replace("'", "").replace("’", "")
    s = re.sub(r"\b(hospital|hastanesi|hastane|klinik|clinic|medical centre|medical center|centre|center)\b", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def countries_table(recs: list[dict], wb: dict | None, prices: dict, fac: dict, legality: dict) -> dict:
    """One row per country that anything on this site touches: the records that sit on it,
    the World Bank series, how many prices and accreditations it carries. The join key is
    ISO 3166-1 alpha-2 throughout."""
    geo = jload(GEO / "countries.json") if (GEO / "countries.json").exists() else {"countries": []}
    names = {c["iso"]: c["name"] for c in geo["countries"]}
    rows: dict = {}

    def row(iso):
        if iso not in rows:
            rows[iso] = {"iso2": iso, "name": names.get(iso, iso), "records": [], "facilities": 0,
                         "curated_facilities": 0, "prices": 0, "accreditors": [], "legality_rows": 0,
                         "indicators": {}, "destination": None, "hubs": [], "procedures": []}
        return rows[iso]

    for r in recs:
        iso = (r.get("facets") or {}).get("iso2") or (r.get("address") or {}).get("country")
        if not iso:
            continue
        x = row(iso)
        x["records"].append({"id": r["id"], "type": r["type"], "name": r["names"]["name"]})
        if r["type"] == "destination":
            x["destination"] = r["id"]
        if r["type"] == "hub":
            x["hubs"].append(r["id"])
        for a in r.get("recognitions", []):
            if a["by"] not in x["accreditors"]:
                x["accreditors"].append(a["by"])
    for f in fac["facilities"]:
        if not f.get("iso2"):
            continue
        x = row(f["iso2"])
        x["facilities"] += 1
        if f["curated"]:
            x["curated_facilities"] += 1
    for p in prices["prices"]:
        x = row(p["country"])
        x["prices"] += 1
        if p.get("procedure") and p["procedure"] not in x["procedures"]:
            x["procedures"].append(p["procedure"])
    for lg in legality["rows"]:
        row(lg["country"])["legality_rows"] += 1
    for key, ind in ((wb or {}).get("indicators") or {}).items():
        for iso, v in ind["values"].items():
            if iso in rows:
                rows[iso]["indicators"][key] = {"value": v["value"], "year": v["year"]}
    return {"built": time.strftime("%Y-%m-%d"), "count": len(rows),
            "indicator_meta": {k: {kk: ind.get(kk) for kk in ("code", "name", "unit", "source", "license",
                                                              "url", "fetched_at", "countries", "publisher_title")}
                               for k, ind in (((wb or {}).get("indicators") or {}).items())},
            "note": "Joined on ISO 3166-1 alpha-2. A country with no row is a country nothing here touches yet.",
            "countries": dict(sorted(rows.items()))}


# ------------------------------------------------------------------ search

def search_doc(r: dict) -> dict:
    n = r["names"]
    et = r.get("etymology") or {}
    return {
        "id": r["id"], "type": r["type"], "name": n["name"],
        "names": " ".join([n["name"]] + n.get("aliases", []) + [n.get("said", "")]),
        "terms": " ".join([r["type"]] + [t.get("name", "") for t in r["region_terms"]] +
                          [tf["label"] for tf in r.get("tag_facts", [])] +
                          [rf["label"] for rf in r.get("recognition_facts", [])] +
                          [str(v) if not isinstance(v, list) else " ".join(map(str, v))
                           for v in (r.get("facets") or {}).values()] +
                          [k["name"] for k in r["kin_out"]] +
                          [(r.get("address") or {}).get(k, "") for k in ("city", "area", "country")]),
        "text": " ".join([r["text"].get(k, "") for k in ("what", "story", "how", "today", "notes")] +
                         [et.get("root", ""), et.get("note", "")] +
                         [c["tell"] for c in r.get("confusable_with", [])]),
        "blurb": r["blurb"], "country": (r.get("facets") or {}).get("iso2") or (r.get("address") or {}).get("country") or "",
    }


def mine_thesaurus(recs: list[dict]) -> int:
    groups = []
    for r in recs:
        n = r["names"]
        g = sorted({x.lower().strip() for x in [n["name"]] + n.get("aliases", []) if x and len(x.split()) <= 5})
        if len(g) >= 2:
            groups.append(g)
    # the same operation under four names, which is how a reader arrives
    groups += [
        ["medical travel", "medical tourism", "health tourism", "cross-border care", "patient mobility"],
        ["knee replacement", "total knee arthroplasty", "tka", "knee arthroplasty"],
        ["hip replacement", "total hip arthroplasty", "tha", "hip arthroplasty"],
        ["ivf", "in vitro fertilisation", "in vitro fertilization", "fertility treatment"],
        ["gastric sleeve", "sleeve gastrectomy", "bariatric surgery", "weight loss surgery"],
        ["dental implant", "implant", "tooth implant"],
        ["hair transplant", "fue", "follicular unit extraction", "hair restoration"],
        ["lasik", "laser eye surgery", "refractive surgery"],
        ["heart bypass", "cabg", "coronary artery bypass graft", "bypass surgery"],
        ["facilitator", "medical travel agent", "broker", "patient coordinator"],
        ["package price", "bundled price", "all-inclusive price", "case rate"],
        ["accreditation", "jci", "joint commission international"],
    ]
    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    jdump({"note": "mined by build.py from data/nodes names + aliases — synonymy only", "groups": groups},
          SEARCH_DIR / "care.thesaurus.json", indent=0)
    return len(groups)


# ------------------------------------------------------------------ coverage

def coverage(recs: list[dict], osm: dict | None, sources: dict, prices: dict,
             legality: dict, wb: dict | None, fac: dict) -> dict:
    by_type = {t: sum(1 for r in recs if r["type"] == t) for t in TYPES}
    isos = sorted({(r.get("facets") or {}).get("iso2") or (r.get("address") or {}).get("country")
                   for r in recs} - {None, ""})
    return {
        "built": time.strftime("%Y-%m-%d"),
        "scope": ("People who leave their own country to be treated, and the machinery around "
                  "them: the procedures, the hospitals, the prices, the rules, the accreditors "
                  "and the risks. Inbound and outbound both — the countries people leave are "
                  "half the subject."),
        "records": by_type,
        "countries_touched": len(isos),
        "countries": isos,
        "how_records_are_made": ("Hand-written JSON, one per node, each field carrying a "
                                 "provenance tier (cited / harvested / tradition / inference / "
                                 "field). Cited fields name a source in sources.json."),
        "prices": {
            "rows": prices["count"],
            "with_usd": sum(1 for p in prices["prices"] if p["usd"] is not None),
            "rate_date": prices["rate_date"],
            "kinds": {k: sum(1 for p in prices["prices"] if p["kind"] == k)
                      for k in sorted({p["kind"] for p in prices["prices"]})},
            "oldest": min((p["as_of"] for p in prices["prices"]), default=""),
            "newest": max((p["as_of"] for p in prices["prices"]), default=""),
            "reading_an_absence": ("A procedure with no price here is one nobody has published a "
                                   "figure for where this project could read it. It is not a free "
                                   "procedure and not a rare one."),
        },
        "legality": {
            "rows": legality["count"], "subjects": len(legality["subjects"]),
            "countries": len(legality["countries"]),
            "reading_an_absence": ("A blank cell is 'nobody here has read that law', which is a "
                                   "fact about this project. Statutes change between a reading "
                                   "and a reader."),
        },
        "facilities": {
            "written_up": by_type["facility"],
            "harvested_from_osm": (osm or {}).get("count", 0),
            "osm_fetched_at": (osm or {}).get("fetched_at"),
            "hubs_queried": len((osm or {}).get("hubs", {})),
            "reading_an_absence": ("A hospital missing here is missing from OpenStreetMap on the "
                                   "fetch date, outside the radius queried, or not yet written up."),
            "osm_query": (osm or {}).get("query"),
        },
        "indicators": {k: {"code": v["code"], "unit": v["unit"], "countries": v["countries"],
                           "fetched_at": v["fetched_at"], "newest_year": max(v["years"]) if v.get("years") else None}
                       for k, v in (((wb or {}).get("indicators") or {}).items())},
        "images": {"count": sum(len(r.get("images", [])) for r in recs),
                   "licences_accepted": ["CC0", "Public domain", "CC BY", "CC BY-SA", "FAL"]},
        "tags": {k: sum(1 for r in recs for t in r.get("tags", []) if t["tag"] == k) for k in TAGS},
        "recognitions": sum(len(r.get("recognitions", [])) for r in recs),
        "sources": len(sources),
        "not_yet": [
            "field observations — no record carries the field tier",
            "most of the world's hospitals; the written-up ones are a sample, not a census",
            "outcome data per unit outside the few registries that publish it",
            "complication and revision rates for work done abroad, which almost nobody counts",
            "prices in most countries, because most hospitals publish none",
            "photographs for most records",
        ],
        "tiers": TIER_LABEL,
    }


def main() -> int:
    if validate_all(quiet=False) != 0:
        print("build refused: fix the errors above")
        return 1
    t0 = time.time()
    sources = merge_sources()
    regions = {e["key"]: e for e in load_vocab("regions").get("entries", [])}
    raw = load_nodes()
    by_id = {r["id"]: r for r in raw}
    recs = [enrich(r, by_id, sources, regions) for r in raw]
    backlinks(recs)
    osm = load_harvest("osm-facilities")
    wb = load_harvest("worldbank")
    rates = load_harvest("rates")
    prices = price_rows(recs, rates)
    # put the computed dollar figure back on the record, so a page never converts twice
    usd = {p["key"]: p for p in prices["prices"]}
    for r in recs:
        for i, p in enumerate(r.get("prices", [])):
            row = usd.get(f'{r["id"]}#{i}')
            if row:
                p["usd"] = row["usd"]
                p["usd_high"] = row["usd_high"]
                p["rate_date"] = row["rate_date"]
    leg = legality_matrix(recs)
    fac = facilities_table(recs, osm)
    countries = countries_table(recs, wb, prices, fac, leg)
    for r in recs:
        jdump(r, API / r["type"] / f"{r['id']}.json")
    jdump({"built": time.strftime("%Y-%m-%d"), "count": len(recs), "nodes": recs}, API / "nodes.json")
    jdump({"built": time.strftime("%Y-%m-%d"), "count": len(recs), "nodes": [{
        "id": r["id"], "type": r["type"], "name": r["names"]["name"], "aliases": r["names"].get("aliases", []),
        "region": r["region"], "facets": r.get("facets", {}),
        "country": (r.get("facets") or {}).get("iso2") or (r.get("address") or {}).get("country"),
        "blurb": r["blurb"], "image": (r["primary_image"] or {}).get("file"), "confidence": r["confidence"],
        "tags": sorted({t["tag"] for t in r.get("tags", [])}), "acclaim": r.get("acclaim", 0),
        "prices": len(r.get("prices", [])), "legality": len(r.get("legality", [])),
        "needs_verification": r.get("needs_verification", False), "updated": r["updated"],
        "url": f"{PATH_OF[r['type']]}/{r['id']}/",
    } for r in recs]}, API / "index.json")
    jdump({"built": time.strftime("%Y-%m-%d"),
           "edges": [dict(k, **{"from": r["id"]}) for r in recs for k in r["kin_out"]]}, API / "kin.json")
    for a in ("regions", "types", "facets", "tags", "recognizers", "markets"):
        jdump(load_vocab(a), API / "vocab" / f"{a}.json")
    jdump(jload(SOURCES), API / "sources.json")
    jdump(prices, API / "prices.json")
    jdump(leg, API / "legality.json")
    jdump(fac, API / "facilities.json")
    jdump(countries, API / "countries.json")
    jdump(coverage(recs, osm, sources, prices, leg, wb, fac), API / "coverage.json")
    docs = [search_doc(r) for r in recs]
    jdump({"built": time.strftime("%Y-%m-%dT%H:%M:%S"), "docs": docs}, BUILD / "searchdocs.json")
    ng = mine_thesaurus(recs)
    edges = sum(len(r["kin_out"]) for r in recs)
    print(f"built {len(recs)} nodes · {edges} kin edges · {prices['count']} prices · "
          f"{leg['count']} legality rows · {fac['curated']} + {fac['harvested']} facilities · "
          f"{countries['count']} countries · thesaurus {ng} groups · {time.time()-t0:.1f}s")
    return 0


PATH_OF = {"destination": "country", "hub": "city", "procedure": "procedure", "facility": "hospital",
           "pathway": "step", "risk": "risk", "rule": "rule", "org": "org", "person": "person",
           "event": "event", "term": "word", "dataset": "dataset", "story": "story"}


if __name__ == "__main__":
    sys.exit(main())
