"""viz.py — every chart on this site, drawn as inline SVG from the records.

There are almost no photographs here, so the pictures are the data. The rules each
figure follows:

  · one hue, light to dark, for magnitude; two hues and a grey middle for polarity;
    the first three categorical slots only, because past three no ordering clears the
    colour-blind separation gates on an all-pairs form like a map
  · colour is not the only carrier — a matrix cell takes a glyph, a series takes a
    direct label or a legend, a map takes a table under it
  · a figure carries a table twin, so the numbers can be read, copied and checked
  · light and dark are separate steps off the same ramp, not an inversion
  · a missing value is drawn as missing — hatched, labelled and counted, rather than as zero

Values arrive from build/api; nothing here computes one the records did not state.
"""
from __future__ import annotations

import html
import math
import re

import worldmap

# ---------------------------------------------------------------- the palette
# Sequential blue, 100 → 700. Magnitude on every map and heat grid.
SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
       "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
SEQ_DARK = ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6",
            "#3987e5", "#5598e7", "#6da7ec", "#86b6ef", "#9ec5f4", "#b7d3f6", "#cde2fb"]
CAT = ["#2a78d6", "#eb6834", "#1baf7a"]
CAT_DARK = ["#3987e5", "#d95926", "#199e70"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}

# The six legality states. Each carries a glyph as well as a colour, because a reader
# who cannot separate the hues still has to be able to read the grid.
LEGAL = {
    "lawful":                 {"fill": "#0ca30c", "glyph": "●", "label": "Lawful for a visitor"},
    "lawful-with-conditions": {"fill": "#fab219", "glyph": "◐", "label": "Lawful, with conditions"},
    "residents-only":         {"fill": "#ec835a", "glyph": "◑", "label": "Residents only"},
    "unlawful":               {"fill": "#d03b3b", "glyph": "✕", "label": "Prohibited"},
    "unregulated":            {"fill": "#8a8a84", "glyph": "○", "label": "No instrument either way"},
    "no-data":                {"fill": "none",    "glyph": "·", "label": "Not read by this project"},
}

CSS = """
.fig{margin:1.1rem 0 1.4rem}
.fig svg{width:100%;height:auto;display:block}
.fig figcaption{font-size:.83rem;color:var(--mute);margin-top:.45rem;font-family:var(--ui)}
.fig .head{font-family:var(--display);font-weight:700;font-size:1.02rem;margin:0 0 .15rem}
.fig .sub{font-size:.85rem;color:var(--mute);margin:0 0 .5rem}
.viz-grid{stroke:var(--line);stroke-width:1;fill:none}
.viz-ax{font:500 11px var(--ui);fill:var(--mute)}
.viz-lab{font:600 11.5px var(--ui);fill:var(--ink)}
.viz-val{font:600 11.5px var(--ui);fill:var(--ink)}
.viz-land{fill:var(--land);stroke:var(--landline);stroke-width:.7}
.viz-nodata{fill:url(#hatch);stroke:var(--line);stroke-width:.6}
.viz-grat{stroke:var(--line);stroke-width:.5;fill:none;opacity:.55}
.viz-cell{stroke:var(--panel);stroke-width:2}
.viz-dot{stroke:var(--panel);stroke-width:2}
.osmdot{r:2.6;opacity:.72}
.viz-arc{fill:none;stroke-width:1.4;opacity:.75}
.twin{margin:.5rem 0 0}
.twin summary{cursor:pointer;font-size:.84rem;color:var(--mute);font-family:var(--ui)}
.twin table{font-size:.86rem;margin:.5rem 0 0}
.twin th{width:auto}
.vtip{position:fixed;z-index:60;pointer-events:none;background:var(--panel);border:1px solid var(--line);
  border-radius:9px;padding:.4rem .6rem;font:500 .82rem/1.35 var(--ui);color:var(--ink);
  box-shadow:0 8px 22px rgba(0,0,0,.16);max-width:19rem}
.vtip b{display:block;font-size:.9rem}
.vkey{display:flex;flex-wrap:wrap;gap:.3rem .9rem;font-size:.8rem;color:var(--mute);
  font-family:var(--ui);margin:.45rem 0 0;align-items:center}
.vkey i{width:.85rem;height:.85rem;border-radius:3px;display:inline-block;vertical-align:-1px;margin-right:.3rem}
.vramp{display:flex;align-items:center;gap:.4rem;font-size:.78rem;color:var(--mute);font-family:var(--ui);margin-top:.4rem}
.vramp .steps{display:flex;height:.7rem;border-radius:3px;overflow:hidden;flex:0 0 12rem}
.vramp .steps span{flex:1}

/* The sequential ramp and the three categorical slots as classes rather than baked
   fills. Dark mode takes its own steps off the same blue ramp rather than an
   inversion of the light ones. The dark ramp starts at the 550 step rather than the 700:
   below that a country sits within about 2:1 of the dark surface and a whole continent
   reads as unmapped when it is merely at the low end. */
.seq-0{fill:#cde2fb}
.seq-1{fill:#b7d3f6}
.seq-2{fill:#9ec5f4}
.seq-3{fill:#86b6ef}
.seq-4{fill:#6da7ec}
.seq-5{fill:#5598e7}
.seq-6{fill:#3987e5}
.seq-7{fill:#2a78d6}
.seq-8{fill:#256abf}
.seq-9{fill:#1c5cab}
.seq-10{fill:#184f95}
.seq-11{fill:#104281}
.seq-12{fill:#0d366b}
.s1{fill:#2a78d6}.s2{fill:#eb6834}.s3{fill:#1baf7a}
.st1{stroke:#2a78d6}.st2{stroke:#eb6834}.st3{stroke:#1baf7a}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) {
.seq-0{fill:#184f95}.seq-1{fill:#1c5cab}.seq-2{fill:#256abf}.seq-3{fill:#2a78d6}.seq-4{fill:#3987e5}.seq-5{fill:#5598e7}.seq-6{fill:#6da7ec}.seq-7{fill:#86b6ef}.seq-8{fill:#9ec5f4}.seq-9{fill:#b7d3f6}.seq-10{fill:#cde2fb}.seq-11{fill:#deebfd}.seq-12{fill:#eef4fe}.s1{fill:#3987e5}.s2{fill:#d95926}.s3{fill:#199e70}.st1{stroke:#3987e5}.st2{stroke:#d95926}.st3{stroke:#199e70}
}}
:root[data-theme="dark"]{
.seq-0{fill:#184f95}.seq-1{fill:#1c5cab}.seq-2{fill:#256abf}.seq-3{fill:#2a78d6}.seq-4{fill:#3987e5}.seq-5{fill:#5598e7}.seq-6{fill:#6da7ec}.seq-7{fill:#86b6ef}.seq-8{fill:#9ec5f4}.seq-9{fill:#b7d3f6}.seq-10{fill:#cde2fb}.seq-11{fill:#deebfd}.seq-12{fill:#eef4fe}.s1{fill:#3987e5}.s2{fill:#d95926}.s3{fill:#199e70}.st1{stroke:#3987e5}.st2{stroke:#d95926}.st3{stroke:#199e70}
}
"""

TIP_JS = """
(function(){var t=null;
function show(e){var el=e.target.closest('[data-tip]');if(!el){hide();return}
 if(!t){t=document.createElement('div');t.className='vtip';document.body.appendChild(t)}
 t.innerHTML=el.getAttribute('data-tip');t.style.display='block';
 var x=e.clientX+14,y=e.clientY+14;var r=t.getBoundingClientRect();
 if(x+r.width>innerWidth-8)x=e.clientX-r.width-14; if(y+r.height>innerHeight-8)y=e.clientY-r.height-14;
 t.style.left=x+'px';t.style.top=y+'px'}
function hide(){if(t)t.style.display='none'}
document.addEventListener('mousemove',show,{passive:true});
document.addEventListener('mouseleave',hide);
document.addEventListener('scroll',hide,{passive:true});})();
"""

DARK_CSS = """
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .seq-0{fill:#0d366b}}
"""


def E(x) -> str:
    return html.escape("" if x is None else str(x))


def fmt(v, unit=""):
    if v is None:
        return "—"
    if isinstance(v, str):
        return v
    a = abs(v)
    if a >= 1e9:
        s = f"{v/1e9:.1f}bn"
    elif a >= 1e6:
        s = f"{v/1e6:.1f}m"
    elif a >= 1000:
        s = f"{v:,.0f}"
    elif a >= 10:
        s = f"{v:,.0f}"
    elif a >= 1:
        s = f"{v:.1f}"
    else:
        s = f"{v:.2f}"
    return s + (f" {unit}" if unit else "")


def _quantiles(vals: list, n: int) -> list:
    """Bin edges at equal counts, de-duplicated. Equal-count bins are what a skewed
    distribution needs: health spending runs from $20 to $12,000 a head, and equal-width
    bins would paint 180 countries the same colour."""
    s = sorted(vals)
    if not s:
        return []
    out = []
    for i in range(1, n):
        q = s[int(len(s) * i / n)]
        if not out or q > out[-1]:
            out.append(q)
    return out


def _bin(v, edges) -> int:
    i = 0
    for e in edges:
        if v >= e:
            i += 1
    return i


def table_twin(headers: list, rows: list, summary: str, note: str = "") -> str:
    th = "".join(f"<th>{E(h)}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return (f'<details class="twin"><summary>{E(summary)}</summary>'
            + (f'<p class="mute" style="font-size:.83rem">{E(note)}</p>' if note else "")
            + f'<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></details>')


def swatch(cls: str, n: int = 13) -> str:
    """A legend chip that takes its colour from the same class the mark does, so the two
    cannot drift apart between themes."""
    return (f'<svg width="{n}" height="{n}" style="vertical-align:-1px;margin-right:.3rem" aria-hidden="true">'
            f'<rect class="{cls}" width="{n}" height="{n}" rx="3"/></svg>')


def defs() -> str:
    return ('<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
            'patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--panel)"/>'
            '<line x1="0" y1="0" x2="0" y2="6" stroke="var(--line)" stroke-width="2.4"/></pattern></defs>')


# ---------------------------------------------------------------- the world map

def choropleth(geo: dict, values: dict, *, unit="", title="", note="", w=900,
               bins=7, ident="map", label_fn=None, lon0=0.0) -> str:
    """Countries coloured by one number. values: {ISO2: {"value": x, "year": y, "name": n}}.

    A country with no value is hatched, not white and not zero — the difference between
    "nobody reports this" and "this is small" is the whole argument of the coverage page.
    """
    fit = worldmap.fit_world(geo, w, lon0=lon0)
    vals = [v["value"] for v in values.values() if v.get("value") is not None]
    edges = _quantiles(vals, bins)
    paths, missing = [], 0
    for iso, name, d in worldmap.country_paths(geo, fit):
        v = values.get(iso)
        if not v or v.get("value") is None:
            missing += 1
            paths.append(f'<path class="viz-nodata" d="{d}" data-tip="<b>{E(name)}</b>Nothing here yet."></path>')
            continue
        i = min(_bin(v["value"], edges), len(SEQ) - 1)
        extra = label_fn(iso, v) if label_fn else ""
        tip = (f'<b>{E(v.get("name") or name)}</b>{E(fmt(v["value"], unit))}'
               + (f' &middot; {E(v["year"])}' if v.get("year") else "") + extra)
        paths.append(f'<path class="seq-{i}" d="{d}" '
                     f'stroke="var(--panel)" stroke-width=".5" data-tip="{tip}"></path>')
    # the ramp legend, with the bin edges printed
    steps = "".join('<span><svg viewBox="0 0 1 1" preserveAspectRatio="none" style="width:100%;height:100%;display:block">'
                    f'<rect class="seq-{min(i, len(SEQ)-1)}" width="1" height="1"/></svg></span>' for i in range(bins))
    lo, hi = (min(vals), max(vals)) if vals else (0, 0)
    ramp = (f'<div class="vramp"><span>{E(fmt(lo, unit))}</span><span class="steps">{steps}</span>'
            f'<span>{E(fmt(hi, unit))}</span>'
            f'<span style="margin-left:.6rem"><i style="background:var(--chip);border:1px solid var(--line);'
            f'width:.85rem;height:.85rem;border-radius:3px;display:inline-block"></i> '
            f'{missing} countries with no value</span></div>')
    rows = sorted(((v.get("name") or iso), iso, v.get("value"), v.get("year"))
                  for iso, v in values.items() if v.get("value") is not None)
    twin = table_twin(["Country", "ISO", unit or "Value", "Year"],
                      [[E(n), E(i), E(fmt(x)), E(y)] for n, i, x, y in rows],
                      f"The {len(rows)} values behind this map",
                      "Each value is that country's most recent reporting year, which is why the years differ.")
    head = (f'<p class="head">{E(title)}</p>' if title else "")
    return (f'<figure class="fig" id="{E(ident)}">{head}'
            f'<svg viewBox="0 0 {w:.0f} {fit["h"]:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="{E(title or "World map")}">{defs()}'
            f'<path class="viz-grat" d="{worldmap.graticule(fit)}"/>{"".join(paths)}</svg>'
            f'{ramp}' + (f'<figcaption>{E(note)}</figcaption>' if note else "") + twin + '</figure>')


def flow_map(geo: dict, flows: list, *, w=900, title="", note="", ident="flows", lon0=0.0) -> str:
    """Great-circle arcs from source market to destination hub. flows: dicts with
    from_lat/from_lon/to_lat/to_lon/from/to/label."""
    fit = worldmap.fit_world(geo, w, lon0=lon0)
    land = "".join(f'<path class="viz-land" d="{d}"/>' for _, _, d in worldmap.country_paths(geo, fit))
    arcs, dots = [], {}
    for f in flows:
        d = worldmap.arc(f["from_lon"], f["from_lat"], f["to_lon"], f["to_lat"], fit)
        if not d:
            continue
        arcs.append(f'<path class="viz-arc st1" d="{d}" '
                    f'data-tip="<b>{E(f.get("label", ""))}</b>{E(f.get("sub", ""))}"></path>')
        for key, la, lo, nm in (("f", f["from_lat"], f["from_lon"], f.get("from", "")),
                                ("t", f["to_lat"], f["to_lon"], f.get("to", ""))):
            x, y = worldmap.project(lo, la, fit)
            dots[(round(x, 1), round(y, 1))] = (nm, key)
    for (x, y), (nm, key) in dots.items():
        r = 4.2 if key == "t" else 3.0
        cls = "s2" if key == "t" else "s3"
        arcs.append(f'<circle class="viz-dot {cls}" cx="{x}" cy="{y}" r="{r}" data-tip="<b>{E(nm)}</b>"></circle>')
    key = (f'<div class="vkey"><span>{swatch("s3")}where the patient starts</span>'
           f'<span>{swatch("s2")}where the treatment is</span>'
           f'<span>arcs are great circles — the line a plane flies over the curve, not the straight '
           f'line a flat map draws</span></div>')
    twin = table_twin(["From", "To", "Distance"],
                      [[E(f.get("from", "")), E(f.get("to", "")), E(f.get("sub", ""))] for f in flows],
                      f"The {len(flows)} routes on this map")
    return (f'<figure class="fig" id="{E(ident)}">' + (f'<p class="head">{E(title)}</p>' if title else "")
            + f'<svg viewBox="0 0 {w:.0f} {fit["h"]:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" '
              f'aria-label="{E(title or "Flow map")}">{defs()}'
              f'<path class="viz-grat" d="{worldmap.graticule(fit)}"/>{land}{"".join(arcs)}</svg>{key}'
            + (f'<figcaption>{E(note)}</figcaption>' if note else "") + twin + "</figure>")


def locator(geo: dict, lat: float, lon: float, others: list, *, w=460, span=14.0,
            label="", ident="loc") -> str:
    """One point and its neighbours, in the same projection as the world map."""
    fit = worldmap.fit_bbox(lon - span, lat - span * 0.62, lon + span, lat + span * 0.62, w)
    land = "".join(f'<path class="viz-land" d="{d}"/>' for _, _, d in worldmap.country_paths(geo, fit))
    pts = []
    for o in others:
        if o.get("lat") is None:
            continue
        x, y = worldmap.project(o["lon"], o["lat"], fit)
        if 0 <= x <= w and 0 <= y <= fit["h"]:
            pts.append(f'<circle class="viz-dot s3" cx="{x:.1f}" cy="{y:.1f}" r="3" '
                       f'data-tip="<b>{E(o.get("name", ""))}</b>"></circle>')
    x, y = worldmap.project(lon, lat, fit)
    pts.append(f'<circle class="viz-dot s2" cx="{x:.1f}" cy="{y:.1f}" r="5.6" '
               f'data-tip="<b>{E(label)}</b>"></circle>')
    return (f'<svg viewBox="0 0 {w:.0f} {fit["h"]:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="Where {E(label)} is">{defs()}{land}{"".join(pts)}</svg>')


# ---------------------------------------------------------------- prices

def price_strip(groups: list, *, w=840, unit="US$", title="", note="", ident="prices",
                log=True, row_h=30) -> str:
    """One row per country, one dot per published price, a log axis by default.

    Prices in this trade span two orders of magnitude, so a linear axis puts nine tenths
    of the dots in the first inch. The axis says which scale it is on.

    groups: [{"label": "Thailand", "iso": "TH", "points": [{"usd": 9800, "tip": "...",
              "kind": "package"}]}]
    """
    vals = [p["usd"] for g in groups for p in g["points"] if p.get("usd")]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    lo = max(1.0, lo * 0.8)
    hi = hi * 1.15
    # the gutter is as wide as the longest country name needs, at roughly 6.4px a
    # character in the label face — a clipped country name is a broken chart
    padl = min(260, max(110, int(6.4 * max(len(g["label"]) for g in groups)) + 24))
    padr, padt = 34, 34
    plot = w - padl - padr
    h = padt + row_h * len(groups) + 26

    def X(v):
        if log:
            return padl + plot * (math.log10(max(v, 1)) - math.log10(lo)) / max(1e-9, (math.log10(hi) - math.log10(lo)))
        return padl + plot * (v - lo) / max(1e-9, hi - lo)

    ticks = []
    if log:
        e0, e1 = int(math.floor(math.log10(lo))), int(math.ceil(math.log10(hi)))
        for e in range(e0, e1 + 1):
            for m in (1, 2, 5):
                v = m * 10 ** e
                if lo <= v <= hi:
                    ticks.append(v)
    else:
        step = 10 ** int(math.log10(max(hi - lo, 1)))
        v = math.ceil(lo / step) * step
        while v <= hi:
            ticks.append(v)
            v += step
    body = []
    for v in ticks:
        x = X(v)
        body.append(f'<line class="viz-grid" x1="{x:.1f}" y1="{padt-10}" x2="{x:.1f}" y2="{h-24:.1f}"/>')
        body.append(f'<text class="viz-ax" text-anchor="middle" x="{x:.1f}" y="{h-8:.0f}">{E(fmt(v))}</text>')
    for i, g in enumerate(groups):
        y = padt + row_h * i + row_h / 2
        body.append(f'<text class="viz-lab" text-anchor="end" x="{padl-12}" y="{y+4:.1f}">{E(g["label"])}</text>')
        body.append(f'<line class="viz-grid" x1="{padl}" y1="{y:.1f}" x2="{w-padr}" y2="{y:.1f}" opacity=".45"/>')
        for p in g["points"]:
            if not p.get("usd"):
                continue
            x = X(p["usd"])
            cls = {"package": "1", "tariff": "3", "reimbursement": "3"}.get(p.get("kind"), "2")
            if p.get("usd_high"):
                body.append(f'<line class="st{cls}" x1="{x:.1f}" y1="{y:.1f}" x2="{X(p["usd_high"]):.1f}" '
                            f'y2="{y:.1f}" stroke-width="3" stroke-linecap="round" opacity=".55"/>')
            body.append(f'<circle class="viz-dot s{cls}" cx="{x:.1f}" cy="{y:.1f}" r="5.2" '
                        f'data-tip="{p.get("tip", "")}"></circle>')
    key = (f'<div class="vkey"><span>{swatch("s1")}a provider\'s package price</span>'
           f'<span>{swatch("s3")}a state tariff or what a payer refunds</span>'
           f'<span>{swatch("s2")}a list price, an estimate or an advertised range</span>'
           f'<span>{"logarithmic" if log else "linear"} scale, {E(unit)}</span></div>')
    rows = []
    for g in groups:
        for p in g["points"]:
            rows.append([E(g["label"]), E(p.get("kind", "")), E(fmt(p.get("usd"))),
                         E(p.get("native", "")), E(p.get("as_of", "")), p.get("src_html", "")])
    twin = table_twin(["Country", "Kind", unit, "As published", "Dated", "Source"], rows,
                      f"The {len(rows)} prices behind this chart",
                      "Dollar figures are the published price put through one dated rate table; the "
                      "published currency and date are in the next columns.")
    return (f'<figure class="fig" id="{E(ident)}">' + (f'<p class="head">{E(title)}</p>' if title else "")
            + f'<svg viewBox="0 0 {w:.0f} {h:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" '
              f'aria-label="{E(title or "Published prices by country")}">{"".join(body)}</svg>{key}'
            + (f'<figcaption>{E(note)}</figcaption>' if note else "") + twin + "</figure>")


def bars(rows: list, *, w=760, unit="", title="", note="", ident="bars", row_h=26,
         color=None, label_w=190) -> str:
    """Horizontal bars. rows: [{"label":..., "value":..., "tip":..., "sub":...}]."""
    rows = [r for r in rows if r.get("value") is not None]
    if not rows:
        return ""
    hi = max(r["value"] for r in rows) or 1
    # the gutter grows to the longest label rather than clipping it, and the plot gives
    # way instead — a chart that eats a word to keep its bars long has lost the argument
    label_w = min(int(w * 0.42), max(label_w, int(6.4 * max(len(str(r["label"])) for r in rows)) + 18))
    padr = 64
    plot = w - label_w - padr
    h = row_h * len(rows) + 14
    body = []
    for i, r in enumerate(rows):
        y = i * row_h + 6
        bw = max(2.0, plot * r["value"] / hi)
        body.append(f'<text class="viz-lab" text-anchor="end" x="{label_w-12}" y="{y+14:.0f}">{E(r["label"])}</text>')
        body.append(f'<rect class="{color or "s1"}" x="{label_w}" y="{y+3:.0f}" width="{bw:.1f}" '
                    f'height="{row_h-11}" rx="4" data-tip="{r.get("tip", "")}"></rect>')
        body.append(f'<text class="viz-val" x="{label_w+bw+8:.1f}" y="{y+14:.0f}">{E(fmt(r["value"], unit))}</text>')
    twin = table_twin(["", unit or "Value", ""],
                      [[E(r["label"]), E(fmt(r["value"])), E(r.get("sub", ""))] for r in rows],
                      f"The {len(rows)} numbers behind this chart")
    return (f'<figure class="fig" id="{E(ident)}">' + (f'<p class="head">{E(title)}</p>' if title else "")
            + f'<svg viewBox="0 0 {w:.0f} {h:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" '
              f'aria-label="{E(title or "Bar chart")}">{"".join(body)}</svg>'
            + (f'<figcaption>{E(note)}</figcaption>' if note else "") + twin + "</figure>")


def legality_matrix(subjects: list, countries: list, cells: dict, *, w=900, title="",
                    note="", ident="matrix", country_names=None) -> str:
    """Subjects down, jurisdictions across, one glyph and one colour per cell.

    cells: {(subject_id, ISO2): row}. A cell nobody has read is hatched and carries a dot;
    it means this project has not read that law, which is not the same as no law.
    """
    if not subjects or not countries:
        return ""
    names = country_names or {}
    labw = min(int(w * 0.36), max(150, int(6.6 * max(len(x["label"]) for x in subjects)) + 18))
    cw, rh, padt = max(19, min(34, (w - labw) // max(1, len(countries)))), 30, 74
    h = padt + rh * len(subjects) + 12
    w2 = labw + cw * len(countries) + 8
    body = []
    for j, iso in enumerate(countries):
        x = labw + cw * j + cw / 2
        body.append(f'<text class="viz-ax" transform="rotate(-60 {x:.1f} {padt-10:.0f})" '
                    f'text-anchor="start" x="{x:.1f}" y="{padt-10:.0f}">{E(iso)}</text>')
    for i, s in enumerate(subjects):
        y = padt + rh * i
        body.append(f'<text class="viz-lab" text-anchor="end" x="{labw-12}" y="{y+rh/2+4:.1f}">{E(s["label"])}</text>')
        for j, iso in enumerate(countries):
            x = labw + cw * j
            row = cells.get((s["id"], iso))
            st = (row or {}).get("status", "no-data")
            spec = LEGAL.get(st, LEGAL["no-data"])
            fill = spec["fill"] if spec["fill"] != "none" else "url(#hatch)"
            tip = (f'<b>{E(names.get(iso, iso))} &middot; {E(s["label"])}</b>{E(spec["label"])}'
                   + (f'<br>{E(row.get("instrument", ""))}' if row and row.get("instrument") else "")
                   + (f'<br>{E(row.get("conditions", ""))}' if row and row.get("conditions") else "")
                   + (f'<br>read {E(row.get("as_of", ""))}' if row and row.get("as_of") else ""))
            body.append(f'<rect class="viz-cell" x="{x:.0f}" y="{y+3:.0f}" width="{cw-2:.0f}" height="{rh-6:.0f}" '
                        f'rx="4" fill="{fill}" data-tip="{tip}"></rect>')
            body.append(f'<text text-anchor="middle" x="{x+(cw-2)/2:.1f}" y="{y+rh/2+4:.1f}" '
                        f'style="font:600 11px var(--ui);fill:{"#fff" if st in ("lawful","unlawful","unregulated") else "#141414"};'
                        f'pointer-events:none">{spec["glyph"]}</text>')
    key = '<div class="vkey">' + "".join(
        f'<span><i style="background:{v["fill"] if v["fill"] != "none" else "var(--chip)"};'
        f'{"border:1px solid var(--line)" if v["fill"] == "none" else ""}"></i>{v["glyph"]} {E(v["label"])}</span>'
        for v in LEGAL.values()) + "</div>"
    rows = []
    for s in subjects:
        for iso in countries:
            r = cells.get((s["id"], iso))
            if not r:
                continue
            rows.append([E(s["label"]), E(names.get(iso, iso)), E(LEGAL.get(r["status"], {}).get("label", r["status"])),
                         E(r.get("instrument", "")), E(r.get("conditions", "")), E(r.get("as_of", "")),
                         (f'<a href="{E(r["url"])}" rel="noopener">source</a>' if r.get("url") else "")])
    twin = table_twin(["Question", "Jurisdiction", "Status", "Instrument", "Conditions", "Read", ""], rows,
                      f"The {len(rows)} readings behind this grid",
                      "One row is one reading of one named instrument on one date. Law moves.")
    return (f'<figure class="fig" id="{E(ident)}">' + (f'<p class="head">{E(title)}</p>' if title else "")
            + f'<div style="overflow-x:auto"><svg viewBox="0 0 {w2:.0f} {h:.0f}" width="{w2:.0f}" '
              f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{E(title or "Legality grid")}">'
              f'{defs()}{"".join(body)}</svg></div>{key}'
            + (f'<figcaption>{E(note)}</figcaption>' if note else "") + twin + "</figure>")


def recovery_bar(stay, nofly, weeks, *, w=700, ident="recovery") -> str:
    """Ward nights, the wait before a flight, and the span back to ordinary use — on one
    axis of days, because they are three measurements of the same clock."""
    if stay is None and nofly is None and weeks is None:
        return ""
    total = max(x for x in (stay or 0, nofly or 0, (weeks or 0) * 7, 14) if x is not None) * 1.12
    padl, h, rh = 172, 122, 30
    plot = w - padl - 60
    rows = [("In hospital", stay, "s1", "nights on the ward, as the package names them"),
            ("Before a flight", nofly, "s2", "days before boarding, on published clinical guidance"),
            ("Back to ordinary use", (weeks or 0) * 7 if weeks else None, "s3", "days, and it varies widely")]
    body = []
    for i, (lab, v, col, tip) in enumerate(rows):
        y = 12 + i * rh
        body.append(f'<text class="viz-lab" text-anchor="end" x="{padl-12}" y="{y+16:.0f}">{E(lab)}</text>')
        if v is None:
            body.append(f'<rect x="{padl}" y="{y+5:.0f}" width="{plot*.18:.0f}" height="{rh-14}" rx="4" '
                        f'fill="url(#hatch)" data-tip="Nobody has published this one."></rect>')
            body.append(f'<text class="viz-ax" x="{padl+plot*.18+8:.0f}" y="{y+17:.0f}">not published</text>')
            continue
        bw = max(3.0, plot * v / total)
        body.append(f'<rect class="{col}" x="{padl}" y="{y+5:.0f}" width="{bw:.1f}" height="{rh-14}" rx="4" '
                    f'data-tip="<b>{E(fmt(v))} days</b>{E(tip)}"></rect>')
        body.append(f'<text class="viz-val" x="{padl+bw+8:.1f}" y="{y+17:.0f}">{E(fmt(v))} d</text>')
    twin = table_twin(["", "Days"], [[E(l), E(fmt(v))] for l, v, _, _ in rows], "The numbers behind this")
    return (f'<figure class="fig" id="{E(ident)}"><p class="head">How long it takes</p>'
            f'<svg viewBox="0 0 {w:.0f} {h:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="Recovery timeline in days">{defs()}{"".join(body)}</svg>{twin}</figure>')


def timeline(events: list, *, w=860, title="", note="", ident="timeline") -> str:
    """Dated events on one line. events: [{"year": 2008, "label": ..., "tip": ..., "url": ...}]"""
    events = sorted([e for e in events if e.get("year")], key=lambda e: e["year"])
    if len(events) < 2:
        return ""
    y0, y1 = events[0]["year"], events[-1]["year"]
    padl, padr, h = 34, 34, 200
    plot = w - padl - padr
    X = lambda y: padl + plot * (y - y0) / max(1, (y1 - y0))
    body = [f'<line class="viz-grid" x1="{padl}" y1="{h/2:.0f}" x2="{w-padr}" y2="{h/2:.0f}" stroke-width="2"/>']
    for i, e in enumerate(events):
        x = X(e["year"])
        up = i % 2 == 0
        ty = h / 2 - 16 - (34 if up else 0)
        ty = (h / 2 - 18 - (30 if up else 0)) if up else (h / 2 + 30 + 18)
        body.append(f'<line x1="{x:.1f}" y1="{h/2:.0f}" x2="{x:.1f}" y2="{ty + (10 if up else -14):.1f}" '
                    f'class="viz-grid"/>')
        body.append(f'<circle class="viz-dot s1" cx="{x:.1f}" cy="{h/2:.0f}" r="5" '
                    f'data-tip="<b>{E(e["year"])} &middot; {E(e["label"])}</b>{E(e.get("tip", ""))}"></circle>')
        anchor = "middle" if padl + 60 < x < w - padr - 60 else ("start" if x <= padl + 60 else "end")
        body.append(f'<text class="viz-ax" text-anchor="{anchor}" x="{x:.1f}" y="{ty:.1f}">{E(e["year"])}</text>')
        body.append(f'<text class="viz-lab" text-anchor="{anchor}" x="{x:.1f}" y="{ty + (-13 if up else 13):.1f}">'
                    f'{E(e["label"][:30])}</text>')
    twin = table_twin(["Year", "What"], [[E(e["year"]), E(e["label"])] for e in events],
                      f"The {len(events)} dates on this line")
    return (f'<figure class="fig" id="{E(ident)}">' + (f'<p class="head">{E(title)}</p>' if title else "")
            + f'<svg viewBox="0 0 {w:.0f} {h:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" '
              f'aria-label="{E(title or "Timeline")}">{"".join(body)}</svg>'
            + (f'<figcaption>{E(note)}</figcaption>' if note else "") + twin + "</figure>")


def scatter(points: list, *, w=760, h=440, xlab="", ylab="", title="", note="",
            ident="scatter", logx=False, logy=True) -> str:
    """Two numbers against each other, one dot per country. points: [{"x","y","label","tip"}]"""
    pts = [p for p in points if p.get("x") is not None and p.get("y") is not None]
    if len(pts) < 3:
        return ""
    padl, padb, padt, padr = 66, 46, 28, 22

    def mk(vals, logscale):
        lo, hi = min(vals), max(vals)
        if logscale:
            lo, hi = max(lo * 0.8, 1e-6), hi * 1.15
            return (lambda v: (math.log10(max(v, 1e-6)) - math.log10(lo)) / max(1e-9, math.log10(hi) - math.log10(lo))), lo, hi
        pad = (hi - lo) * 0.08 or 1
        lo, hi = lo - pad, hi + pad
        return (lambda v: (v - lo) / max(1e-9, hi - lo)), lo, hi

    fx, xlo, xhi = mk([p["x"] for p in pts], logx)
    fy, ylo, yhi = mk([p["y"] for p in pts], logy)
    X = lambda v: padl + (w - padl - padr) * fx(v)
    Y = lambda v: h - padb - (h - padb - padt) * fy(v)
    body = []
    for t in range(5):
        yv = ylo * (yhi / ylo) ** (t / 4) if logy else ylo + (yhi - ylo) * t / 4
        y = Y(yv)
        body.append(f'<line class="viz-grid" x1="{padl}" y1="{y:.1f}" x2="{w-padr}" y2="{y:.1f}"/>')
        body.append(f'<text class="viz-ax" text-anchor="end" x="{padl-8}" y="{y+4:.1f}">{E(fmt(yv))}</text>')
        xv = xlo * (xhi / xlo) ** (t / 4) if logx else xlo + (xhi - xlo) * t / 4
        x = X(xv)
        body.append(f'<text class="viz-ax" text-anchor="middle" x="{x:.1f}" y="{h-padb+18:.0f}">{E(fmt(xv))}</text>')
    for p in pts:
        body.append(f'<circle class="viz-dot s1" cx="{X(p["x"]):.1f}" cy="{Y(p["y"]):.1f}" r="5.4" '
                    f'data-tip="{p.get("tip", "")}"></circle>')
    # label only the extremes; a number on every point is noise
    for p in sorted(pts, key=lambda p: p["y"])[:2] + sorted(pts, key=lambda p: -p["y"])[:2]:
        body.append(f'<text class="viz-lab" x="{X(p["x"])+9:.1f}" y="{Y(p["y"])+4:.1f}">{E(p.get("label", ""))}</text>')
    body.append(f'<text class="viz-ax" text-anchor="middle" x="{(w+padl)/2:.0f}" y="{h-4:.0f}">{E(xlab)}</text>')
    body.append(f'<text class="viz-ax" transform="rotate(-90 14 {h/2:.0f})" text-anchor="middle" x="14" '
                f'y="{h/2:.0f}">{E(ylab)}</text>')
    twin = table_twin([ylab or "y", xlab or "x", ""],
                      [[E(p.get("label", "")), E(fmt(p["x"])), E(fmt(p["y"]))] for p in pts],
                      f"The {len(pts)} points behind this chart")
    return (f'<figure class="fig" id="{E(ident)}">' + (f'<p class="head">{E(title)}</p>' if title else "")
            + f'<svg viewBox="0 0 {w:.0f} {h:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" '
              f'aria-label="{E(title or "Scatter plot")}">{"".join(body)}</svg>'
            + (f'<figcaption>{E(note)}</figcaption>' if note else "") + twin + "</figure>")


def stat_tiles(tiles: list) -> str:
    """A number that needs no plot. tiles: [(value, label, sub)]"""
    return '<div class="facts">' + "".join(
        f'<div class="fact"><div class="n">{E(v)}</div><div class="l">{E(l)}</div>'
        + (f'<div class="mute" style="font-size:.72rem;margin-top:.25rem">{E(s)}</div>' if s else "")
        + "</div>" for v, l, s in tiles) + "</div>"


def hub_map(lat: float, lon: float, radius_km: float, rows: list, curated: list,
            *, w=760, ident="hubmap", label="") -> str:
    """Every named hospital, clinic and dental surgery OpenStreetMap carries inside the
    radius this hub names, with the ones written up here marked and labelled.

    Drawn in plain equirectangular at city scale — over twenty kilometres the difference
    from any other projection is under a pixel, and the longitude is squeezed by the
    cosine of the latitude so the scale bar is true in both directions.
    """
    if not rows and not curated:
        return ""
    import math as _m
    kx = _m.cos(_m.radians(lat))
    span = radius_km / 111.0 * 1.08
    h = int(w * 0.62)
    def P(la, lo):
        x = w / 2 + (lo - lon) * kx / span * (w / 2)
        y = h / 2 - (la - lat) / span * (w / 2)
        return x, y
    kinds = {"hospital": ("s1", "hospital"), "clinic": ("s3", "clinic"),
             "dentist": ("s2", "dental surgery")}
    counts = {"hospital": 0, "clinic": 0, "dentist": 0, "other": 0}
    dots = []
    for r in rows:
        x, y = P(r["lat"], r["lon"])
        if not (0 <= x <= w and 0 <= y <= h):
            continue
        t = r.get("tags", {})
        k = t.get("amenity") or t.get("healthcare") or "other"
        k = k if k in kinds else ("clinic" if "clinic" in str(k) else "other")
        counts[k] = counts.get(k, 0) + 1
        cls = kinds.get(k, ("viz-land", ""))[0]
        dots.append(f'<circle class="{cls} osmdot" cx="{x:.0f}" cy="{y:.0f}" '
                    f'data-tip="{E(r["name"])}"/>')
    marks = []
    taken: list = []          # label rows already used, so two hospitals a street apart
    for c in sorted(curated, key=lambda c: c["lat"], reverse=True):   # do not print over each other
        x, y = P(c["lat"], c["lon"])
        if not (0 <= x <= w and 0 <= y <= h):
            continue
        marks.append(f'<circle class="viz-dot s2" cx="{x:.1f}" cy="{y:.1f}" r="6.4" '
                     f'data-tip="<b>{E(c["name"])}</b>written up here"></circle>')
        anchor = "start" if x < w * 0.7 else "end"
        dx = 11 if anchor == "start" else -11
        ly = y + 4
        for _ in range(14):
            if all(abs(ly - t[1]) > 13 or abs(x - t[0]) > 200 for t in taken):
                break
            ly += 14
        taken.append((x, ly))
        if ly - y > 8:
            marks.append(f'<line class="viz-grid" x1="{x:.1f}" y1="{y:.1f}" x2="{x+dx*0.5:.1f}" '
                         f'y2="{ly-4:.1f}" opacity=".6"/>')
        marks.append(f'<text class="viz-lab" text-anchor="{anchor}" x="{x+dx:.1f}" y="{ly:.1f}" '
                     f'style="paint-order:stroke;stroke:var(--panel);stroke-width:3.5px;'
                     f'stroke-linejoin:round">{E(c["name"])}</text>')
    # a scale bar, because a dot map with no scale is a decoration
    bar_km = max(1, round(radius_km / 4))
    bar_px = bar_km / 111.0 / span * (w / 2)
    scale = (f'<line class="viz-grid" x1="14" y1="{h-20}" x2="{14+bar_px:.1f}" y2="{h-20}" stroke-width="3"/>'
             f'<text class="viz-ax" x="{14+bar_px+8:.1f}" y="{h-16}">{bar_km} km</text>')
    ring = (f'<circle cx="{w/2:.0f}" cy="{h/2:.0f}" r="{radius_km/111.0/span*(w/2):.1f}" fill="none" '
            f'stroke="var(--landline)" stroke-dasharray="3 4" stroke-width="1"/>')
    total = sum(counts.values())
    key = ('<div class="vkey">'
           + f'<span>{swatch("s1")}hospital ({counts["hospital"]})</span>'
           + f'<span>{swatch("s3")}clinic ({counts["clinic"]})</span>'
           + f'<span>{swatch("s2")}dental surgery ({counts["dentist"]})</span>'
           + f'<span>{swatch("s2")}written up here ({len(marks)//2})</span>'
           + '<span>the dashed circle is the radius this record names</span></div>')
    twin = table_twin(["Name", "Kind"],
                      [[E(r["name"]), E((r.get("tags", {}).get("amenity")
                                         or r.get("tags", {}).get("healthcare") or ""))]
                       for r in sorted(rows, key=lambda r: r["name"].lower())[:120]],
                      f"{total} points on this map" + (", first 120 listed" if total > 120 else ""),
                      note=("The whole harvest, every hub, is in api/facilities.json."
                            if total > 120 else ""))
    return (f'<figure class="fig" id="{E(ident)}"><p class="head">Every one OpenStreetMap carries</p>'
            f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="Hospitals, clinics and dental surgeries around {E(label)}">'
            f'<rect width="{w}" height="{h}" fill="var(--panel)" rx="10"/>{ring}'
            f'{"".join(dots)}{"".join(marks)}{scale}</svg>{key}'
            f'<figcaption>What mappers have mapped inside {E(f"{radius_km:g}")} km of this point, '
            f'as of the fetch date on the coverage page. A place missing here is missing from the '
            f'map; a place here is a point with a name and little else.</figcaption>{twin}</figure>')
