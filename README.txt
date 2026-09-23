CARE ABROAD
===========
Live at https://nanobotco.github.io/care-abroad/
Repo: github.com/NaNoBotCo/care-abroad (GitHub Pages serves docs/)


A directory of treatment across borders, built the way wichaa.net is built: one JSON
record per node of the subject — a country, a city cluster, a procedure, a hospital, a
step of the journey, a risk, a rule, an organization, a person, an event, a word, a
dataset, a long piece of writing — each field carrying where it came from, each page
saying what its neighbours are to it. A static site for people and for machines.

The pictures are drawn from the data. Photographs of hospitals are hard to license and
tell a reader nothing; a map of what a country spends on health per person, a strip of
every published price for a knee, and a grid of where surrogacy is lawful all tell them
something. So the visuals here are charts and maps generated from the records.

Nothing on the site is medical advice or legal advice.


WHERE THINGS ARE
----------------
  data/nodes/<type>/<id>.json   the records. THE TRUTH. Edit these.
  data/sources/sources.json     every source a record may cite
  data/vocab/*.json             regions, the thirteen types, facet keys, tags,
                                accreditors, and the source markets behind /near/
  data/harvest/worldbank.json   eleven World Bank series for every country that reports
                                (tools/harvest_worldbank.py; CC BY 4.0; fetch date inside)
  data/harvest/osm-facilities.json  every named hospital, clinic and dental surgery
                                around each hub (tools/harvest_osm.py; ODbL)
  data/harvest/rates.json       one dated exchange-rate table (tools/fetch_rates.py)
  data/geo/countries.json       country outlines, Natural Earth, public domain
                                (tools/fetch_geo.py refetches them)
  schema/node.schema.json       what a record must look like
  AUTHORING.txt                 how to write a record; the cast list
  BRIEF.txt                     the brief every drafting agent works from
  tools/                        the pipeline (below)
  build/                        generated. Never edit. Safe to delete.
  build/site/                   the website, ready for any static host
  docs/                         the published build (GitHub Pages serves this)


THE PIPELINE (in order)
-----------------------
  python3 tools/validate.py     every record must pass
  python3 tools/build.py        records + harvests -> build/api, search tables, the
                                price table, the legality grid, the country join
  python3 tools/cards.py        the 1200x630 share cards (draws only what is missing)
  python3 tools/site.py         build/site: pages, maps, charts, search, JSON-LD,
                                sitemap, llms.txt, robots, CSV/JSONL
  python3 tools/serve.py        http://127.0.0.1:8797
  python3 -m unittest discover -s tests

  Or double-click "Care Abroad.command" for a numbered menu.

  SITE_URL=https://example.org python3 tools/site.py   sets the canonical host.
  BUILD_DRAFT=1 python3 tools/build.py                 builds while records are still
                                being written: an unwritten kin target warns instead of
                                failing. Not for a publish.


MAPS
----
Every map is drawn in Equal Earth by tools/worldmap.py. It is an equal-area projection,
which matters because most of these maps colour countries by a rate: on Mercator the
rich northern latitudes swell to several times their size, and the rich north is where
the patients come from rather than where they go. A square kilometre takes the same ink
anywhere on these maps. Shapes are stretched east-west near the poles, which is what
every equal-area projection trades away, and Antarctica is cropped.

Great-circle arcs on the flow maps are the line a plane flies. Distances everywhere are
great-circle kilometres on a 6,371 km sphere; the flying times are that distance at
850 km/h plus 45 minutes, which is arithmetic rather than a timetable, and the page says
so where it prints one.


THE PAGES THAT ANSWER A QUESTION
--------------------------------
  /prices/  Every published price on one logarithmic axis, per procedure, with the
            provider's own inclusion and exclusion lists under it. A logarithmic axis
            because prices here run over two orders of magnitude.
  /map/     One world map, several series: health spending per person, doctors, beds,
            out-of-pocket share, life expectancy, GDP, visitor arrivals and tourism receipts —
            plus a layer showing this site's own coverage, so the gap between what the
            world reports and what this directory has written up is visible.
  /rules/   The legality grid. One question down the side, one jurisdiction across the
            top, every cell a reading of one named instrument on one date.
  /near/    Pick the city you would fly from. Every hospital and cluster sorted by
            distance, with an estimate of the time in the air.
  /journey/ The steps in order: deciding, booking, the visa, the flight, consent, the
            ward, the discharge summary, the flight home, aftercare, and the complaint.
  /numbers/ What this directory holds and the shape of what is missing.
  /data/    Every series a chart here draws on, with the sentence saying what it does
            NOT count.
  /words/   The vocabulary, with roots.
  /search/  The fleet search core in the browser: fuzzy, thesaurus, tier reported.
  /coverage/ Scope as an object.
  /api/     Everything as JSON. llms.txt and llms-full.txt for machines.
  wander.html  A page at random. Press r anywhere.


HOW A PRICE IS HANDLED
----------------------
A price row is a number somebody PUBLISHED, read off their own page, carrying:

  the currency it was billed in, and the date it was published
  what kind of number it is — a provider's package, a list price, a state tariff, what
    an insurer reimburses, a survey figure, or an advertised range
  the provider's own inclusion list AND exclusion list

The exclusion list is where the story usually is. A knee package at 356,500 baht
excludes the implant, and the implant is frequently the largest single line on the bill.

Dollar figures beside a price are that price put through ONE exchange-rate table, whose
date is printed. A 2019 lira price converted at a 2026 rate is not what that patient
paid, and both dates are on the page so the gap is visible.

The schema has no field for an average, and validate.py currently rejects a price
that carries no date or no source.


HOW LAW IS HANDLED
------------------
A legality row is one reading of ONE named instrument in ONE jurisdiction on ONE date.
Six statuses: lawful · lawful with conditions · residents only · prohibited ·
unregulated · not read by this project. That last one is hatched on the grid and means
what it says: a fact about this directory, not about the country. Law moves between a
reading and a reader, so every cell carries the date it was read.


TIERS
-----
Each field carries one:
  cited      a named source, linked
  harvested  fetched from an open dataset, with its licence
  tradition  how the trade works, hedged in the prose
  inference  this project's own reasoning, said so in the prose
  field      somebody stood there (nothing carries this yet)


REFRESHING THE HARVESTS
-----------------------
  python3 tools/harvest_worldbank.py         eleven series, one request each
  python3 tools/harvest_worldbank.py --only beds
  python3 tools/fetch_rates.py               one dated rate table
  python3 tools/fetch_geo.py                 country outlines
  python3 tools/fetch_geo.py --detail        the 1:50m outlines, for close-ups
  python3 tools/harvest_osm.py               every hub, one Overpass query each
  python3 tools/harvest_osm.py --resume      only the hubs not already on disk
  python3 tools/harvest_osm.py --hubs bangkok,istanbul


ADDING A RECORD
---------------
Read AUTHORING.txt. Copy an exemplar, change every field, keep the id in the filename,
cite only ids in sources.json, run validate.py.


WHAT IS IN IT
------------
329 records: 52 countries, 40 city clusters, 58 procedures,
34 hospitals written up beside 17,520 points harvested from OpenStreetMap,
22 organizations, 23 rules, 23 risks, 17 journey steps, 26 words,
13 datasets, 8 events, 5 people and 8 longer pieces.

243 published prices across 23 countries, dated 2013 to 2026-09-17.
151 readings of named legal instruments across 55 jurisdictions.
762 sources.

8 of the 34 hospitals written up carry a price of their own. That ratio is a
finding about the trade rather than a gap in the directory.


NOT HERE YET
------------
A domain. Field observations. Photographs for most records. Outcome data per unit
outside the few registries that publish it. Complication and revision rates for work
done abroad, which almost nobody counts. Prices in most countries, because most
hospitals publish none. The OpenStreetMap harvest covers 29 of the 40 clusters;
`python3 tools/harvest_osm.py --resume` finishes the rest.


LICENCE
Records, prose and pages: CC BY 4.0. Other layers — upstream data,
pictures, tools — keep their own terms, set out in LICENSE.

USING IT
Attribution is the whole of the condition — copy it, adapt it, sell it,
index it, train on it, and say where it came from. Open an issue if
something is missing:
https://github.com/NaNoBotCo/care-abroad/issues

---

Contact: Nan · nan@motdang.net · Sponsor: ko-fi.com/defiantchiangmai · patreon.com/nanobotco

<!-- fleet-roster -->

Elsewhere from the same publisher

- Mot Dang — https://motdang.net/ — city directory for Chiang Mai and Chiang Rai
- The Mae Hong Son Loop — https://nanobotco.github.io/mae-hong-son-loop/ — motorcycling the 600 km loop out of Chiang Mai — curves counted, air measured
- Muay Thai — https://motdang.net/muay-thai/ — the eight limbs, the thirty named techniques, the ceremony, and every gym on the map
- Roads of Chiang Mai — https://motdang.net/roads/ — the square of 1296, four rings, and what each one did to the city — counted from the map
- wichaa — https://wichaa.net/ — Lanna manuscripts, the amulet market, and the traditions around them
- Hand Poke — https://nanobotco.github.io/hand-poke/ — 28 traditions of marking skin by hand — the leg-tattoo zone of Burma, the Shan States and Lanna, counted
- Black Holes, Drawn — https://nanobotco.github.io/black-holes/ — black holes modelled and drawn from the equations — generators, the past, present and future, the legends
- Quantum Computing, plainly — https://nanobotco.github.io/quantum-computing/ — the history and theory of quantum computing in plain words, with demos; refreshed weekly
- Goin' Fast — https://nanobotco.github.io/goin-fast/ — a dirt-simple explainer about speed — twenty measured speeds from the ground under the house to light, and what each one costs
- The Three-Body Problem — https://nanobotco.github.io/three-body/ — the mathematics of the three-body problem in plain words, with the orbits found rather than copied
- Exceptional Magic — https://nanobotco.github.io/exceptional-magic/ — the octonions, triality, the magic square and E8, computed and drawn — a plain-spoken reading of one paper
- Amulet Atlas — https://nanobotco.github.io/amulet-atlas/ — amulets, charms and talismans worldwide
- Carolina Barbecue — https://nanobotco.github.io/carolina-barbecue/ — barbecue in North and South Carolina
- Wing Country — https://nanobotco.github.io/buffalo-wings/ — the American chicken wing
- Pink Box — https://nanobotco.github.io/pink-box/ — the American mom-and-pop donut shop
- Basque Tables — https://nanobotco.github.io/basque-tables/ — Basque dining rooms of California, Nevada and Idaho
- Pinot Country — https://nanobotco.github.io/pinot-noir/ — pinot noir: the vine, the regions, the cellars
- Thai Roots — https://nanobotco.github.io/thairoots/ — a root dictionary of Thai, with a word decomposer
- The index — https://nanobotco.github.io/index/ — every corpus, site and repository, counted
- Uptake — https://nanobotco.github.io/uptake/ — a field manual on publishing for machines that copy
- NaNoBotCo — https://nanobotco.github.io/ — the portal
- ฮักฝรั่ง — https://hakfarang.net/ — เรื่องเงิน วีซ่า และชีวิตกับแฟนฝรั่ง
- Offrampt — https://offrampt.net/ — turning crypto into spendable local money, Thailand first

All of it, counted: https://nanobotco.github.io/index/ · roster as JSON: https://nanobotco.github.io/index/fleet.json
