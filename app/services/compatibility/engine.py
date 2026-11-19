"""Compatibility engine.

Pure functions over a mapping of category -> component. No database, no
aiogram: a build can be validated in a unit test in microseconds.

``validate(parts)`` runs every rule in ``rules/`` and returns a
``CompatibilityReport``. A build is offered to a customer only when
``report.ok`` - no failed check and no *critical* check left UNKNOWN by
missing catalogue data. Physical fit is judged before anything else; price,
looks and profit never override it.
"""

from __future__ import annotations

from app.domain.components import Component, ComponentCategory
from app.services.compatibility.power import (
    BASE_SYSTEM_DRAW_W,
    PSU_SAFETY_FACTOR,
    PowerBudget,
    estimate_power_draw_w,
    power_budget,
    recommended_psu_w,
)
from app.services.compatibility.report import (
    Check,
    CheckStatus,
    CompatibilityReport,
    Issue,
    Severity,
)
from app.services.compatibility.rules import ALL_RULES

Parts = dict[ComponentCategory, Component]


def validate(parts: Parts) -> CompatibilityReport:
    """Run every rule against a set of parts."""
    report = CompatibilityReport()
    for rule in ALL_RULES:
        rule(parts, report)
    return report


def validate_build(parts: Parts) -> CompatibilityReport:
    """The pre-order gate. Same report; the name states the intent."""
    return validate(parts)


__all__ = [
    "BASE_SYSTEM_DRAW_W",
    "PSU_SAFETY_FACTOR",
    "Check",
    "CheckStatus",
    "CompatibilityReport",
    "Issue",
    "Parts",
    "PowerBudget",
    "Severity",
    "estimate_power_draw_w",
    "power_budget",
    "recommended_psu_w",
    "validate",
    "validate_build",
]
