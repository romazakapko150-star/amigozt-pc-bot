"""Photograph the machines customers are most likely to be shown.

A configured build is rendered on demand and cached, so the first customer
to reach a given machine waits for it and pays for it. This walks the
requirement space the configurator can actually produce, counts how many
configurations land on each distinct machine, and renders the most common
ones ahead of time - most reach, least money.

    python -m scripts.pregenerate_builds --dry-run
    python -m scripts.pregenerate_builds --limit 40 --max-spend-usd 1.60 --confirm

Nothing is rendered twice: a machine already in the library is skipped, and
the run stops before the call that would cross the ceiling.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import logging
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.repositories.visualization_repo import VisualizationRepository
from app.db.session import create_engine, create_session_factory
from app.domain.enums import Aesthetics, Priority, Purpose, Resolution
from app.domain.requirements import BuildRequirements
from app.logging_setup import setup_logging
from app.services.ai.visualizer import Visualizer
from app.services.media.presets import VisualPreset, default_preset
from app.services.recommendation import BuildService

logger = logging.getLogger("pregenerate_builds")

#: The requirement space, sampled at the points a customer can actually pick.
BUDGETS = (3000, 4000, 5000, 6000, 7000, 8000, 10000, 12000, 15000, 20000)
PURPOSES = (Purpose.GAMING, Purpose.WORK, Purpose.DESIGN, Purpose.AI_ML, Purpose.UNIVERSAL)
LOOKS = (Aesthetics.BLACK, Aesthetics.WHITE, Aesthetics.BLACK_RGB, Aesthetics.WHITE_RGB)
PRIORITY_SETS: tuple[tuple[Priority, ...], ...] = (
    (),
    (Priority.SILENCE,),
    (Priority.LOOKS,),
    (Priority.SILENCE, Priority.LOOKS),
    (Priority.MAX_FPS,),
    (Priority.COMPACT,),
)


@dataclass(slots=True)
class Candidate:
    """One distinct machine, and how many configurations reach it."""

    identity: str
    parts: dict
    preset: VisualPreset
    priorities: list[str]
    reach: int = 0


def survey() -> list[Candidate]:
    """Every distinct machine the sample produces, most-reached first."""
    service = BuildService()
    visualizer = Visualizer.from_settings(get_settings())
    found: dict[str, Candidate] = {}
    counts: Counter[str] = Counter()
    considered = 0

    for budget, purpose, look, priorities in itertools.product(
        BUDGETS, PURPOSES, LOOKS, PRIORITY_SETS
    ):
        considered += 1
        requirements = BuildRequirements(
            budget_pln=budget,
            purpose=purpose,
            resolution=Resolution.QHD if budget >= 7000 else Resolution.FHD,
            aesthetics=look,
            priorities=list(priorities),
        )
        try:
            option = service.recommended_option(requirements)
        except Exception:  # pragma: no cover - a generator failure is not fatal here
            logger.debug("No build for %s/%s/%s", budget, purpose, look, exc_info=True)
            continue
        if option is None:
            continue

        wanted = [p.value for p in requirements.priorities]
        preset = default_preset(option.parts, requirements.aesthetics)
        key = visualizer.identity_for(option.parts, preset, wanted)
        counts[key] += 1
        found.setdefault(
            key,
            Candidate(identity=key, parts=option.parts, preset=preset, priorities=wanted),
        )

    for key, candidate in found.items():
        candidate.reach = counts[key]
    logger.info("Sampled %s configurations -> %s distinct machines", considered, len(found))
    return sorted(found.values(), key=lambda c: (-c.reach, c.identity))


async def missing_only(session: AsyncSession, candidates: list[Candidate]) -> list[Candidate]:
    """Drop the machines the library has already photographed."""
    repo = VisualizationRepository(session)
    known = await repo.by_identities([c.identity for c in candidates])
    return [c for c in candidates if c.identity not in known]


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    cost = settings.ai_image_cost_usd

    try:
        candidates = survey()
        async with factory() as session:
            todo = await missing_only(session, candidates)

        covered = sum(c.reach for c in candidates)
        logger.info("ALREADY PHOTOGRAPHED: %s", len(candidates) - len(todo))
        logger.info("MISSING: %s", len(todo))
        if args.limit is not None:
            todo = todo[: max(0, args.limit)]
        reach = sum(c.reach for c in todo)
        logger.info(
            "SELECTED: %s machines, reaching %s of %s sampled configurations (%.0f%%)",
            len(todo),
            reach,
            covered,
            (reach / covered * 100) if covered else 0,
        )
        logger.info("ESTIMATED COST: $%s", (len(todo) * cost).quantize(Decimal("0.01")))

        if args.dry_run or not todo:
            return 0
        if not args.confirm:
            logger.error("%s paid renders - re-run with --confirm", len(todo))
            return 3

        ceiling = Decimal(str(args.max_spend_usd)) if args.max_spend_usd is not None else None
        visualizer = Visualizer.from_settings(settings)
        spent = Decimal(0)
        rendered = 0

        for index, candidate in enumerate(todo, start=1):
            if ceiling is not None and spent + cost > ceiling:
                logger.warning(
                    "Stopping: %s machines left, $%s ceiling reached",
                    len(todo) - index + 1,
                    ceiling,
                )
                break
            async with factory() as session:
                result = await visualizer.get_or_create(
                    session,
                    candidate.parts,
                    candidate.preset,
                    priorities=candidate.priorities,
                )
                await session.commit()
            spent += Decimal(result.api_calls) * cost
            rendered += 1 if result.ok and not result.cache_hit else 0
            logger.info(
                "[%s/%s] reach %s: %s",
                index,
                len(todo),
                candidate.reach,
                "OK" if result.ok else f"FAILED ({result.error})",
            )

        logger.info("RENDERED: %s", rendered)
        logger.info("SPENT (approx): $%s", spent.quantize(Decimal("0.01")))
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, no API calls")
    parser.add_argument("--limit", type=int, default=None, help="render at most N machines")
    parser.add_argument("--confirm", action="store_true", help="required to spend anything")
    parser.add_argument(
        "--max-spend-usd",
        type=float,
        default=None,
        help="hard ceiling: the run stops before the call that would cross it",
    )
    args = parser.parse_args()
    setup_logging(get_settings().log_level)
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
