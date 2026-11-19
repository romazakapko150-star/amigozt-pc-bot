"""Populate the ready-build catalogue.

    python -m scripts.seed_ready_builds [--dry-run] [--replace]

Regenerates every recipe through the live engine, so re-running after a
catalogue or price change refreshes the shelf. Existing slugs are updated in
place, which keeps any links a customer already has working.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from decimal import Decimal

from sqlalchemy import select

from app.config import get_settings
from app.db.models import ReadyBuild, ReadyBuildStatus
from app.db.session import create_engine, create_session_factory
from app.logging_setup import setup_logging
from app.services.compatibility import validate
from app.services.ready_builds import ReadyBuildDraft, generate_catalogue

logger = logging.getLogger("seed_ready_builds")


def _to_row(draft: ReadyBuildDraft, row: ReadyBuild | None = None) -> ReadyBuild:
    recipe = draft.recipe
    build = row or ReadyBuild(slug=draft.slug)

    build.name = draft.name
    build.description = draft.description
    build.category = draft.category
    build.tags = draft.tags
    build.purpose = recipe.purpose.value
    build.resolution = recipe.resolution.value
    build.target_fps = recipe.target_fps.value if recipe.target_fps else None
    build.tier = draft.option.tier.value
    # A shelf entry is browsed by budget, so store the band it belongs to
    # rather than a single number.
    build.budget_min_pln = int(draft.budget_pln * 0.9)
    build.budget_max_pln = int(draft.budget_pln * 1.1)
    build.cpu_brand = recipe.cpu_brand.value
    build.gpu_brand = recipe.gpu_brand.value
    build.style = recipe.aesthetics.value
    build.rgb = recipe.aesthetics.wants_rgb
    build.wifi = recipe.wifi
    build.bluetooth = recipe.bluetooth
    build.ram_gb = recipe.ram_gb
    build.storage_gb = recipe.storage_gb
    build.components = draft.components
    build.reference_price_pln = draft.price_pln
    build.reference_cost_pln = draft.cost_pln
    build.performance_score = draft.performance_score

    quote = draft.option.quote
    build.estimated_hours = Decimal(str(quote.estimated_total_hours))
    build.complexity_score = quote.complexity.score
    build.complexity_level = quote.complexity_level.value
    build.labor_value_pln = quote.labor_value_pln
    build.component_margin_pln = quote.component_margin_pln
    build.service_reserve_pln = quote.service_reserve_pln
    build.gross_profit_pln = quote.gross_profit_pln
    build.profit_per_hour_pln = quote.profit_per_hour_pln
    build.pricing_snapshot = quote.as_snapshot()
    build.status = ReadyBuildStatus.ACTIVE
    build.source = "amigozt-generator"
    return build


async def seed(dry_run: bool = False, replace: bool = False) -> int:
    drafts = generate_catalogue()
    if not drafts:
        logger.error("Generator produced nothing - check the component catalogue")
        return 1

    rejected = 0
    for draft in drafts:
        report = validate(draft.option.parts)
        if not report.ok:
            rejected += 1
            logger.error(
                "%s is incompatible and will not be stored: %s",
                draft.slug,
                "; ".join(issue.detail for issue in report.errors),
            )

    usable = [d for d in drafts if validate(d.option.parts).ok]
    logger.info("%s builds generated, %s rejected as incompatible", len(drafts), rejected)

    if dry_run:
        for draft in usable:
            logger.info(
                "%-38s %10s PLN  perf=%4s  %s",
                draft.name,
                draft.price_pln,
                draft.performance_score,
                draft.category,
            )
        return 0

    engine = create_engine(get_settings().database_url)
    factory = create_session_factory(engine)
    created = updated = 0

    try:
        async with factory() as session:
            if replace:
                existing_rows = list(await session.scalars(select(ReadyBuild)))
                for row in existing_rows:
                    row.status = ReadyBuildStatus.ARCHIVED

            for draft in usable:
                row = await session.scalar(select(ReadyBuild).where(ReadyBuild.slug == draft.slug))
                if row is None:
                    session.add(_to_row(draft))
                    created += 1
                else:
                    _to_row(draft, row)
                    updated += 1

            await session.commit()
    finally:
        await engine.dispose()

    logger.info("Catalogue seeded: %s created, %s updated", created, updated)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the ready-build catalogue")
    parser.add_argument("--dry-run", action="store_true", help="generate but do not write")
    parser.add_argument(
        "--replace", action="store_true", help="archive existing entries before seeding"
    )
    args = parser.parse_args()

    setup_logging("INFO", secrets=[get_settings().bot_token])
    sys.exit(asyncio.run(seed(dry_run=args.dry_run, replace=args.replace)))


if __name__ == "__main__":
    main()
