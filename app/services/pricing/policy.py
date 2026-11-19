"""Commercial pricing policy.

Every number a shop owner might want to tune lives here, not inside the
engine: hourly rate, margin tiers, service reserve, profit floors and how a
price is rounded. Changing the business model must never mean editing pricing
logic.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.services.pricing.complexity import ComplexityLevel


class MarginTier(BaseModel):
    """Component margin for orders up to ``up_to_pln``."""

    model_config = ConfigDict(frozen=True)

    #: ``None`` means "everything above the previous tier".
    up_to_pln: Decimal | None
    percent: Decimal = Field(ge=0, le=60)


#: Thinner margin as the ticket grows: a percentage that is fair on a 3 000 PLN
#: machine makes a 15 000 PLN one uncompetitive, while a flat fee earns far too
#: little at the bottom.
DEFAULT_MARGIN_TIERS: tuple[MarginTier, ...] = (
    MarginTier(up_to_pln=Decimal(3000), percent=Decimal(10)),
    MarginTier(up_to_pln=Decimal(5000), percent=Decimal("8.5")),
    MarginTier(up_to_pln=Decimal(8000), percent=Decimal(7)),
    MarginTier(up_to_pln=Decimal(12000), percent=Decimal(6)),
    MarginTier(up_to_pln=None, percent=Decimal(5)),
)

#: Cover for re-diagnosis, a return, or a customer who needs more help than
#: usual. Scales with how likely the build is to cause trouble.
DEFAULT_SERVICE_RESERVE: dict[ComplexityLevel, Decimal] = {
    ComplexityLevel.EASY: Decimal(50),
    ComplexityLevel.STANDARD: Decimal(75),
    ComplexityLevel.ADVANCED: Decimal(100),
    ComplexityLevel.COMPLEX: Decimal(150),
    ComplexityLevel.EXTREME: Decimal(250),
}


class PricingPolicy(BaseModel):
    """The commercial rules. Serialisable, so it can be snapshotted per order."""

    model_config = ConfigDict(frozen=True)

    #: What an hour of the owner's time should earn.
    target_hourly_earnings_pln: Decimal = Field(default=Decimal(150), gt=0)

    #: Floors. Whichever binds harder wins.
    minimum_profit_per_order_pln: Decimal = Field(default=Decimal(500), ge=0)
    minimum_profit_per_hour_pln: Decimal = Field(default=Decimal(100), ge=0)

    margin_tiers: tuple[MarginTier, ...] = DEFAULT_MARGIN_TIERS
    service_reserve_pln: dict[ComplexityLevel, Decimal] = Field(
        default_factory=lambda: dict(DEFAULT_SERVICE_RESERVE)
    )

    #: Prices are rounded up to end in ``step - 1``: 6 562 -> 6 599.
    rounding_step_pln: int = Field(default=100, gt=0)

    def margin_percent_for(self, component_cost_pln: Decimal) -> Decimal:
        for tier in self.margin_tiers:
            if tier.up_to_pln is None or component_cost_pln <= tier.up_to_pln:
                return tier.percent
        return self.margin_tiers[-1].percent

    def component_margin_pln(self, component_cost_pln: Decimal) -> Decimal:
        percent = self.margin_percent_for(component_cost_pln)
        return (component_cost_pln * percent / Decimal(100)).quantize(Decimal("0.01"))

    def reserve_for(self, level: ComplexityLevel) -> Decimal:
        return self.service_reserve_pln.get(level, DEFAULT_SERVICE_RESERVE[level])

    def as_snapshot(self) -> dict:
        """Frozen copy stored with an order, so old orders stay explainable."""
        return {
            "target_hourly_earnings_pln": str(self.target_hourly_earnings_pln),
            "minimum_profit_per_order_pln": str(self.minimum_profit_per_order_pln),
            "minimum_profit_per_hour_pln": str(self.minimum_profit_per_hour_pln),
            "margin_tiers": [
                {
                    "up_to_pln": str(tier.up_to_pln) if tier.up_to_pln is not None else None,
                    "percent": str(tier.percent),
                }
                for tier in self.margin_tiers
            ],
            "service_reserve_pln": {
                level.value: str(value) for level, value in self.service_reserve_pln.items()
            },
            "rounding_step_pln": self.rounding_step_pln,
        }
