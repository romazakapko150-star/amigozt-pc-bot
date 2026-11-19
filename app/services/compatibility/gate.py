"""The pre-order gate.

A build is generated compatible, but between "generate" and "order" the
catalogue can change, a shelf entry can go stale, or a stored component id
can stop resolving. So the moment a customer confirms an order the stored
component ids are resolved again and re-validated, and the result is frozen
into the lead. A build that fails here is never turned into a lead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.domain.components import Component, ComponentCategory
from app.services.catalog import Catalog, get_catalog
from app.services.compatibility.engine import Parts, validate_build
from app.services.compatibility.power import power_budget
from app.services.compatibility.report import CheckStatus, CompatibilityReport

logger = logging.getLogger(__name__)

#: Codes a customer can act on, with an explanation in their language.
CUSTOMER_BLOCK_CODES: frozenset[str] = frozenset(
    {
        "gpu_too_long",
        "gpu_front_radiator",
        "gpu_slots",
        "board_form_factor",
        "cooler_too_tall",
        "radiator_unsupported",
        "psu_too_long",
        "psu_form_factor",
        "psu_underpowered",
        "psu_gpu_minimum",
        "gpu_power_connector",
        "socket_mismatch",
        "memory_type_mismatch",
        "argb_header",
        "missing_part",
    }
)


@dataclass(slots=True)
class GateResult:
    parts: Parts
    report: CompatibilityReport
    unknown_ids: list[str]

    @property
    def compatible(self) -> bool:
        return self.report.compatible and not self.unknown_ids

    def snapshot(self) -> dict:
        data = self.report.as_dict()
        data["power"] = power_budget(self.parts).as_dict()
        data["components"] = {
            category.value: component.id for category, component in self.parts.items()
        }
        if self.unknown_ids:
            data["unknown_component_ids"] = list(self.unknown_ids)
        return data

    def customer_reason_codes(self) -> list[str]:
        """Blocking check codes worth explaining to the customer, in report order."""
        codes: list[str] = []
        for check in self.report.checks:
            if not check.blocking:
                continue
            code = check.code if check.code in CUSTOMER_BLOCK_CODES else "generic"
            if code not in codes:
                codes.append(code)
        if self.unknown_ids and "generic" not in codes:
            codes.append("generic")
        return codes or ["generic"]


def parts_from_ids(components: dict, catalog: Catalog) -> tuple[Parts, list[str]]:
    parts: Parts = {}
    unknown: list[str] = []
    for raw_category, component_id in (components or {}).items():
        try:
            category = ComponentCategory(str(raw_category))
        except ValueError:
            unknown.append(str(component_id))
            continue
        component: Component | None = catalog.get(str(component_id))
        if component is None:
            unknown.append(str(component_id))
            continue
        parts[category] = component
    return parts, unknown


def check_components(components: dict, catalog: Catalog | None = None) -> GateResult:
    """Re-validate stored component ids against the current catalogue."""
    parts, unknown = parts_from_ids(components, catalog or get_catalog())
    report = validate_build(parts)
    if unknown:
        logger.warning("Order gate: unknown component ids %s", unknown)
    if not report.compatible:
        logger.warning(
            "Order gate blocked a build: %s",
            "; ".join(c.detail for c in report.checks if c.blocking),
        )
    return GateResult(parts=parts, report=report, unknown_ids=unknown)


def statuses_of(report: CompatibilityReport) -> dict[str, int]:
    counts: dict[str, int] = {}
    for check in report.checks:
        counts[check.status.value] = counts.get(check.status.value, 0) + 1
    for status in CheckStatus:
        counts.setdefault(status.value, 0)
    return counts
