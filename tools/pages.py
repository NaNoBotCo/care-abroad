"""pages.py — the pages that answer a question rather than describe a record.

  /map/      the world, coloured by whichever series you pick
  /prices/   every published price on one logarithmic axis, per procedure
  /rules/    the legality grid: one question, many jurisdictions, each cell dated
  /near/     from where you are: distance, flying time, and what is published there
  /numbers/  the counts, and the shape of what is missing
  /journey/  the steps, in order
  /data/     every series this site draws on, and the sentence about what it leaves out

Each takes the shared page() from site.py so the chrome stays in one place.
"""
from __future__ import annotations

import html
import json
import math

import viz
import worldmap
from common import haversine_km

E = viz.E

CRUISE_KMH = 850.0
TAXI_MIN = 45.0


def flight_hours(km: float) -> float:
    """Great-circle kilometres at 850 km/h plus 45 minutes on the ground and in the climb.
    An arithmetic estimate, not a timetable: the routing, the wind and the stop are not in it."""
    return km / CRUISE_KMH + TAXI_MIN / 60.0


def hm(hours: float) -> str:
    h = int(hours)
    return f"{h}h {int(round((hours - h) * 60)):02d}m"


# ------------------------------------------------------------------ /map/

def map_page(page, countries: dict, geo: dict, recs: list, site_url: str, wb: dict | None = None) -> str:
    fit = worldmap.fit_world(geo, 940)
    meta = countries["indicator_meta"]
    order = [k for k in ("spend_pc", "doctors", "beds", "oop", "life", "gdp_pc", "arrivals", "receipts")
             if k in meta]
    # one path per country, drawn once; the fills are set in the browser from the table below
    paths = []
    for iso, name, d in worldmap.country_paths(geo, fit):
        paths.append(f'<path id="c-{E(iso)}" data-iso="{E(iso)}" d="{d}" class="viz-nodata" '
                     f'stroke="var(--panel)" stroke-width=".5"></path>')
    # EVERY country the publisher covers, not only the ones this directory writes about.
    # Drawing the join table instead would paint a map of this project's attention and
    # call it a map of the world.
    values: dict = {}
    for key in order:
        for iso, v in ((wb or {}).get("indicators", {}).get(key, {}).get("values", {})).items():
            values.setdefault(iso, {})[key] = [v["value"], v["year"]]
    # every country the World Bank covers, not only the ones this site writes about:
    # a map of 40 countries out of 195 is a map of this project, not of the world
    names = {c["iso"]: c["name"] for c in geo["countries"]}
    site_layer = {iso: {"n": row["name"], "f": row["curated_facilities"], "p": row["prices"],
                        "h": len(row["hubs"]), "d": bool(row["destination"])}
                  for iso, row in countries["countries"].items()}
    buttons = "".join(
        '<button type="button" data-ind="%s" aria-pressed="%s">%s</button>'
        % (E(k), "true" if i == 0 else "false", E(meta[k]["name"]))
        for i, k in enumerate(order))
    buttons += ('<button type="button" data-ind="__site" aria-pressed="false">Written up here</button>')
    body = (f'<h1><span class="kind">The world</span>One map, several questions</h1>'
            f'<p class="lede">Pick a series. Every country the publisher covers is coloured, not only the ones '
            f'this directory writes about — the gap between those two sets is itself worth looking at. '
            f'A hatched country is one the series does not carry.</p>'
            f'<div class="chips" id="indchips" role="group" aria-label="Choose a series">{buttons}</div>'
            f'<p class="mute" id="indnote" style="font-size:.86rem"></p>'
            f'<div class="mapwrap"><svg viewBox="0 0 940 {fit["h"]:.0f}" id="worldmap" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="World map coloured by the selected series">'
            f'{viz.defs()}<path class="viz-grat" d="{worldmap.graticule(fit)}"/>{"".join(paths)}</svg></div>'
            f'<div class="vramp" id="indramp"></div>'
            f'<p class="mute" style="font-size:.85rem">Equal Earth projection: a square kilometre takes the same '
            f'ink anywhere on it. Antarctica is cropped. Country outlines are Natural Earth, public domain; '
            f'the series are the World Bank\'s, CC BY 4.0, each fetched on the date its '
            f'<a href="../data/index.html">data page</a> names.</p>'
            f'<div id="indtable"></div>')
    body += f"""
<script>
(function(){{
var VAL={json.dumps(values)}, META={json.dumps({k: meta[k] for k in order})}, NAMES={json.dumps(names)},
    SITE={json.dumps(site_layer)}, BINS=7;
var cur=null;
function esc(s){{return String(s==null?"":s).replace(/[&<>"]/g,function(c){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
function fmt(v){{if(v==null)return"—";var a=Math.abs(v);
 if(a>=1e9)return (v/1e9).toFixed(1)+"bn"; if(a>=1e6)return (v/1e6).toFixed(1)+"m";
 if(a>=1000)return Math.round(v).toLocaleString(); if(a>=10)return Math.round(v).toString();
 if(a>=1)return v.toFixed(1); return v.toFixed(2)}}
function edges(vals,n){{var s=vals.slice().sort(function(a,b){{return a-b}}),o=[];
 for(var i=1;i<n;i++){{var q=s[Math.floor(s.length*i/n)]; if(!o.length||q>o[o.length-1])o.push(q)}} return o}}
function paint(key){{
 cur=key;
 var svg=document.getElementById("worldmap"), ramp=document.getElementById("indramp"),
     note=document.getElementById("indnote"), tab=document.getElementById("indtable");
 var rows=[],vals=[];
 if(key==="__site"){{
   for(var iso in SITE){{var s=SITE[iso]; var n=s.f+s.h+(s.d?1:0); if(n>0){{vals.push(n);rows.push([iso,s.n,n])}}}}
 }} else {{ for(var iso2 in VAL){{ var v=VAL[iso2][key]; if(v){{vals.push(v[0]);rows.push([iso2,NAMES[iso2]||iso2,v[0],v[1]])}} }} }}
 var eg=edges(vals,7), painted=0;
 svg.querySelectorAll("path[data-iso]").forEach(function(p){{
   var iso=p.dataset.iso, v=null, extra="";
   if(key==="__site"){{var s=SITE[iso]; if(s){{v=s.f+s.h+(s.d?1:0);
     extra=(s.d?"a country page":"")+(s.f?" &middot; "+s.f+" hospitals written up":"")+(s.h?" &middot; "+s.h+" cities":"")+(s.p?" &middot; "+s.p+" prices":"")}}}}
   else {{ var r=VAL[iso]&&VAL[iso][key]; if(r){{v=r[0];extra=(META[key].unit||"")+" &middot; "+r[1]}} }}
   if(v==null){{p.setAttribute("class","viz-nodata");
     p.setAttribute("data-tip","<b>"+esc(NAMES[iso]||iso)+"</b>"+(key==="__site"?"Nothing here yet.":"Not in this series."));return}}
   var i=0; for(var k=0;k<eg.length;k++) if(v>=eg[k]) i++;
   p.setAttribute("class","seq-"+Math.min(i,BINS-1)); painted++;
   p.setAttribute("data-tip","<b>"+esc(NAMES[iso]||iso)+"</b>"+fmt(v)+" "+extra);
 }});
 var m=key==="__site"?{{name:"Records on this site",unit:"records",source:"this directory",url:"",fetched_at:"",countries:rows.length}}:META[key];
 var swatches=""; for(var b=0;b<BINS;b++) swatches+='<span><svg viewBox="0 0 1 1" preserveAspectRatio="none" style="width:100%;height:100%;display:block"><rect class="seq-'+b+'" width="1" height="1"/></svg></span>';
 ramp.innerHTML='<span>'+fmt(Math.min.apply(null,vals))+'</span><span class="steps">'+swatches+
   '</span><span>'+fmt(Math.max.apply(null,vals))+'</span><span style="margin-left:.6rem">'+
   painted+' countries coloured, '+(svg.querySelectorAll("path[data-iso]").length-painted)+' hatched</span>';
 note.innerHTML=esc(m.name)+(m.unit?", "+esc(m.unit):"")+" &middot; "+esc(m.source)+
   (m.url?' &middot; <a href="'+esc(m.url)+'" rel="noopener">the series</a>':"")+
   (m.fetched_at?" &middot; fetched "+esc(m.fetched_at):"")+
   " &middot; bins hold equal numbers of countries, so the colour is a rank, not a ratio";
 rows.sort(function(a,b){{return b[2]-a[2]}});
 tab.innerHTML='<details class="twin"><summary>The '+rows.length+' values behind this map</summary><table>'+
  '<thead><tr><th>Country</th><th>ISO</th><th>'+esc(m.unit||"Value")+'</th><th>Year</th></tr></thead><tbody>'+
  rows.map(function(r){{return "<tr><td>"+esc(r[1])+"</td><td>"+esc(r[0])+"</td><td>"+fmt(r[2])+"</td><td>"+esc(r[3]||"")+"</td></tr>"}}).join("")+
  "</tbody></table></details>";
}}
document.getElementById("indchips").addEventListener("click",function(e){{
 var b=e.target.closest("[data-ind]"); if(!b)return;
 this.querySelectorAll("button").forEach(function(x){{x.setAttribute("aria-pressed",String(x===b))}});
 paint(b.dataset.ind)}});
paint({json.dumps(order[0] if order else "__site")});
}})();
</script>"""
    jl = [{"@context": "https://schema.org", "@type": "Dataset", "name": "Country indicators — Care Abroad",
           "url": f"{site_url}/map/", "license": "https://creativecommons.org/licenses/by/4.0/",
           "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json",
                             "contentUrl": f"{site_url}/api/countries.json"}]}]
    return page("One map, several questions — Care Abroad", body, 1,
                "Health spending, doctors, beds, out-of-pocket share and tourism receipts, country by country, "
                "on one equal-area world map.", jl, f"{site_url}/map/", card="map")


# ------------------------------------------------------------------ /prices/

def prices_page(page, prices: dict, recs: list, site_url: str) -> str:
    by_id = {r["id"]: r for r in recs}
    rows = prices["prices"]
    procs: dict = {}
    for p in rows:
        if not p.get("procedure"):
            continue
        procs.setdefault(p["procedure"], []).append(p)
    ranked = sorted(procs.items(), key=lambda kv: -len({r["country"] for r in kv[1]}))
    tiles = [(f'{prices["count"]:,}', "prices", "each read off a published page"),
             (f'{len({p["country"] for p in rows})}', "countries", ""),
             (f'{len(procs)}', "procedures priced", ""),
             (f'{prices["prices"] and min(p["as_of"][:4] for p in rows) or "—"}–'
              f'{prices["prices"] and max(p["as_of"][:4] for p in rows) or "—"}', "dates", "oldest to newest")]
    body = (f'<h1><span class="kind">Money</span>Prices</h1>'
            f'<p class="lede">Every price here is a number somebody published, with the date it was published '
            f'and the list of what it covers. Averages are not carried here, and neither are quotes given in private. The dollar figure beside each price is that price put through one rate table, '
            f'dated {E(prices["rate_date"] or "—")}, which is not the rate the patient got.</p>'
            + viz.stat_tiles(tiles))
    body += ('<h2>What the headline price leaves out</h2>'
             '<p>A package names an inclusion list and an exclusion list. On the joint packages the implant sits '
             'on the exclusion list, and the implant is frequently the largest single line on the bill. The '
             'exclusion lists are printed under every chart below, in the provider\'s own words.</p>')
    for pid, plist in ranked[:14]:
        rec = by_id.get(pid)
        name = rec["names"]["name"] if rec else pid
        groups: dict = {}
        for p in plist:
            groups.setdefault(p["country"], []).append(p)
        gs = []
        for iso, items in sorted(groups.items(), key=lambda kv: min(
                (x["usd"] for x in kv[1] if x["usd"] is not None), default=9e12)):
            pts = []
            for p in items:
                src = by_id.get(p["on"])
                fac = by_id.get(p.get("facility") or "")
                native = f'{p["amount"]:,.0f} {p["currency"]}' if p["amount"] is not None else ""
                if p.get("amount_high"):
                    native = f'{p["amount"]:,.0f}–{p["amount_high"]:,.0f} {p["currency"]}'
                tip = ("<b>" + E((fac["names"]["name"] if fac else (p.get("city") or iso))) + "</b>"
                       + E(native) + (f' &middot; {E(p["kind"])}') + f'<br>dated {E(p["as_of"])}'
                       + (f'<br>includes {E(", ".join(p["includes"][:4]))}' if p.get("includes") else "")
                       + (f'<br><b>excludes {E(", ".join(p["excludes"][:4]))}</b>' if p.get("excludes") else ""))
                pts.append({"usd": p["usd"], "usd_high": p.get("usd_high"), "kind": p["kind"], "tip": tip,
                            "native": native, "as_of": p["as_of"],
                            "src_html": (f'<a href="{E(p["url"])}" rel="noopener">page</a>' if p.get("url") else E(p["source"]))})
            gs.append({"label": ISO_NAME.get(iso, iso), "iso": iso, "points": pts})
        fig = viz.price_strip(gs, ident=f"p-{pid}",
                              note=f'{len(plist)} published prices for {name.lower()}, across {len(groups)} countries.')
        if fig:
            body += (f'<h2><a href="../procedure/{E(pid)}/index.html" style="text-decoration:none">{E(name)}</a></h2>'
                     + fig)
    body += ('<h2>How to read any of this</h2>'
             '<ul>'
             '<li><b>Package</b> — a fixed bundle from a provider\'s own page. Read the exclusion list.</li>'
             '<li><b>Tariff</b> or <b>reimbursement</b> — what a state or an insurer pays, which is not what a '
             'self-payer is charged in the same country.</li>'
             '<li><b>List</b>, <b>estimate</b> or <b>quoted-range</b> — advertised numbers. The range is usually '
             'wide and the low end is usually the one repeated.</li>'
             '<li>A missing price is a missing <i>publication</i>. Most hospitals in most countries publish '
             'none, and their absence from this page says nothing about their cost.</li>'
             '</ul>'
             f'<p class="mute">The whole table as JSON: <a href="../api/prices.json">api/prices.json</a>.</p>')
    jl = [{"@context": "https://schema.org", "@type": "Dataset", "name": "Published prices — Care Abroad",
           "url": f"{site_url}/prices/", "license": "https://creativecommons.org/licenses/by/4.0/"}]
    return page("Prices — Care Abroad", body, 1,
                "Every published price for treatment abroad this directory has read, with its currency, its date "
                "and what the provider said it covers.", jl, f"{site_url}/prices/", card="prices")


# ------------------------------------------------------------------ /rules/

def rules_page(page, legality: dict, recs: list, geo: dict, site_url: str) -> str:
    by_id = {r["id"]: r for r in recs}
    names = {c["iso"]: c["name"] for c in geo["countries"]}
    cells = {(r["subject"], r["country"]): r for r in legality["rows"]}
    subjects = [{"id": s, "label": by_id[s]["names"]["name"] if s in by_id else s}
                for s in legality["subjects"]]
    body = (f'<h1><span class="kind">Law</span>Rules</h1>'
            f'<p class="lede">Some people travel because treatment is cheaper elsewhere. Others travel because '
            f'it is lawful elsewhere. This grid is the second kind: one question down the side, one jurisdiction '
            f'across the top, and every cell a reading of one named instrument on one date. Hover a cell for the '
            f'instrument and the date it was read. Nothing here is legal advice.</p>')
    body += viz.legality_matrix(subjects, legality["countries"], cells, w=940,
                                country_names=names, ident="legal",
                                note=("A hatched cell means nobody here has read that law — a fact about this "
                                      "project, not about the country. Statutes change between a reading and a "
                                      "reader; the date in each cell is how old the reading is."))
    if legality["rows"]:
        years = sorted({r["as_of"][:4] for r in legality["rows"]})
        body += (f'<p class="mute">Readings dated {E(years[0])}–{E(years[-1])}. '
                 f'{len(legality["rows"])} rows across {len(legality["countries"])} jurisdictions and '
                 f'{len(subjects)} questions.</p>')
    body += '<h2>The rules themselves</h2><div class="cards">'
    for r in sorted([r for r in recs if r["type"] == "rule"], key=lambda r: r["names"]["name"].lower()):
        body += (f'<div class="card"><a class="t" href="../rule/{E(r["id"])}/index.html">{E(r["names"]["name"])}</a>'
                 f'<p>{E(r["blurb"])}</p>'
                 + (f'<p class="mute" style="font-size:.8rem">{len(r.get("legality", []))} jurisdictions read</p>'
                    if r.get("legality") else "") + "</div>")
    body += "</div>"
    body += (f'<p class="mute">The whole grid as JSON: <a href="../api/legality.json">api/legality.json</a>.</p>')
    return page("Rules — Care Abroad", body, 1,
                "Where a treatment is lawful for a visitor, one question at a time, each cell naming its "
                "instrument and the date it was read.", None, f"{site_url}/rules/", card="rules")


# ------------------------------------------------------------------ /near/

def near_page(page, markets: dict, recs: list, facilities: dict, geo: dict, site_url: str) -> str:
    by_id = {r["id"]: r for r in recs}
    dests = []
    for r in recs:
        if r["type"] not in ("hub", "facility") or not r.get("geo"):
            continue
        iso = (r.get("facets") or {}).get("iso2") or (r.get("address") or {}).get("country") or ""
        dests.append({"id": r["id"], "t": r["type"], "n": r["names"]["name"], "iso": iso,
                      "lat": r["geo"]["lat"], "lon": r["geo"]["lon"],
                      "u": ("city/" if r["type"] == "hub" else "hospital/") + r["id"] + "/",
                      "b": r["blurb"][:150],
                      "d": (r.get("facets") or {}).get("draws") or [],
                      "p": len(r.get("prices", []))})
    picks = "".join(f'<option value="{i}">{E(m["name"])} ({E(m["city"])})</option>'
                    for i, m in enumerate(markets["entries"]))
    body = (f'<h1><span class="kind">Distance</span>From where you are</h1>'
            f'<p class="lede">Pick the city you would fly from, or let the browser ask for your position. '
            f'Every hospital and cluster in this directory, sorted by great-circle distance, with an arithmetic '
            f'estimate of the flying time.</p>'
            f'<div class="search"><select id="mkt" aria-label="Where you would fly from">'
            f'<option value="">— choose a city —</option>{picks}</select>'
            f'<button id="geo" type="button">Use my location</button></div>'
            f'<p class="mute" id="whence" aria-live="polite"></p>'
            f'<div class="chips" id="nearchips" role="group" aria-label="Filter">'
            f'<button type="button" data-f="price" aria-pressed="false">Publishes a price</button>'
            f'<button type="button" data-f="hub" aria-pressed="false">Clusters only</button>'
            f'<button type="button" data-f="fac" aria-pressed="false">Hospitals only</button></div>'
            f'<div id="nearout"></div>'
            f'<p class="legend">Distance is the great circle: 6,371 km sphere, point to point. The flying time '
            f'is that distance at 850 km/h plus 45 minutes for the ground and the climb — arithmetic, not a '
            f'timetable, and it knows nothing about routing, wind or a connection. A position, if the browser gives '
            f'one, is read by the arithmetic on this page.</p>')
    body += f"""
<script>
(function(){{
var D={json.dumps(dests)}, M={json.dumps(markets["entries"])}, F={{}};
function esc(s){{return String(s==null?"":s).replace(/[&<>"]/g,function(c){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
function km(a,b,c,d){{var R=6371,r=Math.PI/180,x=(c-a)*r,y=(d-b)*r;
 var h=Math.sin(x/2)*Math.sin(x/2)+Math.cos(a*r)*Math.cos(c*r)*Math.sin(y/2)*Math.sin(y/2);
 return 2*R*Math.asin(Math.min(1,Math.sqrt(h)))}}
function hm(h){{var i=Math.floor(h);return i+"h "+String(Math.round((h-i)*60)).padStart(2,"0")+"m"}}
function render(lat,lon,label){{
 document.getElementById("whence").textContent="Measured from "+label+".";
 var rows=D.map(function(x){{var k=km(lat,lon,x.lat,x.lon);return {{x:x,k:k}}}})
   .filter(function(r){{ if(F.price&&!r.x.p)return false; if(F.hub&&r.x.t!=="hub")return false;
                        if(F.fac&&r.x.t!=="facility")return false; return true}})
   .sort(function(a,b){{return a.k-b.k}});
 document.getElementById("nearout").innerHTML='<p class="mute">'+rows.length+' places</p><div class="cards">'+
  rows.slice(0,120).map(function(r){{var x=r.x;
   return '<div class="card"><a class="t" href="../'+x.u+'index.html">'+esc(x.n)+'</a>'+
    '<p class="mute" style="font-size:.8rem">'+esc(x.iso)+' &middot; '+Math.round(r.k).toLocaleString()+
    ' km &middot; about '+hm(r.k/850+0.75)+' in the air'+(x.p?' &middot; '+x.p+' published price'+(x.p>1?'s':''):'')+'</p>'+
    '<p>'+esc(x.b)+'</p></div>'}}).join("")+"</div>";
}}
var last=null;
function go(lat,lon,label){{last=[lat,lon,label];render(lat,lon,label)}}
document.getElementById("mkt").addEventListener("change",function(){{
 if(this.value==="")return; var m=M[+this.value]; go(m.lat,m.lon,m.city+", "+m.name)}});
document.getElementById("geo").addEventListener("click",function(){{
 if(!navigator.geolocation){{document.getElementById("whence").textContent="This browser offers no position.";return}}
 navigator.geolocation.getCurrentPosition(function(p){{go(p.coords.latitude,p.coords.longitude,"your position")}},
  function(){{document.getElementById("whence").textContent="The browser declined to give a position."}})}});
document.getElementById("nearchips").addEventListener("click",function(e){{
 var b=e.target.closest("[data-f]"); if(!b)return; F[b.dataset.f]=!F[b.dataset.f];
 b.setAttribute("aria-pressed",String(!!F[b.dataset.f])); if(last)render(last[0],last[1],last[2])}});
}})();
</script>"""
    return page("From where you are — Care Abroad", body, 1,
                "Every hospital and cluster in this directory sorted by distance from the city you would fly "
                "from, with an estimate of the flying time.", None, f"{site_url}/near/", card="near")


# ------------------------------------------------------------------ /numbers/

def numbers_page(page, recs: list, countries: dict, prices: dict, legality: dict,
                 cov: dict, facilities: dict, geo: dict, site_url: str) -> str:
    rowsc = countries["countries"]
    meta = countries["indicator_meta"]
    body = (f'<h1><span class="kind">Counts</span>Numbers</h1>'
            f'<p class="lede">What this directory holds, and the shape of what it does not. Every chart on this '
            f'page has a table under it.</p>')
    body += viz.stat_tiles([
        (f'{sum(cov["records"].values()):,}', "records", ""),
        (f'{cov["countries_touched"]}', "countries touched", f'of {len(geo["countries"])} on the map'),
        (f'{prices["count"]:,}', "published prices", f'dated {cov["prices"]["oldest"]}–{cov["prices"]["newest"]}'),
        (f'{legality["count"]:,}', "legality readings", f'{len(legality["subjects"])} questions'),
        (f'{facilities["curated"]}', "hospitals written up", f'+{facilities["harvested"]:,} off OpenStreetMap'),
        (f'{cov["sources"]}', "sources", ""),
    ])

    # what a price ratio actually looks like, per procedure, against the dearest country
    body += "<h2>Where the published prices sit</h2>"
    by_proc: dict = {}
    for p in prices["prices"]:
        if p.get("procedure") and p.get("usd"):
            by_proc.setdefault(p["procedure"], []).append(p)
    by_id = {r["id"]: r for r in recs}
    ratio_rows = []
    for pid, plist in by_proc.items():
        if len({x["country"] for x in plist}) < 3:
            continue
        lo = min(plist, key=lambda x: x["usd"])
        hi = max(plist, key=lambda x: x["usd"])
        ratio_rows.append({"label": (by_id[pid]["names"]["name"] if pid in by_id else pid),
                           "value": round(hi["usd"] / max(lo["usd"], 1), 1),
                           "tip": (f'<b>{E(by_id[pid]["names"]["name"] if pid in by_id else pid)}</b>'
                                   f'{ISO_NAME.get(lo["country"], lo["country"])} ${lo["usd"]:,.0f} '
                                   f'to {ISO_NAME.get(hi["country"], hi["country"])} ${hi["usd"]:,.0f}'),
                           "sub": (f'{ISO_NAME.get(lo["country"], lo["country"])} ${lo["usd"]:,.0f} → '
                                   f'{ISO_NAME.get(hi["country"], hi["country"])} ${hi["usd"]:,.0f}')})
    ratio_rows.sort(key=lambda r: -r["value"])
    if ratio_rows:
        body += viz.bars(ratio_rows[:18], unit="×", ident="ratios",
                         title="Dearest published price divided by cheapest",
                         note=("Both ends are published prices, not quotes, and they rarely cover the same "
                               "things — one may exclude the implant and the other include four nights. The "
                               "ratio is a starting point for a question, not an answer."))

    # spending against prices: the obvious hypothesis, drawn so it can be argued with
    pts = []
    for iso, row in rowsc.items():
        sp = row["indicators"].get("spend_pc")
        pr = [p["usd"] for p in prices["prices"] if p["country"] == iso and p.get("usd")]
        if sp and pr:
            med = sorted(pr)[len(pr) // 2]
            pts.append({"x": sp["value"], "y": med, "label": iso,
                        "tip": (f'<b>{E(row["name"])}</b>health spending ${sp["value"]:,.0f} a head ({sp["year"]})'
                                f'<br>median published price on this site ${med:,.0f} ({len(pr)} prices)')})
    if len(pts) >= 4:
        body += viz.scatter(pts, xlab="Health spending per person, current US$", logx=True,
                            ylab="Median published price on this site, US$", ident="spendprice",
                            title="What a country spends on health, against what it charges a visitor",
                            note=("Each dot is one country. The vertical axis is the median of whatever prices "
                                  "this directory happens to have read there, which is a sample of publications, "
                                  "not of the market. Read it as a picture of this dataset."))

    # who publishes at all
    pub = sorted(((row["name"], row["prices"]) for row in rowsc.values() if row["prices"]),
                 key=lambda t: -t[1])[:20]
    if pub:
        body += viz.bars([{"label": n, "value": v, "tip": f"<b>{E(n)}</b>{v} published prices read here"}
                          for n, v in pub], unit="prices", ident="pubcount",
                         title="Countries where a price could be read at all",
                         note="A country's absence is an absence of publication, or of this project's attention.")

    # accreditation counts
    acc: dict = {}
    for r in recs:
        for a in r.get("recognitions", []):
            acc[a["by"]] = acc.get(a["by"], 0) + 1
    if acc:
        body += viz.bars([{"label": k, "value": v, "tip": f"<b>{E(k)}</b>{v} facilities in this directory"}
                          for k, v in sorted(acc.items(), key=lambda kv: -kv[1])],
                         unit="facilities", ident="accs", title="Which accreditor's mark appears on these records",
                         note=("A count of marks in this directory, which reflects which hospitals got written "
                               "up here. Accreditation is an inspection the applicant pays for; it is not a "
                               "score, and this chart ranks nothing."))

    body += ('<h2>What is missing, said plainly</h2><ul>'
             + "".join(f"<li>{E(x)}</li>" for x in cov["not_yet"]) + "</ul>"
             f'<p>{E(cov["prices"]["reading_an_absence"])}</p>'
             f'<p>{E(cov["legality"]["reading_an_absence"])}</p>'
             f'<p>{E(cov["facilities"]["reading_an_absence"])}</p>'
             f'<p class="mute">The same object as JSON: <a href="../api/coverage.json">api/coverage.json</a>.</p>')
    return page("Numbers — Care Abroad", body, 1,
                "What this directory holds, what the published prices look like side by side, and the shape of "
                "what is missing.", None, f"{site_url}/numbers/", card="numbers")


# ------------------------------------------------------------------ /journey/

STAGE_ORDER = ["deciding", "booking", "before-you-fly", "on-arrival", "in-hospital",
               "going-home", "aftercare", "when-it-goes-wrong"]
STAGE_LABEL = {"deciding": "Deciding", "booking": "Booking", "before-you-fly": "Before the flight",
               "on-arrival": "On arrival", "in-hospital": "In hospital", "going-home": "Going home",
               "aftercare": "Aftercare", "when-it-goes-wrong": "When it goes wrong"}


def journey_page(page, recs: list, site_url: str) -> str:
    steps = [r for r in recs if r["type"] == "pathway"]
    by_stage: dict = {}
    for r in steps:
        by_stage.setdefault((r.get("facets") or {}).get("stage") or "deciding", []).append(r)
    body = (f'<h1><span class="kind">The order it happens in</span>The journey</h1>'
            f'<p class="lede">Deciding, booking, flying, consenting, recovering, going home, and the part '
            f'nobody quotes for. Each step says what happens, who does it, what money and what paper move, and '
            f'where it commonly fails. None of it says what anyone should do.</p>')
    n = 0
    for st in STAGE_ORDER:
        rs = by_stage.get(st)
        if not rs:
            continue
        body += f'<h2>{E(STAGE_LABEL.get(st, st))}</h2><div class="cards">'
        for r in sorted(rs, key=lambda r: r["names"]["name"].lower()):
            n += 1
            risks = [k for k in r.get("kin_out", []) if k["type"] == "risk"]
            body += (f'<div class="card"><a class="t" href="../step/{E(r["id"])}/index.html">'
                     f'{n}. {E(r["names"]["name"])}</a><p>{E(r["blurb"])}</p>'
                     + ("".join(f'<span class="chip">{E(k["name"])}</span>' for k in risks[:3]))
                     + "</div>")
        body += "</div>"
    leftover = [s for s in by_stage if s not in STAGE_ORDER]
    for st in leftover:
        body += f'<h2>{E(st)}</h2><div class="cards">' + "".join(
            f'<div class="card"><a class="t" href="../step/{E(r["id"])}/index.html">{E(r["names"]["name"])}</a>'
            f'<p>{E(r["blurb"])}</p></div>' for r in by_stage[st]) + "</div>"
    return page("The journey — Care Abroad", body, 1,
                "The steps of treatment abroad in the order they happen, and where each one commonly fails.",
                None, f"{site_url}/journey/", card="journey")


# ------------------------------------------------------------------ /dataset/ extras

def data_note(recs: list) -> str:
    """The sentence that makes the dataset index worth reading, pulled from each record."""
    out = []
    for r in sorted([r for r in recs if r["type"] == "dataset"], key=lambda r: r["names"]["name"].lower()):
        d = r.get("dataset") or {}
        if not d.get("does_not_count"):
            continue
        out.append(f'<tr><th><a href="../dataset/{E(r["id"])}/index.html">{E(r["names"]["name"])}</a></th>'
                   f'<td><b>Counts.</b> {E(d.get("counts", ""))}<br><b>Does not count.</b> '
                   f'{E(d["does_not_count"])}</td></tr>')
    if not out:
        return ""
    return ('<h2>What each series leaves out</h2><table>' + "".join(out) + "</table>")


ISO_NAME: dict = {}

# Natural Earth's own NAME field runs long for a handful of countries, and a chart axis
# is not the place for a country's full ceremonial name.
SHORT = {"United States of America": "United States", "United Kingdom": "United Kingdom",
         "Dominican Rep.": "Dominican Republic", "Czechia": "Czechia",
         "Bosnia and Herz.": "Bosnia", "Dem. Rep. Congo": "DR Congo",
         "Central African Rep.": "Central African Rep.", "Eq. Guinea": "Equatorial Guinea",
         "Solomon Is.": "Solomon Islands", "S. Sudan": "South Sudan",
         "United Arab Emirates": "UAE", "Korea": "South Korea",
         "Republic of Korea": "South Korea", "Turkey": "Türkiye"}


def set_iso_names(names: dict):
    global ISO_NAME
    ISO_NAME = {k: SHORT.get(v, v) for k, v in names.items()}
