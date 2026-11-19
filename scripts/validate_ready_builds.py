"""Check every stored ready build.

    python -m scripts.validate_ready_builds

Exits non-zero when anything is wrong, so it can gate a deploy. Checks that
each row references real components, still passes the compatibility engine,
has the fields the UI needs, and can still be priced.
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
from app.domain.components import REQUIRED_CATEGORIES, ComponentCategory
from app.logging_setup import setup_logging
from app.services.catalog import Catalog, get_catalog
from app.services.compatibility import validate
from app.services.pricing import PriceService

logger = logging.getLogger("validate_ready_builds")

REQUIRED_FIELDS = ("name", "slug", "category", "purpose", "resolution", "components")


def _check_row(row: ReadyBuild, catalog: Catalog, prices: PriceService) -> list[str]:
    problems: list[str] = []

    for field in REQUIRED_FIELDS:
        if not getattr(row, field, None):
            problems.append(f"missing field: {field}")

    if not row.components:
        problems.append("no components")
        return problems

    parts = {}
    for raw_category, component_id in row.components.items():
        try:
            category = ComponentCategory(raw_category)
        except ValueError:
            problems.append(f"unknown category: {raw_category}")
            continue

        component = catalog.get(component_id)
        if component is None:
            problems.append(f"unknown component: {component_id}")
            continue
        if component.discontinued:
            problems.append(f"discontinued component: {component_id}")
        parts[category] = component

    missing = REQUIRED_CATEGORIES - set(parts)
    problems.extend(f"missing part: {category.value}" for category in sorted(missing))

    if parts:
        report = validate(parts)
        problems.extend(f"incompatible: {issue.detail}" for issue in report.errors)
        if report.ok and report.unknowns:
            logger.info(
                "%s: %s checks without data (%s)",
                row.slug,
                len(report.unknowns),
                ", ".join(sorted({c.code for c in report.unknowns})),
            )

        breakdown = prices.price_parts(parts)
        problems.extend(f"no price for {c.value}" for c in breakdown.missing)

        if row.reference_price_pln is not None and breakdown.acquisition_cost_pln > Decimal(0):
            # A snapshot far from the current cost means the shelf is stale.
            drift = abs(breakdown.acquisition_cost_pln - (row.reference_cost_pln or Decimal(0)))
            if row.reference_cost_pln and drift / row.reference_cost_pln > Decimal("0.15"):
                problems.append(
                    f"price drifted by {drift} PLN since seeding - re-run seed_ready_builds"
                )

    return problems


async def run(include_archived: bool = False) -> int:
    catalog = get_catalog()
    prices = PriceService()

    engine = create_engine(get_settings().database_url)
    factory = create_session_factory(engine)

    try:
        async with factory() as session:
            stmt = select(ReadyBuild)
            if not include_archived:
                stmt = stmt.where(ReadyBuild.status == ReadyBuildStatus.ACTIVE)
            rows = list(await session.scalars(stmt))
    finally:
        await engine.dispose()

    if not rows:
        logger.error("No ready builds found. Run: python -m scripts.seed_ready_builds")
        return 1

    slugs = [row.slug for row in rows]
    failures = 0

    if len(slugs) != len(set(slugs)):
        logger.error("Duplicate slugs in the catalogue")
        failures += 1

    for row in rows:
        problems = _check_row(row, catalog, prices)
        if problems:
            failures += 1
            logger.error("%s (%s):", row.name, row.slug)
            for problem in problems:
                logger.error("    - %s", problem)

    logger.info("Checked %s builds, %s with problems", len(rows), failures)
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the ready-build catalogue")
    parser.add_argument("--include-archived", action="store_true")
    args = parser.parse_args()

    setup_logging("INFO", secrets=[get_settings().bot_token])
    sys.exit(asyncio.run(run(include_archived=args.include_archived)))


if __name__ == "__main__":
    main()
