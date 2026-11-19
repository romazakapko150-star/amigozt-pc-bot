"""Record a verified market price for a catalogue component.

    python -m scripts.set_market_price amd-rx-9070 2599 --source x-kom \\
        --url https://www.x-kom.pl/... [--date 2026-08-22] [--note "promo"]

Only prices you actually read at the named source belong here. The bot shows
them to customers as market prices; estimates stay in reference_pln.json and
are labelled approximate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from app.services.catalog import get_catalog
from app.services.pricing.market import MARKET_FILE


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a verified market price")
    parser.add_argument("component_id")
    parser.add_argument("price", help="PLN incl. VAT, e.g. 2599 or 2599.00")
    parser.add_argument("--source", required=True, help="store name, e.g. x-kom")
    parser.add_argument("--url", required=True, help="product page the price was read from")
    parser.add_argument("--date", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--note", default=None)
    args = parser.parse_args()

    if get_catalog().get(args.component_id) is None:
        print(f"unknown component id: {args.component_id}", file=sys.stderr)
        return 1

    try:
        price = Decimal(args.price)
    except InvalidOperation:
        print(f"not a price: {args.price}", file=sys.stderr)
        return 1
    if price <= 0:
        print("price must be positive", file=sys.stderr)
        return 1

    if not args.url.startswith(("http://", "https://")):
        print("url must be a full http(s) link to the product page", file=sys.stderr)
        return 1

    data = json.loads(MARKET_FILE.read_text(encoding="utf-8"))
    entry = {
        "price": float(price),
        "source": args.source,
        "url": args.url,
        "checked_at": args.date,
    }
    if args.note:
        entry["note"] = args.note
    data.setdefault("prices", {})[args.component_id] = entry

    MARKET_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"recorded {args.component_id}: {price} PLN @ {args.source} ({args.date})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
