"""Build generator.

Strategy: enumerate CPU x GPU pairs (a few hundred at most), fit the cheapest
supporting parts that satisfy the customer's requirements around each pair,
reject anything the compatibility engine rejects, then score the survivors
according to the requested tier.

Exhaustive search over the pair space is affordable at catalogue sizes in the
thousands and removes a whole class of greedy-selection bugs: a build is either
compatible and inside budget, or it is not produced at all.

The customer's budget is what they pay. Acquisition budget is derived from it
by removing the target margin and the assembly fee, so a build never quietly
costs the shop more than it earns.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.components import (
    CaseSpec,
    Colour,
    Component,
    ComponentCategory,
    CoolerSpec,
    CoolerType,
    CpuSpec,
    FormFactor,
    GpuSpec,
    MotherboardSpec,
    PsuSpec,
    RamSpec,
    Socket,
    SsdSpec,
)
from app.domain.enums import BuildTier, CpuBrand, GpuBrand, Priority, Purpose, Resolution
from app.domain.requirements import BuildRequirements
from app.services.catalog import Catalog
from app.services.compatibility import CompatibilityReport, recommended_psu_w, validate
from app.services.compatibility.rules.common import radiator_fits
from app.services.compatibility.rules.electrical import gpu_power_path

logger = logging.getLogger(__name__)

Parts = dict[ComponentCategory, Component]
PriceBook = Mapping[str, Decimal]

#: The slice of the acquisition budget each tier occupies, as (floor, cap).
#:
#: Tiers are price points, not just three rankings of one pool. Without a floor
#: the value-seeking tiers hand a customer with a 12 000 PLN budget a 5 500 PLN
#: machine; without a cap "budget" and "performance" collapse onto the same
#: build whenever one candidate tops both rankings.
_TIER_BAND: dict[BuildTier, tuple[Decimal, Decimal]] = {
    BuildTier.BUDGET: (Decimal("0.58"), Decimal("0.78")),
    BuildTier.OPTIMAL: (Decimal("0.78"), Decimal("0.93")),
    BuildTier.PERFORMANCE: (Decimal("0.88"), Decimal("1.00")),
}

#: Sockets with no realistic upgrade path left. Still good value, so they are
#: penalised rather than excluded - and the build carries a note saying why.
LEGACY_SOCKETS = frozenset({Socket.AM4})

#: Multiplier applied to a legacy-platform build in the tiers where a customer
#: is paying for longevity as well as frames.
LEGACY_PLATFORM_PENALTY = 0.92

#: How much the GPU matters relative to the CPU, by resolution.
_GPU_WEIGHT: dict[Resolution, float] = {
    Resolution.FHD: 0.60,
    Resolution.QHD: 0.72,
    Resolution.UHD: 0.82,
}

DEFAULT_RAM_GB = {
    Purpose.GAMING: 32,
    Purpose.GAMING_STREAMING: 32,
    Purpose.WORK: 16,
    Purpose.DESIGN: 32,
    Purpose.AI_ML: 64,
    Purpose.WORKSTATION: 64,
    Purpose.UNIVERSAL: 32,
}

DEFAULT_STORAGE_GB = 1000

#: How many PLN of extra cost one preference point is worth. Looks are a
#: budget concession, never an override: letting "white case" outrank price
#: starves the GPU, which is the part the customer actually feels.
PREFERENCE_VALUE_PLN = Decimal(70)

#: How much a full style match lifts an OPTIMAL candidate's score.
STYLE_BONUS = 0.18

#: Preference points a PREFERRED part earns: it is kept whenever it fits and
#: the budget allows, and dropped silently in the looks-free trim.
PREFERRED_POINTS = 10


@dataclass(slots=True)
class GeneratedBuild:
    tier: BuildTier
    parts: Parts
    acquisition_cost_pln: Decimal
    report: CompatibilityReport
    performance_score: float
    notes: list[str] = field(default_factory=list)

    @property
    def cpu(self) -> Component | None:
        return self.parts.get(ComponentCategory.CPU)

    @property
    def gpu(self) -> Component | None:
        return self.parts.get(ComponentCategory.GPU)


class BuildGenerationError(RuntimeError):
    """No compatible build could be produced for these requirements."""


# --- public API ---------------------------------------------------------------


def generate_build(
    requirements: BuildRequirements,
    tier: BuildTier,
    catalog: Catalog,
    prices: PriceBook,
    *,
    acquisition_budget_pln: Decimal,
) -> GeneratedBuild | None:
    """Best build of ``tier`` that fits ``acquisition_budget_pln``, or ``None``."""
    candidates = _enumerate(requirements, catalog, prices, acquisition_budget_pln)
    if not candidates:
        return None

    best = _pick_for_tier(candidates, tier, acquisition_budget_pln, requirements)
    if best is None:
        return None

    return GeneratedBuild(
        tier=tier,
        parts=best.parts,
        acquisition_cost_pln=best.cost,
        report=best.report,
        performance_score=best.performance,
    )


def generate_variants(
    requirements: BuildRequirements,
    catalog: Catalog,
    prices: PriceBook,
    *,
    acquisition_budget_pln: Decimal,
    tiers: tuple[BuildTier, ...] = (BuildTier.BUDGET, BuildTier.OPTIMAL, BuildTier.PERFORMANCE),
) -> dict[BuildTier, GeneratedBuild]:
    """One build per tier. Tiers with no viable build are simply absent."""
    candidates = _enumerate(requirements, catalog, prices, acquisition_budget_pln)
    if not candidates:
        return {}

    results: dict[BuildTier, GeneratedBuild] = {}
    floor_cost = Decimal(0)
    floor_performance = 0.0

    for tier in tiers:
        # Tiers must not go backwards: a customer comparing three options
        # expects each step up to cost more and do more.
        best = _pick_for_tier(
            candidates,
            tier,
            acquisition_budget_pln,
            requirements,
            min_cost=floor_cost,
            min_performance=floor_performance,
        )
        if best is None:
            continue

        # On a tight budget the tiers converge. Showing the same machine three
        # times under three names is worse than showing it once.
        if any(_same_parts(best.parts, existing.parts) for existing in results.values()):
            continue

        results[tier] = GeneratedBuild(
            tier=tier,
            parts=best.parts,
            acquisition_cost_pln=best.cost,
            report=best.report,
            performance_score=best.performance,
            notes=_notes_for(best),
        )
        floor_cost = best.cost
        floor_performance = best.performance

    return results


def _same_parts(left: Parts, right: Parts) -> bool:
    return {c: p.id for c, p in left.items()} == {c: p.id for c, p in right.items()}


def _notes_for(candidate: _Candidate) -> list[str]:
    notes: list[str] = []
    if is_legacy_platform(candidate.parts):
        notes.append("legacy_platform")
    return notes


def minimum_acquisition_cost(
    requirements: BuildRequirements, catalog: Catalog, prices: PriceBook
) -> Decimal | None:
    """Cheapest compatible build for these requirements, ignoring the budget.

    Used to tell a customer what a configuration like theirs actually starts
    at, instead of failing with no explanation.
    """
    candidates = _enumerate(requirements, catalog, prices, Decimal(10**9))
    if not candidates:
        return None
    return min(candidate.cost for candidate in candidates)


def _pick_for_tier(
    candidates: list[_Candidate],
    tier: BuildTier,
    budget: Decimal,
    requirements: BuildRequirements,
    *,
    min_cost: Decimal = Decimal(0),
    min_performance: float = 0.0,
) -> _Candidate | None:
    """Best candidate for a tier, inside that tier's slice of the budget."""
    floor_ratio, cap_ratio = _TIER_BAND[tier]
    floor = max(budget * floor_ratio, min_cost)
    cap = budget * cap_ratio

    def eligible(pool: list[_Candidate]) -> list[_Candidate]:
        return [c for c in pool if c.performance >= min_performance]

    # Relax in steps, but keep the monotonicity filter for as long as
    # possible: a tier that costs more must never perform worse.
    pool = (
        eligible([c for c in candidates if floor <= c.cost <= cap])
        or eligible([c for c in candidates if min_cost <= c.cost <= cap])
        or eligible([c for c in candidates if c.cost >= min_cost])
        or eligible(candidates)
        or candidates
    )
    if not pool:
        return None
    return max(pool, key=_scorer_for(tier, requirements))


# --- enumeration --------------------------------------------------------------


@dataclass(slots=True)
class _Candidate:
    parts: Parts
    cost: Decimal
    performance: float
    report: CompatibilityReport


def _enumerate(
    requirements: BuildRequirements,
    catalog: Catalog,
    prices: PriceBook,
    budget: Decimal,
) -> list[_Candidate]:
    cpus = _filter_cpus(catalog, requirements, prices)
    gpus = _filter_gpus(catalog, requirements, prices)

    if not cpus:
        logger.info("No CPU matches preference %s", requirements.cpu_brand)
        return []

    # A PREFERRED processor or card is tried on its own first; only when
    # nothing viable comes out of it does the search widen to everything.
    preferred_cpu = requirements.preferred_id(ComponentCategory.CPU)
    preferred_gpu = requirements.preferred_id(ComponentCategory.GPU)
    pools: list[tuple[list[Component], list[Component]]] = []
    if preferred_cpu is not None or preferred_gpu is not None:
        pools.append(
            (
                [c for c in cpus if c.id == preferred_cpu] if preferred_cpu else cpus,
                [g for g in gpus if g.id == preferred_gpu] if preferred_gpu else gpus,
            )
        )
    pools.append((cpus, gpus))

    for cpu_pool, gpu_pool in pools:
        candidates = _enumerate_pairs(cpu_pool, gpu_pool, requirements, catalog, prices, budget)
        if candidates:
            return candidates
    return []


def _enumerate_pairs(
    cpus: list[Component],
    gpus: list[Component],
    requirements: BuildRequirements,
    catalog: Catalog,
    prices: PriceBook,
    budget: Decimal,
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    # An integrated-graphics-only build is viable for office work - unless
    # the customer fixed a graphics card.
    gpu_options: list[Component | None] = list(gpus)
    if (
        not requirements.needs_gaming_performance
        and requirements.locked_id(ComponentCategory.GPU) is None
    ):
        gpu_options.append(None)

    for cpu in cpus:
        cpu_price = prices.get(cpu.id)
        if cpu_price is None:
            continue
        for gpu in gpu_options:
            gpu_price = prices.get(gpu.id) if gpu is not None else Decimal(0)
            if gpu is not None and gpu_price is None:
                continue
            if cpu_price + (gpu_price or Decimal(0)) > budget:
                continue

            # Two trims per pair: one ignoring looks entirely, one paying for
            # them. Without the first, an aesthetic preference can quietly cost
            # the customer a GPU tier.
            for preference_value in (Decimal(0), PREFERENCE_VALUE_PLN):
                built = _assemble(cpu, gpu, requirements, catalog, prices, budget, preference_value)
                if built is not None:
                    candidates.append(built)

    logger.debug("Generated %s viable candidates", len(candidates))
    return candidates


def _assemble(
    cpu: Component,
    gpu: Component | None,
    requirements: BuildRequirements,
    catalog: Catalog,
    prices: PriceBook,
    budget: Decimal,
    preference_value: Decimal = PREFERENCE_VALUE_PLN,
) -> _Candidate | None:
    cpu_spec = _as(cpu, CpuSpec)
    if cpu_spec is None:
        return None

    parts: Parts = {ComponentCategory.CPU: cpu}
    if gpu is not None:
        parts[ComponentCategory.GPU] = gpu

    board = _pick_motherboard(cpu_spec, requirements, catalog, prices)
    if board is None:
        return None
    parts[ComponentCategory.MOTHERBOARD] = board

    ram = _pick_ram(board, requirements, catalog, prices, preference_value)
    if ram is None:
        return None
    parts[ComponentCategory.RAM] = ram

    ssd = _pick_ssd(requirements, catalog, prices)
    if ssd is None:
        return None
    parts[ComponentCategory.SSD] = ssd

    cooler = _pick_cooler(cpu_spec, requirements, catalog, prices, preference_value)
    if cooler is not None:
        parts[ComponentCategory.COOLER] = cooler
    elif not cpu_spec.includes_cooler:
        return None

    case = _pick_case(parts, requirements, catalog, prices, preference_value)
    if case is None:
        return None
    parts[ComponentCategory.CASE] = case

    psu = _pick_psu(parts, requirements, catalog, prices, preference_value)
    if psu is None:
        return None
    parts[ComponentCategory.PSU] = psu

    cost = sum((prices.get(part.id, Decimal(0)) for part in parts.values()), Decimal(0))
    if cost > budget:
        return None

    report = validate(parts)
    if not report.ok:
        return None

    return _Candidate(
        parts=parts,
        cost=cost,
        performance=_performance(parts, requirements),
        report=report,
    )


# --- part selection -----------------------------------------------------------


def _cheapest(
    components: list[Component],
    prices: PriceBook,
    *,
    prefer: Callable[[Component], int] | None = None,
    preference_value: Decimal = PREFERENCE_VALUE_PLN,
    locked: str | None = None,
    preferred: str | None = None,
) -> Component | None:
    """Cheapest candidate once preference points are discounted from price.

    ``locked`` narrows the choice to one part (it still has to pass every
    filter the caller applied, or the build is simply not produced).
    ``preferred`` earns ``PREFERRED_POINTS`` in the trim that pays for
    preferences and nothing in the looks-free trim.
    """
    if locked is not None:
        components = [c for c in components if c.id == locked]
    priced = [(c, prices[c.id]) for c in components if c.id in prices]
    if not priced:
        return None
    if preference_value <= 0:
        return min(priced, key=lambda item: item[1])[0]

    def key(item: tuple[Component, Decimal]) -> Decimal:
        component, price = item
        points = prefer(component) if prefer is not None else 0
        if preferred is not None and component.id == preferred:
            points += PREFERRED_POINTS
        return price - points * preference_value

    return min(priced, key=key)[0]


def _locked_case(requirements: BuildRequirements, catalog: Catalog) -> CaseSpec | None:
    """Spec of the case the customer fixed, so parts picked *before* the case
    (board, cooler, GPU) are already chosen to fit it."""
    locked = requirements.locked_id(ComponentCategory.CASE)
    if locked is None:
        return None
    return _as(catalog.get(locked), CaseSpec)


def _filter_cpus(
    catalog: Catalog, requirements: BuildRequirements, prices: PriceBook
) -> list[Component]:
    cpus = catalog.by_category(ComponentCategory.CPU)
    locked = requirements.locked_id(ComponentCategory.CPU)
    brand = requirements.cpu_brand
    if locked is not None:
        cpus = [cpu for cpu in cpus if cpu.id == locked]
    elif brand is not CpuBrand.ANY:
        wanted = "AMD" if brand is CpuBrand.AMD else "Intel"
        cpus = [cpu for cpu in cpus if cpu.brand == wanted]
    return [cpu for cpu in cpus if cpu.id in prices]


def _filter_gpus(
    catalog: Catalog, requirements: BuildRequirements, prices: PriceBook
) -> list[Component]:
    gpus = catalog.by_category(ComponentCategory.GPU)
    case = _locked_case(requirements, catalog)
    if case is not None:
        gpus = [
            gpu
            for gpu in gpus
            if (spec := _as(gpu, GpuSpec)) is not None and spec.length_mm <= case.max_gpu_length_mm
        ]
    locked = requirements.locked_id(ComponentCategory.GPU)
    brand = requirements.gpu_brand
    if locked is not None:
        gpus = [gpu for gpu in gpus if gpu.id == locked]
    elif brand is not GpuBrand.ANY:
        wanted = {GpuBrand.NVIDIA: "NVIDIA", GpuBrand.AMD: "AMD", GpuBrand.INTEL: "Intel"}[brand]
        gpus = [gpu for gpu in gpus if gpu.brand == wanted]
    return [gpu for gpu in gpus if gpu.id in prices]


def _pick_motherboard(
    cpu: CpuSpec, requirements: BuildRequirements, catalog: Catalog, prices: PriceBook
) -> Component | None:
    case = _locked_case(requirements, catalog)
    boards = []
    for board in catalog.by_category(ComponentCategory.MOTHERBOARD):
        spec = _as(board, MotherboardSpec)
        if spec is None or spec.socket is not cpu.socket:
            continue
        if case is not None and spec.form_factor not in case.form_factors:
            continue
        if spec.memory_type not in cpu.memory_types:
            continue
        if requirements.wifi and not spec.wifi:
            continue
        if requirements.bluetooth and not spec.bluetooth:
            continue
        boards.append(board)

    # DDR5 is the sensible default when the platform offers both.
    def prefer(board: Component) -> int:
        spec = _as(board, MotherboardSpec)
        return 1 if spec is not None and spec.memory_type.value == "DDR5" else 0

    return _cheapest(
        boards,
        prices,
        prefer=prefer,
        locked=requirements.locked_id(ComponentCategory.MOTHERBOARD),
        preferred=requirements.preferred_id(ComponentCategory.MOTHERBOARD),
    )


def _pick_ram(
    board: Component,
    requirements: BuildRequirements,
    catalog: Catalog,
    prices: PriceBook,
    preference_value: Decimal = PREFERENCE_VALUE_PLN,
) -> Component | None:
    board_spec = _as(board, MotherboardSpec)
    if board_spec is None:
        return None

    wanted_gb = requirements.ram_gb or DEFAULT_RAM_GB.get(requirements.purpose, 32)
    modules = []
    for ram in catalog.by_category(ComponentCategory.RAM):
        spec = _as(ram, RamSpec)
        if spec is None or spec.memory_type is not board_spec.memory_type:
            continue
        if spec.total_capacity_gb < wanted_gb:
            continue
        if spec.modules > board_spec.memory_slots:
            continue
        if spec.total_capacity_gb > board_spec.max_memory_gb:
            continue
        modules.append(ram)

    def prefer(ram: Component) -> int:
        spec = _as(ram, RamSpec)
        if spec is None:
            return 0
        return 1 if spec.rgb == requirements.aesthetics.wants_rgb else 0

    return _cheapest(
        modules,
        prices,
        prefer=prefer,
        preference_value=preference_value,
        locked=requirements.locked_id(ComponentCategory.RAM),
        preferred=requirements.preferred_id(ComponentCategory.RAM),
    )


def _pick_ssd(
    requirements: BuildRequirements, catalog: Catalog, prices: PriceBook
) -> Component | None:
    wanted_gb = requirements.storage_gb or DEFAULT_STORAGE_GB
    drives = [
        ssd
        for ssd in catalog.by_category(ComponentCategory.SSD)
        if (spec := _as(ssd, SsdSpec)) is not None and spec.capacity_gb >= wanted_gb
    ]
    return _cheapest(
        drives,
        prices,
        locked=requirements.locked_id(ComponentCategory.SSD),
        preferred=requirements.preferred_id(ComponentCategory.SSD),
    )


def _pick_cooler(
    cpu: CpuSpec,
    requirements: BuildRequirements,
    catalog: Catalog,
    prices: PriceBook,
    preference_value: Decimal = PREFERENCE_VALUE_PLN,
) -> Component | None:
    case = _locked_case(requirements, catalog)
    coolers = []
    for cooler in catalog.by_category(ComponentCategory.COOLER):
        spec = _as(cooler, CoolerSpec)
        if spec is None or cpu.socket not in spec.sockets:
            continue
        if spec.tdp_rating_w < cpu.max_power_w:
            continue
        if case is not None:
            if spec.cooler_type is CoolerType.AIR and spec.height_mm > case.max_cooler_height_mm:
                continue
            if (
                spec.cooler_type is CoolerType.AIO
                and not radiator_fits(spec.radiator_mm, case.radiator_support_mm)[0]
            ):
                continue
        coolers.append(cooler)

    wants_white = requirements.aesthetics.is_white
    quiet = requirements.wants(Priority.SILENCE)
    cold = requirements.wants(Priority.COOLING)
    lit = requirements.wants(Priority.LOOKS) or requirements.aesthetics.wants_rgb
    compact = requirements.wants(Priority.COMPACT)

    def prefer(cooler: Component) -> int:
        spec = _as(cooler, CoolerSpec)
        if spec is None:
            return 0
        score = 0
        if wants_white and spec.colour is Colour.WHITE:
            score += 4
        # Headroom over the CPU's draw is what actually makes a build quiet.
        if quiet and spec.tdp_rating_w >= cpu.max_power_w + 60:
            score += 2
        if cold and spec.cooler_type is CoolerType.AIO:
            score += 2
        if lit and spec.rgb:
            score += 2
        if compact and spec.cooler_type is CoolerType.AIR and spec.height_mm <= 160:
            score += 2
        return score

    return _cheapest(
        coolers,
        prices,
        prefer=prefer,
        preference_value=preference_value,
        locked=requirements.locked_id(ComponentCategory.COOLER),
        preferred=requirements.preferred_id(ComponentCategory.COOLER),
    )


def _pick_case(
    parts: Parts,
    requirements: BuildRequirements,
    catalog: Catalog,
    prices: PriceBook,
    preference_value: Decimal = PREFERENCE_VALUE_PLN,
) -> Component | None:
    board_spec = _as(parts[ComponentCategory.MOTHERBOARD], MotherboardSpec)
    gpu_spec = _as(parts.get(ComponentCategory.GPU), GpuSpec)
    cooler_spec = _as(parts.get(ComponentCategory.COOLER), CoolerSpec)
    if board_spec is None:
        return None

    cases = []
    for case in catalog.by_category(ComponentCategory.CASE):
        spec = _as(case, CaseSpec)
        if spec is None or board_spec.form_factor not in spec.form_factors:
            continue
        if gpu_spec is not None and gpu_spec.length_mm > spec.max_gpu_length_mm:
            continue
        if cooler_spec is not None:
            if cooler_spec.cooler_type is CoolerType.AIR:
                if cooler_spec.height_mm > spec.max_cooler_height_mm:
                    continue
            elif not radiator_fits(cooler_spec.radiator_mm, spec.radiator_support_mm)[0]:
                continue
        cases.append(case)

    wants_white = requirements.aesthetics.is_white
    wants_rgb = requirements.aesthetics.wants_rgb or requirements.wants(Priority.LOOKS)
    compact = requirements.wants(Priority.COMPACT)
    roomy = requirements.wants(Priority.UPGRADEABILITY)
    quiet = requirements.wants(Priority.SILENCE)
    cold = requirements.wants(Priority.COOLING)

    def prefer(case: Component) -> int:
        spec = _as(case, CaseSpec)
        if spec is None:
            return 0
        score = 0
        if wants_white and spec.colour is Colour.WHITE:
            score += 4
        if not wants_white and spec.colour is Colour.BLACK:
            score += 1
        if wants_rgb and spec.rgb:
            score += 2
        if not wants_rgb and not spec.rgb:
            score += 1
        if compact and FormFactor.MICRO_ATX in spec.form_factors:
            # A case that also takes a smaller board is the smaller case.
            score += 2
        if compact and spec.max_gpu_length_mm <= 340:
            score += 1
        # Room to grow: long GPUs, tall coolers and drive bays.
        if roomy and spec.max_gpu_length_mm >= 360:
            score += 2
        if roomy and (spec.drive_bays_35 or 0) >= 2:
            score += 1
        # Airflow and silence both come from the fans that ship with the case.
        if (quiet or cold) and spec.included_fans >= 3:
            score += 2
        return score

    return _cheapest(
        cases,
        prices,
        prefer=prefer,
        preference_value=preference_value,
        locked=requirements.locked_id(ComponentCategory.CASE),
        preferred=requirements.preferred_id(ComponentCategory.CASE),
    )


#: 80 PLUS tiers, cheapest first. Only used to rank, never to invent a spec.
_PSU_EFFICIENCY_RANK: dict[str, int] = {
    "80+ white": 0,
    "80+ bronze": 1,
    "80+ silver": 2,
    "80+ gold": 3,
    "80+ platinum": 4,
    "80+ titanium": 5,
}


def _pick_psu(
    parts: Parts,
    requirements: BuildRequirements,
    catalog: Catalog,
    prices: PriceBook,
    preference_value: Decimal = PREFERENCE_VALUE_PLN,
) -> Component | None:
    needed = recommended_psu_w(parts)
    gpu_spec = _as(parts.get(ComponentCategory.GPU), GpuSpec)
    case_spec = _as(parts.get(ComponentCategory.CASE), CaseSpec)

    supplies = []
    for psu in catalog.by_category(ComponentCategory.PSU):
        spec = _as(psu, PsuSpec)
        if spec is None or spec.wattage < needed:
            continue
        if case_spec is not None and spec.length_mm > case_spec.max_psu_length_mm:
            continue
        if gpu_spec is not None:
            if spec.wattage < gpu_spec.recommended_psu_w:
                continue
            if gpu_power_path(gpu_spec, spec) is None:
                continue
        supplies.append(psu)

    wants_white = requirements.aesthetics.is_white
    efficient = requirements.wants(Priority.EFFICIENCY)
    roomy = requirements.wants(Priority.UPGRADEABILITY)
    quiet = requirements.wants(Priority.SILENCE)

    def prefer(psu: Component) -> int:
        spec = _as(psu, PsuSpec)
        score = 1 if wants_white and "White" in psu.model else 0
        if spec is None:
            return score
        if efficient and _PSU_EFFICIENCY_RANK.get(spec.efficiency.lower(), 0) >= 2:
            score += 3
        if roomy and spec.wattage >= needed + 150:
            score += 2
        # A supply loafing at a third of its rating spins its fan slower.
        if quiet and spec.wattage >= needed + 100:
            score += 1
        if (efficient or quiet) and spec.modular.lower().startswith("full"):
            score += 1
        return score

    return _cheapest(
        supplies,
        prices,
        prefer=prefer,
        preference_value=preference_value,
        locked=requirements.locked_id(ComponentCategory.PSU),
        preferred=requirements.preferred_id(ComponentCategory.PSU),
    )


# --- scoring ------------------------------------------------------------------


def _performance(parts: Parts, requirements: BuildRequirements) -> float:
    """Coarse relative capability of a build. Not a benchmark, not an FPS number."""
    cpu_spec = _as(parts.get(ComponentCategory.CPU), CpuSpec)
    gpu_spec = _as(parts.get(ComponentCategory.GPU), GpuSpec)

    if not requirements.needs_gaming_performance:
        cpu_score = float(cpu_spec.performance_index) if cpu_spec else 0.0
        gpu_score = float(gpu_spec.performance_index) if gpu_spec else 0.0
        if requirements.purpose in {Purpose.AI_ML, Purpose.DESIGN}:
            vram_bonus = float(gpu_spec.vram_gb) * 8 if gpu_spec else 0.0
            return cpu_score * 0.4 + gpu_score * 0.6 + vram_bonus
        return cpu_score * 0.75 + gpu_score * 0.25

    gpu_weight = _GPU_WEIGHT[requirements.resolution]
    if requirements.wants(Priority.MAX_FPS) and requirements.resolution is Resolution.FHD:
        # High-refresh 1080p is CPU-bound; lean back towards the processor.
        gpu_weight -= 0.15

    cpu_score = float(cpu_spec.gaming_index) if cpu_spec else 0.0
    gpu_score = float(gpu_spec.performance_index) if gpu_spec else 0.0
    return gpu_score * gpu_weight + cpu_score * (1 - gpu_weight)


def _scorer_for(tier: BuildTier, requirements: BuildRequirements) -> Callable[[_Candidate], float]:
    """Ranking function per tier, applied inside that tier's budget cap.

    BUDGET maximises performance per złoty. PERFORMANCE maximises raw
    capability. OPTIMAL blends the two, which is what customers mean by "best
    price/performance": strong, but not paying double for the last 10%.
    """

    def value_score(candidate: _Candidate) -> float:
        if candidate.cost <= 0:
            return 0.0
        return candidate.performance / float(candidate.cost) * 1000

    def performance_score(candidate: _Candidate) -> float:
        return candidate.performance

    def optimal_score(candidate: _Candidate) -> float:
        # OPTIMAL is the tier that honours an explicit look. BUDGET chases
        # value and PERFORMANCE chases frames, so without this a customer who
        # asked for a white RGB machine could be shown three black ones.
        style = 1.0 + STYLE_BONUS * style_match(candidate.parts, requirements)
        return (
            value_score(candidate)
            * (candidate.performance**0.35)
            * _platform_factor(candidate)
            * style
        )

    def performance_with_platform(candidate: _Candidate) -> float:
        return performance_score(candidate) * _platform_factor(candidate)

    match tier:
        case BuildTier.BUDGET:
            # The cheapest tier is where a mature platform is a fair trade.
            base = value_score
        case BuildTier.PERFORMANCE:
            base = performance_with_platform
        case _:
            base = optimal_score

    if not requirements.preferred:
        return base

    def with_preferences(candidate: _Candidate) -> float:
        return base(candidate) * _preference_factor(candidate.parts, requirements)

    return with_preferences


#: Score multiplier when every PREFERRED part made it into the build.
PREFERRED_SCORE_BONUS = 0.30


def _preference_factor(parts: Parts, requirements: BuildRequirements) -> float:
    """1.0 .. 1 + PREFERRED_SCORE_BONUS by the share of preferred parts kept."""
    wanted = requirements.preferred
    if not wanted:
        return 1.0
    kept = sum(
        1
        for category, component_id in wanted.items()
        if (part := parts.get(ComponentCategory(category))) is not None and part.id == component_id
    )
    return 1.0 + PREFERRED_SCORE_BONUS * kept / len(wanted)


def style_match(parts: Parts, requirements: BuildRequirements) -> float:
    """How well a build matches the requested look, from 0.0 to 1.0.

    Only the parts a customer actually sees are counted: the case dominates,
    the cooler and memory are visible through a side panel.
    """
    wants_white = requirements.aesthetics.is_white
    wants_rgb = requirements.aesthetics.wants_rgb
    if not wants_white and not wants_rgb:
        return 1.0

    scored = 0.0
    total = 0.0

    case_spec = _as(parts.get(ComponentCategory.CASE), CaseSpec)
    if case_spec is not None:
        total += 2.0
        if wants_white:
            scored += 2.0 if case_spec.colour is Colour.WHITE else 0.0
        if wants_rgb:
            total += 1.0
            scored += 1.0 if case_spec.rgb else 0.0

    cooler_spec = _as(parts.get(ComponentCategory.COOLER), CoolerSpec)
    if cooler_spec is not None and wants_white:
        total += 1.0
        scored += 1.0 if cooler_spec.colour is Colour.WHITE else 0.0

    ram_spec = _as(parts.get(ComponentCategory.RAM), RamSpec)
    if ram_spec is not None and wants_rgb:
        total += 1.0
        scored += 1.0 if ram_spec.rgb else 0.0

    return scored / total if total else 1.0


def _platform_factor(candidate: _Candidate) -> float:
    cpu_spec = _as(candidate.parts.get(ComponentCategory.CPU), CpuSpec)
    if cpu_spec is not None and cpu_spec.socket in LEGACY_SOCKETS:
        return LEGACY_PLATFORM_PENALTY
    return 1.0


def is_legacy_platform(parts: Parts) -> bool:
    """True when the build sits on a socket with no upgrade path left."""
    cpu_spec = _as(parts.get(ComponentCategory.CPU), CpuSpec)
    return cpu_spec is not None and cpu_spec.socket in LEGACY_SOCKETS


def _as(component: Component | None, expected: type):  # type: ignore[no-untyped-def]
    if component is None:
        return None
    spec = component.spec
    return spec if isinstance(spec, expected) else None
