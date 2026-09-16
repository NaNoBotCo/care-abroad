"""fetch_rates.py — one dated set of exchange rates, so prices in twenty currencies can
sit on one axis.

A price is published in the currency the hospital bills in. Comparing them needs a rate,
and a rate has a date: a 2019 Turkish lira price converted at today's rate is not what
that patient paid. So the rate table is fetched once, stamped, and stored — and every
converted figure on the site carries the date of the rate as well as the date of the
price.

    python3 tools/fetch_rates.py

Writes data/harvest/rates.json from open.er-api.com (no key). A currency the table does
not carry leaves its price unconverted, and the page prints it in its own currency.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HARVEST, jdump  # noqa: E402

URL = "https://open.er-api.com/v6/latest/USD"


def main() -> int:
    with urllib.request.urlopen(URL, timeout=60) as r:
        body = json.loads(r.read().decode("utf-8"))
    if body.get("result") != "success":
        print("rate service said:", body.get("error-type", "?"))
        return 1
    rates = {k: v for k, v in body["rates"].items() if isinstance(v, (int, float)) and v > 0}
    jdump({"base": "USD", "per_usd": rates, "count": len(rates),
           "provider": body.get("provider", URL), "url": URL,
           "rate_date": body.get("time_last_update_utc", "")[:16],
           "fetched_at": time.strftime("%Y-%m-%d"),
           "note": ("Units of each currency per US dollar on the date above. Prices on this "
                    "site keep the currency they were published in; the dollar figure beside "
                    "them is this table applied, and it moves when the table is refetched.")},
          HARVEST / "rates.json", indent=None)
    print(f"{len(rates)} currencies, rates dated {body.get('time_last_update_utc', '')[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
