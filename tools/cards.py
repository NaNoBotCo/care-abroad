#!/usr/bin/env python3
"""cards.py — the picture that shows when a page is shared.

One 1200x630 card per record and per standing page, drawn with Pillow. Masters live in
cards/ and are copied into the site by site.py, which points og:image at a card only
when its file exists — an og:image that 404s unfurls worse than none at all.

There are no photographs in this project, so a card is a small chart. Each says what
kind of thing the page is, names it, and shows the one fact that makes it worth a click:

    destination  the world map with that country lit, and its health spending per head
    hub          the same map, lit at the point, with what the cluster is known for
    facility     the map, the beds, the accreditors' initials
    procedure    the published prices as a strip, cheapest to dearest
    rule         the legality row: how many jurisdictions read, and how they came out
    risk         the kind of risk, and any published rate
    dataset      the unit, and the first line of what it does not count
    term         the root of the word
    pathway      where in the journey it sits
    story        the lede

    python3 tools/cards.py              # every card that is missing or out of date
    python3 tools/cards.py --all        # redraw everything
    python3 tools/cards.py procedure/knee-replacement index prices
"""
from __future__ import annotations

import math
import sys
import textwrap
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    print("cards.py needs Pillow (pip3 install pillow) — skipping")
    raise SystemExit(0)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, GEO, ROOT, jload  # noqa: E402
import worldmap  # noqa: E402

CARDS = ROOT / "cards"
W, H = 1200, 630
PAD = 62

# The site's dark ground: a card is read at thumbnail size in a feed, and the blue the
# charts use burns brightest against it.
INK = (16, 18, 21)
INK_2 = (25, 28, 32)
PAPER = (238, 241, 244)
MUTE = (150, 160, 172)
BLUE = (57, 135, 229)
EMBER = (217, 89, 38)
AQUA = (25, 158, 112)
WARN = (250, 178, 25)
CRIT = (208, 59, 59)
LINE = (43, 48, 55)
CHIP = (34, 38, 43)

SANS_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
SERIF = "/System/Library/Fonts/Supplemental/Georgia.ttf"

TYPE_LABEL = {"destination": "A COUNTRY", "hub": "A CLUSTER", "procedure": "A PROCEDURE",
              "facility": "A HOSPITAL", "pathway": "A STEP", "risk": "A RISK", "rule": "A RULE",
              "org": "AN ORGANIZATION", "person": "A PERSON", "event": "AN EVENT",
              "term": "A WORD", "dataset": "A SERIES", "story": "A LONG ONE"}
SITE_MARK = "CARE ABROAD"

LEGAL_COLOR = {"lawful": (12, 163, 12), "lawful-with-conditions": WARN,
               "residents-only": (236, 131, 90), "unlawful": CRIT,
               "unregulated": (138, 138, 132), "no-data": LINE}


def font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def FB(sz):
    return font(SANS_B, sz)


def FR(sz):
    return font(SANS, sz)


def FS(sz):
    return font(SERIF, sz)


def fit_text(d, text, fnt_for, max_w, max_lines, start, floor):
    """Shrink until the name fits in the box; a card that clips a hospital's name is
    worse than one that sets it two points smaller."""
    size = start
    while size >= floor:
        f = fnt_for(size)
        avg = max(1, d.textlength("nn", font=f) / 2)
        lines = textwrap.wrap(text, width=max(8, int(max_w / avg)))
        if len(lines) <= max_lines and all(d.textlength(x, font=f) <= max_w for x in lines):
            return f, lines
        size -= 3
    f = fnt_for(floor)
    return f, textwrap.wrap(text, width=max(8, int(max_w / max(1, d.textlength("nn", font=f) / 2))))[:max_lines]


def draw_lines(d, x, y, lines, fnt, fill, leading=1.15):
    asc = fnt.size
    for i, ln in enumerate(lines):
        d.text((x, y + i * asc * leading), ln, font=fnt, fill=fill)
    return y + len(lines) * asc * leading


def chip(d, x, y, text, fnt, fg=PAPER, bg=CHIP, border=LINE):
    w = d.textlength(text, font=fnt) + 26
    h = fnt.size + 16
    d.rounded_rectangle([x, y, x + w, y + h], radius=h / 2, fill=bg, outline=border, width=2)
    d.text((x + 13, y + 8), text, font=fnt, fill=fg)
    return x + w + 10


def base_card():
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 6], fill=BLUE)
    return img, d


def footer(d, right=""):
    d.line([(PAD, H - 86), (W - PAD, H - 86)], fill=LINE, width=2)
    d.text((PAD, H - 66), SITE_MARK, font=FB(24), fill=BLUE)
    if right:
        f = FR(21)
        d.text((W - PAD - d.textlength(right, font=f), H - 64), right, font=f, fill=MUTE)


def eyebrow(d, text, y=PAD):
    f = FB(21)
    t = " ".join(text.upper())
    d.text((PAD, y), t, font=f, fill=MUTE)
    return y + 44


# ------------------------------------------------------------------ the panels

_GEO = None


def geo():
    global _GEO
    if _GEO is None:
        _GEO = jload(GEO / "countries.json")
    return _GEO


def mini_map(size=(470, 268), lit: set | None = None, dot=None):
    """The world in Equal Earth, with a country filled or a point marked — the same
    projection the site's own maps use, so a card and a page agree."""
    w, h = size
    img = Image.new("RGB", (w, h), INK_2)
    d = ImageDraw.Draw(img)
    g = geo()
    fit = worldmap.fit_world(g, w, pad=6)
    dy = (h - fit["h"]) / 2
    for iso, name, path in worldmap.country_paths(g, fit):
        if iso in ("AQ", "HM", "GS", "BV", "TF"):     # cropped off the bottom of the frame
            continue
        for sub in path.split("M")[1:]:
            pts = []
            for pair in sub.rstrip("Z").split("L"):
                try:
                    x, y = pair.strip().split(" ")
                    pts.append((float(x), float(y) + dy))
                except ValueError:
                    continue
            if len(pts) < 3 or all(y < 0 or y > h for _, y in pts):
                continue
            on = lit and iso in lit
            d.polygon(pts, fill=BLUE if on else (48, 54, 62), outline=BLUE if on else (62, 69, 78))
    if dot:
        x, y = worldmap.project(dot[1], dot[0], fit)
        y += dy
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=EMBER, outline=PAPER, width=3)
    return img


def price_strip(prices: list, size=(470, 200)):
    """The published prices for one procedure, cheapest to dearest, on a log axis."""
    w, h = size
    img = Image.new("RGB", (w, h), INK_2)
    d = ImageDraw.Draw(img)
    vals = [p["usd"] for p in prices if p.get("usd")]
    if not vals:
        return None
    lo, hi = max(1.0, min(vals) * 0.8), max(vals) * 1.2
    pad = 34
    def X(v):
        return pad + (w - 2 * pad) * (math.log10(v) - math.log10(lo)) / max(1e-9, math.log10(hi) - math.log10(lo))
    y = h / 2
    d.line([(pad, y), (w - pad, y)], fill=LINE, width=3)
    for p in prices:
        if not p.get("usd"):
            continue
        x = X(p["usd"])
        col = {"package": BLUE, "tariff": AQUA, "reimbursement": AQUA}.get(p.get("kind"), EMBER)
        d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=col, outline=INK_2, width=2)
    f = FB(22)
    d.text((pad, y + 26), f"${min(vals):,.0f}", font=f, fill=PAPER)
    t = f"${max(vals):,.0f}"
    d.text((w - pad - d.textlength(t, font=f), y + 26), t, font=f, fill=PAPER)
    d.text((pad, y - 52), f"{len(vals)} published prices", font=FR(20), fill=MUTE)
    return img


def legality_strip(rows: list, size=(470, 210)):
    """A rule's readings as a block of cells — the shape of the grid, at card size."""
    w, h = size
    img = Image.new("RGB", (w, h), INK_2)
    d = ImageDraw.Draw(img)
    n = len(rows)
    if not n:
        return None
    cols = min(10, max(4, int(math.ceil(math.sqrt(n * 1.8)))))
    cw = (w - 40) / cols
    ch = min(38, (h - 70) / max(1, math.ceil(n / cols)))
    for i, r in enumerate(rows):
        cx, cy = 20 + (i % cols) * cw, 20 + (i // cols) * ch
        d.rounded_rectangle([cx + 2, cy + 2, cx + cw - 4, cy + ch - 4], radius=5,
                            fill=LEGAL_COLOR.get(r["status"], LINE))
    counts: dict = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    txt = " · ".join(f"{v} {k.replace('-', ' ')}" for k, v in
                     sorted(counts.items(), key=lambda kv: -kv[1])[:3])
    d.text((20, h - 40), txt[:56], font=FR(19), fill=MUTE)
    return img


# ------------------------------------------------------------------ cards

def record_card(rec: dict, ctx: dict) -> Image.Image:
    img, d = base_card()
    t = rec["type"]
    f = rec.get("facets") or {}
    iso = f.get("iso2") or (rec.get("address") or {}).get("country")
    y = eyebrow(d, TYPE_LABEL.get(t, t) + (f"  ·  {ctx['iso_name'].get(iso, iso)}" if iso else ""))
    panel_w = 470
    text_w = W - 2 * PAD - panel_w - 40
    fnt, lines = fit_text(d, rec["names"]["name"], FB, text_w, 3, 68, 34)
    y = draw_lines(d, PAD, y, lines, fnt, PAPER) + 14
    blurb = rec["blurb"]
    bf, blines = fit_text(d, blurb, FS, text_w, 5, 26, 20)
    y = draw_lines(d, PAD, y, blines[:5], bf, MUTE, leading=1.35) + 18

    panel = None
    if t == "procedure" and ctx["prices_by_proc"].get(rec["id"]):
        panel = price_strip(ctx["prices_by_proc"][rec["id"]])
    elif t == "rule" and rec.get("legality"):
        panel = legality_strip(rec["legality"])
    elif rec.get("geo"):
        panel = mini_map(lit={iso} if iso else None, dot=(rec["geo"]["lat"], rec["geo"]["lon"]))
    elif iso:
        panel = mini_map(lit={iso})
    if panel is not None:
        img.paste(panel, (W - PAD - panel.width, 132))

    # the chip row: one or two facts, chosen by type
    chips = []
    if t == "destination" and iso:
        ind = (ctx["countries"].get(iso) or {}).get("indicators", {})
        if "spend_pc" in ind:
            chips.append(f'${ind["spend_pc"]["value"]:,.0f} a head on health · {ind["spend_pc"]["year"]}')
        n = (ctx["countries"].get(iso) or {}).get("curated_facilities", 0)
        if n:
            chips.append(f'{n} hospitals written up')
    elif t == "facility":
        m = rec.get("metrics") or {}
        if m.get("beds"):
            chips.append(f'{m["beds"]:,} beds')
        acc = [a["by"].upper() for a in rec.get("recognitions", [])][:3]
        if acc:
            chips.append(" · ".join(acc))
    elif t == "procedure":
        m = rec.get("metrics") or {}
        if m.get("stay_days"):
            chips.append(f'{m["stay_days"]:g} nights')
        if m.get("days_before_flying"):
            chips.append(f'{m["days_before_flying"]:g} days before flying')
    elif t == "rule" and rec.get("legality"):
        chips.append(f'{len(rec["legality"])} jurisdictions read')
    elif t == "dataset":
        ds = rec.get("dataset") or {}
        if ds.get("unit"):
            chips.append(ds["unit"][:44])
        if ds.get("countries"):
            chips.append(f'{ds["countries"]} countries')
    elif t == "term" and (rec.get("etymology") or {}).get("root"):
        chips.append((rec["etymology"]["root"])[:52])
    elif t == "pathway" and f.get("stage"):
        chips.append(f["stage"].replace("-", " "))
    elif t == "risk" and f.get("kind"):
        chips.append(f["kind"])
    x = PAD
    cf = FB(20)
    for c in chips[:2]:
        x = chip(d, x, min(y, H - 168), c, cf, border=BLUE)
    footer(d, ctx["host"])
    return img


def page_card(title: str, lede: str, eyebrow_text: str, ctx: dict, panel=None,
              stats: list | None = None) -> Image.Image:
    img, d = base_card()
    y = eyebrow(d, eyebrow_text)
    text_w = W - 2 * PAD - (490 if panel is not None else 0)
    fnt, lines = fit_text(d, title, FB, text_w, 2, 76, 40)
    y = draw_lines(d, PAD, y, lines, fnt, PAPER) + 16
    bf, blines = fit_text(d, lede, FS, text_w, 5, 27, 21)
    y = draw_lines(d, PAD, y, blines[:5], bf, MUTE, leading=1.35) + 20
    if panel is not None:
        img.paste(panel, (W - PAD - panel.width, 140))
    if stats:
        x = PAD
        for n, lab in stats[:3]:
            d.text((x, H - 210), str(n), font=FB(56), fill=BLUE)
            d.text((x, H - 144), lab.upper(), font=FB(19), fill=MUTE)
            x += max(200, d.textlength(lab.upper(), font=FB(19)) + 52)
    footer(d, ctx["host"])
    return img


def main(argv: list[str]) -> int:
    api = BUILD / "api"
    if not (api / "nodes.json").exists():
        print("run tools/build.py first")
        return 1
    CARDS.mkdir(exist_ok=True)
    force = "--all" in argv
    want = [a for a in argv if not a.startswith("-")]
    recs = jload(api / "nodes.json")["nodes"]
    countries = jload(api / "countries.json")["countries"]
    prices = jload(api / "prices.json")
    cov = jload(api / "coverage.json")
    legality = jload(api / "legality.json")
    facilities = jload(api / "facilities.json")
    by_proc: dict = {}
    for p in prices["prices"]:
        if p.get("procedure"):
            by_proc.setdefault(p["procedure"], []).append(p)
    ctx = {"countries": countries, "prices_by_proc": by_proc,
           "iso_name": {c["iso"]: c["name"] for c in jload(GEO / "countries.json")["countries"]},
           "host": "nanobotco.github.io/medical-tourism"}
    n = 0
    for r in recs:
        key = f'{r["type"]}__{r["id"]}'
        if want and f'{r["type"]}/{r["id"]}' not in want:
            continue
        out = CARDS / f"{key}.jpg"
        if out.exists() and not force and not want:
            continue
        record_card(r, ctx).save(out, "JPEG", quality=86, optimize=True, progressive=True)
        n += 1
    standing = [
        ("index", "Care Abroad", "Who goes where, what it costs, and who checked. Countries, clusters, "
                                 "hospitals, procedures, published prices, the law, and the risks.",
         "a directory of treatment across borders",
         mini_map(lit={iso for iso, row in countries.items() if row.get("destination")}),
         [(f'{sum(cov["records"].values()):,}', "records"), (f'{prices["count"]:,}', "prices"),
          (f'{legality["count"]:,}', "law readings")]),
        ("prices", "Prices", "Every published price this directory has read, with its date and the "
                             "provider's own exclusion list.", "money", None,
         [(f'{prices["count"]:,}', "prices"),
          (f'{len({p["country"] for p in prices["prices"]})}', "countries"),
          (f'{len(by_proc)}', "procedures")]),
        ("rules", "Rules", "Where a treatment is lawful for a visitor. One question, many "
                           "jurisdictions, every cell dated.", "law", None,
         [(f'{legality["count"]:,}', "readings"), (f'{len(legality["countries"])}', "jurisdictions"),
          (f'{len(legality["subjects"])}', "questions")]),
        ("map", "One map, several questions", "Health spending, doctors, beds, out-of-pocket share — "
                                              "on an equal-area world map.", "the world",
         mini_map(lit=set(countries)), None),
        ("near", "From where you are", "Every hospital and cluster sorted by distance from the city "
                                       "you would fly from.", "distance", None, None),
        ("numbers", "Numbers", "What this directory holds, and the shape of what is missing.",
         "counts", None, [(f'{cov["countries_touched"]}', "countries"),
                          (f'{facilities["count"]:,}', "hospital points"),
                          (f'{cov["sources"]}', "sources")]),
        ("journey", "The journey", "Deciding, booking, the visa, the flight, consent, the ward, the "
                                   "discharge summary, and the part nobody quotes for.", "in order", None, None),
        ("coverage", "Coverage", cov["scope"], "where this stops", None, None),
        ("sources", "Sources", "Every source a record may cite, by id.", "provenance", None, None),
        ("search", "Search", "Spell it however you spell it.", "find it", None, None),
    ]
    for t in jload(api / "vocab" / "types.json")["entries"]:
        standing.append((
            {"destination": "countries", "hub": "cities", "procedure": "procedures",
             "facility": "hospitals", "pathway": "journey", "risk": "risks", "rule": "rules",
             "org": "organizations", "person": "people", "event": "events", "term": "words",
             "dataset": "data", "story": "stories"}[t["key"]],
            t["name"], t["blurb"], "care abroad", None, None))
    for key, title, lede, eyeb, panel, stats in standing:
        if want and key not in want:
            continue
        out = CARDS / f"{key}.jpg"
        if out.exists() and not force and not want:
            continue
        page_card(title, lede, eyeb, ctx, panel, stats).save(
            out, "JPEG", quality=86, optimize=True, progressive=True)
        n += 1
    print(f"cards: {n} drawn · {len(list(CARDS.glob('*.jpg')))} on disk · {CARDS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
