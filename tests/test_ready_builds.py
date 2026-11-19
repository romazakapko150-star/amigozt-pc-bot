"""The ready-build shelf: generation, storage, filtering and rendering."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.views.ready_builds import render_build_page, render_list, render_row
from app.db.models import ReadyBuild, ReadyBuildStatus
from app.db.repositories import ReadyBuildRepository
from app.domain.components import REQUIRED_CATEGORIES, ComponentCategory
from app.services.catalog import get_catalog
from app.services.compatibility import validate
from app.services.ready_builds import RECIPES, generate_catalogue, requirements_for

MIN_CATALOGUE_SIZE = 40


@pytest.fixture(scope="module")
def drafts():  # type: ignore[no-untyped-def]
    return generate_catalogue()


# --- generation ---------------------------------------------------------------


def test_catalogue_is_big_enough(drafts) -> None:  # type: ignore[no-untyped-def]
    assert len(drafts) >= MIN_CATALOGUE_SIZE


def test_every_generated_build_is_compatible(drafts) -> None:  # type: ignore[no-untyped-def]
    for draft in drafts:
        report = validate(draft.option.parts)
        assert report.ok, f"{draft.slug}: {[i.detail for i in report.errors]}"


def test_every_build_has_the_required_parts(drafts) -> None:  # type: ignore[no-untyped-def]
    for draft in drafts:
        present = {ComponentCategory(c) for c in draft.components}
        assert present >= REQUIRED_CATEGORIES, draft.slug


def test_slugs_and_names_are_unique(drafts) -> None:  # type: ignore[no-untyped-def]
    slugs = [draft.slug for draft in drafts]
    names = [draft.name for draft in drafts]
    assert len(slugs) == len(set(slugs))
    assert len(names) == len(set(names)), [n for n, c in Counter(names).items() if c > 1]


def test_every_component_referenced_exists(drafts) -> None:  # type: ignore[no-untyped-def]
    catalog = get_catalog()
    for draft in drafts:
        for component_id in draft.components.values():
            assert catalog.get(component_id) is not None, component_id


def test_builds_span_a_wide_price_range(drafts) -> None:  # type: ignore[no-untyped-def]
    prices = [draft.price_pln for draft in drafts]
    assert min(prices) < Decimal(6000)
    assert max(prices) > Decimal(15000)


def test_catalogue_covers_many_categories(drafts) -> None:  # type: ignore[no-untyped-def]
    categories = {draft.category for draft in drafts}
    assert len(categories) >= 8


def test_no_two_builds_share_the_same_parts(drafts) -> None:  # type: ignore[no-untyped-def]
    """Duplicates would pad the shelf with identical machines."""
    signatures = [tuple(sorted(draft.components.values())) for draft in drafts]
    assert len(signatures) == len(set(signatures))


def test_price_matches_the_option(drafts) -> None:  # type: ignore[no-untyped-def]
    for draft in drafts:
        assert draft.price_pln == draft.option.customer_total_pln
        assert draft.cost_pln < draft.price_pln


def test_recipes_have_unique_keys() -> None:
    keys = [recipe.key for recipe in RECIPES]
    assert len(keys) == len(set(keys))


def test_recipe_requirements_are_valid() -> None:
    for recipe in RECIPES:
        for budget in recipe.budgets:
            requirements = requirements_for(recipe, budget)
            assert requirements.budget_pln == budget
            assert requirements.purpose is recipe.purpose


def test_brand_locked_recipes_produce_matching_builds(drafts) -> None:  # type: ignore[no-untyped-def]
    all_amd = [d for d in drafts if d.recipe.key == "amd-only"]
    assert all_amd
    for draft in all_amd:
        assert draft.option.parts[ComponentCategory.CPU].brand == "AMD"
        assert draft.option.parts[ComponentCategory.GPU].brand == "AMD"


def test_white_recipes_actually_produce_white_builds(drafts) -> None:  # type: ignore[no-untyped-def]
    from app.services.recommendation.generator import style_match

    white = [d for d in drafts if d.recipe.key == "white-dream"]
    assert white
    assert any(
        style_match(d.option.parts, requirements_for(d.recipe, d.budget_pln)) >= 0.5 for d in white
    )


# --- storage and filtering ----------------------------------------------------


async def _store(session: AsyncSession, **overrides: object) -> ReadyBuild:
    defaults: dict = {
        "slug": "test-build",
        "name": "AmigoZT Test",
        "description": "Test",
        "category": "gaming",
        "tags": ["1440p"],
        "purpose": "gaming",
        "resolution": "1440p",
        "target_fps": "144",
        "tier": "optimal",
        "budget_min_pln": 5000,
        "budget_max_pln": 7000,
        "cpu_brand": "any",
        "gpu_brand": "any",
        "style": "black",
        "components": {"cpu": "amd-ryzen-5-7600", "gpu": "amd-rx-7600"},
        "reference_price_pln": Decimal(6000),
        "reference_cost_pln": Decimal(4800),
        "performance_score": 400,
        "status": ReadyBuildStatus.ACTIVE,
    }
    defaults.update(overrides)
    row = ReadyBuild(**defaults)
    session.add(row)
    await session.flush()
    return row


async def test_repository_filters_by_category(session: AsyncSession) -> None:
    await _store(session, slug="a", category="gaming", reference_price_pln=Decimal(6000))
    await _store(session, slug="b", category="budget", reference_price_pln=Decimal(4000))
    await session.commit()

    repo = ReadyBuildRepository(session)
    assert await repo.count(category="gaming") == 1
    assert await repo.count(category="budget") == 1
    assert await repo.count() == 2


async def test_repository_filters_by_price(session: AsyncSession) -> None:
    await _store(session, slug="cheap", reference_price_pln=Decimal(4000))
    await _store(session, slug="dear", reference_price_pln=Decimal(15000))
    await session.commit()

    repo = ReadyBuildRepository(session)
    assert await repo.count(max_price_pln=9000) == 1


async def test_archived_builds_are_hidden(session: AsyncSession) -> None:
    await _store(session, slug="live")
    await _store(session, slug="gone", status=ReadyBuildStatus.ARCHIVED)
    await session.commit()

    repo = ReadyBuildRepository(session)
    assert await repo.count() == 1
    assert [b.slug for b in await repo.fetch()] == ["live"]


async def test_listing_is_ordered_by_price_and_paginated(session: AsyncSession) -> None:
    for index, price in enumerate([9000, 5000, 7000]):
        await _store(session, slug=f"b{index}", reference_price_pln=Decimal(price))
    await session.commit()

    repo = ReadyBuildRepository(session)
    first_page = await repo.fetch(limit=2, offset=0)
    assert [int(b.reference_price_pln) for b in first_page] == [5000, 7000]

    second_page = await repo.fetch(limit=2, offset=2)
    assert [int(b.reference_price_pln) for b in second_page] == [9000]


async def test_categories_report_counts(session: AsyncSession) -> None:
    await _store(session, slug="g1", category="gaming")
    await _store(session, slug="g2", category="gaming")
    await _store(session, slug="b1", category="budget")
    await session.commit()

    categories = dict(await ReadyBuildRepository(session).categories())
    assert categories == {"gaming": 2, "budget": 1}


# --- rendering ----------------------------------------------------------------


async def test_row_is_short_enough_for_a_phone(session: AsyncSession) -> None:
    row = await _store(session, name="AmigoZT 1440p Sweet Spot 7.2K")
    rendered = render_row(1, row)
    for line in rendered.splitlines():
        assert len(line) < 60


async def test_list_reports_the_page(session: AsyncSession) -> None:
    row = await _store(session)
    text = render_list([row], total=12, page=2, pages=3, lang="ru")
    assert "2" in text and "3" in text


def test_empty_list_says_so() -> None:
    assert "пусто" in render_list([], total=0, page=1, pages=1, lang="ru")


async def test_build_page_lists_components_and_price(session: AsyncSession) -> None:
    row = await _store(
        session,
        components={
            "cpu": "amd-ryzen-7-7800x3d",
            "gpu": "amd-rx-9070",
            "motherboard": "asus-tuf-b650-plus-wifi",
            "ram": "kingston-fury-beast-32-ddr5-6000",
            "ssd": "samsung-990-evo-1tb",
            "psu": "corsair-rm750e",
            "case": "lianli-lancool-216-black",
            "cooler": "thermalright-peerless-assassin-120-se",
        },
    )
    text = render_build_page(row, get_catalog(), "ru")

    assert "Ryzen 7 7800X3D" in text
    assert "RX 9070" in text
    assert "6 000 PLN" in text
    # Estimates must always be flagged, and frame rates never invented.
    assert "ориентировочная" in text
    assert "benchmark" in text.lower()


async def test_build_page_never_shows_the_acquisition_cost(session: AsyncSession) -> None:
    row = await _store(session, reference_cost_pln=Decimal(4800))
    text = render_build_page(row, get_catalog(), "ru")
    assert "4 800" not in text
    assert "4800" not in text.replace(" ", "")
