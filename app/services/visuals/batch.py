"""Inventory and safe batch generation for the Visual Library.

Used by ``scripts/generate_visual_library.py`` and the admin commands. The
inventory never spends money: it walks every entity the bot can show (shelf
builds, catalogue components), computes the identity and fingerprint and
asks the library what exists. Generation runs only over the plans the
caller hands back, honours ``limit`` and ``force``, and reports
SUCCESS / FAILED / SKIPPED plus the API calls made and the money spent.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.models import ReadyBuild, ReadyBuildStatus, Visual, VisualEntityType
from app.db.repositories.visualization_repo import VisualizationRepository
from app.domain.components import Component, ComponentCategory
from app.domain.enums import Aesthetics
from app.services.ai.visualizer import Visualizer
from app.services.catalog import Catalog, get_catalog
from app.services.compatibility import validate_build
from app.services.compatibility.gate import parts_from_ids
from app.services.media.presets import VisualPreset, default_preset
from app.services.visuals.components import ComponentVisualizer
from app.services.visuals.library import VisualizationResult

logger = logging.getLogger(__name__)

STATE_EXISTING = "existing"
STATE_OUTDATED = "outdated"
STATE_FAILED = "failed"
STATE_MISSING = "missing"
STATE_SKIPPED = "skipped"  # not buildable / unknown parts

#: Where the money goes first when the budget cannot cover everything. The
#: parts a customer compares are worth more than a hero shot of one build.
PRIORITY_CATEGORIES: tuple[str, ...] = (
    "gpu",
    "cpu",
    "case",
    "cooler",
    "motherboard",
    "ram",
    "ssd",
    "psu",
    "fans",
    "monitor",
    "keyboard",
    "mouse",
    "headset",
    "mousepad",
    "microphone",
    "webcam",
    "speakers",
    "chair",
    "desk",
    "build",
)


@dataclass(slots=True)
class EntityPlan:
    entity_type: str
    entity_id: str
    label: str
    category: str
    identity_key: str
    fingerprint: str
    state: str
    visual: Visual | None = None
    note: str = ""
    # what generation needs
    component: Component | None = None
    parts: dict | None = None
    preset: VisualPreset | None = None
    ready_build_id: int | None = None
    #: What this build asks the photograph to emphasise. Part of its key.
    priorities: tuple[str, ...] = ()

    @property
    def needs_generation(self) -> bool:
        return self.state in {STATE_MISSING, STATE_FAILED}


@dataclass(slots=True)
class Inventory:
    plans: list[EntityPlan] = field(default_factory=list)
    cost_per_call_usd: Decimal = Decimal("0.04")

    def by_state(self, state: str) -> list[EntityPlan]:
        return [p for p in self.plans if p.state == state]

    @property
    def builds(self) -> list[EntityPlan]:
        return [p for p in self.plans if p.entity_type == VisualEntityType.READY_BUILD]

    @property
    def components(self) -> list[EntityPlan]:
        return [p for p in self.plans if p.entity_type == VisualEntityType.COMPONENT]

    @property
    def accessories(self) -> list[EntityPlan]:
        from app.domain.components import ACCESSORY_CATEGORIES

        names = {c.value for c in ACCESSORY_CATEGORIES}
        return [p for p in self.components if p.category in names]

    def summary(self) -> dict:
        missing = self.by_state(STATE_MISSING)
        failed = self.by_state(STATE_FAILED)
        return {
            "total_entities": len(self.plans),
            "builds": len(self.builds),
            "components": len(self.components) - len(self.accessories),
            "accessories": len(self.accessories),
            "visuals_existing": len(self.by_state(STATE_EXISTING)),
            "visuals_outdated": len(self.by_state(STATE_OUTDATED)),
            "visuals_missing": len(missing),
            "visuals_failed": len(failed),
            "skipped": len(self.by_state(STATE_SKIPPED)),
            "estimated_calls": len(missing) + len(failed),
            "estimated_cost_usd": ((len(missing) + len(failed)) * self.cost_per_call_usd).quantize(
                Decimal("0.01")
            ),
        }

    def by_category(self) -> dict[str, dict[str, int]]:
        """Coverage per category: what exists, what is missing, what failed.

        This is the audit the owner actually needs before spending: "GPUs
        are done, monitors are not" is actionable, "55 missing" is not.
        """
        table: dict[str, dict[str, int]] = {}
        for plan in self.plans:
            bucket = table.setdefault(
                plan.category,
                {"total": 0, "existing": 0, "outdated": 0, "missing": 0, "failed": 0, "skipped": 0},
            )
            bucket["total"] += 1
            if plan.state in bucket:
                bucket[plan.state] += 1
        return table

    def priority_order(self) -> list[EntityPlan]:
        """Missing plans in the order the money should be spent.

        Components first (a customer meets them in every list), then
        monitors, then the rest of the desk, then whole builds - a build
        picture is the most impressive and the least reusable, so it is
        worth paying for last.
        """
        rank: dict[str, int] = {}
        for index, category in enumerate(PRIORITY_CATEGORIES):
            rank[category] = index
        fallback = len(PRIORITY_CATEGORIES)
        return sorted(
            (p for p in self.plans if p.needs_generation),
            key=lambda p: (rank.get(p.category, fallback), p.label),
        )

    def select(
        self,
        *,
        missing_only: bool = True,
        include_failed: bool = True,
        include_outdated: bool = False,
        force: bool = False,
        limit: int | None = None,
    ) -> list[EntityPlan]:
        """Plans to generate, in inventory order, capped by ``limit``."""
        chosen: list[EntityPlan] = []
        for plan in self.plans:
            if plan.state == STATE_SKIPPED:
                continue
            if (
                force
                or plan.state == STATE_MISSING
                or (plan.state == STATE_FAILED and include_failed)
                or (plan.state == STATE_OUTDATED and include_outdated)
                or (plan.state == STATE_EXISTING and not missing_only)
            ):
                chosen.append(plan)
        if limit is not None:
            chosen = chosen[: max(0, limit)]
        return chosen


async def inventory(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
    catalog: Catalog | None = None,
    include_builds: bool = True,
    include_components: bool = True,
    categories: set[ComponentCategory] | None = None,
) -> Inventory:
    cfg = settings or get_settings()
    cat = catalog or get_catalog()
    build_visualizer = Visualizer.from_settings(cfg)
    component_visualizer = ComponentVisualizer.from_settings(cfg)
    repo = VisualizationRepository(session)
    plans: list[EntityPlan] = []

    if include_builds:
        stmt = (
            select(ReadyBuild)
            .where(ReadyBuild.status == ReadyBuildStatus.ACTIVE)
            .order_by(ReadyBuild.id)
        )
        for ready in await session.scalars(stmt):
            parts, unknown = parts_from_ids(ready.components, cat)

            def shelf_plan(
                ready: ReadyBuild,
                *,
                identity_key: str,
                fingerprint: str,
                state: str,
                note: str,
                parts_map: dict | None = None,
                preset: VisualPreset | None = None,
                priorities: tuple[str, ...] = (),
            ) -> EntityPlan:
                return EntityPlan(
                    entity_type=VisualEntityType.READY_BUILD,
                    entity_id=str(ready.id),
                    label=ready.slug,
                    category="build",
                    ready_build_id=ready.id,
                    identity_key=identity_key,
                    fingerprint=fingerprint,
                    state=state,
                    note=note,
                    parts=parts_map,
                    preset=preset,
                    priorities=priorities,
                )

            if unknown or not parts:
                plans.append(
                    shelf_plan(
                        ready,
                        identity_key="",
                        fingerprint="",
                        state=STATE_SKIPPED,
                        note=f"unknown components {unknown}",
                    )
                )
                continue
            report = validate_build(parts)
            if not report.compatible:
                plans.append(
                    shelf_plan(
                        ready,
                        identity_key="",
                        fingerprint="",
                        state=STATE_SKIPPED,
                        note=f"not buildable: {report.final_label}",
                    )
                )
                continue
            try:
                aesthetics: Aesthetics | None = Aesthetics(ready.style)
            except ValueError:
                aesthetics = None
            preset = default_preset(parts, aesthetics)
            wants = ready.visual_priorities
            spec = build_visualizer.describe(parts, preset, wants)
            plans.append(
                shelf_plan(
                    ready,
                    identity_key=build_visualizer.identity_for(parts, preset, wants),
                    fingerprint=build_visualizer.fingerprint_for(parts, preset, wants),
                    state=STATE_MISSING,
                    note=spec.accent.value,
                    parts_map=parts,
                    preset=preset,
                    priorities=tuple(wants),
                )
            )

    if include_components:
        for component in cat:
            if component.discontinued:
                continue
            if categories is not None and component.category not in categories:
                continue
            request = component_visualizer.request_for(component)
            plans.append(
                EntityPlan(
                    entity_type=VisualEntityType.COMPONENT,
                    entity_id=component.id,
                    label=component.name,
                    category=component.category.value,
                    identity_key=request.identity_key,
                    fingerprint=request.fingerprint,
                    state=STATE_MISSING,
                    component=component,
                )
            )

    fingerprints = [p.fingerprint for p in plans if p.fingerprint]
    identities = [p.identity_key for p in plans if p.identity_key]
    exact = await repo.by_fingerprints(fingerprints)
    by_identity = await repo.by_identities(identities)
    for plan in plans:
        if plan.state == STATE_SKIPPED:
            continue
        row = exact.get(plan.fingerprint)
        if row is not None and row.is_ready and _file_ok(row):
            plan.state, plan.visual = STATE_EXISTING, row
            continue
        older = by_identity.get(plan.identity_key)
        if older is not None and _file_ok(older):
            plan.state, plan.visual = STATE_OUTDATED, older
            continue
        if row is not None and row.status == "failed":
            plan.state, plan.visual = STATE_FAILED, row
            continue
        plan.state, plan.visual = STATE_MISSING, row

    return Inventory(plans=plans, cost_per_call_usd=cfg.ai_image_cost_usd)


class BudgetExhausted(Exception):
    """Raised when a run stops because the next render would overspend."""


@dataclass(slots=True)
class BatchSummary:
    success: int = 0
    failed: int = 0
    skipped: int = 0
    api_calls: int = 0
    cost_usd: Decimal = Decimal(0)
    #: Plans left unrendered because the ceiling was reached.
    stopped_on_budget: int = 0
    results: list[tuple[EntityPlan, VisualizationResult]] = field(default_factory=list)

    @property
    def hit_the_ceiling(self) -> bool:
        return self.stopped_on_budget > 0


async def generate(
    session_factory: async_sessionmaker[AsyncSession],
    plans: list[EntityPlan],
    *,
    settings: Settings | None = None,
    force: bool = False,
    max_spend_usd: Decimal | None = None,
    progress: Callable[[int, int, EntityPlan, VisualizationResult], None] | None = None,
) -> BatchSummary:
    """Render the given plans one by one; one failure never stops the run.

    ``max_spend_usd`` is a hard ceiling on this run: before every render the
    cost of one more call is added to what has already been spent, and the
    run stops the moment that would cross the line. The check happens
    *before* the call, so the ceiling can never be exceeded - only reached.
    """
    cfg = settings or get_settings()
    build_visualizer = Visualizer.from_settings(cfg)
    component_visualizer = ComponentVisualizer.from_settings(cfg)
    summary = BatchSummary()
    total = len(plans)

    for index, plan in enumerate(plans, start=1):
        if max_spend_usd is not None and summary.cost_usd + cfg.ai_image_cost_usd > max_spend_usd:
            summary.stopped_on_budget = total - index + 1
            logger.warning(
                "Stopping the batch: %s more render(s) would exceed the $%s ceiling (spent $%s)",
                summary.stopped_on_budget,
                max_spend_usd,
                summary.cost_usd,
            )
            break
        async with session_factory() as session:
            try:
                if plan.entity_type == VisualEntityType.COMPONENT and plan.component is not None:
                    result = await component_visualizer.get_or_create(
                        session, plan.component, force=force, allow_generation=True
                    )
                elif plan.parts is not None and plan.preset is not None:
                    result = await build_visualizer.get_or_create(
                        session,
                        plan.parts,
                        plan.preset,
                        ready_build_id=plan.ready_build_id,
                        force=force,
                        priorities=plan.priorities,
                    )
                else:
                    summary.skipped += 1
                    continue
                await session.commit()
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Batch item %s crashed", plan.label)
                result = VisualizationResult(status="failed", error=str(exc)[:300])

        summary.api_calls += result.api_calls
        summary.cost_usd += Decimal(result.api_calls) * cfg.ai_image_cost_usd
        if result.ok and not result.cache_hit:
            summary.success += 1
        elif result.ok and result.cache_hit:
            summary.skipped += 1
        else:
            summary.failed += 1
        summary.results.append((plan, result))
        if progress is not None:
            progress(index, total, plan, result)

    return summary


async def rekey_legacy(session: AsyncSession, inv: Inventory) -> int:
    """Attach renders made by the first visualiser to their new keys.

    Those rows stored the same parts and preset but a fingerprint from the
    old formula. Moving them under the new identity costs nothing and saves
    a paid re-render per build.
    """
    repo = VisualizationRepository(session)
    moved = 0
    for plan in inv.plans:
        if (
            plan.state not in {STATE_MISSING, STATE_FAILED}
            or plan.parts is None
            or plan.preset is None
        ):
            continue
        wanted = {
            category.value: component.id
            for category, component in plan.parts.items()
            if category.value
            in {"cpu", "cooler", "motherboard", "ram", "gpu", "ssd", "psu", "case", "fans"}
        }
        for row in await repo.list_for_entity(VisualEntityType.READY_BUILD, plan.entity_id):
            if row.fingerprint == plan.fingerprint or not row.is_ready:
                continue
            if row.preset_key != plan.preset.key or dict(row.components or {}) != wanted:
                continue
            if await repo.get_by_fingerprint(plan.fingerprint) is not None:
                break
            row.identity_key = plan.identity_key
            row.fingerprint = plan.fingerprint
            await session.flush()
            plan.state, plan.visual = STATE_EXISTING, row
            moved += 1
            break
    return moved


def _file_ok(row: Visual) -> bool:
    from pathlib import Path

    return bool(row.image_path) and Path(row.image_path or "").is_file()
