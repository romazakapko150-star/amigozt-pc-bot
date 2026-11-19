"""Time an order actually costs, end to end.

Building the machine is a fraction of the work. Talking to the customer,
sourcing parts, checking the delivery, BIOS and EXPO, driver setup, stress
testing, packing and the questions afterwards all take real hours, and the
price has to reflect them.

Everything here is derived from the configuration. Nothing needs to be typed
in per order.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.components import Component, ComponentCategory
from app.services.pricing.complexity import ComplexityAssessment

#: Only the number of parts matters here, so a read-only mapping is enough.
Parts = Mapping[ComponentCategory, Component]


@dataclass(frozen=True, slots=True)
class BaseHours:
    """Hours a straightforward build takes before complexity is added.

    Defaults are calibrated against a normal ATX tower with air cooling; the
    total lands close to four hours, which matches the shop's own estimate.
    """

    customer_communication: float = 0.30
    configuration: float = 0.30
    #: Fixed part of sourcing; the per-component part is added separately.
    procurement_base: float = 0.15
    procurement_per_component: float = 0.03
    receiving_check: float = 0.20
    assembly: float = 1.20
    cable_management: float = 0.30
    bios_setup: float = 0.20
    software_setup: float = 0.20
    testing: float = 0.70
    packaging: float = 0.20
    delivery: float = 0.00
    support_reserve: float = 0.30


@dataclass(slots=True)
class TimeBreakdown:
    """Hours per activity. The admin panel shows this verbatim."""

    customer_communication_hours: float = 0.0
    configuration_hours: float = 0.0
    procurement_hours: float = 0.0
    receiving_check_hours: float = 0.0
    assembly_hours: float = 0.0
    cable_management_hours: float = 0.0
    bios_setup_hours: float = 0.0
    software_setup_hours: float = 0.0
    testing_hours: float = 0.0
    packaging_hours: float = 0.0
    delivery_hours: float = 0.0
    support_reserve_hours: float = 0.0

    #: Where the complexity minutes landed, for explainability.
    complexity_notes: list[str] = field(default_factory=list)

    @property
    def total_hours(self) -> float:
        return round(
            self.customer_communication_hours
            + self.configuration_hours
            + self.procurement_hours
            + self.receiving_check_hours
            + self.assembly_hours
            + self.cable_management_hours
            + self.bios_setup_hours
            + self.software_setup_hours
            + self.testing_hours
            + self.packaging_hours
            + self.delivery_hours
            + self.support_reserve_hours,
            2,
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "customer_communication": round(self.customer_communication_hours, 2),
            "configuration": round(self.configuration_hours, 2),
            "procurement": round(self.procurement_hours, 2),
            "receiving_check": round(self.receiving_check_hours, 2),
            "assembly": round(self.assembly_hours, 2),
            "cable_management": round(self.cable_management_hours, 2),
            "bios_setup": round(self.bios_setup_hours, 2),
            "software_setup": round(self.software_setup_hours, 2),
            "testing": round(self.testing_hours, 2),
            "packaging": round(self.packaging_hours, 2),
            "delivery": round(self.delivery_hours, 2),
            "support_reserve": round(self.support_reserve_hours, 2),
            "total": self.total_hours,
        }


#: Which activity each complexity factor slows down. Putting SFF minutes into
#: "assembly" and ARGB minutes into "cable management" keeps the breakdown
#: honest enough to argue with.
_FACTOR_BUCKET: dict[str, str] = {
    "sff": "assembly",
    "compact": "cable_management",
    "many_fans": "cable_management",
    "argb": "cable_management",
    "aio": "assembly",
    "tall_cooler": "assembly",
    "large_gpu": "assembly",
    "non_modular_psu": "cable_management",
    "heavy_psu": "cable_management",
    "multi_drive": "assembly",
}


def estimate_time(
    parts: Parts,
    complexity: ComplexityAssessment,
    base: BaseHours | None = None,
) -> TimeBreakdown:
    """Total hours for this order, activity by activity."""
    hours = base or BaseHours()
    component_count = len(parts)

    breakdown = TimeBreakdown(
        customer_communication_hours=hours.customer_communication,
        configuration_hours=hours.configuration,
        # Sourcing scales with the number of separate things to find, compare
        # and order.
        procurement_hours=hours.procurement_base
        + hours.procurement_per_component * component_count,
        receiving_check_hours=hours.receiving_check,
        assembly_hours=hours.assembly,
        cable_management_hours=hours.cable_management,
        bios_setup_hours=hours.bios_setup,
        software_setup_hours=hours.software_setup,
        testing_hours=hours.testing,
        packaging_hours=hours.packaging,
        delivery_hours=hours.delivery,
        support_reserve_hours=hours.support_reserve,
    )

    for factor in complexity.factors:
        bucket = _FACTOR_BUCKET.get(factor.code, "assembly")
        extra = factor.extra_minutes / 60
        current = getattr(breakdown, f"{bucket}_hours")
        setattr(breakdown, f"{bucket}_hours", current + extra)

    breakdown.complexity_notes = complexity.describe()
    return breakdown


def labor_value_pln(breakdown: TimeBreakdown, hourly_rate_pln: Decimal) -> Decimal:
    """What the time is worth at the configured rate."""
    return (Decimal(str(breakdown.total_hours)) * hourly_rate_pln).quantize(Decimal("0.01"))
