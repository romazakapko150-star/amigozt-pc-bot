"""Commercial pricing of a whole build.

    for every part:   market price → category margin (low end) → price ending in 9
    optimiser:        raise all margins together, then the assembly tier,
                      until the order earns the target profit - never above
                      a known market reference
    + assembly fee    (Basic / Standard / Premium, by build complexity)
    + other services
    = raw price  →  rounded UP to …49 / …99  =  CUSTOMER PRICE

    customer price - best purchase cost            = total gross profit
    total gross profit - estimated operating costs = estimated net profit

Profit comes from honest places only: a category-specific margin on each
product, a visible paid assembly service, and nothing else. Market prices
that are *verified* are used as-is, *estimated* ones are used but flagged so
the customer card says "approximate", *unknown* or *historical* ones are
refused and reported rather than guessed.

``CommercialQuote.client_price_pln``, ``components_price_pln``,
``assembly_fee_pln``, ``assembly_tier_name`` and ``is_approximate`` are the
customer-facing fields. Everything else is admin-only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal

from app.domain.components import Component, ComponentCategory
from app.services.pricing.competitiveness import CompetitivenessReport, check_competitiveness
from app.services.pricing.complexity import ComplexityAssessment, ComplexityLevel, assess
from app.services.pricing.config import AssemblyTier, PricingConfig, ProfitTier, get_pricing_config
from app.services.pricing.currency import Money, pln
from app.services.pricing.customer import CustomerPrice
from app.services.pricing.labor import BaseHours, TimeBreakdown, estimate_time, labor_value_pln
from app.services.pricing.market import MarketPrice, MarketPriceService
from app.services.pricing.optimizer import OptimisationResult, optimise
from app.services.pricing.policy import PricingPolicy
from app.services.pricing.validator import ProfitCheck, validate_build

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")

Parts = dict[ComponentCategory, Component]


def commercial_round(amount: Decimal, step: int = 50) -> Decimal:
    """Round *up* to the next price ending in ``step - 1``.

    With the default step of 50 that is …49 or …99: 6 387 → 6 399,
    6 421 → 6 449, 6 478 → 6 499. Only ever upwards.
    """
    if amount <= 0:
        return Decimal(0)
    step_dec = Decimal(step)
    blocks = (amount / step_dec).to_integral_value(rounding=ROUND_FLOOR)
    candidate = blocks * step_dec + (step_dec - 1)
    if candidate < amount:
        candidate += step_dec
    return candidate.quantize(CENT)


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """What a sale is made of. Admin-only, every field in the base currency.

    ``supplier_cost`` is what the parts cost to buy, ``internal_cost`` what
    selling one costs the business (payment fees, packaging, the share of
    running costs), ``margin`` what is left, and ``customer_price`` the one
    number the customer ever sees. They add up by construction:

        supplier_cost + internal_cost + margin == customer_price

    There are no hidden extras on top of ``customer_price`` - it is the
    real price of the sale, and the other three are how it is composed.
    """

    supplier_cost_pln: Decimal
    internal_cost_pln: Decimal
    margin_pln: Decimal
    customer_price_pln: Decimal

    @property
    def balances(self) -> bool:
        total = self.supplier_cost_pln + self.internal_cost_pln + self.margin_pln
        return abs(total - self.customer_price_pln) <= Decimal("0.05")

    @property
    def margin_percent(self) -> Decimal:
        if self.customer_price_pln <= 0:
            return Decimal(0)
        return (self.margin_pln / self.customer_price_pln * 100).quantize(Decimal("0.1"))

    def as_money(self) -> dict[str, Money]:
        """The same four numbers as :class:`Money`, for display layers."""
        return {
            "supplier_cost": pln(self.supplier_cost_pln),
            "internal_cost": pln(self.internal_cost_pln),
            "margin": pln(self.margin_pln),
            "customer_price": pln(self.customer_price_pln),
        }


@dataclass(slots=True)
class CommercialQuote:
    """The full commercial picture for one configuration."""

    items: dict[ComponentCategory, CustomerPrice]
    unpriced: dict[ComponentCategory, MarketPrice]
    complexity: ComplexityAssessment
    time: TimeBreakdown
    assembly_key: str
    assembly_tier: AssemblyTier
    other_services_pln: Decimal
    margin_position: Decimal
    profit_check: ProfitCheck
    client_price_pln: Decimal
    policy: PricingPolicy
    config: PricingConfig
    competitiveness: CompetitivenessReport
    adjustments: list[str] = field(default_factory=list)

    # --- customer side --------------------------------------------------

    @property
    def components_price_pln(self) -> Decimal:
        return sum((item.customer_price_pln for item in self.items.values()), Decimal(0)).quantize(
            CENT
        )

    @property
    def assembly_fee_pln(self) -> Decimal:
        return self.assembly_tier.fee_pln

    @property
    def assembly_tier_name(self) -> str:
        return self.assembly_tier.name

    @property
    def assembly_includes(self) -> tuple[str, ...]:
        return self.assembly_tier.includes

    @property
    def is_approximate(self) -> bool:
        """True unless every part carries a verified market price."""
        return any(not item.market.is_verified for item in self.items.values())

    @property
    def complete(self) -> bool:
        return not self.unpriced

    # --- admin side: the ten numbers ------------------------------------

    @property
    def market_cost_pln(self) -> Decimal:
        return sum((item.market_price_pln for item in self.items.values()), Decimal(0)).quantize(
            CENT
        )

    @property
    def purchase_cost_pln(self) -> Decimal:
        """Best purchase cost. Equals market cost until supplier offers exist."""
        return self.market_cost_pln

    @property
    def product_profit_pln(self) -> Decimal:
        return sum((item.profit_pln for item in self.items.values()), Decimal(0)).quantize(CENT)

    @property
    def raw_sale_price_pln(self) -> Decimal:
        return (
            self.components_price_pln + self.assembly_fee_pln + self.other_services_pln
        ).quantize(CENT)

    @property
    def rounding_uplift_pln(self) -> Decimal:
        return (self.client_price_pln - self.raw_sale_price_pln).quantize(CENT)

    @property
    def gross_profit_pln(self) -> Decimal:
        return (self.client_price_pln - self.purchase_cost_pln).quantize(CENT)

    @property
    def operating_costs_pln(self) -> Decimal:
        return self.config.operating_costs.estimate(self.client_price_pln)

    @property
    def net_profit_pln(self) -> Decimal:
        return (self.gross_profit_pln - self.operating_costs_pln).quantize(CENT)

    @property
    def margin_percent(self) -> Decimal:
        if self.client_price_pln <= 0:
            return Decimal(0)
        return (self.gross_profit_pln / self.client_price_pln * 100).quantize(Decimal("0.1"))

    @property
    def profit_tier(self) -> ProfitTier:
        return self.config.profit_tier_for(self.gross_profit_pln)

    @property
    def meets_minimum_profit(self) -> bool:
        return self.gross_profit_pln >= self.config.profit.minimum_order_profit_pln

    @property
    def meets_target_profit(self) -> bool:
        return self.gross_profit_pln >= self.config.profit.target_order_profit_pln

    def cost_breakdown(self) -> CostBreakdown:
        """The four numbers the business runs on, in one place.

        Nothing new is computed here - it is a named view over what the
        quote already knows, so that "what did we pay, what did it cost us
        to sell, what did we keep" can be answered without re-deriving it
        at every call site. Only ``customer_price_pln`` may ever be shown
        to a customer.
        """
        return CostBreakdown(
            supplier_cost_pln=self.purchase_cost_pln,
            internal_cost_pln=self.operating_costs_pln,
            margin_pln=self.net_profit_pln,
            customer_price_pln=self.client_price_pln,
        )

    # --- admin side: effort metrics --------------------------------------

    @property
    def estimated_total_hours(self) -> float:
        return self.time.total_hours

    @property
    def labor_value_pln(self) -> Decimal:
        """What the hours would be worth at the target rate - a yardstick, not a charge."""
        return labor_value_pln(self.time, self.policy.target_hourly_earnings_pln)

    @property
    def profit_per_hour_pln(self) -> Decimal:
        hours = Decimal(str(self.estimated_total_hours))
        if hours <= 0:
            return Decimal(0)
        return (self.gross_profit_pln / hours).quantize(CENT)

    @property
    def complexity_level(self) -> ComplexityLevel:
        return self.complexity.level

    @property
    def warnings(self) -> list[str]:
        notes = list(self.profit_check.warnings)
        if self.unpriced:
            names = ", ".join(category.value for category in self.unpriced)
            notes.append(f"no usable market price for: {names}")
        competitiveness = self.competitiveness.warning
        if competitiveness:
            notes.append(competitiveness)
        return notes

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items.values():
            counts[item.status.value] = counts.get(item.status.value, 0) + 1
        for market in self.unpriced.values():
            counts[market.status.value] = counts.get(market.status.value, 0) + 1
        return counts

    def as_snapshot(self) -> dict:
        """Everything needed to explain this price months later."""
        return {
            "market_cost_pln": str(self.market_cost_pln),
            "purchase_cost_pln": str(self.purchase_cost_pln),
            "components_price_pln": str(self.components_price_pln),
            "product_profit_pln": str(self.product_profit_pln),
            "assembly_tier": self.assembly_tier.name,
            "assembly_fee_pln": str(self.assembly_fee_pln),
            "other_services_pln": str(self.other_services_pln),
            "raw_sale_price_pln": str(self.raw_sale_price_pln),
            "rounding_uplift_pln": str(self.rounding_uplift_pln),
            "sale_price_pln": str(self.client_price_pln),
            "gross_profit_pln": str(self.gross_profit_pln),
            "operating_costs_pln": str(self.operating_costs_pln),
            "net_profit_pln": str(self.net_profit_pln),
            "margin_percent": str(self.margin_percent),
            "profit_tier": self.profit_tier.label,
            "margin_position": str(self.margin_position),
            "profit_per_hour_pln": str(self.profit_per_hour_pln),
            "estimated_total_hours": self.estimated_total_hours,
            "labor_value_pln": str(self.labor_value_pln),
            "time_breakdown": self.time.as_dict(),
            "complexity_score": self.complexity.score,
            "complexity_level": self.complexity.level.value,
            "complexity_factors": [
                {"code": f.code, "detail": f.detail, "minutes": f.extra_minutes}
                for f in self.complexity.factors
            ],
            "items": {category.value: item.as_dict() for category, item in self.items.items()},
            "unpriced": {
                category.value: market.as_dict() for category, market in self.unpriced.items()
            },
            "price_statuses": self.status_counts(),
            "adjustments": list(self.adjustments),
            "warnings": self.warnings,
            "competitiveness": self.competitiveness.as_dict(),
            "pricing_config": self.config.as_snapshot(),
            "pricing_policy": self.policy.as_snapshot(),
        }

    # --- aliases for code written against earlier models -----------------

    @property
    def component_cost_pln(self) -> Decimal:
        return self.market_cost_pln

    @property
    def service_fee_pln(self) -> Decimal:
        return self.assembly_fee_pln

    @property
    def service_tier_name(self) -> str:
        return self.assembly_tier_name

    @property
    def component_margin_pln(self) -> Decimal:
        return self.product_profit_pln

    @property
    def service_reserve_pln(self) -> Decimal:
        return Decimal(0)


def quote(
    parts: Parts,
    policy: PricingPolicy,
    *,
    market: MarketPriceService | None = None,
    config: PricingConfig | None = None,
    base_hours: BaseHours | None = None,
    target_margins: dict[ComponentCategory, Decimal] | None = None,
    other_services: dict[str, Decimal] | None = None,
    market_reference_low_pln: Decimal | None = None,
    market_reference_high_pln: Decimal | None = None,
    market_reference_source: str | None = None,
) -> CommercialQuote:
    """Price one configuration end to end."""
    cfg = config or get_pricing_config()
    prices = market or MarketPriceService()

    lookups = {category: prices.lookup(component.id) for category, component in parts.items()}
    complexity = assess(parts)
    time = estimate_time(parts, complexity, base_hours)

    services_total = sum((other_services or {}).values(), Decimal(0)).quantize(CENT)

    result: OptimisationResult = optimise(
        parts,
        lookups,
        cfg.assembly_key_for(complexity.level),
        config=cfg,
        target_margins=target_margins,
        other_services_pln=services_total,
        market_reference_high_pln=market_reference_high_pln,
    )
    tier = cfg.assembly_tier(result.assembly_key)

    check = validate_build(
        result.market_cost_pln,
        result.product_profit_pln,
        tier,
        other_services_pln=services_total,
        config=cfg,
    )

    raw_total = (result.components_price_pln + tier.fee_pln + services_total).quantize(CENT)
    client_price = commercial_round(raw_total, cfg.rounding_step_pln)

    adjustments = list(result.steps)
    if client_price != raw_total:
        adjustments.append("commercial rounding of the total")

    competitiveness = check_competitiveness(
        client_price,
        market_reference_low_pln,
        market_reference_high_pln,
        reference_source=market_reference_source,
        config=cfg,
    )

    warnings_from_optimiser = [w for w in result.warnings if w not in check.warnings]
    check.warnings.extend(warnings_from_optimiser)

    if result.unpriced:
        logger.info(
            "Quote has unpriced parts: %s",
            ", ".join(f"{c.value}={m.status.value}" for c, m in result.unpriced.items()),
        )

    return CommercialQuote(
        items=result.items,
        unpriced=result.unpriced,
        complexity=complexity,
        time=time,
        assembly_key=result.assembly_key,
        assembly_tier=tier,
        other_services_pln=services_total,
        margin_position=result.position,
        profit_check=check,
        client_price_pln=client_price,
        policy=policy,
        config=cfg,
        competitiveness=competitiveness,
        adjustments=adjustments,
    )
