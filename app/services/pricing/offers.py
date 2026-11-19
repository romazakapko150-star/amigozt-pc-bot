"""Pricing layer: offers, providers and best-buy selection.

Deliberately separate from the recommendation engine. The engine reasons about
*components*; this module reasons about *where to buy them and for how much*.
Swapping in a real retailer feed must not require touching build logic.

Nothing here invents data. When a provider has no offer for a part, the result
says so instead of guessing, and every offer carries the provenance
(``source_type``) and the time it was checked so stale data is visible.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

DEFAULT_PRICE_FILE = Path(__file__).resolve().parents[2] / "data" / "prices" / "reference_pln.json"


class Availability(StrEnum):
    IN_STOCK = "in_stock"
    ON_ORDER = "on_order"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"

    @property
    def is_buyable(self) -> bool:
        return self in {Availability.IN_STOCK, Availability.ON_ORDER}


class OfferSource(StrEnum):
    """Where a price came from - never presented as more certain than it is."""

    STORE_API = "store_api"
    PARTNER_FEED = "partner_feed"
    MANUAL = "manual"
    #: Internal estimate. Must be shown to customers as approximate.
    ESTIMATE = "estimate"


@dataclass(frozen=True, slots=True)
class Offer:
    component_id: str
    store: str
    price_pln: Decimal
    availability: Availability
    source_type: OfferSource
    last_checked_at: datetime
    url: str | None = None
    shipping_pln: Decimal = Decimal(0)
    delivery_days: int | None = None
    store_trust: int = 50

    @property
    def total_pln(self) -> Decimal:
        return self.price_pln + self.shipping_pln

    @property
    def is_estimate(self) -> bool:
        return self.source_type is OfferSource.ESTIMATE

    def age_days(self, now: datetime | None = None) -> int:
        reference = now or datetime.now(UTC)
        checked = self.last_checked_at
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=UTC)
        return max(0, (reference - checked).days)


class PriceProvider(Protocol):
    """Contract every price source implements.

    Real retailer adapters (x-kom, Morele, Media Expert, Komputronik, RTV Euro
    AGD, Amazon.pl) plug in here once an API key or partner feed is available.
    See ``app/services/pricing/providers.py``.
    """

    name: str

    def get_offers(self, component_ids: list[str]) -> dict[str, list[Offer]]:
        """Offers per component id. Missing ids simply have no entry."""
        ...


class EstimatePriceProvider:
    """Fallback provider backed by the checked-in estimate table.

    This exists so the configurator is usable before any retailer integration
    is signed. Every offer it returns is marked ``OfferSource.ESTIMATE`` and the
    UI is responsible for labelling those prices as approximate.
    """

    name = "AmigoZT estimate"

    def __init__(self, price_file: Path | None = None) -> None:
        path = price_file or DEFAULT_PRICE_FILE
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._prices: dict[str, Decimal] = {
            key: Decimal(str(value)) for key, value in payload["prices"].items()
        }
        meta = payload.get("_meta", {})
        self._as_of = str(meta.get("as_of", "unknown"))
        self._checked_at = datetime.now(UTC)

    def __len__(self) -> int:
        return len(self._prices)

    @property
    def as_of(self) -> str:
        return self._as_of

    def get_offers(self, component_ids: list[str]) -> dict[str, list[Offer]]:
        offers: dict[str, list[Offer]] = {}
        for component_id in component_ids:
            price = self._prices.get(component_id)
            if price is None:
                continue
            offers[component_id] = [
                Offer(
                    component_id=component_id,
                    store=self.name,
                    price_pln=price,
                    availability=Availability.UNKNOWN,
                    source_type=OfferSource.ESTIMATE,
                    last_checked_at=self._checked_at,
                )
            ]
        return offers


class Strategy(StrEnum):
    BEST_PRICE = "best_price"
    BEST_VALUE = "best_value"
    FASTEST_DELIVERY = "fastest_delivery"
    MOST_TRUSTED = "most_trusted"


def select_offer(offers: list[Offer], strategy: Strategy = Strategy.BEST_VALUE) -> Offer | None:
    """Pick one offer out of several.

    ``BEST_PRICE`` is the raw cheapest total. ``BEST_VALUE`` - the default -
    balances total cost against availability, delivery time and how much the
    store is trusted, because the cheapest listing is worthless if the part
    never ships.
    """
    buyable = [offer for offer in offers if offer.availability.is_buyable]
    candidates = buyable or offers
    if not candidates:
        return None

    match strategy:
        case Strategy.BEST_PRICE:
            return min(candidates, key=lambda offer: offer.total_pln)
        case Strategy.FASTEST_DELIVERY:
            return min(
                candidates,
                key=lambda offer: (offer.delivery_days is None, offer.delivery_days or 0),
            )
        case Strategy.MOST_TRUSTED:
            return max(candidates, key=lambda offer: (offer.store_trust, -offer.total_pln))
        case _:
            return min(candidates, key=_value_score)


def _value_score(offer: Offer) -> Decimal:
    """Lower is better: total cost nudged by delivery time and trust."""
    score = offer.total_pln
    if offer.availability is Availability.ON_ORDER:
        score += Decimal(50)
    elif offer.availability is Availability.UNKNOWN:
        score += Decimal(25)
    if offer.delivery_days:
        score += Decimal(min(offer.delivery_days, 14)) * Decimal(5)
    score += Decimal(100 - min(offer.store_trust, 100)) / Decimal(2)
    return score
