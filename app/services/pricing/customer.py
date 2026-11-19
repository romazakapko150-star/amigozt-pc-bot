"""Customer price for one product: market price → margin → rounded price.

    customer_price = round_up_to_9(
        max(market_price x (1 + margin), market_price + minimum_profit)
    )

The rounding is "psychological": 366.85 becomes 369, 527.40 becomes 529. It
only ever moves the price up, so the minimum profit survives it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

from app.domain.components import Component, ComponentCategory
from app.services.pricing.config import PricingConfig, get_pricing_config
from app.services.pricing.margin import MarginRule, margin_for
from app.services.pricing.market import MarketPrice, PriceStatus

CENT = Decimal("0.01")
ITEM_ROUNDING_STEP = 10


@dataclass(frozen=True, slots=True)
class CustomerPrice:
    """One priced product, with everything needed to explain the number."""

    component_id: str
    category: str
    market: MarketPrice
    rule: MarginRule
    raw_price_pln: Decimal
    customer_price_pln: Decimal

    @property
    def market_price_pln(self) -> Decimal:
        return self.market.price_pln if self.market.price_pln is not None else Decimal(0)

    @property
    def profit_pln(self) -> Decimal:
        return (self.customer_price_pln - self.market_price_pln).quantize(CENT)

    @property
    def status(self) -> PriceStatus:
        return self.market.status

    def as_dict(self) -> dict:
        return {
            **self.market.as_dict(),
            "category": self.category,
            "margin_percent": str(self.rule.margin_percent),
            "margin_position": str(self.rule.position),
            "minimum_profit": str(self.rule.min_profit_pln),
            "raw_price": str(self.raw_price_pln),
            "customer_price": str(self.customer_price_pln),
            "profit": str(self.profit_pln),
        }


def round_to_nine(amount: Decimal, step: int = ITEM_ROUNDING_STEP) -> Decimal:
    """Round *up* to the next amount ending in ``step - 1``: 366.85 → 369."""
    if amount <= 0:
        return Decimal(0)
    step_dec = Decimal(step)
    blocks = (amount / step_dec).to_integral_value(rounding=ROUND_FLOOR)
    candidate = blocks * step_dec + (step_dec - 1)
    if candidate < amount:
        candidate += step_dec
    return candidate.quantize(CENT)


def calculate_customer_price(
    market_price: Decimal,
    category: ComponentCategory | str,
    target_margin: Decimal | None = None,
    *,
    position: Decimal = Decimal(0),
    config: PricingConfig | None = None,
) -> tuple[Decimal, MarginRule]:
    """The formula from the brief, for a bare market price.

    Returns the rounded customer price and the rule that produced it.
    """
    cfg = config or get_pricing_config()
    rule = margin_for(
        category,
        market_price,
        position=position,
        config=cfg,
        target_margin_percent=target_margin,
    )
    raw = market_price + rule.profit_for(market_price)
    return round_to_nine(raw), rule


def price_product(
    component: Component,
    market: MarketPrice,
    *,
    position: Decimal = Decimal(0),
    config: PricingConfig | None = None,
    target_margin: Decimal | None = None,
) -> CustomerPrice | None:
    """Price a catalogue product, or ``None`` when its market price is unknown.

    Historical prices are refused on purpose: an old figure must never be
    dressed up as today's price.
    """
    if not market.usable or market.price_pln is None:
        return None

    cfg = config or get_pricing_config()
    rule = margin_for(
        component.category,
        market.price_pln,
        position=position,
        config=cfg,
        target_margin_percent=target_margin,
    )
    raw = (market.price_pln + rule.profit_for(market.price_pln)).quantize(CENT)
    return CustomerPrice(
        component_id=component.id,
        category=component.category.value,
        market=market,
        rule=rule,
        raw_price_pln=raw,
        customer_price_pln=round_to_nine(raw),
    )
