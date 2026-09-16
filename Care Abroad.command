#!/bin/bash
# Double-click this file to run the Care Abroad pipeline from a numbered menu.
# The project folder is wherever this script lives, so moving the folder does not break it.
cd "$(dirname "$0")" || { echo "Cannot find the project folder."; read -p "Press return to close."; exit 1; }
PY=python3

while true; do
  echo
  echo "CARE ABROAD"
  echo "  1  Validate every record"
  echo "  2  Build (validate + API + prices + law + search tables)"
  echo "  3  Make the website (build/site)"
  echo "  4  Everything: 1-3 then open the site"
  echo "  5  Serve the site (http://127.0.0.1:8797)"
  echo "  6  Run the tests"
  echo "  7  Refresh the World Bank series"
  echo "  8  Refresh today's exchange rates"
  echo "  9  Refresh hospitals from OpenStreetMap (hubs not yet fetched)"
  echo " 10  Refresh country outlines"
  echo " 11  Publish: build into docs/ for the live site"
  echo "  0  Quit"
  read -p "Number: " n
  case "$n" in
    1) $PY tools/validate.py ;;
    2) $PY tools/build.py ;;
    3) $PY tools/cards.py && $PY tools/site.py ;;
    4) $PY tools/build.py && $PY tools/site.py && open "build/site/index.html" ;;
    5) $PY tools/serve.py ;;
    6) $PY -m unittest discover -s tests -v 2>&1 | tail -25 ;;
    7) $PY tools/harvest_worldbank.py ;;
    8) $PY tools/fetch_rates.py ;;
    9) $PY tools/harvest_osm.py --resume ;;
   10) $PY tools/fetch_geo.py ;;
   11) ./publish.sh ;;
    0) exit 0 ;;
    *) echo "Pick a number." ;;
  esac
done
