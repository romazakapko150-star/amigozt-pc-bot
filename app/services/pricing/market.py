"""Market prices: what a product really costs in Polish shops right now.

Three kinds of number can describe a product, and they must never be
confused:

* **verified** - the exact model was seen at a named source on a date
  (``app/data/prices/market_pln.json``). The only kind a customer may be told
  is "the market price".
* **estimated** - AmigoZT's own indicative figure
  (``app/data/prices/reference_pln.json``). Fine for ranking and for an
  approximate quote, always labelled as approximate.
* **unknown** - nothing on file. The engine says so instead of guessing.

A verified price older than ``stale_after_days`` degrades to **historical**:
still shown to the admin for context, never used for today's customer price.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "prices"
MARKET_FILE = DATA_DIR / "market_pln.json"
ESTIMATE_FILE = DATA_DIR / "reference_pln.json"
DEFAULT_STALE_AFTER_DAYS = 14


class PriceStatus(StrEnum):
    VERIFIED = "verified"
    ESTIMATED = "estimated"
    HISTORICAL = "historical"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MarketPrice:
    component_id: str
    price_pln: Decimal | None
    status: PriceStatus
    source: str | None = None
    url: str | None = None
    checked_at: date | None = None
    note: str | None = None

    @property
    def usable(self) -> bool:
        """May this number feed a customer price?"""
        return self.price_pln is not None and self.status in {
            PriceStatus.VERIFIED,
            PriceStatus.ESTIMATED,
        }

    @property
    def is_verified(self) -> bool:
        return self.status is PriceStatus.VERIFIED

    def as_dict(self) -> dict:
        return {
            "market_price": str(self.price_pln) if self.price_pln is not None else None,
            "market_currency": "PLN",
            "market_price_source": self.source,
            "market_price_url": self.url,
            "market_price_checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "price_status": self.status.value,
        }


def _parse_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class MarketPriceService:
    """Looks a component up in the verified file, then the estimate file."""

    def __init__(
        self,
        market_file: Path | None = None,
        estimate_file: Path | None = None,
        *,
        today: date | None = None,
    ) -> None:
        self._today = today or datetime.now(UTC).date()

        market_raw = json.loads((market_file or MARKET_FILE).read_text(encoding="utf-8"))
        meta = market_raw.get("_meta", {})
        self._stale_after = int(meta.get("stale_after_days", DEFAULT_STALE_AFTER_DAYS))
        self._verified: dict[str, dict] = dict(market_raw.get("prices", {}))

        estimate_raw = json.loads((estimate_file or ESTIMATE_FILE).read_text(encoding="utf-8"))
        self._estimates: dict[str, Decimal] = {
            key: Decimal(str(value)) for key, value in estimate_raw.get("prices", {}).items()
        }

    @property
    def verified_count(self) -> int:
        return len(self._verified)

    def lookup(self, component_id: str) -> MarketPrice:
        entry = self._verified.get(component_id)
        if entry is not None:
            checked = _parse_date(entry.get("checked_at"))
            price = Decimal(str(entry["price"]))
            stale = checked is None or (self._today - checked).days > self._stale_after
            return MarketPrice(
                component_id=component_id,
                price_pln=price,
                status=PriceStatus.HISTORICAL if stale else PriceStatus.VERIFIED,
                source=entry.get("source"),
                url=entry.get("url"),
                checked_at=checked,
                note=entry.get("note"),
            )

        estimate = self._estimates.get(component_id)
        if estimate is not None:
            return MarketPrice(
                component_id=component_id,
                price_pln=estimate,
                status=PriceStatus.ESTIMATED,
                source="AmigoZT estimate",
            )

        return MarketPrice(component_id=component_id, price_pln=None, status=PriceStatus.UNKNOWN)

    def lookup_many(self, component_ids: list[str]) -> dict[str, MarketPrice]:
        return {component_id: self.lookup(component_id) for component_id in component_ids}

    def historical_estimate(self, component_id: str) -> Decimal | None:
        """The old estimate for a product that now has a verified price.

        Kept so the admin can see how far the estimate was off; never used
        for the customer price once a verified figure exists.
        """
        if component_id in self._verified:
            return self._estimates.get(component_id)
        return None
