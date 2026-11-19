"""Is our build price still competitive?

Compares the customer price against a market reference for a *similar* build
and warns when the gap is wider than the configured tolerance. The reference
must come from outside - a named source the admin recorded - because there
is no live market feed, and the engine refuses to invent one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.services.pricing.config import PricingConfig, get_pricing_config


class Competitiveness(StrEnum):
    UNAVAILABLE = "unavailable"
    COMPETITIVE = "competitive"
    ABOVE_MARKET = "above_market"
    BELOW_MARKET = "below_market"


@dataclass(slots=True)
class CompetitivenessReport:
    status: Competitiveness
    our_price_pln: Decimal
    reference_low_pln: Decimal | None = None
    reference_high_pln: Decimal | None = None
    reference_source: str | None = None
    difference_percent: Decimal | None = None
    suggestions: list[str] = field(default_factory=list)

    @property
    def warning(self) -> str | None:
        if self.status is not Competitiveness.ABOVE_MARKET:
            return None
        low = self.reference_low_pln or Decimal(0)
        high = self.reference_high_pln or low
        return (
            f"⚠️ Price competitiveness warning\n"
            f"Similar market builds: {low:.0f}-{high:.0f} PLN\n"
            f"Our price: {self.our_price_pln:.0f} PLN\n"
            f"Difference: +{self.difference_percent}%"
        )

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "our_price": str(self.our_price_pln),
            "reference_low": str(self.reference_low_pln) if self.reference_low_pln else None,
            "reference_high": str(self.reference_high_pln) if self.reference_high_pln else None,
            "reference_source": self.reference_source,
            "difference_percent": str(self.difference_percent)
            if self.difference_percent is not None
            else None,
        }


def check_competitiveness(
    our_price_pln: Decimal,
    reference_low_pln: Decimal | None = None,
    reference_high_pln: Decimal | None = None,
    *,
    reference_source: str | None = None,
    config: PricingConfig | None = None,
) -> CompetitivenessReport:
    """Compare against a recorded market range. No reference → UNAVAILABLE."""
    cfg = config or get_pricing_config()
    report = CompetitivenessReport(
        status=Competitiveness.UNAVAILABLE,
        our_price_pln=our_price_pln,
        reference_low_pln=reference_low_pln,
        reference_high_pln=reference_high_pln,
        reference_source=reference_source,
    )
    if reference_low_pln is None or reference_low_pln <= 0:
        return report

    high = (
        reference_high_pln
        if reference_high_pln and reference_high_pln >= reference_low_pln
        else reference_low_pln
    )
    report.reference_high_pln = high

    if our_price_pln > high:
        gap = ((our_price_pln - high) / high * Decimal(100)).quantize(Decimal("0.1"), ROUND_HALF_UP)
        report.difference_percent = gap
        if gap > cfg.competitiveness_warn_percent:
            report.status = Competitiveness.ABOVE_MARKET
            report.suggestions = [
                "reduce the margin on the most expensive part",
                "swap a component for a cheaper equivalent",
                "drop an accessory from the bundle",
                "keep the price if the service/warranty justifies it",
            ]
        else:
            report.status = Competitiveness.COMPETITIVE
    elif our_price_pln < reference_low_pln:
        gap = ((reference_low_pln - our_price_pln) / reference_low_pln * Decimal(100)).quantize(
            Decimal("0.1"), ROUND_HALF_UP
        )
        report.difference_percent = -gap
        report.status = Competitiveness.BELOW_MARKET
    else:
        report.difference_percent = Decimal(0)
        report.status = Competitiveness.COMPETITIVE

    return report
