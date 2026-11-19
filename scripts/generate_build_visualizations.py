"""Render the AI visualisation of every ready build that lacks one.

    python -m scripts.generate_build_visualizations [--limit N] [--slug SLUG]
                                                     [--dry-run] [--force]

For each active shelf entry: resolve the parts, run the compatibility check,
compute the fingerprint for the build's default look, skip it when a ready
image exists, otherwise generate, save and record. One failure never stops
the run; the summary at the end lists SUCCESS / FAILED / SKIPPED.

Costs: one paid request per *missing* visualisation (plus at most one retry
on a transient error). Re-running the script is free for builds already
rendered. Use ``--limit 1`` for the first quality check.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from app.config import get_settings
from app.db.models import ReadyBuild, ReadyBuildStatus
from app.db.session import create_engine, create_session_factory
from app.domain.enums import Aesthetics
from app.logging_setup import setup_logging
from app.services.ai import Visualizer
from app.services.catalog import get_catalog
from app.services.compatibility import validate_build
from app.services.compatibility.gate import parts_from_ids
from app.services.media.presets import default_preset

logger = logging.getLogger("generate_build_visualizations")


async def run(
    *, limit: int | None, slug: str | None, dry_run: bool, force: bool
) -> tuple[int, int, int]:
    settings = get_settings()
    visualizer = Visualizer.from_settings(settings)
    if not visualizer.enabled and not dry_run:
        logger.error("AI visualisation is disabled or OPENAI_API_KEY is missing")
        return 0, 0, 0

    catalog = get_catalog()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)

    success = failed = skipped = 0
    try:
        async with factory() as session:
            stmt = select(ReadyBuild).where(ReadyBuild.status == ReadyBuildStatus.ACTIVE)
            if slug:
                stmt = stmt.where(ReadyBuild.slug == slug)
            stmt = stmt.order_by(ReadyBuild.id)
            rows = list(await session.scalars(stmt))

        total = len(rows)
        done = 0
        for index, row in enumerate(rows, start=1):
            if limit is not None and done >= limit:
                break

            parts, unknown = parts_from_ids(row.components, catalog)
            if unknown:
                logger.error(
                    "[%s/%s] %s: unknown components %s - skipped", index, total, row.slug, unknown
                )
                skipped += 1
                continue
            report = validate_build(parts)
            if not report.compatible:
                logger.error(
                    "[%s/%s] %s: not buildable (%s) - skipped",
                    index,
                    total,
                    row.slug,
                    report.final_label,
                )
                skipped += 1
                continue

            try:
                aesthetics: Aesthetics | None = Aesthetics(row.style)
            except ValueError:
                aesthetics = None
            preset = default_preset(parts, aesthetics)
            key = visualizer.fingerprint_for(parts, preset)

            async with factory() as session:
                existing = await visualizer.status_for(session, parts, preset)
                if existing is not None and existing.is_ready and not force:
                    logger.info("[%s/%s] %s: ready (%s) - skipped", index, total, row.slug, key)
                    skipped += 1
                    continue
                if dry_run:
                    logger.info(
                        "[%s/%s] %s: would generate %s (%s)",
                        index,
                        total,
                        row.slug,
                        key,
                        preset.key,
                    )
                    done += 1
                    continue

                logger.info(
                    "[%s/%s] %s: generating %s (%s)...", index, total, row.slug, key, preset.key
                )
                result = await visualizer.get_or_create(
                    session, parts, preset, ready_build_id=row.id, force=force
                )
                await session.commit()
                done += 1

            if result.ok:
                success += 1
                logger.info("[%s/%s] %s: OK -> %s", index, total, row.slug, result.path)
            else:
                failed += 1
                logger.error("[%s/%s] %s: FAILED - %s", index, total, row.slug, result.error)
    finally:
        await engine.dispose()

    logger.info("SUCCESS: %s", success)
    logger.info("FAILED: %s", failed)
    logger.info("SKIPPED: %s", skipped)
    return success, failed, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AI visualisations for ready builds")
    parser.add_argument("--limit", type=int, default=None, help="generate at most N images")
    parser.add_argument("--slug", default=None, help="only this ready build")
    parser.add_argument("--dry-run", action="store_true", help="list what would be generated")
    parser.add_argument("--force", action="store_true", help="re-render even if an image exists")
    args = parser.parse_args()

    setup_logging("INFO", secrets=[get_settings().bot_token])
    success, failed, _ = asyncio.run(
        run(limit=args.limit, slug=args.slug, dry_run=args.dry_run, force=args.force)
    )
    sys.exit(1 if failed and not success else 0)


if __name__ == "__main__":
    main()
