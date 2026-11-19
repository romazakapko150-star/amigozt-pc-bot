"""Inventory and safe batch generation of the Visual Library.

    python -m scripts.generate_visual_library --dry-run
    python -m scripts.generate_visual_library --limit 10
    python -m scripts.generate_visual_library --category gpu --limit 10
    python -m scripts.generate_visual_library --category monitor
    python -m scripts.generate_visual_library --builds
    python -m scripts.generate_visual_library --components
    python -m scripts.generate_visual_library --rekey

Defaults: ``--missing-only`` - a visual that exists is never re-rendered.
``--force`` re-renders the selection and ``--upgrade-prompt`` re-renders
visuals made with an older prompt version; both need ``--confirm`` when more
than CONFIRM_ABOVE renders are involved. ``--rekey`` attaches renders made by
the first visualiser to their new identity keys - free, no API calls.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from decimal import Decimal

from app.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.domain.components import ComponentCategory
from app.logging_setup import setup_logging
from app.services.visuals import batch

logger = logging.getLogger("generate_visual_library")

#: Above this many paid renders an explicit --confirm is required.
CONFIRM_ABOVE = 10


def _print_report(inv: batch.Inventory, selected: list[batch.EntityPlan]) -> None:
    s = inv.summary()
    cost = (len(selected) * inv.cost_per_call_usd).quantize(inv.cost_per_call_usd.normalize())
    logger.info("TOTAL ENTITIES: %s", s["total_entities"])
    logger.info("BUILDS: %s", s["builds"])
    logger.info("COMPONENTS: %s", s["components"])
    logger.info("ACCESSORIES: %s", s["accessories"])
    logger.info(
        "VISUALS EXISTING: %s (+%s older prompt version)",
        s["visuals_existing"],
        s["visuals_outdated"],
    )
    logger.info("VISUALS MISSING: %s", s["visuals_missing"])
    logger.info("VISUALS FAILED: %s", s["visuals_failed"])
    if s["skipped"]:
        logger.info("SKIPPED (not buildable / unknown parts): %s", s["skipped"])
    logger.info("SELECTED FOR THIS RUN: %s", len(selected))
    logger.info("ESTIMATED NEW IMAGE CALLS: %s", len(selected))
    logger.info("ESTIMATED COST: $%s (at $%s per call)", cost, inv.cost_per_call_usd)
    logger.info('CACHE POLICY: "Existing visual -> reused, 0 image API calls"')


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    categories = None
    if args.category:
        try:
            categories = {ComponentCategory(c) for c in args.category}
        except ValueError as exc:
            logger.error("Unknown category: %s", exc)
            return 2

    only_builds = args.builds and not args.components and not args.category
    only_components = (args.components or bool(args.category)) and not args.builds
    try:
        async with factory() as session:
            inv = await batch.inventory(
                session,
                settings=settings,
                include_builds=not only_components,
                include_components=not only_builds,
                categories=categories,
            )
            if args.rekey:
                moved = await batch.rekey_legacy(session, inv)
                await session.commit()
                logger.info("REKEYED: %s legacy render(s) attached to their new identity", moved)
                inv = await batch.inventory(
                    session,
                    settings=settings,
                    include_builds=not only_components,
                    include_components=not only_builds,
                    categories=categories,
                )

        if args.slug:
            # Targeted re-render: the surgical alternative to --force over the
            # whole shelf when only a handful of builds changed meaning.
            wanted = set(args.slug)
            selected = [p for p in inv.plans if p.label in wanted]
            missing_slugs = wanted - {p.label for p in selected}
            if missing_slugs:
                logger.error("Unknown slug(s): %s", ", ".join(sorted(missing_slugs)))
                return 2
        elif args.priority:
            # Spend on what a customer meets most often first; whole-build
            # hero shots are the least reusable, so they come last.
            selected = inv.priority_order()
            if args.limit is not None:
                selected = selected[: max(0, args.limit)]
        else:
            selected = inv.select(
                missing_only=not args.force,
                include_failed=not args.skip_failed,
                include_outdated=args.upgrade_prompt,
                force=args.force,
                limit=args.limit,
            )
        _print_report(inv, selected)

        if args.dry_run or not selected:
            return 0
        if (
            args.force or args.upgrade_prompt or len(selected) > CONFIRM_ABOVE
        ) and not args.confirm:
            logger.error(
                "%s paid render(s) requested%s - re-run with --confirm to proceed",
                len(selected),
                " with --force/--upgrade-prompt" if (args.force or args.upgrade_prompt) else "",
            )
            return 3

        def progress(index: int, total: int, plan: batch.EntityPlan, result) -> None:  # type: ignore[no-untyped-def]
            state = "OK" if result.ok else "FAILED"
            if result.cache_hit:
                state = "CACHE HIT"
            logger.info(
                "[%s/%s] %s %s: %s%s",
                index,
                total,
                plan.entity_type,
                plan.label,
                state,
                f" ({result.error})" if result.error else "",
            )

        ceiling = Decimal(str(args.max_spend_usd)) if args.max_spend_usd is not None else None
        summary = await batch.generate(
            factory,
            selected,
            settings=settings,
            force=args.force or args.upgrade_prompt,
            max_spend_usd=ceiling,
            progress=progress,
        )
        logger.info("SUCCESS: %s", summary.success)
        logger.info("FAILED: %s", summary.failed)
        logger.info("SKIPPED: %s", summary.skipped)
        logger.info("OPENAI IMAGE CALLS: %s", summary.api_calls)
        if summary.hit_the_ceiling:
            logger.warning(
                "STOPPED ON BUDGET: %s plan(s) left unrendered at the $%s ceiling",
                summary.stopped_on_budget,
                args.max_spend_usd,
            )
        logger.info(
            "SPENT (approx): $%s", summary.cost_usd.quantize(inv.cost_per_call_usd.normalize())
        )
        return 1 if summary.failed and not summary.success else 0
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Visual Library inventory and batch generation")
    parser.add_argument("--dry-run", action="store_true", help="report only, no API calls")
    parser.add_argument("--limit", type=int, default=None, help="render at most N visuals")
    parser.add_argument("--category", action="append", help="component category (repeatable)")
    parser.add_argument("--builds", action="store_true", help="ready builds only")
    parser.add_argument("--components", action="store_true", help="components only")
    parser.add_argument("--missing-only", action="store_true", default=True, help="(default)")
    parser.add_argument("--skip-failed", action="store_true", help="do not retry failed visuals")
    parser.add_argument(
        "--upgrade-prompt", action="store_true", help="re-render older prompt versions"
    )
    parser.add_argument(
        "--force", action="store_true", help="re-render the selection even if it exists"
    )
    parser.add_argument("--confirm", action="store_true", help="required for large or forced runs")
    parser.add_argument("--rekey", action="store_true", help="attach legacy renders to new keys")
    parser.add_argument(
        "--slug",
        action="append",
        help="re-render exactly these entities by label/slug (repeatable)",
    )
    parser.add_argument(
        "--priority",
        action="store_true",
        help="render missing visuals in priority order (parts first, builds last)",
    )
    parser.add_argument(
        "--max-spend-usd",
        type=float,
        default=None,
        help="hard ceiling for this run: it stops before the call that would cross it",
    )
    args = parser.parse_args()

    setup_logging("INFO", secrets=[get_settings().bot_token])
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
