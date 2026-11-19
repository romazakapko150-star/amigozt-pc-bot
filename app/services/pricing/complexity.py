"""How hard a build is to actually put together.

Complexity is expressed in two ways: a score that buckets a build into a
level, and - more importantly - the extra minutes each awkward detail adds to
the job. The minutes are what feed the labour calculation, so a fiddly build
is paid for because it takes longer, not because of an arbitrary surcharge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.components import (
    CaseSpec,
    Component,
    ComponentCategory,
    CoolerSpec,
    CoolerType,
    FormFactor,
    GpuSpec,
    PsuSpec,
    RamSpec,
)

Parts = dict[ComponentCategory, Component]


class ComplexityLevel(StrEnum):
    EASY = "easy"
    STANDARD = "standard"
    ADVANCED = "advanced"
    COMPLEX = "complex"
    EXTREME = "extreme"


@dataclass(frozen=True, slots=True)
class ComplexityFactor:
    """One thing about this build that costs extra effort."""

    code: str
    detail: str
    score: int
    extra_minutes: int


@dataclass(slots=True)
class ComplexityAssessment:
    factors: list[ComplexityFactor] = field(default_factory=list)
    level: ComplexityLevel = ComplexityLevel.STANDARD

    @property
    def score(self) -> int:
        return sum(factor.score for factor in self.factors)

    @property
    def extra_minutes(self) -> int:
        return sum(factor.extra_minutes for factor in self.factors)

    @property
    def extra_hours(self) -> float:
        return self.extra_minutes / 60

    def describe(self) -> list[str]:
        return [f"{factor.detail} (+{factor.extra_minutes} мин)" for factor in self.factors]


#: Score at which each level starts. Tunable without touching the rules.
DEFAULT_THRESHOLDS: dict[ComplexityLevel, int] = {
    ComplexityLevel.EASY: 0,
    ComplexityLevel.STANDARD: 10,
    ComplexityLevel.ADVANCED: 28,
    ComplexityLevel.COMPLEX: 50,
    ComplexityLevel.EXTREME: 75,
}

#: A card this long fights the cooler, the drive cage and the cables.
LARGE_GPU_MM = 320
HEAVY_PSU_W = 1000
MANY_FANS = 6
TALL_AIR_COOLER_MM = 155


def level_for(score: int, thresholds: dict[ComplexityLevel, int] | None = None) -> ComplexityLevel:
    table = thresholds or DEFAULT_THRESHOLDS
    level = ComplexityLevel.EASY
    for candidate, floor in sorted(table.items(), key=lambda item: item[1]):
        if score >= floor:
            level = candidate
    return level


def assess(
    parts: Parts, thresholds: dict[ComplexityLevel, int] | None = None
) -> ComplexityAssessment:
    """Inspect a parts list and report what will make the build slow."""
    factors: list[ComplexityFactor] = []

    case_spec = _spec(parts, ComponentCategory.CASE, CaseSpec)
    cooler_spec = _spec(parts, ComponentCategory.COOLER, CoolerSpec)
    gpu_spec = _spec(parts, ComponentCategory.GPU, GpuSpec)
    psu_spec = _spec(parts, ComponentCategory.PSU, PsuSpec)
    ram_spec = _spec(parts, ComponentCategory.RAM, RamSpec)

    if case_spec is not None:
        largest = _largest_form_factor(case_spec)
        if largest is FormFactor.MINI_ITX:
            factors.append(
                ComplexityFactor("sff", "Mini-ITX корпус: работа в тесном объёме", 25, 45)
            )
        elif largest is FormFactor.MICRO_ATX:
            factors.append(
                ComplexityFactor("compact", "Компактный корпус: меньше места под кабели", 12, 25)
            )

        radiator_fans = 3 if cooler_spec and cooler_spec.radiator_mm >= 360 else 0
        fans = case_spec.included_fans + radiator_fans
        if fans >= MANY_FANS:
            factors.append(
                ComplexityFactor("many_fans", f"{fans} вентиляторов: разводка и хабы", 10, 20)
            )

        if case_spec.rgb or (ram_spec is not None and ram_spec.rgb):
            factors.append(
                ComplexityFactor("argb", "ARGB: контроллер и синхронизация подсветки", 8, 15)
            )

    if cooler_spec is not None:
        if cooler_spec.cooler_type is CoolerType.AIO:
            factors.append(
                ComplexityFactor("aio", "СЖО: установка радиатора и прокладка шлангов", 15, 30)
            )
        elif cooler_spec.height_mm >= TALL_AIR_COOLER_MM:
            factors.append(
                ComplexityFactor("tall_cooler", "Крупный башенный кулер: тесная установка", 6, 10)
            )

    if gpu_spec is not None and gpu_spec.length_mm >= LARGE_GPU_MM:
        factors.append(
            ComplexityFactor("large_gpu", "Длинная видеокарта: установка и поддержка", 8, 10)
        )

    if psu_spec is not None:
        # Counter-intuitive but true on the bench: a non-modular supply means
        # every unused cable has to be hidden somewhere, which is the slow part
        # of cable management. A modular unit is faster, not harder.
        if psu_spec.modular == "non-modular":
            factors.append(
                ComplexityFactor("non_modular_psu", "Немодульный БП: прятать лишние кабели", 10, 20)
            )
        if psu_spec.wattage >= HEAVY_PSU_W:
            factors.append(ComplexityFactor("heavy_psu", "Мощный БП: толстые жгуты", 5, 5))

    drives = sum(1 for category in parts if category is ComponentCategory.SSD)
    if drives > 1:
        factors.append(
            ComplexityFactor(
                "multi_drive",
                f"{drives} накопителя: монтаж и разметка",
                5,
                10 * (drives - 1),
            )
        )

    assessment = ComplexityAssessment(factors=factors)
    assessment.level = level_for(assessment.score, thresholds)
    return assessment


def _largest_form_factor(case_spec: CaseSpec) -> FormFactor:
    order = [FormFactor.MINI_ITX, FormFactor.MICRO_ATX, FormFactor.ATX, FormFactor.E_ATX]
    return max(case_spec.form_factors, key=order.index)


def _spec(parts: Parts, category: ComponentCategory, expected: type):  # type: ignore[no-untyped-def]
    component = parts.get(category)
    if component is None:
        return None
    spec = component.spec
    return spec if isinstance(spec, expected) else None
