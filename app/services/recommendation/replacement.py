"""Smart replacement when a build conflicts with what the customer fixed.

Given a set of parts and a failing compatibility report, find the
*least* disruptive change: never touch a LOCKED part, change FLEXIBLE
parts before PREFERRED ones, and offer alternatives that are close in
performance, fit physically and electrically, stay inside the budget and
keep the requested look.

    User locked the case, the GPU is too long
        -> "To keep your case I suggest replacing the GPU" + options

    User locked the GPU
        -> case / PSU / board are picked around it by the generator; if
           the stored build stops fitting, those are what gets replaced.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.components import (
    CaseSpec,
    Colour,
    Component,
    ComponentCategory,
    CoolerSpec,
    CpuSpec,
    GpuSpec,
    PsuSpec,
    RamSpec,
    SsdSpec,
)
from app.domain.requirements import BuildRequirements, ComponentStatus
from app.services.catalog import Catalog
from app.services.compatibility import CompatibilityReport, validate_build
from app.services.compatibility.report import Check

logger = logging.getLogger(__name__)

Parts = dict[ComponentCategory, Component]
PriceBook = Mapping[str, Decimal]

#: How far a replacement may stray from the original's performance rating.
PERFORMANCE_TOLERANCE = 0.15

C = ComponentCategory

#: Which parts a failing check is about, by the pair label the report uses.
PAIR_CATEGORIES: dict[str, tuple[ComponentCategory, ...]] = {
    "CPU → Motherboard": (C.CPU, C.MOTHERBOARD),
    "Motherboard → RAM": (C.RAM, C.MOTHERBOARD),
    "CPU → Cooler": (C.COOLER, C.CPU),
    "GPU → Case": (C.GPU, C.CASE),
    "Cooler → Case": (C.COOLER, C.CASE),
    "Cooler → RAM": (C.COOLER, C.RAM),
    "Motherboard → Case": (C.MOTHERBOARD, C.CASE),
    "PSU → Case": (C.PSU, C.CASE),
    "PSU Wattage": (C.PSU, C.GPU),
    "GPU Power": (C.PSU, C.GPU),
    "SSD → Motherboard": (C.SSD, C.MOTHERBOARD),
    "Drives → Case": (C.SSD, C.CASE),
    "Fans → Case": (C.FANS, C.CASE),
    "Fans → Motherboard": (C.FANS, C.MOTHERBOARD),
    "ARGB → Motherboard": (C.MOTHERBOARD, C.CASE, C.COOLER, C.RAM, C.FANS),
    "Front panel → Motherboard": (C.MOTHERBOARD, C.CASE),
    "Monitor → GPU": (C.MONITOR, C.GPU),
}


@dataclass(slots=True)
class Replacement:
    component: Component
    report: CompatibilityReport
    price_delta_pln: Decimal
    performance_delta: float = 0.0

    @property
    def compatible(self) -> bool:
        return self.report.compatible


@dataclass(slots=True)
class ConflictResolution:
    """What to change and the options for it."""

    category: ComponentCategory
    status: ComponentStatus
    #: Locked parts that caused the conflict and are being kept.
    kept: list[ComponentCategory] = field(default_factory=list)
    replacements: list[Replacement] = field(default_factory=list)
    #: Checks that led here, for the admin / the explanation.
    because: list[Check] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return bool(self.replacements)


def involved_categories(check: Check) -> tuple[ComponentCategory, ...]:
    return PAIR_CATEGORIES.get(check.pair, ())


def _rating(component: Component) -> float | None:
    spec = component.spec
    if isinstance(spec, GpuSpec):
        return float(spec.performance_index)
    if isinstance(spec, CpuSpec):
        return float(spec.gaming_index + spec.performance_index) / 2
    return None


def _at_least_as_capable(candidate: Component, original: Component) -> bool:
    """Category-specific floor so a 'replacement' is not a downgrade in kind."""
    c, o = candidate.spec, original.spec
    if isinstance(c, RamSpec) and isinstance(o, RamSpec):
        return c.memory_type is o.memory_type and c.total_capacity_gb >= o.total_capacity_gb
    if isinstance(c, SsdSpec) and isinstance(o, SsdSpec):
        return c.capacity_gb >= o.capacity_gb
    if isinstance(c, PsuSpec) and isinstance(o, PsuSpec):
        return c.wattage >= o.wattage
    if isinstance(c, CoolerSpec) and isinstance(o, CoolerSpec):
        return c.tdp_rating_w >= o.tdp_rating_w
    return True


def _style_rank(component: Component, requirements: BuildRequirements) -> int:
    """0 = matches the requested look, 1 = does not. Only visible parts count."""
    spec = component.spec
    colour = getattr(spec, "colour", None)
    rgb = getattr(spec, "rgb", None)
    if not isinstance(spec, CaseSpec | CoolerSpec | RamSpec):
        return 0
    if requirements.aesthetics.is_white and colour is not Colour.WHITE:
        return 1
    if requirements.aesthetics.wants_rgb and rgb is False:
        return 1
    return 0


def suggest_replacements(
    parts: Parts,
    category: ComponentCategory,
    requirements: BuildRequirements,
    catalog: Catalog,
    prices: PriceBook,
    *,
    limit: int = 3,
    acquisition_budget_pln: Decimal | None = None,
) -> list[Replacement]:
    """Compatible alternatives for one part, closest in price first.

    Every option is validated against the *whole* build, so the result is
    never "fits the case but not the power supply".
    """
    original = parts.get(category)
    original_price = prices.get(original.id, Decimal(0)) if original is not None else Decimal(0)
    original_rating = _rating(original) if original is not None else None
    others_cost = sum(
        (prices.get(part.id, Decimal(0)) for cat, part in parts.items() if cat != category),
        Decimal(0),
    )

    found: list[Replacement] = []
    for candidate in catalog.by_category(category):
        if original is not None and candidate.id == original.id:
            continue
        price = prices.get(candidate.id)
        if price is None:
            continue
        if acquisition_budget_pln is not None and others_cost + price > acquisition_budget_pln:
            continue
        if original is not None and not _at_least_as_capable(candidate, original):
            continue
        rating = _rating(candidate)
        performance_delta = 0.0
        if original_rating and rating is not None:
            performance_delta = (rating - original_rating) / original_rating
            if performance_delta < -PERFORMANCE_TOLERANCE:
                continue

        trial = dict(parts)
        trial[category] = candidate
        report = validate_build(trial)
        if not report.compatible:
            continue
        found.append(
            Replacement(
                component=candidate,
                report=report,
                price_delta_pln=(price - original_price).quantize(Decimal("0.01")),
                performance_delta=performance_delta,
            )
        )

    found.sort(
        key=lambda r: (
            _style_rank(r.component, requirements),
            abs(r.price_delta_pln),
            -r.performance_delta,
        )
    )
    return found[:limit]


def resolve_conflict(
    parts: Parts,
    report: CompatibilityReport,
    requirements: BuildRequirements,
    catalog: Catalog,
    prices: PriceBook,
    *,
    acquisition_budget_pln: Decimal | None = None,
    limit: int = 3,
) -> ConflictResolution | None:
    """Pick the part to change for a failing report and list alternatives.

    Order of sacrifice: FLEXIBLE parts first, PREFERRED next, LOCKED never.
    Returns ``None`` when the report has nothing blocking, and a resolution
    with no replacements when every involved part is locked or nothing in
    the catalogue resolves it.
    """
    blocking = [check for check in report.checks if check.blocking]
    if not blocking:
        return None

    involved: list[ComponentCategory] = []
    for check in blocking:
        for category in involved_categories(check):
            if category in parts and category not in involved:
                involved.append(category)

    kept = [c for c in involved if requirements.status_of(c) is ComponentStatus.LOCKED]
    order = [c for c in involved if requirements.status_of(c) is ComponentStatus.FLEXIBLE] + [
        c for c in involved if requirements.status_of(c) is ComponentStatus.PREFERRED
    ]

    for category in order:
        options = suggest_replacements(
            parts,
            category,
            requirements,
            catalog,
            prices,
            limit=limit,
            acquisition_budget_pln=acquisition_budget_pln,
        )
        if options:
            return ConflictResolution(
                category=category,
                status=requirements.status_of(category),
                kept=kept,
                replacements=options,
                because=blocking,
            )

    fallback = order[0] if order else (involved[0] if involved else C.GPU)
    logger.info(
        "No replacement resolves the conflict (involved=%s, locked=%s)",
        [c.value for c in involved],
        [c.value for c in kept],
    )
    return ConflictResolution(
        category=fallback,
        status=requirements.status_of(fallback),
        kept=kept,
        replacements=[],
        because=blocking,
    )
