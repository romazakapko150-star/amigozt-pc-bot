"""Generation of the ready-build catalogue.

Every entry is produced by the same engine that serves the configurator, so a
catalogue build is compatibility-checked and priced by construction - there is
no second, hand-maintained source of truth that can drift.

Each recipe exists for a reason (a resolution, a frame-rate target, a look, a
workload). Filling the shelf with arbitrary component permutations would give
a customer more rows and less help.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.enums import (
    Aesthetics,
    BuildTier,
    CpuBrand,
    GpuBrand,
    Priority,
    Purpose,
    Resolution,
    TargetFps,
)
from app.domain.requirements import BuildRequirements
from app.services.recommendation import BuildOption, BuildService

logger = logging.getLogger(__name__)


class Category:
    """Shelves a build can sit on."""

    BUDGET = "budget"
    GAMING = "gaming"
    HIGH_FPS = "high_fps"
    PERFORMANCE = "performance"
    HIGH_END = "high_end"
    EXTREME = "extreme"
    STREAMING = "streaming"
    DESIGN = "design"
    AI = "ai"
    WORKSTATION = "workstation"
    WHITE = "white"
    RGB = "rgb"
    QUIET = "quiet"


@dataclass(frozen=True, slots=True)
class Recipe:
    """One catalogue idea, instantiated at several budgets."""

    key: str
    name: str
    description: str
    category: str
    purpose: Purpose
    resolution: Resolution
    #: Budgets (PLN) this idea is worth building at.
    budgets: tuple[int, ...]
    target_fps: TargetFps | None = None
    priority: Priority = Priority.PRICE_PERFORMANCE
    aesthetics: Aesthetics = Aesthetics.BLACK
    tier: BuildTier = BuildTier.OPTIMAL
    cpu_brand: CpuBrand = CpuBrand.ANY
    gpu_brand: GpuBrand = GpuBrand.ANY
    ram_gb: int | None = None
    storage_gb: int | None = None
    wifi: bool = True
    bluetooth: bool = True
    tags: tuple[str, ...] = ()


RECIPES: tuple[Recipe, ...] = (
    Recipe(
        key="starter",
        name="AmigoZT Starter",
        description="Тихий компьютер для учёбы, работы и нетребовательных игр.",
        category=Category.BUDGET,
        purpose=Purpose.UNIVERSAL,
        resolution=Resolution.FHD,
        budgets=(3800, 4200, 4600, 5000),
        target_fps=TargetFps.FPS_60,
        ram_gb=16,
        storage_gb=500,
        tier=BuildTier.BUDGET,
        tags=("office", "1080p"),
    ),
    Recipe(
        key="budget-gamer",
        name="AmigoZT Budget Gamer",
        description="Первый игровой ПК: комфортный 1080p в популярных играх.",
        category=Category.BUDGET,
        purpose=Purpose.GAMING,
        resolution=Resolution.FHD,
        budgets=(4600, 5000, 5400, 6000),
        target_fps=TargetFps.FPS_100,
        ram_gb=16,
        tier=BuildTier.BUDGET,
        tags=("1080p", "fortnite", "cs2"),
    ),
    Recipe(
        key="1080p-king",
        name="AmigoZT 1080p King",
        description="Уверенные 144 FPS в 1080p с запасом на пару лет.",
        category=Category.GAMING,
        purpose=Purpose.GAMING,
        resolution=Resolution.FHD,
        budgets=(5500, 6000, 6500, 7200),
        target_fps=TargetFps.FPS_144,
        tags=("1080p",),
    ),
    Recipe(
        key="cs2-300",
        name="AmigoZT CS2 300",
        description="Сборка под соревновательный CS2: приоритет процессору и частоте кадров.",
        category=Category.HIGH_FPS,
        purpose=Purpose.GAMING,
        resolution=Resolution.FHD,
        budgets=(6000, 7000, 8000),
        target_fps=TargetFps.FPS_300_PLUS,
        priority=Priority.MAX_FPS,
        tier=BuildTier.PERFORMANCE,
        tags=("1080p", "cs2", "valorant", "esports"),
    ),
    Recipe(
        key="cs2-500",
        name="AmigoZT CS2 500",
        description="Максимум кадров в киберспортивных дисциплинах на 1080p.",
        category=Category.HIGH_FPS,
        purpose=Purpose.GAMING,
        resolution=Resolution.FHD,
        budgets=(9000, 11000, 12500),
        target_fps=TargetFps.FPS_500_PLUS,
        priority=Priority.MAX_FPS,
        tier=BuildTier.PERFORMANCE,
        tags=("1080p", "cs2", "esports"),
    ),
    Recipe(
        key="fps-beast",
        name="AmigoZT FPS Beast",
        description="Для мониторов 360 Гц и выше: всё вложено в кадры.",
        category=Category.HIGH_FPS,
        purpose=Purpose.GAMING,
        resolution=Resolution.FHD,
        budgets=(13000, 16000, 19000),
        target_fps=TargetFps.FPS_700_PLUS,
        priority=Priority.MAX_FPS,
        tier=BuildTier.PERFORMANCE,
        ram_gb=32,
        tags=("1080p", "esports"),
    ),
    Recipe(
        key="1440p-sweet-spot",
        name="AmigoZT 1440p Sweet Spot",
        description="Лучшее соотношение цены и кадров в 1440p.",
        category=Category.GAMING,
        purpose=Purpose.GAMING,
        resolution=Resolution.QHD,
        budgets=(6500, 7200, 8000, 8800),
        target_fps=TargetFps.FPS_144,
        tags=("1440p",),
    ),
    Recipe(
        key="1440p-high-fps",
        name="AmigoZT 1440p High FPS",
        description="240 Гц в 1440p: для тех, кто уже перерос 144.",
        category=Category.HIGH_FPS,
        purpose=Purpose.GAMING,
        resolution=Resolution.QHD,
        budgets=(10000, 12000, 14000),
        target_fps=TargetFps.FPS_240,
        priority=Priority.MAX_FPS,
        tier=BuildTier.PERFORMANCE,
        ram_gb=32,
        storage_gb=2000,
        tags=("1440p",),
    ),
    Recipe(
        key="white-dream",
        name="AmigoZT White Dream",
        description="Белая сборка целиком: корпус, охлаждение и подсветка в одном стиле.",
        category=Category.WHITE,
        purpose=Purpose.GAMING,
        resolution=Resolution.QHD,
        budgets=(7000, 8500, 10000, 12000),
        target_fps=TargetFps.FPS_144,
        aesthetics=Aesthetics.WHITE_RGB,
        priority=Priority.LOOKS,
        tags=("1440p", "white", "rgb"),
    ),
    Recipe(
        key="black-rgb",
        name="AmigoZT Black RGB",
        description="Чёрный корпус с подсветкой — классика игрового стола.",
        category=Category.RGB,
        purpose=Purpose.GAMING,
        resolution=Resolution.QHD,
        budgets=(7000, 9000, 11000),
        target_fps=TargetFps.FPS_144,
        aesthetics=Aesthetics.BLACK_RGB,
        priority=Priority.LOOKS,
        tags=("1440p", "rgb"),
    ),
    Recipe(
        key="silent-gaming",
        name="AmigoZT Silent Gaming",
        description="Игровой ПК, которого почти не слышно: упор на охлаждение с запасом.",
        category=Category.QUIET,
        purpose=Purpose.GAMING,
        resolution=Resolution.QHD,
        budgets=(8000, 10000, 12000),
        target_fps=TargetFps.FPS_144,
        priority=Priority.SILENCE,
        aesthetics=Aesthetics.MINIMAL,
        tags=("1440p", "quiet"),
    ),
    Recipe(
        key="streamer",
        name="AmigoZT Streamer",
        description="Игры и стрим одновременно: многопоточный процессор и много памяти.",
        category=Category.STREAMING,
        purpose=Purpose.GAMING_STREAMING,
        resolution=Resolution.QHD,
        budgets=(9000, 11000, 13000, 15000),
        target_fps=TargetFps.FPS_144,
        ram_gb=32,
        storage_gb=2000,
        tags=("1440p", "streaming"),
    ),
    Recipe(
        key="creator",
        name="AmigoZT Creator",
        description="Монтаж, графика и рендер: память, накопитель и видеокарта с VRAM.",
        category=Category.DESIGN,
        purpose=Purpose.DESIGN,
        resolution=Resolution.QHD,
        budgets=(9000, 12000, 15000, 18000),
        ram_gb=32,
        storage_gb=2000,
        tags=("design", "video"),
    ),
    Recipe(
        key="4k-beast",
        name="AmigoZT 4K Beast",
        description="Комфортная игра в 4K с высокими настройками.",
        category=Category.PERFORMANCE,
        purpose=Purpose.GAMING,
        resolution=Resolution.UHD,
        budgets=(11000, 13000, 15000),
        target_fps=TargetFps.FPS_60,
        tier=BuildTier.PERFORMANCE,
        ram_gb=32,
        storage_gb=2000,
        tags=("4k",),
    ),
    Recipe(
        key="4k-high",
        name="AmigoZT 4K High Refresh",
        description="4K на высокой частоте обновления, без компромиссов по видеокарте.",
        category=Category.HIGH_END,
        purpose=Purpose.GAMING,
        resolution=Resolution.UHD,
        budgets=(16000, 19000, 22000),
        target_fps=TargetFps.FPS_144,
        tier=BuildTier.PERFORMANCE,
        ram_gb=32,
        storage_gb=2000,
        tags=("4k",),
    ),
    Recipe(
        key="workstation",
        name="AmigoZT Workstation",
        description="Рабочая станция: ядра, память и быстрый накопитель.",
        category=Category.WORKSTATION,
        purpose=Purpose.WORKSTATION,
        resolution=Resolution.QHD,
        budgets=(11000, 14000, 17000),
        ram_gb=64,
        storage_gb=2000,
        tags=("workstation",),
    ),
    Recipe(
        key="ai-workstation",
        name="AmigoZT AI Workstation",
        description="Для локальных моделей: приоритет объёму видеопамяти и оперативной памяти.",
        category=Category.AI,
        purpose=Purpose.AI_ML,
        resolution=Resolution.QHD,
        budgets=(14000, 18000, 22000, 26000),
        ram_gb=64,
        storage_gb=2000,
        tags=("ai", "ml"),
    ),
    Recipe(
        key="ultimate",
        name="AmigoZT Ultimate",
        description="Максимум, который имеет смысл собрать: топовая связка без компромиссов.",
        category=Category.EXTREME,
        purpose=Purpose.GAMING,
        resolution=Resolution.UHD,
        budgets=(22000, 26000, 30000),
        target_fps=TargetFps.FPS_144,
        priority=Priority.MAX_FPS,
        tier=BuildTier.PERFORMANCE,
        ram_gb=32,
        storage_gb=2000,
        tags=("4k", "extreme"),
    ),
    Recipe(
        key="amd-only",
        name="AmigoZT All-AMD",
        description="Полностью AMD: Ryzen и Radeon в одной связке.",
        category=Category.GAMING,
        purpose=Purpose.GAMING,
        resolution=Resolution.QHD,
        budgets=(7500, 9500, 12000, 15000),
        target_fps=TargetFps.FPS_144,
        cpu_brand=CpuBrand.AMD,
        gpu_brand=GpuBrand.AMD,
        tags=("1440p", "amd"),
    ),
    Recipe(
        key="intel-nvidia",
        name="AmigoZT Intel + GeForce",
        description="Связка Intel Core и GeForce для игр и работы.",
        category=Category.GAMING,
        purpose=Purpose.GAMING,
        resolution=Resolution.QHD,
        budgets=(8000, 10000, 13000, 16000),
        target_fps=TargetFps.FPS_144,
        cpu_brand=CpuBrand.INTEL,
        gpu_brand=GpuBrand.NVIDIA,
        tags=("1440p", "intel", "nvidia"),
    ),
)


@dataclass(slots=True)
class ReadyBuildDraft:
    """A generated catalogue entry, ready to be persisted."""

    slug: str
    name: str
    description: str
    category: str
    tags: list[str]
    recipe: Recipe
    budget_pln: int
    option: BuildOption
    components: dict[str, str] = field(default_factory=dict)

    @property
    def performance_score(self) -> int:
        return round(self.option.performance_score)

    @property
    def price_pln(self) -> Decimal:
        return self.option.client_price_pln

    @property
    def cost_pln(self) -> Decimal:
        return self.option.quote.component_cost_pln


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:80]


def requirements_for(recipe: Recipe, budget_pln: int) -> BuildRequirements:
    return BuildRequirements(
        budget_pln=budget_pln,
        purpose=recipe.purpose,
        games=[],
        resolution=recipe.resolution,
        target_fps=recipe.target_fps,
        priority=recipe.priority,
        aesthetics=recipe.aesthetics,
        wifi=recipe.wifi,
        bluetooth=recipe.bluetooth,
        storage_gb=recipe.storage_gb,
        ram_gb=recipe.ram_gb,
        cpu_brand=recipe.cpu_brand,
        gpu_brand=recipe.gpu_brand,
    )


def generate_catalogue(
    service: BuildService | None = None, recipes: tuple[Recipe, ...] = RECIPES
) -> list[ReadyBuildDraft]:
    """Instantiate every recipe at every budget, dropping duplicates.

    Two budgets often land on the same parts once the catalogue runs out of
    rungs; keeping both would pad the shelf with identical machines under
    different prices.
    """
    builder = service or BuildService()
    drafts: list[ReadyBuildDraft] = []
    seen: set[tuple[str, ...]] = set()
    used_names: set[str] = set()

    for recipe in recipes:
        for budget in recipe.budgets:
            requirements = requirements_for(recipe, budget)
            options = builder.build_options(requirements)
            option = _preferred(options, recipe.tier)
            if option is None:
                logger.info("Recipe %s has no build at %s PLN", recipe.key, budget)
                continue

            signature = tuple(sorted(component.id for component in option.parts.values()))
            if signature in seen:
                continue
            seen.add(signature)

            # Label by what the build actually costs, not by the budget it was
            # aimed at: a list sorted by price where "6K" sits below "5K" reads
            # as a bug to a customer.
            price_k = round(float(option.customer_total_pln) / 1000, 1)
            name = f"{recipe.name} {price_k:g}K"
            if name in used_names:
                name = f"{name} {recipe.tier.value[:3].upper()}"
            suffix = 2
            while name in used_names:
                name = f"{recipe.name} {price_k:g}K #{suffix}"
                suffix += 1
            used_names.add(name)
            drafts.append(
                ReadyBuildDraft(
                    slug=_slugify(f"{recipe.key}-{budget}"),
                    name=name,
                    description=recipe.description,
                    category=recipe.category,
                    tags=list(recipe.tags),
                    recipe=recipe,
                    budget_pln=budget,
                    option=option,
                    components={
                        category.value: component.id for category, component in option.parts.items()
                    },
                )
            )

    drafts.sort(key=lambda draft: draft.price_pln)
    logger.info("Generated %s catalogue builds from %s recipes", len(drafts), len(recipes))
    return drafts


def _preferred(options: list[BuildOption], tier: BuildTier) -> BuildOption | None:
    if not options:
        return None
    for option in options:
        if option.tier is tier:
            return option
    return options[-1]
