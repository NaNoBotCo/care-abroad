#!/usr/bin/env python3
"""site.py — build/api → build/site: a static site people and bots can both read.

People: a directory front, one page per node with its kin said in both directions, an
equal-area world map, charts drawn from the records rather than photographed, large type,
high contrast, theme-aware, motion gated behind prefers-reduced-motion.

Bots: JSON-LD on every page, robots.txt that allows everything and says so with
Content-Signal, sitemap.xml with lastmod, llms.txt and llms-full.txt, an Atom feed, an
OpenSearch description, CSV and JSONL dumps, and the whole /api tree.

    python3 tools/site.py
    SITE_URL=https://example.org python3 tools/site.py
"""
from __future__ import annotations

import csv
import html
import json
import os

import fleet
import shutil
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, DATA, GEO, IMAGES, ROOT, TIER_LABEL, TYPES, VENDOR, haversine_km, jload  # noqa: E402
import pages  # noqa: E402
import viz  # noqa: E402
import worldmap  # noqa: E402

SITE = BUILD / "site"
API = BUILD / "api"
SITE_URL = os.environ.get("SITE_URL", "https://nanobotco.github.io/care-abroad").rstrip("/")
SITE_NAME = "Care Abroad"
TAGLINE = "who goes where, what it costs, and who checked"
DATA_LICENSE = "https://creativecommons.org/licenses/by/4.0/"
AUTHOR = {"@type": "Person", "name": "NaN", "url": "https://wichaa.net"}
CARDS_DIR = ROOT / "cards"

PATH_OF = {"destination": "country", "hub": "city", "procedure": "procedure", "facility": "hospital",
           "pathway": "step", "risk": "risk", "rule": "rule", "org": "org", "person": "person",
           "event": "event", "term": "word", "dataset": "dataset", "story": "story"}
DIR_OF = {"destination": "countries", "hub": "cities", "procedure": "procedures", "facility": "hospitals",
          "pathway": "journey", "risk": "risks", "rule": "rules", "org": "organizations",
          "person": "people", "event": "events", "term": "words", "dataset": "data", "story": "stories"}
KIND_OF = {"destination": "a country", "hub": "a cluster", "procedure": "a procedure",
           "facility": "a hospital", "pathway": "a step", "risk": "a risk", "rule": "a rule",
           "org": "an organization", "person": "a person", "event": "an event", "term": "a word",
           "dataset": "a series", "story": "a long one"}


def E(x) -> str:
    """html.escape, with null printed as a blank: a field is null here when nobody
    published the thing, which is a state this site prints rather than hides."""
    return html.escape("" if x is None else str(x))


def clip(text: str, n: int) -> str:
    t = (text or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"


def rel(depth: int) -> str:
    return "../" * depth


def url_of(r: dict) -> str:
    return f"{PATH_OF[r['type']]}/{r['id']}/"


def img_src(im: dict, depth: int) -> str:
    return f"{rel(depth)}images/{im['file']}"


CSS = """
:root{--bg:#f7f6f2;--panel:#fffefb;--ink:#15171a;--mute:#5f6670;--line:#e0ddd4;
  --blue:#2a78d6;--ember:#eb6834;--aqua:#1baf7a;--deep:#184f95;--warn:#fab219;--crit:#d03b3b;
  --chip:#eceae2;--focus:#1f5fa8;--land:#e2ded1;--landline:#b9b3a2;
  /* A directory about hospitals should read like a timetable, not like a brochure: a
     grotesque for headings, a humanist sans for the reading text, tabular figures
     wherever a number sits beside another number. All of it is already on the machine. */
  --display:"Helvetica Neue","Inter","Segoe UI",system-ui,-apple-system,Arial,sans-serif;
  --body:"Charter","Iowan Old Style","Source Serif 4",Georgia,"Times New Roman",serif;
  --ui:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#101215;--panel:#191c20;--ink:#eef1f4;
  --mute:#a3abb5;--line:#2b3037;--blue:#3987e5;--ember:#d95926;--aqua:#199e70;--deep:#86b6ef;
  --chip:#22262b;--focus:#8ab4f8;--land:#333941;--landline:#4c545e}}
:root[data-theme="dark"]{--bg:#101215;--panel:#191c20;--ink:#eef1f4;--mute:#a3abb5;--line:#2b3037;
  --blue:#3987e5;--ember:#d95926;--aqua:#199e70;--deep:#86b6ef;--chip:#22262b;--focus:#8ab4f8;--land:#333941;--landline:#4c545e}
*{box-sizing:border-box}html{font-size:19px;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);line-height:1.62;font-size:1.02rem;
  font-variant-numeric:tabular-nums}
a{color:var(--blue);text-decoration-thickness:.07em;text-underline-offset:.16em}a:hover{color:var(--deep)}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--focus);outline-offset:2px;border-radius:4px}
header.top{border-bottom:1px solid var(--line);padding:.7rem 1rem;max-width:68rem;margin:0 auto;display:flex;gap:.5rem 1.2rem;flex-wrap:wrap;align-items:baseline}
header.top .brand{font-family:var(--display);font-weight:700;text-decoration:none;color:var(--ink);letter-spacing:-.01em;font-size:1.05rem}
header.top .brand b{color:var(--blue)}
nav.crumbs{font-size:.83rem;color:var(--mute);font-family:var(--ui)}nav.crumbs a{text-decoration:none}nav.crumbs a:hover{text-decoration:underline}
main{max-width:68rem;margin:0 auto;padding:1.2rem 1rem 4rem}
h1{font-family:var(--display);font-size:clamp(1.9rem,4.2vw,2.7rem);line-height:1.1;margin:.5rem 0 .3rem;font-weight:700;letter-spacing:-.02em}
h1 .kind{display:block;font-size:.72rem;color:var(--mute);text-transform:uppercase;letter-spacing:.2em;font-family:var(--ui);margin-bottom:.5rem}
h2{font-family:var(--display);font-size:1.28rem;margin:1.9rem 0 .5rem;border-bottom:1px solid var(--line);padding-bottom:.28rem;font-weight:700;letter-spacing:-.01em}
h3{font-family:var(--display);font-size:1.04rem;margin:1rem 0 .3rem;font-weight:700}
.said{font-style:italic;color:var(--mute);margin:.2rem 0 .8rem}.lede{font-size:1.1rem;margin:.2rem 0 1rem}.mute{color:var(--mute)}
p{margin:.55rem 0}.prose p{margin:.75rem 0}
.dir{display:grid;grid-template-columns:repeat(auto-fill,minmax(19rem,1fr));gap:1.3rem 2.4rem;align-items:start;margin-top:.8rem}
.dir section{margin:0}.dir h2{margin:.2rem 0 .3rem;border:0;font-size:1.1rem}
.dir h2 a{text-decoration:none;color:var(--ink)}.dir h2 a:hover{color:var(--blue)}
.dir ul{list-style:none;margin:0;padding:0 0 0 .7rem;border-left:2px solid var(--line)}.dir li{margin:.14rem 0}
.dir li.sub{padding-left:.9rem;font-size:.95rem}
.count{color:var(--mute);font-size:.85em;font-family:var(--ui)}
.chip{display:inline-block;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:.05rem .6rem;font-size:.77rem;margin:.1rem .25rem .1rem 0;color:var(--ink);font-family:var(--ui)}
.tier-cited{border-color:var(--blue)}.tier-harvested{border-color:var(--aqua)}.tier-tradition{border-color:var(--warn)}
.tier-inference{border-style:dashed}.tier-field{border-color:var(--ember)}
table{border-collapse:collapse;width:100%;margin:.4rem 0 1rem;font-size:.94rem}
th,td{text-align:left;vertical-align:top;padding:.45rem .5rem;border-bottom:1px solid var(--line)}
th{width:26%;color:var(--mute);font-weight:600;font-family:var(--ui);font-size:.88rem}
.kin{display:grid;grid-template-columns:repeat(auto-fill,minmax(17rem,1fr));gap:.9rem}
.kin a.card{display:block;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.8rem .95rem;text-decoration:none;color:var(--ink)}
.kin a.card b{display:block;font-size:1.02rem;color:var(--blue);font-family:var(--display);font-weight:700}
.kin a.card small{display:block;font-size:.68rem;color:var(--mute);text-transform:uppercase;letter-spacing:.16em;font-family:var(--ui)}
.kin a.card span{display:block;margin-top:.3rem;font-size:.9rem;color:var(--ink)}
.kin a.card:hover b{color:var(--deep)}
figure{margin:0 0 1rem}
.mapwrap{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:.5rem}.mapwrap svg{width:100%;height:auto;display:block}
.facts{display:flex;flex-wrap:wrap;gap:.7rem;margin:.6rem 0 1.2rem}
.fact{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.7rem 1rem;min-width:8rem;text-align:center;flex:1 1 8rem}
.fact .n{font-family:var(--display);font-size:1.9rem;font-weight:700;line-height:1;letter-spacing:-.02em}
.fact .l{font-size:.72rem;color:var(--mute);margin-top:.28rem;font-family:var(--ui);text-transform:uppercase;letter-spacing:.09em}
.search{display:flex;gap:.5rem;margin:.6rem 0 1rem;flex-wrap:wrap}
.search input,.search select{flex:1;min-width:12rem;font:inherit;font-family:var(--ui);font-size:1rem;padding:.55rem .7rem;border:2px solid var(--line);border-radius:10px;background:var(--panel);color:var(--ink)}
.search button{font:inherit;font-family:var(--ui);padding:.55rem 1rem;border-radius:10px;border:2px solid var(--blue);background:var(--blue);color:#fff;cursor:pointer}
.chips{display:flex;flex-wrap:wrap;gap:.4rem;margin:.8rem 0 .2rem}
.chips button{font:inherit;font-size:.85rem;font-family:var(--ui);padding:.3rem .75rem;border-radius:999px;border:1.5px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer}
.chips button[aria-pressed=true]{background:var(--blue);border-color:var(--blue);color:#fff}
.tierline{font-size:.9rem;color:var(--mute);margin:.2rem 0 .8rem}
.legend{font-size:.85rem;color:var(--mute);border-top:1px solid var(--line);margin-top:2rem;padding-top:.6rem}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:1rem;align-items:start}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.9rem}
.card a.t{font-family:var(--display);font-weight:700;text-decoration:none;font-size:1.04rem}
.card p{margin:.3rem 0 0;font-size:.89rem;color:var(--mute)}
footer{max-width:68rem;margin:0 auto;padding:1rem;color:var(--mute);font-size:.84rem;border-top:1px solid var(--line);font-family:var(--ui)}
.bots a{margin-right:.7rem}.support{margin:.45rem 0 0}.support a{margin-right:.5rem}.fleet{margin:.6rem 0 0;line-height:1.9}.fleet a{margin-right:.55rem;white-space:nowrap}
.btn{display:inline-block;padding:.5rem 1rem;border-radius:999px;background:var(--blue);color:#fff;text-decoration:none;font-weight:700;border:2px solid var(--blue);font-family:var(--ui);font-size:.9rem}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line)}
.btn:hover{color:#fff;filter:brightness(1.08)}.btn.ghost:hover{color:var(--ink);border-color:var(--blue)}
.cta{display:flex;gap:.55rem;flex-wrap:wrap;margin:.8rem 0}
.etym{background:var(--panel);border-left:4px solid var(--warn);border-radius:0 12px 12px 0;padding:.7rem 1rem;margin:.8rem 0}
.hero{display:grid;grid-template-columns:1fr;gap:1rem;margin:.4rem 0 1.2rem}
.tagrow{display:flex;flex-wrap:wrap;gap:.35rem;margin:.5rem 0 .3rem}
.tagrow span.tg{display:inline-flex;align-items:center;gap:.3rem;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:.15rem .7rem;font-size:.83rem;font-family:var(--ui);color:var(--ink)}
.tagrow .tg.money{border-color:var(--warn)}.tagrow .tg.clinical{border-color:var(--aqua)}.tagrow .tg.welcome{border-color:#9b59b6}
.acc{display:flex;flex-wrap:wrap;gap:.4rem;margin:.3rem 0 .6rem;font-size:.86rem;font-family:var(--ui)}
.acc b{color:var(--mute)}
.pricebox{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:.9rem 1.1rem;margin:.6rem 0 1rem}
.pricebox .amt{font-family:var(--display);font-size:1.5rem;font-weight:700;letter-spacing:-.02em}
.pricebox .usd{color:var(--mute);font-size:1rem;font-weight:400}
.pricebox ul{margin:.35rem 0 0;padding-left:1.1rem;font-size:.9rem}
.pricebox .ex li{color:var(--ink)}
.pricebox .meta{font-size:.82rem;color:var(--mute);font-family:var(--ui);margin-top:.45rem}
.two-up{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1.4rem 0}
@media(max-width:760px){.two-up{grid-template-columns:1fr}html{font-size:18px}}
.pitch{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1rem 1.2rem}
mark.tier{background:transparent;color:var(--mute);font-style:italic}
.wander{font-size:.85rem;color:var(--mute)}
@media (prefers-reduced-motion: no-preference){.kin a.card,.card,.fact{transition:transform .18s ease,box-shadow .18s ease}
.kin a.card:hover,.card:hover{transform:translateY(-3px);box-shadow:0 10px 24px rgba(0,0,0,.09)}
.btn{transition:transform .15s ease}.btn:hover{transform:scale(1.03)}}
"""

SHARE_CSS = """
.shareme{margin:2.4rem 0 .4rem;padding:.9rem 1.1rem;background:var(--panel);border:1px solid var(--line);border-radius:14px}
.shareme b{display:block;font-size:.93rem;margin-bottom:.5rem}
.shareme .row{display:flex;flex-wrap:wrap;gap:.45rem}
.shareme a,.shareme button{font:inherit;font-size:.86rem;font-family:var(--ui);padding:.35rem .8rem;border-radius:999px;
  border:1.5px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:.35rem}
.shareme a:hover,.shareme button:hover{border-color:var(--blue);color:var(--blue)}
.shareme .said{font-size:.84rem;color:var(--mute);margin-left:.4rem}
.shareme .copy{border-color:var(--blue);color:#fff;background:var(--blue)}
.shareme .copy:hover{color:#fff;filter:brightness(1.08)}
"""

NAV = [("index.html", "Everything"), ("map/index.html", "Map"), ("prices/index.html", "Prices"),
       ("rules/index.html", "Rules"), ("near/index.html", "Near me"), ("journey/index.html", "Journey"),
       ("numbers/index.html", "Numbers"), ("countries/index.html", "Countries"),
       ("procedures/index.html", "Procedures"), ("hospitals/index.html", "Hospitals"),
       ("risks/index.html", "Risks"), ("words/index.html", "Words"), ("data/index.html", "Data"),
       ("search/index.html", "Search"), ("sources/index.html", "Sources"),
       ("coverage/index.html", "Coverage"), ("api/index.json", "API"), ("llms.txt", "llms.txt")]


def page(title: str, body: str, depth: int, desc: str = "", jsonld: list | None = None,
         canonical: str = "", extra_head: str = "", og_image: str = "", alt_json: str = "",
         og_alt: str = "", og_type: str = "website", card: str = "", share_title: str = "") -> str:
    r = rel(depth)
    if card and (CARDS_DIR / f"{card}.jpg").exists():
        og_image = f"{SITE_URL}/cards/{card}.jpg"
    ld = "".join(f'<script type="application/ld+json">{json.dumps(o, ensure_ascii=False)}</script>'
                 for o in (jsonld or []))
    nav = " · ".join(f'<a href="{r}{h}">{E(l)}</a>' for h, l in NAV)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc[:300])}">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<meta name="color-scheme" content="light dark">
<meta property="og:site_name" content="{E(SITE_NAME)}"><meta property="og:locale" content="en">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc[:200])}"><meta property="og:type" content="{E(og_type)}">
{f'<meta property="og:image" content="{E(og_image)}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:alt" content="{E(og_alt or title)}"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{E(og_image)}"><meta name="twitter:title" content="{E(title)}"><meta name="twitter:description" content="{E(desc[:200])}">' if og_image else ''}
{f'<link rel="canonical" href="{E(canonical)}">' if canonical else ''}
{f'<link rel="alternate" type="application/json" href="{E(alt_json)}">' if alt_json else ''}
<link rel="manifest" href="{r}manifest.webmanifest">
<meta name="theme-color" content="#2a78d6">
<link rel="icon" href="{r}icon.svg" type="image/svg+xml">
<link rel="search" type="application/opensearchdescription+xml" title="{E(SITE_NAME)}" href="{r}opensearch.xml">
<link rel="alternate" type="application/atom+xml" title="{E(SITE_NAME)} updates" href="{r}feed.xml">
{extra_head}
<style>{CSS}{SHARE_CSS}{viz.CSS}</style>
{ld}
</head>
<body>
<header class="top"><a class="brand" href="{r}index.html">Care <b>Abroad</b></a>
<nav class="crumbs">{nav} · <a class="wander" href="{r}wander.html" title="a page at random">🎲 Wander</a></nav></header>
<main>
{body}
{share_row(canonical, share_title or title) if canonical else ""}
</main>
<script>{viz.TIP_JS}</script>
<script>document.addEventListener("keydown",function(e){{if(e.key==="r"&&!e.metaKey&&!e.ctrlKey&&!e.altKey&&!/input|textarea|select/i.test(e.target.tagName))location.href="{r}wander.html"}});</script>
<footer>
<div class="bots">For the machines: <a href="{r}api/nodes.json">nodes.json</a> <a href="{r}api/countries.json">countries.json</a> <a href="{r}api/prices.json">prices.json</a> <a href="{r}api/legality.json">legality.json</a> <a href="{r}api/facilities.json">facilities.json</a> <a href="{r}api/kin.json">kin.json</a> <a href="{r}nodes.jsonl">nodes.jsonl</a> <a href="{r}nodes.csv">nodes.csv</a> <a href="{r}llms-full.txt">llms-full.txt</a> <a href="{r}sitemap.xml">sitemap.xml</a> <a href="{r}feed.xml">feed.xml</a></div>
<p>Records licensed <a href="{DATA_LICENSE}">CC BY 4.0</a>. Country outlines from <a href="https://www.naturalearthdata.com/">Natural Earth</a>, public domain. Health and tourism indicators from <a href="https://data.worldbank.org/">World Bank Open Data</a>, CC BY 4.0. Hospital and clinic points from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, ODbL. Each field carries a provenance tier.</p>
<p>Nothing here is medical advice or legal advice. It is a directory of what other people have published, with the dates they published it.</p>
{fleet.row_html("care-abroad")}
{fleet.support_html(self_id="care-abroad")}
{fleet.maker_html()}
</footer>
</body>
</html>
"""


# ------------------------------------------------------------------ helpers

def tier_chip(t: dict) -> str:
    tier = (t or {}).get("tier", "")
    if not tier:
        return ""
    lab = {"cited": "Cited", "harvested": "Harvested", "tradition": "Trade practice",
           "inference": "Inference", "field": "Field"}.get(tier, tier)
    src = (t or {}).get("source", "")
    note = (t or {}).get("note", "")
    return (f'<span class="chip tier-{E(tier)}" title="{E((src + " — " if src else "") + note)}">'
            f'{E(lab)}{(" · " + E(src[2:])) if src else ""}</span>')


def marks(text: str) -> str:
    import re
    return re.sub(r"\*([^*]+)\*", r'<mark class="tier">\1</mark>', E(text or ""))


def prose(text: str) -> str:
    import re
    out = []
    for para in re.split(r"\n\s*\n", (text or "").strip()):
        p = E(para.strip())
        p = re.sub(r"\*([^*]+)\*", r'<mark class="tier">\1</mark>', p)
        out.append(f"<p>{p}</p>")
    return "".join(out)


def name_link(r: dict, depth: int) -> str:
    return f'<a href="{rel(depth)}{url_of(r)}index.html">{E(r["names"]["name"])}</a>'


def group_key(r: dict, key: str):
    node = r
    for part in key.split("."):
        node = (node or {}).get(part) if isinstance(node, dict) else None
    if key == "facets.letter":
        return (r["names"]["name"][:1] or "?").upper()
    if isinstance(node, list):
        return node[0] if node else None
    return node


GROUP_LABEL = {
    "—": "Everything else", "global": "Everywhere",
    "orthopaedic": "Bone, joint and spine", "dental": "Teeth", "fertility": "Fertility",
    "bariatric": "Weight", "cardiac": "Heart", "ophthalmic": "Eyes", "cosmetic": "Cosmetic",
    "hair": "Hair", "oncology": "Cancer", "neurological": "Brain and nerve",
    "transplant": "Transplant", "gender-affirming": "Gender-affirming", "diagnostic": "Screening",
    "rehabilitation": "Rehabilitation", "unproven": "Sold without approval",
    "infection": "Infection", "clinical": "Clinical", "legal": "Legal", "financial": "Money",
    "travel": "Travel", "ethical": "Ethics", "data": "Data",
    "visa": "Visas", "entitlement": "Entitlement", "licensing": "Licensing",
    "prohibition": "Prohibitions", "reimbursement": "Who pays", "treaty": "Treaties",
    "advertising": "Advertising", "accreditor": "Accreditors", "regulator": "Regulators",
    "ministry": "Ministries", "trade-body": "Trade bodies", "registry": "Registries",
    "professional-society": "Professional societies", "ngo": "Non-governmental", "insurer": "Insurers",
    "facilitator": "Facilitators", "conference": "Conferences", "ruling": "Rulings",
    "outbreak": "Outbreaks", "turning-point": "Turning points",
    "essay": "Essays", "explainer": "Explainers", "method": "Method", "resources": "Where it came from",
    "deciding": "Deciding", "booking": "Booking", "before-you-fly": "Before the flight",
    "on-arrival": "On arrival", "in-hospital": "In hospital", "going-home": "Going home",
    "aftercare": "Aftercare", "when-it-goes-wrong": "When it goes wrong",
    "surgeon": "Surgeons", "physician": "Physicians", "founder": "Founders", "regulator_": "Regulators",
    "researcher": "Researchers", "journalist": "Journalists", "patient": "Patients",
    "administrator": "Administrators", "broker": "Brokers", "ethicist": "Ethicists",
}
ISO_NAME: dict = {}
REGION_LABEL: dict = {}


def glabel(g) -> str:
    g = str(g)
    return GROUP_LABEL.get(g) or ISO_NAME.get(g) or REGION_LABEL.get(g) or g


def directory_sections(recs: list[dict], types: dict, depth: int, limit: int | None = None) -> str:
    out = []
    for t in types["entries"]:
        rs = [r for r in recs if r["type"] == t["key"]]
        if not rs:
            continue
        groups: dict = {}
        for r in rs:
            groups.setdefault(group_key(r, t["group_by"]) or "—", []).append(r)
        lis = []
        for g, members in sorted(groups.items(), key=lambda kv: (kv[0] == "—", glabel(kv[0]))):
            members.sort(key=lambda r: (r["names"].get("sort") or r["names"]["name"]).lower())
            if len(groups) > 1:
                lis.append(f'<li><b>{E(glabel(g))}</b> <span class="count">({len(members)})</span></li>')
            for r in (members if limit is None else members[:limit]):
                lis.append(f'<li class="{"sub" if len(groups) > 1 else ""}">{name_link(r, depth)}</li>')
            if limit is not None and len(members) > limit:
                lis.append(f'<li class="sub"><a href="{rel(depth)}{DIR_OF[t["key"]]}/index.html">… all {len(members)}</a></li>')
        out.append(f'<section><h2><a href="{rel(depth)}{DIR_OF[t["key"]]}/index.html">{E(t["name"])}</a> '
                   f'<span class="count">({len(rs)})</span></h2>'
                   f'<p class="mute" style="margin:.1rem 0 .4rem;font-size:.88rem">{E(t["blurb"])}</p>'
                   f'<ul>{"".join(lis)}</ul></section>')
    return f'<div class="dir">{"".join(out)}</div>'


def share_row(url: str, title: str) -> str:
    u, t = urllib.parse.quote(url, safe=""), urllib.parse.quote(title)
    links = [("Bluesky", f"https://bsky.app/intent/compose?text={t}%20{u}"),
             ("Mastodon", f"https://mastodonshare.com/?text={t}&url={u}"),
             ("X", f"https://twitter.com/intent/tweet?text={t}&url={u}"),
             ("Facebook", f"https://www.facebook.com/sharer/sharer.php?u={u}"),
             ("Reddit", f"https://www.reddit.com/submit?url={u}&title={t}"),
             ("WhatsApp", f"https://api.whatsapp.com/send?text={t}%20{u}"),
             ("Email", f"mailto:?subject={t}&body={u}")]
    btns = "".join(f'<a href="{E(href)}" target="_blank" rel="noopener">{E(name)}</a>' for name, href in links)
    return (f'<section class="shareme" data-url="{E(url)}" data-title="{E(title)}">'
            f'<b>Pass it on</b><div class="row">'
            f'<button type="button" class="copy" data-sh="copy">Copy link</button>'
            f'<button type="button" data-sh="native" hidden>Share…</button>{btns}'
            f'<span class="said" aria-live="polite"></span></div></section>'
            '<script>(function(){var s=document.currentScript.previousElementSibling;'
            'var n=s.querySelector(\'[data-sh="native"]\');if(navigator.share)n.hidden=false;'
            's.addEventListener("click",function(e){var b=e.target.closest("[data-sh]");if(!b)return;'
            'var url=s.dataset.url,title=s.dataset.title,said=s.querySelector(".said");'
            'if(b.dataset.sh==="copy"){(navigator.clipboard?navigator.clipboard.writeText(url):Promise.reject())'
            '.then(function(){said.textContent="copied"},function(){said.textContent=url});}'
            'else if(b.dataset.sh==="native"){navigator.share({title:title,url:url}).catch(function(){})}});})();</script>')


GEO_CACHE: dict = {}
MARKETS: list = []
OSM_BY_HUB: dict = {}
PRICES_BY_PROC: dict = {}


# ------------------------------------------------------------------ node page

def node_jsonld(r: dict) -> list:
    url = f"{SITE_URL}/{url_of(r)}"
    base = {"@context": "https://schema.org", "url": url, "name": r["names"]["name"],
            "description": r["blurb"], "inLanguage": "en",
            "isPartOf": {"@type": "Dataset", "name": SITE_NAME, "url": SITE_URL + "/"},
            "license": DATA_LICENSE, "dateModified": r["updated"]}
    if r.get("names", {}).get("aliases"):
        base["alternateName"] = r["names"]["aliases"]
    a = r.get("address") or {}
    g = r.get("geo") or {}
    if r["type"] == "facility":
        base.update({"@type": "Hospital"})
        if a:
            base["address"] = {"@type": "PostalAddress", "streetAddress": a.get("street", ""),
                               "addressLocality": a.get("city", ""), "addressRegion": a.get("area", ""),
                               "postalCode": a.get("postcode", ""), "addressCountry": a.get("country", "")}
        if g:
            base["geo"] = {"@type": "GeoCoordinates", "latitude": g["lat"], "longitude": g["lon"]}
        if r.get("links"):
            base["sameAs"] = [x["url"] for x in r["links"]]
    elif r["type"] == "procedure":
        base.update({"@type": "MedicalProcedure"})
    elif r["type"] == "risk":
        base.update({"@type": "MedicalRiskFactor"})
    elif r["type"] in ("destination", "hub"):
        base.update({"@type": "Place"})
        if g:
            base["geo"] = {"@type": "GeoCoordinates", "latitude": g["lat"], "longitude": g["lon"]}
    elif r["type"] == "person":
        base.update({"@type": "Person"})
        if r.get("links"):
            base["sameAs"] = [x["url"] for x in r["links"]]
    elif r["type"] == "org":
        base.update({"@type": "Organization"})
        if r.get("links"):
            base["sameAs"] = [x["url"] for x in r["links"]]
    elif r["type"] == "event":
        base.update({"@type": "Event"})
    elif r["type"] == "dataset":
        d = r.get("dataset") or {}
        base.update({"@type": "Dataset", "creator": {"@type": "Organization", "name": d.get("publisher", "")},
                     "measurementTechnique": d.get("counts", ""), "variableMeasured": d.get("unit", "")})
        if d.get("url"):
            base["sameAs"] = d["url"]
    else:
        base.update({"@type": "DefinedTerm", "inDefinedTermSet": f"{SITE_URL}/{DIR_OF[r['type']]}/"})
    out = [base, {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": SITE_URL + "/"},
        {"@type": "ListItem", "position": 2, "name": DIR_OF[r["type"]].replace("-", " ").title(),
         "item": f"{SITE_URL}/{DIR_OF[r['type']]}/"},
        {"@type": "ListItem", "position": 3, "name": r["names"]["name"], "item": url}]}]
    for i, p in enumerate(r.get("prices", []), 1):
        if p.get("amount") is None:
            continue
        out.append({"@context": "https://schema.org", "@type": "Offer", "url": f"{url}#price-{i}",
                    "price": p["amount"], "priceCurrency": p["currency"],
                    "priceValidUntil": None, "availabilityStarts": str(p["as_of"]),
                    "description": ("includes " + "; ".join(p.get("includes", []))) if p.get("includes") else "",
                    "itemOffered": {"@type": "MedicalProcedure", "name": p.get("procedure", "")}})
    return out


def kin_block(r: dict, by_id: dict, depth: int) -> str:
    cards = []
    back_by = {k["from"]: k["as"] for k in r.get("kin_in", [])}
    for k in r.get("kin_out", []):
        t = by_id.get(k["to"])
        if not t:
            continue
        reply = back_by.get(k["to"])
        cards.append(f'<a class="card" href="{rel(depth)}{url_of(t)}index.html">'
                     f'<small>{E(KIND_OF.get(t["type"], t["type"]))}</small><b>{E(t["names"]["name"])}</b>'
                     f'<span>{E(k["as"])}</span>'
                     + (f'<span class="mute" style="font-size:.82rem;font-style:italic;margin-top:.45rem">'
                        f'and of this page it says: {E(reply)}</span>' if reply else "") + '</a>')
    seen = {k["to"] for k in r.get("kin_out", [])}
    back = []
    for k in r.get("kin_in", []):
        if k["from"] in seen:
            continue
        t = by_id.get(k["from"])
        if not t:
            continue
        back.append(f'<a class="card" href="{rel(depth)}{url_of(t)}index.html">'
                    f'<small>{E(KIND_OF.get(t["type"], t["type"]))} · on this page</small>'
                    f'<b>{E(t["names"]["name"])}</b><span>{E(k["as"])}</span></a>')
    out = ""
    if cards:
        out += f'<h2>What it connects to</h2><div class="kin">{"".join(cards)}</div>'
    if back:
        out += f'<h2>Pages that point here</h2><div class="kin">{"".join(back)}</div>'
    return out


def price_block(p: dict, by_id: dict, depth: int, i: int) -> str:
    native = (f'{p["amount"]:,.0f}' if p.get("amount") is not None else "")
    if p.get("amount_high"):
        native += f'–{p["amount_high"]:,.0f}'
    usd = ""
    if p.get("usd"):
        usd = f' <span class="usd">≈ US${p["usd"]:,.0f}' + (f'–{p["usd_high"]:,.0f}' if p.get("usd_high") else "") + "</span>"
    fac = by_id.get(p.get("facility") or "")
    proc = by_id.get(p.get("procedure") or "")
    who = (f'<a href="{rel(depth)}{url_of(fac)}index.html">{E(fac["names"]["name"])}</a>' if fac
           else E(p.get("city") or ISO_NAME.get(p["country"], p["country"])))
    inc = ("<p style='margin:.5rem 0 0'><b>Includes.</b></p><ul>"
           + "".join(f"<li>{E(x)}</li>" for x in p["includes"]) + "</ul>") if p.get("includes") else ""
    exc = ("<p style='margin:.5rem 0 0'><b>Excludes.</b></p><ul class='ex'>"
           + "".join(f"<li>{E(x)}</li>" for x in p["excludes"]) + "</ul>") if p.get("excludes") else ""
    return (f'<div class="pricebox" id="price-{i}">'
            f'<div class="amt">{E(native)} {E(p["currency"])}{usd}</div>'
            f'<p class="mute" style="margin:.2rem 0 0">{E(p["kind"])} · {who}'
            + (f' · {E(ISO_NAME.get(p["country"], p["country"]))}' if not fac else "")
            + (f' · for <a href="{rel(depth)}{url_of(proc)}index.html">{E(proc["names"]["name"])}</a>' if proc and proc["id"] != by_id.get("", {}).get("id") else "")
            + "</p>" + inc + exc
            + f'<p class="meta">Published price dated {E(p["as_of"])}'
            + (f' · dollars at the rate of {E(p["rate_date"])}' if p.get("rate_date") else "")
            + (f' · <a href="{E(p["url"])}" rel="noopener">the page it was read from</a>' if p.get("url") else "")
            + (f' · {E(p["note"])}' if p.get("note") else "") + "</p></div>")


def node_page(r: dict, by_id: dict, sources: dict, countries: dict) -> str:
    n = r["names"]
    depth = 2
    et = r.get("etymology") or {}
    f = r.get("facets") or {}
    head = f'<h1><span class="kind">{E(KIND_OF.get(r["type"], r["type"]))}'
    if f.get("iso2"):
        head += f' · {E(ISO_NAME.get(f["iso2"], f["iso2"]))}'
    head += f'</span>{E(n["name"])}</h1>'
    if n.get("aliases"):
        head += f'<p class="mute" style="margin:.1rem 0">also: {E(" · ".join(n["aliases"]))}</p>'
    if n.get("said"):
        head += f'<p class="said">{E(n["said"])}</p>'
    body = head
    body += f'<div class="prose"><p class="lede">{E(r["text"]["what"])}</p></div>'

    # the picture: drawn from the record, not photographed
    if r["type"] == "hub" and r.get("geo") and OSM_BY_HUB.get(r["id"]):
        rad = float(f.get("radius_km") or 15)
        cur = [{"lat": o["geo"]["lat"], "lon": o["geo"]["lon"], "name": o["names"]["name"]}
               for o in by_id.values()
               if o["type"] == "facility" and o.get("geo")
               and haversine_km(r["geo"]["lat"], r["geo"]["lon"], o["geo"]["lat"], o["geo"]["lon"]) <= rad * 1.2]
        body += viz.hub_map(r["geo"]["lat"], r["geo"]["lon"], rad, OSM_BY_HUB[r["id"]], cur,
                            ident=f"osm-{r['id']}", label=n["name"])
    elif r["type"] in ("facility", "hub") and r.get("geo") and GEO_CACHE:
        others = [{"lat": (o.get("geo") or {}).get("lat"), "lon": (o.get("geo") or {}).get("lon"),
                   "name": o["names"]["name"]}
                  for o in by_id.values() if o["type"] in ("facility", "hub") and o["id"] != r["id"] and o.get("geo")]
        span = 6.0 if r["type"] == "facility" else 12.0
        body += (f'<figure class="fig">{viz.locator(GEO_CACHE, r["geo"]["lat"], r["geo"]["lon"], others, w=760, span=span, label=n["name"])}'
                 f'<figcaption>{E(n["name"])} and everything else in this directory nearby. '
                 f'Equal Earth, same projection as the world map.</figcaption></figure>')
    elif r["type"] == "destination" and f.get("iso2") and GEO_CACHE:
        row = countries["countries"].get(f["iso2"], {})
        ind = row.get("indicators", {})
        meta = countries["indicator_meta"]
        rows = []
        for k in ("spend_pc", "doctors", "beds", "oop", "life"):
            if k in ind and k in meta:
                rows.append({"label": meta[k]["name"], "value": ind[k]["value"],
                             "sub": f'{meta[k]["unit"]} · {ind[k]["year"]}',
                             "tip": f'<b>{E(meta[k]["name"])}</b>{ind[k]["value"]:,.1f} {E(meta[k]["unit"])} &middot; {ind[k]["year"]}'})
        bb = worldmap.bbox_of(GEO_CACHE, f["iso2"])
        if bb:
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            span = max(bb[2] - bb[0], (bb[3] - bb[1]) * 1.6, 8) * 0.75
            hubs = [{"lat": o["geo"]["lat"], "lon": o["geo"]["lon"], "name": o["names"]["name"]}
                    for o in by_id.values()
                    if o.get("geo") and o["type"] in ("hub", "facility")
                    and ((o.get("facets") or {}).get("iso2") or (o.get("address") or {}).get("country")) == f["iso2"]]
            body += (f'<figure class="fig">{viz.locator(GEO_CACHE, cy, cx, hubs, w=760, span=span, label=n["name"])}'
                     f'<figcaption>{E(n["name"])}, with every cluster and hospital in this directory on it.</figcaption></figure>')
        if rows:
            body += viz.bars(rows, ident=f"ind-{r['id']}", title="What its own health system looks like",
                             note=("World Bank series, each at that country's most recent reporting year. These "
                                   "describe the system its own residents use, which is not the tier a visitor "
                                   "is sold."), label_w=250)
    elif r["type"] == "procedure":
        m = r.get("metrics") or {}
        fig = viz.recovery_bar(m.get("stay_days"), m.get("days_before_flying"), m.get("recovery_weeks"),
                               ident=f"rec-{r['id']}")
        if fig:
            body += fig

    if et.get("root"):
        body += (f'<div class="etym"><b>Root.</b> {marks(et["root"])}'
                 + (f'<br><b>First seen.</b> {marks(et["first_attested"])}' if et.get("first_attested") else "")
                 + (f'<br>{marks(et["note"])}' if et.get("note") else "")
                 + f' {tier_chip({"tier": et.get("tier", ""), "source": et.get("source", "")})}</div>')
    if r.get("tag_facts"):
        body += '<div class="tagrow">' + "".join(
            f'<span class="tg {E(t.get("group", ""))}" title="{E(t.get("evidence", ""))}">'
            f'{E(t.get("icon", ""))} {E(t.get("label", t["key"]))}</span>' for t in r["tag_facts"]) + "</div>"
    if r.get("recognition_facts"):
        body += '<div class="acc"><b>Inspected or listed by</b> ' + " · ".join(
            (f'<a href="{E(x["url"])}" rel="noopener">{E(x.get("label", x["key"]))}</a>' if x.get("url")
             else E(x.get("label", x["key"])))
            + (f' ({E(str(x["year"]))})' if x.get("year") else "")
            for x in r["recognition_facts"]) + "</div>"

    for key, title in (("story", "The story"), ("how", "How it works"), ("today", "Today"), ("notes", "Notes")):
        if r["text"].get(key):
            body += (f'<h2>{title} {tier_chip(r["tiers"].get(f"text.{key}"))}</h2>'
                     f'<div class="prose">{prose(r["text"][key])}</div>')
    for sec in (r.get("sections") or []):
        body += f'<h2>{E(sec["h"])}</h2><div class="prose">{prose(sec["text"])}</div>'

    # every price for this procedure, wherever it sits, on one axis
    if r["type"] == "procedure" and PRICES_BY_PROC.get(r["id"]):
        rows = PRICES_BY_PROC[r["id"]]
        groups: dict = {}
        for p in rows:
            groups.setdefault(p["country"], []).append(p)
        gs = []
        for iso, items in sorted(groups.items(), key=lambda kv: min(
                (x["usd"] for x in kv[1] if x["usd"] is not None), default=9e12)):
            pts = []
            for p in items:
                fac = by_id.get(p.get("facility") or "")
                native = f'{p["amount"]:,.0f} {p["currency"]}' if p.get("amount") is not None else ""
                if p.get("amount_high"):
                    native = f'{p["amount"]:,.0f}–{p["amount_high"]:,.0f} {p["currency"]}'
                tip = ("<b>" + E(fac["names"]["name"] if fac else (p.get("city") or ISO_NAME.get(iso, iso)))
                       + "</b>" + E(native) + f' &middot; {E(p["kind"])}<br>dated {E(p["as_of"])}'
                       + (f'<br><b>excludes {E(", ".join(p["excludes"][:3]))}</b>' if p.get("excludes") else ""))
                pts.append({"usd": p["usd"], "usd_high": p.get("usd_high"), "kind": p["kind"],
                            "tip": tip, "native": native, "as_of": p["as_of"],
                            "src_html": (f'<a href="{E(p["url"])}" rel="noopener">page</a>'
                                         if p.get("url") else E(p["source"]))})
            gs.append({"label": ISO_NAME.get(iso, iso), "iso": iso, "points": pts})
        fig = viz.price_strip(gs, w=760, ident=f"strip-{r['id']}",
                              note=(f'{len(rows)} published price{"s" if len(rows) != 1 else ""} for '
                                    f'this procedure, across {len(groups)} '
                                    f'{"countries" if len(groups) != 1 else "country"}.'))
        if fig:
            body += ("<h2>What it costs where anyone publishes a price</h2>" + fig
                     + f'<p class="mute" style="font-size:.86rem">Every price this directory has read, '
                       f'for every procedure, sits together on <a href="{rel(depth)}prices/index.html">'
                       f'the prices page</a>.</p>')

    # prices on this record
    if r.get("prices"):
        body += (f'<h2>Published prices {tier_chip(r["tiers"].get("prices"))}</h2>'
                 f'<p class="mute">Each is a number read off a page on the date named, in the currency the '
                 f'provider bills in. Dollars are that number through one dated rate table.</p>')
        for i, p in enumerate(sorted(r["prices"], key=lambda p: p.get("usd") or 9e12), 1):
            body += price_block(p, by_id, depth, i)
        others = [(o, p) for o in by_id.values() for p in o.get("prices", [])
                  if r["type"] == "procedure" and p.get("procedure") == r["id"] and o["id"] != r["id"]]
        if others:
            body += (f'<p class="mute">{len(others)} more published prices for this procedure sit on other '
                     f'records — all of them together are on <a href="{rel(depth)}prices/index.html">the prices page</a>.</p>')
    elif r["type"] == "procedure":
        body += ('<h2>Published prices</h2><p class="mute">None read yet for this one. Most providers publish '
                 'no price at all; that is a fact about publication, not about cost.</p>')

    # legality grid on a rule record
    if r.get("legality"):
        subs = [{"id": r["id"], "label": n["name"]}]
        cells = {(r["id"], x["country"]): x for x in r["legality"]}
        body += ('<h2>Where it stands ' + tier_chip(r["tiers"].get("legality")) + "</h2>"
                 + viz.legality_matrix(subs, sorted({x["country"] for x in r["legality"]}), cells,
                                       w=880, country_names=ISO_NAME, ident=f"leg-{r['id']}",
                                       note=("One reading of one named instrument on one date. Law moves; the "
                                             "date in each cell is how old the reading is. Nothing here is legal advice."))
                 + f'<p class="mute">The whole grid across every question: <a href="{rel(depth)}rules/index.html">the rules page</a>.</p>')

    # facts table
    rows = []
    for k, v in f.items():
        if k in ("letter",):
            continue
        if k == "iso2":
            vv = f'{E(ISO_NAME.get(v, v))} <span class="mute">({E(v)})</span>'
        elif k == "draws" and isinstance(v, list):
            vv = ", ".join(f'<a href="{rel(depth)}{url_of(by_id[s])}index.html">{E(by_id[s]["names"]["name"])}</a>'
                           if s in by_id else E(s) for s in v)
        elif isinstance(v, list):
            vv = E(", ".join(map(str, v)))
        else:
            vv = E(str(v))
        rows.append(f"<tr><th>{E(k.replace('_', ' '))}</th><td>{vv}</td></tr>")
    rows.append(f"<tr><th>region</th><td>{E(', '.join(t.get('name', t['key']) for t in r['region_terms']))}</td></tr>")
    m = r.get("metrics") or {}
    for k, v in m.items():
        if k in ("note", "as_of", "source", "url") or v is None:
            continue
        rows.append(f"<tr><th>{E(k.replace('_', ' '))}</th><td>{E(f'{v:,}' if isinstance(v, (int, float)) else v)}</td></tr>")
    if m.get("note"):
        rows.append(f'<tr><th>about those numbers</th><td>{E(m["note"])}'
                    + (f' <span class="mute">({E(m.get("as_of", ""))})</span>' if m.get("as_of") else "")
                    + (f' · <a href="{E(m["url"])}" rel="noopener">source</a>' if m.get("url") else "") + "</td></tr>")
    if r.get("address"):
        a = r["address"]
        rows.append(f"<tr><th>address</th><td>{E(', '.join(x for x in (a.get('street'), a.get('city'), a.get('area'), a.get('postcode')) if x))}"
                    + (f", {E(ISO_NAME.get(a.get('country', ''), a.get('country', '')))}" if a.get("country") else "")
                    + f" {tier_chip(r['tiers'].get('address'))}</td></tr>")
    if r.get("geo"):
        g = r["geo"]
        rows.append(f'<tr><th>where</th><td>{g["lat"]:.4f}, {g["lon"]:.4f} ({E(g.get("precision", ""))}) · '
                    f'<a href="https://www.openstreetmap.org/?mlat={g["lat"]}&mlon={g["lon"]}#map=14/{g["lat"]}/{g["lon"]}">OpenStreetMap</a> · '
                    f'<a href="geo:{g["lat"]},{g["lon"]}">open in maps</a> {tier_chip(r["tiers"].get("geo"))}</td></tr>')
    if r.get("dataset"):
        d = r["dataset"]
        for k in ("publisher", "unit", "indicator", "years", "countries", "license", "updated_by_publisher"):
            if d.get(k):
                rows.append(f"<tr><th>{E(k.replace('_', ' '))}</th><td>{E(d[k])}</td></tr>")
        if d.get("counts"):
            rows.append(f'<tr><th>counts</th><td>{E(d["counts"])}</td></tr>')
        if d.get("does_not_count"):
            rows.append(f'<tr><th>does not count</th><td>{E(d["does_not_count"])}</td></tr>')
    if r.get("links"):
        rows.append("<tr><th>links</th><td>" + " · ".join(
            f'<a href="{E(x["url"])}" rel="noopener">{E(x["label"])}</a>' for x in r["links"]) + "</td></tr>")
    rows.append(f"<tr><th>confidence</th><td>{E(r['confidence'])}"
                f"{' · needs verification' if r.get('needs_verification') else ''} · updated {E(r['updated'])}</td></tr>")
    body += f"<h2>The particulars</h2><table>{''.join(rows)}</table>"

    if r.get("confusable_with"):
        body += "<h2>Not to be confused with</h2><ul>" + "".join(
            f'<li><b>{name_link(by_id[c["id"]], depth) if c["id"] in by_id else E(c["id"])}</b> — {E(c["tell"])}</li>'
            for c in r["confusable_with"]) + "</ul>"

    # nearest others, for anything with a point
    if r["type"] in ("facility", "hub") and r.get("geo"):
        g = r["geo"]
        others = []
        for o in by_id.values():
            if o["id"] == r["id"] or not o.get("geo") or o["type"] not in ("facility", "hub"):
                continue
            others.append((haversine_km(g["lat"], g["lon"], o["geo"]["lat"], o["geo"]["lon"]), o))
        others.sort(key=lambda x: x[0])
        if others[:6]:
            body += ('<h2>Nearest in this directory</h2><p class="mute">Great-circle kilometres. '
                     f'<a href="{rel(depth)}near/index.html">The distance page</a> sorts every one of them from '
                     'wherever you would fly from.</p><ul>' + "".join(
                         f'<li><b>{d:,.0f} km</b> — {name_link(o, depth)}'
                         + (f' <span class="mute">{E((o.get("address") or {}).get("city", ""))}</span>'
                            if (o.get("address") or {}).get("city") else "") + "</li>"
                         for d, o in others[:6]) + "</ul>")

    # how far it is from the places people leave — arithmetic, and the page says so
    if r["type"] in ("facility", "hub", "destination") and r.get("geo") and MARKETS:
        g = r["geo"]
        rows = []
        for m in MARKETS:
            if m.get("alt"):
                continue
            km = haversine_km(m["lat"], m["lon"], g["lat"], g["lon"])
            rows.append((km, m))
        rows.sort(key=lambda x: x[0])
        pick = rows[:7]
        flows = [{"from_lat": m["lat"], "from_lon": m["lon"], "to_lat": g["lat"], "to_lon": g["lon"],
                  "from": f'{m["city"]}, {m["name"]}', "to": n["name"],
                  "label": f'{m["city"]} to {n["name"]}',
                  "sub": f'{km:,.0f} km · about {pages.hm(pages.flight_hours(km))} in the air'}
                 for km, m in pick]
        body += viz.flow_map(GEO_CACHE, flows, w=760, ident=f"flow-{r['id']}",
                             title="How far it is from the places people leave",
                             note=("Great-circle kilometres on a 6,371 km sphere, and that distance at "
                                   "850 km/h plus 45 minutes for the ground and the climb. Arithmetic, "
                                   "not a timetable: it knows nothing about routing, wind or a connection. "
                                   "The seven nearest source markets in this directory's list."))
    body += kin_block(r, by_id, depth)
    if r.get("images"):
        body += '<h2>Pictures</h2><div class="cards">' + "".join(
            f'<figure><img src="{img_src(im, depth)}" alt="{E(im.get("alt", ""))}" loading="lazy" '
            f'style="width:100%;border-radius:9px"><figcaption>{E(im.get("author", ""))} · '
            f'<a href="{E(im.get("page_url", "#"))}">{E(im.get("license", ""))}</a></figcaption></figure>'
            for im in r["images"]) + "</div>"
    if r.get("source_list"):
        body += "<h2>Sources</h2><ul>" + "".join(
            f'<li>{E(s.get("title", s["id"]))}'
            + (f' — {E(s["publisher"])}' if s.get("publisher") else "")
            + (f', {E(str(s["year"]))}' if s.get("year") else "")
            + (f' · <a href="{E(s["url"])}" rel="noopener">link</a>' if s.get("url") else "")
            + (f' <span class="mute">(read {E(s["accessed"])})</span>' if s.get("accessed") else "")
            + "</li>" for s in r["source_list"]) + "</ul>"
    body += ('<p class="legend">Where it came from: <span class="chip tier-cited">Cited</span> a source named here · '
             '<span class="chip tier-harvested">Harvested</span> pulled from an open dataset · '
             '<span class="chip tier-tradition">Trade practice</span> how the trade works, hedged · '
             '<span class="chip tier-inference">Inference</span> this project\'s own reasoning · '
             '<span class="chip tier-field">Field</span> somebody stood there. '
             f'<a href="{rel(depth)}api/{E(r["type"])}/{E(r["id"])}.json">This record as JSON</a>.</p>')
    return page(f"{n['name']} — {SITE_NAME}", body, depth, r["blurb"], node_jsonld(r),
                f"{SITE_URL}/{url_of(r)}", alt_json=f"{SITE_URL}/api/{r['type']}/{r['id']}.json",
                og_type="article" if r["type"] == "story" else "website",
                card=f'{r["type"]}__{r["id"]}', share_title=n["name"])


def type_index(t: dict, recs: list[dict], by_id: dict) -> str:
    rs = [r for r in recs if r["type"] == t["key"]]
    depth = 1
    groups: dict = {}
    for r in rs:
        groups.setdefault(group_key(r, t["group_by"]) or "—", []).append(r)
    body = (f'<h1><span class="kind">{E(SITE_NAME)}</span>{E(t["name"])} '
            f'<span class="count">({len(rs)})</span></h1><p class="lede">{E(t["blurb"])}</p>')
    if t["key"] == "dataset":
        body += pages.data_note(recs)
    for g, members in sorted(groups.items(), key=lambda kv: (kv[0] == "—", glabel(kv[0]))):
        members.sort(key=lambda r: (r["names"].get("sort") or r["names"]["name"]).lower())
        if len(groups) > 1:
            body += f'<h2>{E(glabel(g))} <span class="count">({len(members)})</span></h2>'
        body += '<div class="cards">' + "".join(
            f'<div class="card"><a class="t" href="{rel(depth)}{url_of(r)}index.html">{E(r["names"]["name"])}</a>'
            + (f'<p class="mute" style="font-size:.78rem">{E(", ".join(r["names"]["aliases"][:3]))}</p>'
               if r["names"].get("aliases") else "")
            + f'<p>{E(r["blurb"])}</p>'
            + (f'<p><span class="chip">{len(r["prices"])} published price'
               f'{"s" if len(r["prices"]) != 1 else ""}</span></p>' if r.get("prices") else "")
            + (f'<p><span class="chip">{len(r["legality"])} jurisdictions read</span></p>' if r.get("legality") else "")
            + "</div>" for r in members) + "</div>"
    jl = [{"@context": "https://schema.org", "@type": "ItemList", "name": f"{t['name']} — {SITE_NAME}",
           "url": f"{SITE_URL}/{DIR_OF[t['key']]}/",
           "itemListElement": [{"@type": "ListItem", "name": r["names"]["name"],
                                "url": f"{SITE_URL}/{url_of(r)}"} for r in rs]}]
    return page(f"{t['name']} — {SITE_NAME}", body, depth, t["blurb"], jl,
                f"{SITE_URL}/{DIR_OF[t['key']]}/", card=DIR_OF[t["key"]])


# ------------------------------------------------------------------ front

def fmt_amt(p: dict) -> str:
    return f'{p["amount"]:,.0f}' if p.get("amount") is not None else ""


def front_page(recs: list[dict], by_id: dict, countries: dict, types: dict, cov: dict,
               prices: dict, legality: dict, facilities: dict, geo: dict) -> str:
    depth = 0
    values = {}
    meta = countries["indicator_meta"]
    key = "spend_pc" if "spend_pc" in meta else (list(meta) or [None])[0]
    if key:
        wb = jload(DATA / "harvest" / "worldbank.json") if (DATA / "harvest" / "worldbank.json").exists() else None
        if wb:
            values = {iso: {"value": v["value"], "year": v["year"], "name": v.get("name")}
                      for iso, v in wb["indicators"][key]["values"].items()}
    body = ('<div class="hero"><h1><span class="kind">a directory of treatment across borders</span>'
            'Care Abroad</h1>'
            f'<p class="lede">{E(TAGLINE.capitalize())}. Countries, clusters, hospitals, operations, prices as '
            f'published, the law where the law is the reason, and the risks nobody quotes for. Every field says '
            f'where it came from.</p>'
            '<div class="cta"><a class="btn" href="prices/index.html">What it costs</a>'
            '<a class="btn ghost" href="map/index.html">The map</a>'
            '<a class="btn ghost" href="rules/index.html">Where it is lawful</a>'
            '<a class="btn ghost" href="near/index.html">From where you are</a>'
            '<a class="btn ghost" href="journey/index.html">The journey</a>'
            '<a class="btn ghost" href="risks/index.html">What goes wrong</a>'
            '<a class="btn ghost" href="wander.html">🎲 Anywhere</a></div></div>')
    body += viz.stat_tiles([
        (f'{sum(cov["records"].values()):,}', "records", ""),
        (f'{cov["countries_touched"]}', "countries", ""),
        (f'{prices["count"]:,}', "published prices", "each with its date"),
        (f'{legality["count"]:,}', "legality readings", ""),
        (f'{facilities["curated"]:,}', "hospitals written up", f'+{facilities["harvested"]:,} off the map'),
        (f'{sum(len(r.get("kin_out", [])) for r in recs):,}', "links between pages", ""),
    ])
    if values and key:
        body += viz.choropleth(geo, values, unit=meta[key]["unit"], w=940, ident="front-map",
                               title=meta[key]["name"],
                               note=("World Bank, each country at its own most recent reporting year. A hatched "
                                     "country is one the series does not carry. "
                                     "Other series, and this site's own coverage, are on the map page."))
    # what this site can answer, said as questions
    body += ('<div class="two-up">'
             '<div class="pitch"><h2 style="border:0;margin-top:0">Two reasons people fly</h2>'
             '<p>One is money: the operation costs less somewhere else, or the queue at home is fourteen months '
             'long. The other is law: the treatment is prohibited at home and lawful across a border. The '
             '<a href="prices/index.html">prices page</a> is the first. The '
             '<a href="rules/index.html">rules grid</a> is the second.</p></div>'
             '<div class="pitch"><h2 style="border:0;margin-top:0">The number under the number</h2>'
             '<p>A joint package priced at 356,500 baht excludes the implant, and the implant is often the '
             'largest line on the bill. Every price here carries the provider\'s own exclusion list, because '
             'that is where the difference between two quotes usually lives.</p></div></div>')
    # the newest prices, as a front-page fact rather than a promise
    newest = sorted(prices["prices"], key=lambda p: p["as_of"], reverse=True)[:8]
    if newest:
        body += '<h2>Lately read</h2><div class="cards">'
        for p in newest:
            on = by_id.get(p["on"])
            proc = by_id.get(p.get("procedure") or "")
            body += (f'<div class="card"><a class="t" href="{url_of(on)}index.html">'
                     f'{E(on["names"]["name"]) if on else E(p["on"])}</a>'
                     f'<p>{E(fmt_amt(p))} {E(p["currency"])}'
                     + (f' ≈ US${p["usd"]:,.0f}' if p.get("usd") else "")
                     + (f' · {E(proc["names"]["name"])}' if proc else "")
                     + f' · dated {E(p["as_of"])}</p></div>')
        body += "</div>"
    body += directory_sections(recs, types, depth, limit=7)
    body += ('<p class="legend">Plain prose is cited. <mark class="tier">Trade practice —</mark> means this is '
             'how the trade works, hedged; <mark class="tier">Inference —</mark> means this project worked it '
             'out. It is all <a href="api/index.json">JSON</a> as well, and the gaps are listed at '
             '<a href="coverage/index.html">coverage</a>.</p>')
    jl = [{"@context": "https://schema.org", "@type": "Dataset", "name": SITE_NAME,
           "description": ("A structured directory of treatment across borders: destination countries, city "
                           "clusters, procedures, hospitals, published prices, the rules that make a treatment "
                           "lawful or not for a visitor, the risks, the vocabulary and the datasets behind every "
                           "chart. One JSON record per node, with a provenance tier per field."),
           "url": SITE_URL + "/", "license": DATA_LICENSE, "creator": AUTHOR, "publisher": fleet.publisher_ld(), "includedInDataCatalog": fleet.catalog_ld(), "isAccessibleForFree": True,
           "keywords": ["medical travel", "cross-border healthcare", "patient mobility", "hospital prices",
                        "JCI accreditation", "health system indicators"],
           "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json",
                             "contentUrl": f"{SITE_URL}/api/nodes.json"},
                            {"@type": "DataDownload", "encodingFormat": "text/csv",
                             "contentUrl": f"{SITE_URL}/nodes.csv"},
                            {"@type": "DataDownload", "encodingFormat": "application/x-ndjson",
                             "contentUrl": f"{SITE_URL}/nodes.jsonl"}]},
          {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": SITE_URL + "/",
           "potentialAction": {"@type": "SearchAction",
                               "target": f"{SITE_URL}/search/?q={{search_term_string}}",
                               "query-input": "required name=search_term_string"}}]
    return page(f"{SITE_NAME} — {TAGLINE}", body, depth,
                "A directory of treatment across borders: countries, clusters, hospitals, procedures, published "
                "prices with their dates, the law, and the risks — each field with its source.",
                jl, SITE_URL + "/", card="index", share_title=SITE_NAME)


def wander_page(recs: list[dict]) -> str:
    urls = [url_of(r) for r in recs]
    body = ('<h1><span class="kind">🎲</span>Wander</h1><p class="lede">A page at random. If nothing happens, '
            'pick from the list.</p>'
            f'<script>(function(){{var u={json.dumps(urls)};location.replace(u[Math.floor(Math.random()*u.length)]+"index.html")}})();</script>'
            '<ul>' + "".join(f'<li><a href="{E(url_of(r))}index.html">{E(r["names"]["name"])}</a></li>'
                             for r in sorted(recs, key=lambda r: r["names"]["name"].lower())) + "</ul>")
    return page(f"Wander — {SITE_NAME}", body, 0, "A page at random.", None,
                f"{SITE_URL}/wander.html", '<meta name="robots" content="noindex">')


def sources_page(sources: dict) -> str:
    kinds: dict = {}
    for s in sources.values():
        kinds.setdefault(s.get("kind", "other"), []).append(s)
    body = (f'<h1><span class="kind">{E(SITE_NAME)}</span>Sources <span class="count">({len(sources)})</span></h1>'
            f'<p class="lede">Every source a record may cite, by id. A record citing anything else does not build.</p>')
    for k in ("org", "web", "dataset", "article", "book", "wikipedia", "law", "film", "other"):
        rows = kinds.get(k)
        if not rows:
            continue
        body += f'<h2>{E(k.replace("-", " ").title())} <span class="count">({len(rows)})</span></h2><ul>' + "".join(
            f'<li><code class="mute" style="font-size:.78rem">{E(s["id"])}</code> {E(s.get("title", ""))}'
            + (f' — {E(s["author"])}' if s.get("author") else "")
            + (f', {E(s["publisher"])}' if s.get("publisher") else "")
            + (f' {E(str(s["year"]))}' if s.get("year") else "")
            + (f' · <a href="{E(s["url"])}" rel="noopener">link</a>' if s.get("url") else "")
            + (f' <span class="mute">(read {E(s["accessed"])})</span>' if s.get("accessed") else "")
            + (f' <span class="mute">({E(s["license"])})</span>' if s.get("license") else "")
            + (f'<br><span class="mute" style="font-size:.85rem">{E(s["note"])}</span>' if s.get("note") else "")
            + "</li>" for s in sorted(rows, key=lambda s: s.get("title", ""))) + "</ul>"
    return page(f"Sources — {SITE_NAME}", body, 1, "Every source the records cite.", None,
                f"{SITE_URL}/sources/", card="sources")


def coverage_page(cov: dict) -> str:
    def cell(v):
        """A nested count table prints as a row of chips, not as raw JSON — the coverage
        page is the one a sceptical reader opens first."""
        if isinstance(v, dict):
            return " ".join(f'<span class="chip">{E(str(k).replace("_", " "))} <b>{E(x)}</b></span>'
                            for k, x in sorted(v.items(), key=lambda kv: (-kv[1] if isinstance(kv[1], (int, float)) else 0, kv[0])))
        if isinstance(v, list):
            return " ".join(f'<span class="chip">{E(x)}</span>' for x in v)
        if isinstance(v, bool) or v is None:
            return E("—" if v is None else v)
        return E(f"{v:,}" if isinstance(v, int) else v)

    def tbl(d):
        return "<table>" + "".join(
            f"<tr><th>{E(str(k).replace('_', ' '))}</th><td>{cell(v)}</td></tr>"
            for k, v in d.items()) + "</table>"
    body = (f'<h1><span class="kind">{E(SITE_NAME)}</span>Coverage</h1><p class="lede">{E(cov["scope"])}</p>'
            '<h2>Records</h2><table>' + "".join(
                f"<tr><th>{E(DIR_OF[t])}</th><td>{n}</td></tr>" for t, n in cov["records"].items()) + "</table>"
            f'<h2>How a record gets made</h2><p>{E(cov["how_records_are_made"])}</p>'
            '<h2>Prices</h2>' + tbl(cov["prices"])
            + '<h2>Law</h2>' + tbl(cov["legality"])
            + '<h2>Hospitals</h2>' + tbl(cov["facilities"])
            + '<h2>The series behind the charts</h2><table>'
            + '<tr><th>series</th><td><b>code</b> · unit · countries · newest year · fetched</td></tr>'
            + "".join(f'<tr><th>{E(k.replace("_", " "))}</th><td><b>{E(v["code"])}</b> · {E(v["unit"])} · '
                      f'{E(v["countries"])} countries · newest {E(v["newest_year"])} · fetched {E(v["fetched_at"])}</td></tr>'
                      for k, v in cov["indicators"].items()) + "</table>"
            + f'<h2>Pictures</h2><p>{cov["images"]["count"]} on file. The licences accepted are '
              f'{E(", ".join(cov["images"]["licences_accepted"]))}. The visuals on this site are drawn from the '
              f'data rather than photographed, which is why that number is small.</p>'
            + '<h2>Not here yet</h2><ul>' + "".join(f"<li>{E(x)}</li>" for x in cov["not_yet"]) + "</ul>"
            + '<h2>The marks</h2><table>' + "".join(
                f"<tr><th>{E(k)}</th><td>{E(v)}</td></tr>" for k, v in cov["tiers"].items()) + "</table>"
            + '<p class="mute">The same object as JSON: <a href="../api/coverage.json">api/coverage.json</a>.</p>')
    return page(f"Coverage — {SITE_NAME}", body, 1,
                "What this directory covers, where its rows come from, and what it has not got to.", None,
                f"{SITE_URL}/coverage/", card="coverage")


def search_page(n_docs: int) -> str:
    body = f"""
<h1><span class="kind">{E(SITE_NAME)}</span>Search</h1>
<p class="lede">Spell it however you spell it. If the match had to stretch, the page says so.</p>
<form class="search" role="search" onsubmit="return false"><input id="q" type="search" placeholder="knee · IVF · Bumrungrad · surrogacy · package price · Istanbul…" aria-label="Search" autofocus><button id="go" type="button">Search</button></form>
<p id="tier" class="tierline" aria-live="polite"></p>
<div id="out" class="cards"></div>
<p class="legend" id="how">Runs in your browser over all {n_docs} records: exact → same meaning, other word → near spellings → partial. The index is fetched once, then searched without another request.</p>
<script src="../vendor/searchcore.js"></script>
<script>
(function(){{
var DOCS=null, PATH={json.dumps(PATH_OF)};
var TABLES=null, core=null, index=null, PREP=null, byId={{}};
var TIER={{exact:"exact match",thesaurus:"same meaning, other word",loose:"near spellings — closest first",partial:"partial matches"}};
function esc(s){{return String(s==null?"":s).replace(/[&<>"]/g,function(c){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
function build(){{
  core=new SEARCHCORE.SearchCore(TABLES.groups||[],TABLES.words||[]);
  index=new SEARCHCORE.Index(core);
  PREP={{}};
  DOCS.forEach(function(d){{var f={{name:[d.names,3],terms:[d.terms,2],text:[d.text,1]}};index.add(d,f);PREP[d.id]=core.prepareDoc(f)}});
  index.finalize();
}}
function card(d,tier){{
  return '<div class="card"><a class="t" href="../'+PATH[d.type]+'/'+esc(d.id)+'/index.html">'+esc(d.name)+'</a><p class="mute" style="font-size:.76rem;text-transform:uppercase;letter-spacing:.12em">'+esc(d.type)+(d.country?' · '+esc(d.country):'')+'</p><p>'+esc(d.blurb)+'</p><p><span class="chip">'+esc(TIER[tier]||tier)+'</span></p></div>';
}}
function lexical(q){{
  var an=core.analyze(q,index); var rows=[];
  for(var id in PREP){{var r=core.scoreDoc(an,PREP[id]); if(r) rows.push({{id:id,tier:r.tier,score:r.score,coverage:r.coverage}})}}
  var whole=rows.filter(function(r){{return r.coverage>=1}}); var kept=whole.length?whole:rows;
  kept.sort(function(a,b){{return b.score-a.score}}); return kept.slice(0,36);
}}
function render(rows,worst){{
  var out=document.getElementById("out"), t=document.getElementById("tier");
  if(!rows.length){{out.innerHTML="";t.textContent="Nothing here answers to that yet.";return}}
  t.textContent=(TIER[worst]||worst);
  out.innerHTML=rows.map(function(r){{var d=byId[r.id];return d?card(d,r.tier):''}}).join("");
}}
function run(){{
  var q=document.getElementById("q").value.trim(); if(!q){{render([],null);return}}
  var lex=lexical(q); var worst=null;
  lex.forEach(function(r){{if(worst==null||SEARCHCORE.TIER_ORDER.indexOf(r.tier)>SEARCHCORE.TIER_ORDER.indexOf(worst))worst=r.tier}});
  render(lex,worst||"exact");
}}
Promise.all([fetch("tables.json").then(function(r){{return r.json()}}),
             fetch("docs.json").then(function(r){{return r.json()}})]).then(function(a){{
  TABLES=a[0]; DOCS=a[1].docs; DOCS.forEach(function(d){{byId[d.id]=d}}); build();
  var u=new URL(location.href); var q0=u.searchParams.get("q"); if(q0){{document.getElementById("q").value=q0;run()}}
}});
document.getElementById("go").addEventListener("click",run);
document.getElementById("q").addEventListener("keydown",function(e){{if(e.key==="Enter"&&!e.isComposing){{e.preventDefault();run()}}}});
document.getElementById("q").addEventListener("input",function(){{if(index)run()}});
}})();
</script>
"""
    return page(f"Search — {SITE_NAME}", body, 1, "Search every record.", None,
                f"{SITE_URL}/search/", card="search")


def manifest() -> str:
    return json.dumps({"name": SITE_NAME, "short_name": "Care Abroad", "start_url": "./index.html",
                       "display": "standalone", "background_color": "#f7f6f2", "theme_color": "#2a78d6",
                       "description": TAGLINE,
                       "icons": [{"src": "icon.svg", "sizes": "any", "type": "image/svg+xml"}]}, indent=1)


def icon_svg() -> str:
    # a boarding pass and a cross, which is the whole subject in two marks
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            '<rect width="64" height="64" rx="12" fill="#2a78d6"/>'
            '<rect x="12" y="20" width="40" height="26" rx="5" fill="#f7f6f2"/>'
            '<circle cx="32" cy="33" r="9" fill="#2a78d6"/>'
            '<rect x="30" y="27" width="4" height="12" rx="1.4" fill="#f7f6f2"/>'
            '<rect x="26" y="31" width="12" height="4" rx="1.4" fill="#f7f6f2"/>'
            '<circle cx="18" cy="33" r="2.2" fill="#2a78d6"/><circle cx="46" cy="33" r="2.2" fill="#2a78d6"/></svg>')


def llms_txt(recs: list[dict], cov: dict) -> str:
    lines = [f"# {SITE_NAME}", "",
             "> A structured directory of treatment across borders: destination countries, city clusters, "
             "procedures, hospitals, published prices with their dates and inclusion lists, the rules that make "
             "a treatment lawful or not for a visitor, the risks, the vocabulary, and the datasets behind every "
             "chart. One JSON record per node; each field carries a provenance tier (cited / harvested / "
             "tradition / inference / field); records say what their neighbours are to them in both directions.",
             "", f"Records are CC BY 4.0 ({DATA_LICENSE}). Country outlines Natural Earth, public domain. "
                 f"Health indicators World Bank Open Data, CC BY 4.0. Hospital points OpenStreetMap, ODbL 1.0 "
                 f"(share-alike). Scope and gaps: {SITE_URL}/api/coverage.json",
             "", "Nothing here is medical or legal advice.",
             "", "## Data",
             f"- [All records, JSON]({SITE_URL}/api/nodes.json)",
             f"- [Directory index, JSON]({SITE_URL}/api/index.json)",
             f"- [Countries: records, indicators, prices, accreditations]({SITE_URL}/api/countries.json)",
             f"- [Every published price]({SITE_URL}/api/prices.json)",
             f"- [The legality grid]({SITE_URL}/api/legality.json)",
             f"- [Hospitals, written up + OpenStreetMap]({SITE_URL}/api/facilities.json)",
             f"- [Kin edges]({SITE_URL}/api/kin.json)",
             f"- [JSONL]({SITE_URL}/nodes.jsonl) · [CSV]({SITE_URL}/nodes.csv)",
             f"- [Record schema]({SITE_URL}/schema/node.schema.json)",
             f"- [Sources registry]({SITE_URL}/api/sources.json)",
             f"- [Full text of every record]({SITE_URL}/llms-full.txt)", ""]
    for t in TYPES:
        rs = sorted([r for r in recs if r["type"] == t], key=lambda r: r["names"]["name"].lower())
        if not rs:
            continue
        lines.append(f"## {DIR_OF[t].replace('-', ' ').title()}")
        for r in rs:
            lines.append(f"- [{r['names']['name']}]({SITE_URL}/{url_of(r)}): {r['blurb']}")
        lines.append("")
    lines += ["## Optional", f"- [Search]({SITE_URL}/search/)", f"- [World map]({SITE_URL}/map/)",
              f"- [Prices]({SITE_URL}/prices/)", f"- [Rules]({SITE_URL}/rules/)",
              f"- [Atom feed]({SITE_URL}/feed.xml)", f"- [Sitemap]({SITE_URL}/sitemap.xml)"]
    return "\n".join(lines) + "\n"


def llms_full(recs: list[dict], sources: dict) -> str:
    out = [f"# {SITE_NAME} — every record, flattened\n"]
    for t in TYPES:
        for r in sorted([r for r in recs if r["type"] == t], key=lambda r: r["names"]["name"].lower()):
            n = r["names"]
            out.append(f"## {n['name']} ({t})\nURL: {SITE_URL}/{url_of(r)}\n"
                       f"JSON: {SITE_URL}/api/{t}/{r['id']}.json\nid: {r['id']}")
            if n.get("aliases"):
                out.append("aliases: " + " · ".join(n["aliases"]))
            if n.get("said"):
                out.append("said: " + n["said"])
            et = r.get("etymology") or {}
            if et.get("root"):
                out.append(f"root: {et['root']}"
                           + (f" · first seen: {et['first_attested']}" if et.get("first_attested") else ""))
            if r.get("facets"):
                out.append("facets: " + " · ".join(
                    f"{k}={', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in r["facets"].items()))
            out.append("region: " + ", ".join(t2.get("name", t2["key"]) for t2 in r["region_terms"]))
            for k in ("what", "story", "how", "today", "notes"):
                if r["text"].get(k):
                    out.append(f"{k}: {r['text'][k]}")
            a = r.get("address") or {}
            if a:
                out.append("address: " + ", ".join(
                    x for x in (a.get("street"), a.get("city"), a.get("area"), a.get("country")) if x))
            if r.get("geo"):
                out.append(f"geo: {r['geo']['lat']}, {r['geo']['lon']} ({r['geo'].get('precision', '')})")
            m = r.get("metrics") or {}
            if m:
                out.append("metrics: " + " · ".join(f"{k}={v}" for k, v in m.items() if v is not None))
            for p in r.get("prices", []):
                out.append(f"- price: {p.get('amount')} {p['currency']}"
                           + (f" (US${p['usd']:,.0f})" if p.get("usd") else "")
                           + f" · {p['kind']} · {p['country']} · dated {p['as_of']}"
                           + (f" · includes {'; '.join(p.get('includes', []))}" if p.get("includes") else "")
                           + (f" · EXCLUDES {'; '.join(p.get('excludes', []))}" if p.get("excludes") else "")
                           + (f" · {p.get('url', '')}" if p.get("url") else ""))
            for lg in r.get("legality", []):
                out.append(f"- law: {lg['country']} {lg['status']}"
                           + (f" — {lg.get('instrument', '')}" if lg.get("instrument") else "")
                           + (f" ({lg.get('conditions', '')})" if lg.get("conditions") else "")
                           + f" · read {lg['as_of']}")
            for x in r.get("recognitions", []):
                out.append(f"- accreditation: {x['by']} — {x['what']}"
                           + (f" ({x.get('year')})" if x.get("year") else ""))
            for k in r.get("kin_out", []):
                out.append(f"- kin → {k['to']} ({k['type']}): {k['as']}")
            for c in r.get("confusable_with", []):
                out.append(f"- not to be confused with {c['id']}: {c['tell']}")
            out.append("sources: " + "; ".join(
                f"{s} — {sources[s].get('title', '')}" for s in r.get("sources", []) if s in sources))
            out.append(f"provenance default: {r['provenance']['default'].get('tier')} · "
                       f"confidence: {r['confidence']} · needs_verification: {r.get('needs_verification', False)} · "
                       f"updated: {r['updated']}\n")
    return "\n".join(out)


def sitemap(recs: list[dict]) -> str:
    today = time.strftime("%Y-%m-%d")
    urls = [(SITE_URL + "/", max((r["updated"] for r in recs), default=today))]
    for seg in ("search", "map", "prices", "rules", "near", "numbers", "journey", "sources", "coverage"):
        urls.append((f"{SITE_URL}/{seg}/", today))
    urls += [(f"{SITE_URL}/{DIR_OF[t]}/", today) for t in TYPES]
    body = [f"<url><loc>{E(u)}</loc><lastmod>{E(d)}</lastmod></url>" for u, d in urls]
    for r in recs:
        body.append(f"<url><loc>{E(SITE_URL + '/' + url_of(r))}</loc><lastmod>{E(r['updated'])}</lastmod></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(body) + "</urlset>\n")


def ai_txt() -> str:
    return (f"# {SITE_NAME} — {SITE_URL}/\n"
            "# Everything here is meant to be read by machines as well as people.\n\n"
            "User-agent: *\nAllow: /\n\n"
            "Content-Signal: search=yes, ai-input=yes, ai-train=yes\n\n"
            f"Corpus: {SITE_URL}/llms.txt\nFull-text: {SITE_URL}/llms-full.txt\n"
            f"Records: {SITE_URL}/api/nodes.json\nCountries: {SITE_URL}/api/countries.json\n"
            f"Prices: {SITE_URL}/api/prices.json\nLaw: {SITE_URL}/api/legality.json\n"
            f"Hospitals: {SITE_URL}/api/facilities.json\nScope and gaps: {SITE_URL}/api/coverage.json\n"
            f"Schema: {SITE_URL}/schema/node.schema.json\nTabular: {SITE_URL}/nodes.csv · {SITE_URL}/nodes.jsonl\n\n"
            "Licence: records CC BY 4.0. Country outlines Natural Earth, public domain. Health indicators\n"
            "World Bank Open Data, CC BY 4.0. Hospital points OpenStreetMap, ODbL 1.0 (share-alike).\n"
            f"Attribution: {SITE_NAME}, {SITE_URL}/\n\n"
            "Each field carries a provenance tier: cited, harvested, tradition, inference, field.\n"
            "A price carries the date it was published and the provider's own exclusion list.\n"
            "A legality row is one reading of one named instrument on one date.\n"
            "Nothing here is medical or legal advice.\n")


def humans_txt(recs: list[dict], cov: dict) -> str:
    return ("/* CARE ABROAD */\n\n"
            "Built by NaN — https://wichaa.net\n"
            f"{sum(cov['records'].values())} records · {cov['prices']['rows']} published prices · "
            f"{cov['legality']['rows']} legality readings · {cov['sources']} sources\n\n"
            "/* THANKS */\n"
            "OpenStreetMap contributors, for every hospital point.\n"
            "The World Bank and the WHO, for the only comparable country series there are.\n"
            "Natural Earth, for outlines nobody charges for.\n"
            "The regulators who publish clinic-level results, who are still a minority.\n\n"
            "/* SITE */\n"
            "Stdlib Python, no dependencies, no build step.\n"
            "Standards: HTML, JSON-LD, llms.txt, Atom, OpenSearch, ODbL, CC BY.\n"
            "Maps in Equal Earth, because a choropleth on Mercator is an argument, not a map.\n")


def robots() -> str:
    return (f"# {SITE_NAME}: everything here is meant to be read, indexed, quoted and learned from.\n"
            "User-agent: *\nAllow: /\n\n"
            "# Content signals (https://contentsignals.org): yes to search, yes to AI input, yes to AI training.\n"
            "Content-Signal: search=yes, ai-input=yes, ai-train=yes\n\n"
            f"Sitemap: {SITE_URL}/sitemap.xml\n"
            f"# Corpus for language models: {SITE_URL}/llms.txt and {SITE_URL}/llms-full.txt\n"
            f"# Machine terms: {SITE_URL}/ai.txt\n")


def opensearch() -> str:
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<OpenSearchDescription '
            f'xmlns="http://a9.com/-/spec/opensearch/1.1/"><ShortName>{E(SITE_NAME)}</ShortName>'
            f'<Description>Search the {E(SITE_NAME)} directory</Description><InputEncoding>UTF-8</InputEncoding>'
            f'<Url type="text/html" template="{E(SITE_URL)}/search/?q={{searchTerms}}"/></OpenSearchDescription>\n')


def feed(recs: list[dict]) -> str:
    rs = sorted(recs, key=lambda r: r["updated"], reverse=True)[:60]
    upd = (rs[0]["updated"] if rs else time.strftime("%Y-%m-%d")) + "T00:00:00Z"
    ents = "".join(
        f'<entry><title>{E(r["names"]["name"])}</title><link href="{E(SITE_URL + "/" + url_of(r))}"/>'
        f'<id>{E(SITE_URL + "/" + url_of(r))}</id><updated>{E(r["updated"])}T00:00:00Z</updated>'
        f'<summary>{E(r["blurb"])}</summary></entry>' for r in rs)
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
            f'<title>{E(SITE_NAME)}</title><link href="{E(SITE_URL)}/"/>'
            f'<link rel="self" href="{E(SITE_URL)}/feed.xml"/>'
            f'<id>{E(SITE_URL)}/</id><updated>{upd}</updated><author><name>NaN</name></author>{ents}</feed>\n')


def dumps(recs: list[dict], prices: dict, legality: dict):
    rows = []
    for r in recs:
        f = r.get("facets") or {}
        a = r.get("address") or {}
        g = r.get("geo") or {}
        rows.append({"id": r["id"], "type": r["type"], "name": r["names"]["name"],
                     "aliases": "|".join(r["names"].get("aliases", [])), "region": "|".join(r["region"]),
                     "country": f.get("iso2") or a.get("country", ""), "city": a.get("city", ""),
                     "lat": g.get("lat", ""), "lon": g.get("lon", ""),
                     "facets": json.dumps(f, ensure_ascii=False) if f else "",
                     "what": r["text"]["what"], "prices": len(r.get("prices", [])),
                     "legality_rows": len(r.get("legality", [])),
                     "kin": "|".join(k["to"] for k in r.get("kin_out", [])),
                     "sources": "|".join(r.get("sources", [])),
                     "tier": r["provenance"]["default"].get("tier", ""), "confidence": r["confidence"],
                     "needs_verification": r.get("needs_verification", False), "updated": r["updated"],
                     "url": f"{SITE_URL}/{url_of(r)}"})
    with open(SITE / "nodes.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["id"])
        w.writeheader()
        w.writerows(rows)
    with open(SITE / "nodes.jsonl", "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps({k: v for k, v in r.items() if k not in ("tiers",)}, ensure_ascii=False) + "\n")
    with open(SITE / "prices.csv", "w", encoding="utf-8", newline="") as fh:
        cols = ["on", "procedure", "facility", "country", "city", "amount", "amount_high", "currency",
                "usd", "usd_high", "as_of", "rate_date", "kind", "source", "url"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(prices["prices"])
    with open(SITE / "legality.csv", "w", encoding="utf-8", newline="") as fh:
        cols = ["subject", "subject_name", "country", "status", "conditions", "instrument", "as_of", "source", "url"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(legality["rows"])


# ------------------------------------------------------------------ main

def main() -> int:
    if not (API / "nodes.json").exists():
        print("run tools/build.py first")
        return 1
    t0 = time.time()
    recs = jload(API / "nodes.json")["nodes"]
    by_id = {r["id"]: r for r in recs}
    sources = {s["id"]: s for s in jload(API / "sources.json")["sources"]}
    countries = jload(API / "countries.json")
    prices = jload(API / "prices.json")
    legality = jload(API / "legality.json")
    facilities = jload(API / "facilities.json")
    types = jload(API / "vocab" / "types.json")
    markets = jload(API / "vocab" / "markets.json")
    cov = jload(API / "coverage.json")
    geo = jload(GEO / "countries.json")
    global GEO_CACHE, ISO_NAME, REGION_LABEL, MARKETS
    GEO_CACHE = geo
    MARKETS = markets["entries"]
    global OSM_BY_HUB
    osm_path = DATA / "harvest" / "osm-facilities.json"
    if osm_path.exists():
        for row in jload(osm_path).get("places", []):
            if row.get("hub"):
                OSM_BY_HUB.setdefault(row["hub"], []).append(row)
    ISO_NAME = {c["iso"]: c["name"] for c in geo["countries"]}
    REGION_LABEL = {e["key"]: e["name"] for e in jload(API / "vocab" / "regions.json")["entries"]}
    pages.set_iso_names(ISO_NAME)
    global PRICES_BY_PROC
    for row in prices["prices"]:
        if row.get("procedure"):
            PRICES_BY_PROC.setdefault(row["procedure"], []).append(row)

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    shutil.copytree(API, SITE / "api")
    shutil.copytree(ROOT / "schema", SITE / "schema")
    (SITE / "vendor").mkdir()
    core_js = VENDOR / "searchcore.js"
    if not core_js.exists():
        print("vendor/searchcore.js missing")
        return 1
    shutil.copy(core_js, SITE / "vendor" / "searchcore.js")
    for r in recs:
        for im in r.get("images", []):
            src = IMAGES / im["file"]
            if src.exists():
                dst = SITE / "images" / im["file"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)

    (SITE / "index.html").write_text(
        front_page(recs, by_id, countries, types, cov, prices, legality, facilities, geo), encoding="utf-8")
    (SITE / "wander.html").write_text(wander_page(recs), encoding="utf-8")
    for t in types["entries"]:
        d = SITE / DIR_OF[t["key"]]
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(type_index(t, recs, by_id), encoding="utf-8")
    for r in recs:
        d = SITE / url_of(r)
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(node_page(r, by_id, sources, countries), encoding="utf-8")
    for name, html_text in (
            ("map", pages.map_page(page, countries, geo, recs, SITE_URL,
                                   jload(DATA / "harvest" / "worldbank.json")
                                   if (DATA / "harvest" / "worldbank.json").exists() else None)),
            ("prices", pages.prices_page(page, prices, recs, SITE_URL)),
            ("rules", pages.rules_page(page, legality, recs, geo, SITE_URL)),
            ("near", pages.near_page(page, markets, recs, facilities, geo, SITE_URL)),
            ("numbers", pages.numbers_page(page, recs, countries, prices, legality, cov, facilities, geo, SITE_URL)),
            ("sources", sources_page(sources)),
            ("coverage", coverage_page(cov))):
        d = SITE / name
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(html_text, encoding="utf-8")
    # /journey/ is the pathway type index, written over with the ordered walk
    (SITE / "journey").mkdir(exist_ok=True)
    (SITE / "journey" / "index.html").write_text(pages.journey_page(page, recs, SITE_URL), encoding="utf-8")

    docs = jload(BUILD / "searchdocs.json")["docs"]
    (SITE / "search").mkdir(exist_ok=True)
    (SITE / "search" / "index.html").write_text(search_page(len(docs)), encoding="utf-8")
    (SITE / "search" / "docs.json").write_text(
        json.dumps({"built": time.strftime("%Y-%m-%d"), "docs": docs}, ensure_ascii=False), encoding="utf-8")
    groups = []
    p = DATA / "search" / "care.thesaurus.json"
    if p.exists():
        groups += jload(p).get("groups", [])
    (SITE / "search" / "tables.json").write_text(
        json.dumps({"groups": groups, "words": []}, ensure_ascii=False), encoding="utf-8")

    (SITE / "llms.txt").write_text(llms_txt(recs, cov), encoding="utf-8")

    fleet.decorate(SITE, "care-abroad")
    (SITE / "llms-full.txt").write_text(llms_full(recs, sources), encoding="utf-8")
    (SITE / "sitemap.xml").write_text(sitemap(recs), encoding="utf-8")
    (SITE / "robots.txt").write_text(robots(), encoding="utf-8")
    (SITE / "opensearch.xml").write_text(opensearch(), encoding="utf-8")
    (SITE / "feed.xml").write_text(feed(recs), encoding="utf-8")
    (SITE / "manifest.webmanifest").write_text(manifest(), encoding="utf-8")
    (SITE / "humans.txt").write_text(humans_txt(recs, cov), encoding="utf-8")
    wk = SITE / ".well-known"
    wk.mkdir(exist_ok=True)
    (wk / "ai.txt").write_text(ai_txt(), encoding="utf-8")
    (SITE / "ai.txt").write_text(ai_txt(), encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    (SITE / "icon.svg").write_text(icon_svg(), encoding="utf-8")
    if CARDS_DIR.exists():
        shutil.copytree(CARDS_DIR, SITE / "cards")
    dumps(recs, prices, legality)
    n_html = sum(1 for _ in SITE.rglob("*.html"))
    leaks = [p for p in SITE.rglob("*") if p.is_file() and p.suffix in (".html", ".json", ".txt", ".xml", ".csv", ".jsonl")
             and "/Users/" in p.read_text(encoding="utf-8", errors="ignore")]
    if leaks:
        print("REFUSED: host paths in", [str(p.relative_to(SITE)) for p in leaks][:5])
        return 2
    print(f"site: {n_html} pages · {len(recs)} records · {prices['count']} prices · "
          f"{legality['count']} legality rows · {facilities['count']} hospital points · "
          f"{SITE} · {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
