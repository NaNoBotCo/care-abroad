#!/usr/bin/env python3
"""validate.py — every record must pass before anything is built.

Checks, in order:
  1. schema/node.schema.json (structure, enums, patterns)
  2. id == filename; type == folder; ids unique across all types
  3. kin targets and confusable_with targets exist
  4. every source id exists in data/sources/sources.json (record, etymology, prices,
     legality, metrics, tags, recognitions)
  5. region keys — WARN only (open list); facet values — WARN only (open list)
  6. every image licence is on the free-to-use allowlist and its file exists
  7. provenance.fields paths point at real fields
  8. country codes are ISO 3166-1 alpha-2 and appear in data/geo/countries.json
  9. a price carries a currency, a date and a source; a legality row carries an
     instrument date and a source
 10. banned words in reader-facing text (fleet rule) — ERROR

Exit 1 on any error. Warnings never fail the build; they are printed.

    python3 tools/validate.py            # all records
    python3 tools/validate.py --strict   # warnings fail too
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GEO, IMAGES, SCHEMA, jload, load_nodes, load_sources, load_vocab, validate_record  # noqa: E402

FREE_LICENSES = re.compile(
    r"^(CC0(\s*1\.0)?|Public domain|PD(-[A-Za-z0-9-]+)?|CC[- ]BY(-SA)?(\s*[1-4]\.[0-9])?|FAL(\s*1\.[0-9])?"
    r"|No known copyright restrictions|NoC-US|United States Government Work)$", re.I)

DRAFT = bool(os.environ.get("BUILD_DRAFT"))

# Two lists, both hard errors, both escapable the same way: put the words in quotation
# marks and name who said them.
#
# The first is the fleet list. "Tourist" sits on it, which collides with the field's own
# name for itself — so this site writes medical travel and cross-border care, and the
# phrase "medical tourism" appears in quotation marks, attributed, or on the word's own
# page where the fight over it is the subject.
#
# The second is what this subject attracts: the brochure adjectives, the savings claim
# with no date on it, and the second-person advice. A directory that tells a reader what
# to do about their hip has become a clinic, and it is not one.
BANNED = re.compile(
    r"\b(load[- ]bearing|honest(ly|y)?|authentic(ity|ally)?|inauthentic|purist|tourist(s|y)?"
    r"|the real thing|sacrile\w+)\b", re.I)
PUFF = re.compile(
    r"\b(world[- ]class|state[- ]of[- ]the[- ]art|cutting[- ]edge|top[- ]rated|award[- ]winning"
    r"|best hospital|finest|premier destination|risk[- ]free|pain[- ]free|hassle[- ]free"
    r"|life[- ]changing|miracle|breakthrough treatment|guaranteed results?"
    r"|save up to|savings of up to|up to \d+ ?% (?:cheaper|less|savings)"
    r"|we recommend|you should (?:choose|book|go|travel|have)|your best (?:option|bet)"
    r"|don'?t worry|rest assured|peace of mind)\b", re.I)


_ABSENT = object()


def _get(rec: dict, dotted: str):
    """The value at a dotted path, or _ABSENT when the path names a key the record does
    not have. A key that exists and holds null returns null: annotating a null field to
    say WHY it is null is the point of the provenance block, not a mistake."""
    node = rec
    for part in dotted.split("."):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$", part)
        if not m:
            return _ABSENT
        key, idx = m.group(1), m.group(2)
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return _ABSENT
        if idx is not None:
            if isinstance(node, list) and int(idx) < len(node):
                node = node[int(idx)]
            else:
                return _ABSENT
    return node


def text_fields(rec: dict):
    for k, v in (rec.get("text") or {}).items():
        yield f"text.{k}", v
    for i, k in enumerate(rec.get("kin") or []):
        yield f"kin[{i}].as", k.get("as", "")
    for i, c in enumerate(rec.get("confusable_with") or []):
        yield f"confusable_with[{i}].tell", c.get("tell", "")
    e = rec.get("etymology") or {}
    for k in ("root", "note"):
        if e.get(k):
            yield f"etymology.{k}", e[k]
    for i, sec in enumerate(rec.get("sections") or []):
        yield f"sections[{i}].h", sec.get("h", "")
        yield f"sections[{i}].text", sec.get("text", "")
    for i, tg in enumerate(rec.get("tags") or []):
        yield f"tags[{i}].note", tg.get("note", "")
    for i, rg in enumerate(rec.get("recognitions") or []):
        yield f"recognitions[{i}].what", (rg.get("what", "") + " " + rg.get("note", ""))
    for i, pr in enumerate(rec.get("prices") or []):
        yield f"prices[{i}].note", pr.get("note", "")
    for i, lg in enumerate(rec.get("legality") or []):
        yield f"legality[{i}]", (lg.get("conditions", "") + " " + lg.get("note", ""))
    d = rec.get("dataset") or {}
    for k in ("counts", "does_not_count"):
        if d.get(k):
            yield f"dataset.{k}", d[k]
    m = rec.get("metrics") or {}
    if m.get("note"):
        yield "metrics.note", m["note"]


ISO2 = re.compile(r"^[A-Z]{2}$")
CUR = re.compile(r"^[A-Z]{3}$")
DATEISH = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def validate_all(strict=False, quiet=False) -> int:
    schema = jload(SCHEMA)
    recs = load_nodes()
    sources = load_sources()
    regions = {e["key"] for e in load_vocab("regions").get("entries", [])}
    facets = load_vocab("facets").get("facets", {})
    tagkeys = {e["key"] for e in load_vocab("tags").get("entries", [])}
    recog = {e["key"] for e in load_vocab("recognizers").get("entries", [])}
    gp = GEO / "countries.json"
    known_iso = {c["iso"] for c in jload(gp)["countries"]} if gp.exists() else set()
    ids: dict[str, str] = {}
    types_by_id: dict[str, str] = {}
    errors: list[str] = []
    warns: list[str] = []
    for r in recs:
        tag = f"{r.get('type','?')}/{r.get('id','?')}"
        if r.get("id") in ids:
            errors.append(f"{tag}: duplicate id (also {ids[r['id']]})")
        ids[r.get("id", "")] = tag
        types_by_id[r.get("id", "")] = r.get("type", "")

    def check_iso(tag, where, code):
        if not ISO2.match(code or ""):
            errors.append(f"{tag}: {where} {code!r} is not an ISO 3166-1 alpha-2 code")
        elif known_iso and code not in known_iso:
            warns.append(f"{tag}: {where} {code} is not in data/geo/countries.json — it will not colour on a map")

    for r in recs:
        tag = f"{r['type']}/{r['id']}" if "type" in r and "id" in r else r["_path"]
        for e in validate_record(r, schema):
            errors.append(f"{tag}: {e}")
        if Path(r["_path"]).stem != r.get("id"):
            errors.append(f"{tag}: filename {Path(r['_path']).name} != id")
        if r.get("type") != r["_dir_type"]:
            errors.append(f"{tag}: type {r.get('type')!r} but the file sits in data/nodes/{r['_dir_type']}/")
        for k in r.get("kin", []):
            if k["to"] not in ids:
                (warns if DRAFT else errors).append(f"{tag}: kin target {k['to']} not found")
            if k["to"] == r.get("id"):
                errors.append(f"{tag}: kin points at itself")
        for c in r.get("confusable_with", []):
            if c["id"] not in ids:
                (warns if DRAFT else errors).append(f"{tag}: confusable_with {c['id']} not found")
        for s in r.get("sources", []):
            if s not in sources:
                (warns if DRAFT else errors).append(f"{tag}: source {s} not in sources.json")
        prov = r.get("provenance", {})
        for where, p in [("default", prov.get("default", {}))] + list(prov.get("fields", {}).items()):
            if p.get("source") and p["source"] not in sources:
                (warns if DRAFT else errors).append(
                    f"{tag}: provenance {where} cites {p['source']} which is not in sources.json")
            if p.get("tier") == "cited" and not p.get("source") and not r.get("sources"):
                warns.append(f"{tag}: provenance {where} is 'cited' but names no source")
        et = r.get("etymology") or {}
        if et.get("source") and et["source"] not in sources:
            (warns if DRAFT else errors).append(
                f"{tag}: etymology cites {et['source']} which is not in sources.json")
        if r.get("type") == "term" and not et.get("root"):
            warns.append(f"{tag}: a word with no etymology.root")
        for reg in r.get("region", []):
            if reg not in regions:
                warns.append(f"{tag}: region {reg} not in regions.json (open list — add it there)")
        for fk, fv in (r.get("facets") or {}).items():
            if fk == "iso2":
                check_iso(tag, "facets.iso2", fv if isinstance(fv, str) else "")
                continue
            if fk == "radius_km":
                continue
            spec = facets.get(fk)
            if not spec:
                warns.append(f"{tag}: facet {fk} not in facets.json (open list — add it there)")
                continue
            if r["type"] not in spec["types"]:
                warns.append(f"{tag}: facet {fk} is not listed for type {r['type']}")
            vals = fv if isinstance(fv, list) else [fv]
            for v in vals:
                if spec["values"] and v not in spec["values"]:
                    warns.append(f"{tag}: facet {fk}={v!r} not among known values")
        a = r.get("address") or {}
        if a.get("country"):
            check_iso(tag, "address.country", a["country"])
        # ---- prices
        for i, pr in enumerate(r.get("prices", [])):
            if pr["source"] not in sources:
                errors.append(f"{tag}: prices[{i}] source {pr['source']} not in sources.json")
            check_iso(tag, f"prices[{i}].country", pr.get("country", ""))
            if not CUR.match(pr.get("currency", "")):
                errors.append(f"{tag}: prices[{i}] currency {pr.get('currency')!r} is not an ISO 4217 code")
            if not DATEISH.match(str(pr.get("as_of", ""))):
                errors.append(f"{tag}: prices[{i}] as_of {pr.get('as_of')!r} is not a date — a price without its date is not a price")
            if pr.get("procedure") and pr["procedure"] not in ids:
                (warns if DRAFT else errors).append(f"{tag}: prices[{i}] names procedure {pr['procedure']}, which has no record")
            elif pr.get("procedure") and types_by_id.get(pr["procedure"]) != "procedure":
                errors.append(f"{tag}: prices[{i}] procedure {pr['procedure']} is a {types_by_id.get(pr['procedure'])} record")
            if pr.get("facility") and pr["facility"] not in ids:
                (warns if DRAFT else errors).append(f"{tag}: prices[{i}] names facility {pr['facility']}, which has no record")
            if pr.get("amount") is None and pr.get("amount_high") is None:
                errors.append(f"{tag}: prices[{i}] has no amount")
            if pr.get("amount_high") is not None and pr.get("amount") is not None and pr["amount_high"] < pr["amount"]:
                errors.append(f"{tag}: prices[{i}] range runs backwards")
            if pr.get("usd") is not None:
                warns.append(f"{tag}: prices[{i}] carries a usd figure; tools/build.py computes that from the dated rate table and will overwrite it")
        # ---- legality
        for i, lg in enumerate(r.get("legality", [])):
            if lg["source"] not in sources:
                errors.append(f"{tag}: legality[{i}] source {lg['source']} not in sources.json")
            check_iso(tag, f"legality[{i}].country", lg.get("country", ""))
            if not DATEISH.match(str(lg.get("as_of", ""))):
                errors.append(f"{tag}: legality[{i}] as_of {lg.get('as_of')!r} is not a date — law moves, and an undated row cannot be read")
            if lg.get("status") in ("lawful-with-conditions", "residents-only") and not lg.get("conditions"):
                warns.append(f"{tag}: legality[{i}] is {lg['status']} but names no condition")
            if lg.get("status") not in ("no-data", "unregulated") and not lg.get("instrument"):
                warns.append(f"{tag}: legality[{i}] names no instrument")
        # ---- metrics
        m = r.get("metrics") or {}
        if m:
            if m.get("source") and m["source"] not in sources:
                errors.append(f"{tag}: metrics.source {m['source']} not in sources.json")
            if any(v is not None for k, v in m.items() if k not in ("note", "as_of", "source", "url")) and not m.get("as_of"):
                warns.append(f"{tag}: metrics carries numbers but no as_of")
        # ---- dataset
        if r["type"] == "dataset":
            d = r.get("dataset") or {}
            for k in ("publisher", "unit", "counts", "does_not_count"):
                if not d.get(k):
                    warns.append(f"{tag}: dataset.{k} is empty — the point of a dataset record is that sentence")
        for i, tg in enumerate(r.get("tags", [])):
            if tg["tag"] not in tagkeys:
                errors.append(f"{tag}: tags[{i}] {tg['tag']!r} not in tags.json")
            if tg["source"] not in sources:
                errors.append(f"{tag}: tags[{i}] source {tg['source']} not in sources.json")
            if tg.get("tier") in ("tradition", "inference"):
                errors.append(f"{tag}: tags[{i}] {tg['tag']} cannot be tier {tg['tier']} — a tag a reader may travel on is cited, harvested or field")
        for i, rg in enumerate(r.get("recognitions", [])):
            if rg["by"] not in recog:
                errors.append(f"{tag}: recognitions[{i}] by {rg['by']!r} not in recognizers.json")
            if rg["source"] not in sources:
                errors.append(f"{tag}: recognitions[{i}] source {rg['source']} not in sources.json")
        for i, im in enumerate(r.get("images", [])):
            if not FREE_LICENSES.match(im["license"].strip()):
                errors.append(f"{tag}: images[{i}] licence {im['license']!r} is not on the free-to-use allowlist")
            if not (IMAGES / im["file"]).exists():
                warns.append(f"{tag}: images[{i}] file missing: {im['file']}")
        for path in prov.get("fields", {}):
            if _get(r, path) is _ABSENT:
                warns.append(f"{tag}: provenance.fields.{path} names a field the record does not have")
        for fname, txt in text_fields(r):
            clean = txt or ""
            # a quotation keeps its speaker's words, and a proper noun is named what it is
            # named: put either in quotation marks
            clean = re.sub(r'[“"][^”"]{0,400}[”"]', "X", clean)
            for noun in ("Medical Tourism Association", "International Medical Travel Journal",
                         "Medical Tourism Index", "Global Wellness Institute"):
                clean = clean.replace(noun, "X")
            m2 = BANNED.search(clean)
            if m2:
                errors.append(f"{tag}: {fname} uses the banned word {m2.group(0)!r}")
            m3 = PUFF.search(clean)
            if m3:
                errors.append(f"{tag}: {fname} uses brochure or advice language: {m3.group(0)!r}")
        if r.get("type") in ("facility", "hub", "event") and not r.get("geo"):
            warns.append(f"{tag}: no geo (it will not show on a map)")
        if not r.get("sources") and prov.get("default", {}).get("tier") in ("cited", "harvested"):
            warns.append(f"{tag}: tier {prov['default']['tier']} but sources is empty")
    if not quiet:
        for w in warns:
            print("warn ", w)
        for e in errors:
            print("ERROR", e)
        print(f"{len(recs)} records · {len(errors)} errors · {len(warns)} warnings")
    if errors or (strict and warns):
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    sys.exit(validate_all(ap.parse_args().strict))
