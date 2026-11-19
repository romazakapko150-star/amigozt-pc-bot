"""Build-level profit check.

Pure judgement, no price changes: given what the order would cost to buy and
what it would earn, say whether it clears the owner's profit goals and label
it with the admin-only profit tier. Raising margins or the assembly tier to
*reach* the goal is the optimiser's job (:mod:`optimizer`); this module only
reports where the order landed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.services.pricing.config import AssemblyTier, PricingConfig, ProfitTier, get_pricing_config

CENT = Decimal("0.01")


@dataclass(slots=True)
class ProfitCheck:
    market_cost_pln: Decimal
    product_profit_pln: Decimal
    assembly_fee_pln: Decimal
    other_services_pln: Decimal
    minimum_profit_pln: Decimal
    target_profit_pln: Decimal
    tier: ProfitTier
    warnings: list[str] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)

    #: Kept for call sites written against the earlier model.
    @property
    def service_fee_pln(self) -> Decimal:
        return self.assembly_fee_pln

    @property
    def total_profit_pln(self) -> Decimal:
        return (self.product_profit_pln + self.assembly_fee_pln + self.other_services_pln).quantize(
            CENT
        )

    @property
    def is_loss(self) -> bool:
        return self.total_profit_pln < 0

    @property
    def meets_minimum(self) -> bool:
        return self.total_profit_pln >= self.minimum_profit_pln

    @property
    def meets_target(self) -> bool:
        return self.total_profit_pln >= self.target_profit_pln

    @property
    def ok(self) -> bool:
        return not self.is_loss


def validate_build(
    market_cost_pln: Decimal,
    product_profit_pln: Decimal,
    tier: AssemblyTier,
    *,
    other_services_pln: Decimal = Decimal(0),
    config: PricingConfig | None = None,
) -> ProfitCheck:
    """Judge the economics of one build."""
    cfg = config or get_pricing_config()
    total = (product_profit_pln + tier.fee_pln + other_services_pln).quantize(CENT)
    check = ProfitCheck(
        market_cost_pln=market_cost_pln.quantize(CENT),
        product_profit_pln=product_profit_pln.quantize(CENT),
        assembly_fee_pln=tier.fee_pln,
        other_services_pln=other_services_pln,
        minimum_profit_pln=cfg.profit.minimum_order_profit_pln,
        target_profit_pln=cfg.profit.target_order_profit_pln,
        tier=cfg.profit_tier_for(total),
    )

    if check.is_loss:
        check.warnings.append(
            f"LOSS: total profit {check.total_profit_pln} PLN - do not sell at this price"
        )
    elif not check.meets_minimum:
        check.warnings.append(
            f"profit {check.total_profit_pln} PLN is below the "
            f"{cfg.profit.minimum_order_profit_pln} PLN minimum - cheaper supplier, "
            "alternative part, or accept consciously"
        )
    return check
