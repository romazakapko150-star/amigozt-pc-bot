"""Profit optimiser.

Finds the cheapest way for an order to earn the owner's target profit
without becoming uncompetitive:

1. price every part at the *low* end of its category range;
2. if the order is short of target, raise **all** categories by the same
   fraction of their ranges - profit spreads across the build instead of
   landing on the GPU - until the target is met or the ranges are exhausted;
3. if still short of the *minimum*, step the assembly tier up one level;
4. if a market reference is known and the price has gone above it, back the
   margins down to the reference and warn.

It never swaps parts, drops accessories or touches compatibility - those are
decisions for the owner, and the engine only tells them it could not reach
the goal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.components import Component, ComponentCategory
from app.services.pricing.config import PricingConfig, get_pricing_config
from app.services.pricing.customer import CustomerPrice, price_product
from app.services.pricing.market import MarketPrice

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
#: Resolution of the search along the margin range.
POSITION_STEP = Decimal("0.05")

Parts = dict[ComponentCategory, Component]


@dataclass(slots=True)
class OptimisationResult:
    items: dict[ComponentCategory, CustomerPrice]
    unpriced: dict[ComponentCategory, MarketPrice]
    assembly_key: str
    position: Decimal
    other_services_pln: Decimal
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def market_cost_pln(self) -> Decimal:
        return sum((item.market_price_pln for item in self.items.values()), Decimal(0)).quantize(
            CENT
        )

    @property
    def components_price_pln(self) -> Decimal:
        return sum((item.customer_price_pln for item in self.items.values()), Decimal(0)).quantize(
            CENT
        )

    @property
    def product_profit_pln(self) -> Decimal:
        return sum((item.profit_pln for item in self.items.values()), Decimal(0)).quantize(CENT)


def _price_all(
    parts: Parts,
    lookups: dict[ComponentCategory, MarketPrice],
    position: Decimal,
    cfg: PricingConfig,
    overrides: dict[ComponentCategory, Decimal],
) -> tuple[dict[ComponentCategory, CustomerPrice], dict[ComponentCategory, MarketPrice]]:
    items: dict[ComponentCategory, CustomerPrice] = {}
    unpriced: dict[ComponentCategory, MarketPrice] = {}
    for category, component in parts.items():
        priced = price_product(
            component,
            lookups[category],
            position=position,
            config=cfg,
            target_margin=overrides.get(category),
        )
        if priced is None:
            unpriced[category] = lookups[category]
        else:
            items[category] = priced
    return items, unpriced


def optimise(
    parts: Parts,
    lookups: dict[ComponentCategory, MarketPrice],
    assembly_key: str,
    *,
    config: PricingConfig | None = None,
    target_margins: dict[ComponentCategory, Decimal] | None = None,
    other_services_pln: Decimal = Decimal(0),
    market_reference_high_pln: Decimal | None = None,
) -> OptimisationResult:
    cfg = config or get_pricing_config()
    overrides = target_margins or {}
    goals = cfg.profit

    def total_profit(items: dict[ComponentCategory, CustomerPrice], key: str) -> Decimal:
        product = sum((item.profit_pln for item in items.values()), Decimal(0))
        return product + cfg.assembly_tier(key).fee_pln + other_services_pln

    def total_price(items: dict[ComponentCategory, CustomerPrice], key: str) -> Decimal:
        components = sum((item.customer_price_pln for item in items.values()), Decimal(0))
        return components + cfg.assembly_tier(key).fee_pln + other_services_pln

    position = Decimal(0)
    key = assembly_key
    steps: list[str] = []
    warnings: list[str] = []

    items, unpriced = _price_all(parts, lookups, position, cfg, overrides)

    # Step 2: walk every category up its range together until target profit.
    while total_profit(items, key) < goals.target_order_profit_pln and position < Decimal(1):
        position = min(Decimal(1), position + POSITION_STEP)
        items, unpriced = _price_all(parts, lookups, position, cfg, overrides)
    if position > 0:
        steps.append(
            f"margins raised to {position:.0%} of their ranges to approach the "
            f"{goals.target_order_profit_pln} PLN target"
        )

    # Step 3: still below the minimum - a higher assembly tier is the next lever.
    if total_profit(items, key) < goals.minimum_order_profit_pln:
        higher = cfg.next_assembly_key(key)
        if higher is not None:
            key = higher
            steps.append(
                f"assembly tier raised to {cfg.assembly_tier(key).name} "
                f"({cfg.assembly_tier(key).fee_pln} PLN) to protect the minimum profit"
            )

    # Step 4: never price above a known market reference just to hit the target.
    if market_reference_high_pln is not None and market_reference_high_pln > 0:
        ceiling = market_reference_high_pln * (Decimal(1) + cfg.competitiveness_warn_percent / 100)
        while total_price(items, key) > ceiling and position > 0:
            position = max(Decimal(0), position - POSITION_STEP)
            items, unpriced = _price_all(parts, lookups, position, cfg, overrides)
        if total_price(items, key) > ceiling:
            warnings.append(
                f"price {total_price(items, key):.0f} PLN is above the market reference "
                f"{market_reference_high_pln:.0f} PLN even at minimum margins - "
                "consider a cheaper supplier or part"
            )
        elif steps:
            steps.append(f"margins capped at {position:.0%} by the market reference")

    profit = total_profit(items, key)
    if profit < goals.minimum_order_profit_pln:
        warnings.append(
            f"order profit {profit:.0f} PLN stays below the {goals.minimum_order_profit_pln} PLN "
            "minimum after optimisation - find a cheaper supplier, an alternative part, "
            "or accept consciously"
        )

    return OptimisationResult(
        items=items,
        unpriced=unpriced,
        assembly_key=key,
        position=position,
        other_services_pln=other_services_pln,
        steps=steps,
        warnings=warnings,
    )
