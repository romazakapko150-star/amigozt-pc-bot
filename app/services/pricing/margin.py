"""Which margin applies to a product.

Three inputs combine: the *category* sets a range (a GPU cannot carry the
same mark-up as a mousepad and stay competitive), a *position* in that range
says how far up the order has had to move to earn its keep, and the *price
band* sets an absolute minimum profit (15 % of a 60 PLN cable is not worth the
handling). The higher of percent and minimum wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.components import ComponentCategory
from app.services.pricing.config import PricingConfig, get_pricing_config


@dataclass(frozen=True, slots=True)
class MarginRule:
    category: str
    margin_percent: Decimal
    min_profit_pln: Decimal
    #: Where in the category's range this percent sits, 0 = low end, 1 = high.
    position: Decimal = Decimal(0)

    def profit_for(self, market_price_pln: Decimal) -> Decimal:
        """Profit this rule yields on a given market price, before rounding."""
        by_percent = market_price_pln * self.margin_percent / Decimal(100)
        return max(by_percent, self.min_profit_pln)


def margin_for(
    category: ComponentCategory | str,
    market_price_pln: Decimal,
    *,
    position: Decimal = Decimal(0),
    config: PricingConfig | None = None,
    target_margin_percent: Decimal | None = None,
) -> MarginRule:
    """The rule for one product.

    ``position`` picks a percent inside the category range - the optimiser
    raises every category by the same fraction, so profit is spread across the
    order instead of being loaded onto the most expensive part.
    ``target_margin_percent`` overrides the range entirely (an admin trimming a
    margin to win a deal); the band minimum still applies, so an override can
    never push an item into a loss.
    """
    cfg = config or get_pricing_config()
    key = category.value if isinstance(category, ComponentCategory) else str(category)
    percent = (
        Decimal(target_margin_percent)
        if target_margin_percent is not None
        else cfg.margin_percent_for(key, position)
    )
    return MarginRule(
        category=key,
        margin_percent=percent,
        min_profit_pln=cfg.min_profit_for(market_price_pln),
        position=max(Decimal(0), min(Decimal(1), position)),
    )
