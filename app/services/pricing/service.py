"""Price aggregation and business margin.

``PriceService`` turns a set of components into acquisition costs by asking the
configured providers and picking one offer per part. ``quote`` then turns that
cost into what the customer pays.

Customer-facing code may read :attr:`Quote.customer_total_pln` and nothing
else - acquisition cost, profit and margin are admin-only and live on
:class:`MarginBreakdown`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.domain.components import Component, ComponentCategory
from app.services.pricing.offers import (
    EstimatePriceProvider,
    Offer,
    PriceProvider,
    Strategy,
    select_offer,
)

logger = logging.getLogger(__name__)

PLN = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(PLN, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class PricedPart:
    component: Component
    offer: Offer | None
    alternatives: list[Offer] = field(default_factory=list)

    @property
    def cost_pln(self) -> Decimal | None:
        return self.offer.total_pln if self.offer else None

    @property
    def priced(self) -> bool:
        return self.offer is not None


@dataclass(slots=True)
class PriceBreakdown:
    """Acquisition side. Admin-only."""

    parts: dict[ComponentCategory, PricedPart] = field(default_factory=dict)

    @property
    def missing(self) -> list[ComponentCategory]:
        return [category for category, part in self.parts.items() if not part.priced]

    @property
    def complete(self) -> bool:
        return bool(self.parts) and not self.missing

    @property
    def acquisition_cost_pln(self) -> Decimal:
        return _round(
            sum((part.cost_pln or Decimal(0) for part in self.parts.values()), Decimal(0))
        )

    @property
    def contains_estimates(self) -> bool:
        return any(
            part.offer is not None and part.offer.is_estimate for part in self.parts.values()
        )


@dataclass(slots=True)
class MarginBreakdown:
    """Admin-only view of the money."""

    acquisition_cost_pln: Decimal
    assembly_fee_pln: Decimal
    customer_total_pln: Decimal

    @property
    def gross_profit_pln(self) -> Decimal:
        return _round(self.customer_total_pln - self.acquisition_cost_pln)

    @property
    def margin_percent(self) -> Decimal:
        if self.customer_total_pln <= 0:
            return Decimal(0)
        ratio = self.gross_profit_pln / self.customer_total_pln * Decimal(100)
        return ratio.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class Quote:
    """What the customer is told, plus the admin-only breakdown."""

    breakdown: PriceBreakdown
    margin: MarginBreakdown

    @property
    def customer_total_pln(self) -> Decimal:
        return self.margin.customer_total_pln

    @property
    def is_approximate(self) -> bool:
        """True when any input was an estimate rather than a live offer."""
        return self.breakdown.contains_estimates

    @property
    def complete(self) -> bool:
        return self.breakdown.complete


class PriceService:
    def __init__(
        self,
        providers: list[PriceProvider] | None = None,
        *,
        strategy: Strategy = Strategy.BEST_VALUE,
    ) -> None:
        # The estimate provider is the floor: without it nothing can be priced
        # until a retailer integration exists.
        self._providers: list[PriceProvider] = providers or [EstimatePriceProvider()]
        self._strategy = strategy

    def collect_offers(self, component_ids: list[str]) -> dict[str, list[Offer]]:
        collected: dict[str, list[Offer]] = {}
        for provider in self._providers:
            try:
                found = provider.get_offers(component_ids)
            except Exception:  # pragma: no cover - a broken adapter must not break a build
                logger.exception("Price provider %s failed", getattr(provider, "name", provider))
                continue
            for component_id, offers in found.items():
                collected.setdefault(component_id, []).extend(offers)
        return collected

    def price_parts(self, parts: dict[ComponentCategory, Component]) -> PriceBreakdown:
        offers = self.collect_offers([component.id for component in parts.values()])

        breakdown = PriceBreakdown()
        for category, component in parts.items():
            available = offers.get(component.id, [])
            chosen = select_offer(available, self._strategy)
            breakdown.parts[category] = PricedPart(
                component=component,
                offer=chosen,
                alternatives=[offer for offer in available if offer is not chosen],
            )

        if breakdown.missing:
            logger.info(
                "No price for: %s", ", ".join(category.value for category in breakdown.missing)
            )
        return breakdown

    def quote(
        self,
        parts: dict[ComponentCategory, Component],
        *,
        target_margin_percent: Decimal,
        assembly_fee_pln: Decimal,
    ) -> Quote:
        breakdown = self.price_parts(parts)
        return build_quote(
            breakdown,
            target_margin_percent=target_margin_percent,
            assembly_fee_pln=assembly_fee_pln,
        )


def build_quote(
    breakdown: PriceBreakdown,
    *,
    target_margin_percent: Decimal,
    assembly_fee_pln: Decimal,
) -> Quote:
    """Derive the customer price from acquisition cost and the target margin.

    The margin is taken on the selling price, not marked up on cost, so that
    ``margin_percent`` comes back as the number that was asked for.
    """
    cost = breakdown.acquisition_cost_pln + assembly_fee_pln
    ratio = Decimal(1) - (target_margin_percent / Decimal(100))
    customer_total = _round(cost / ratio) if ratio > 0 else cost

    return Quote(
        breakdown=breakdown,
        margin=MarginBreakdown(
            acquisition_cost_pln=breakdown.acquisition_cost_pln,
            assembly_fee_pln=assembly_fee_pln,
            customer_total_pln=customer_total,
        ),
    )
