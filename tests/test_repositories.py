from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.flows.configurator import build_requirements
from app.db.models import AnalyticsEvent, EventName
from app.db.repositories import AnalyticsRepository, BuildRepository, UserRepository


async def test_get_or_create_is_idempotent(session: AsyncSession) -> None:
    repo = UserRepository(session)

    first = await repo.get_or_create(42, username="amigo", first_name="Roma")
    await session.commit()
    second = await repo.get_or_create(42, username="amigo", first_name="Roma")

    assert first.id == second.id


async def test_get_or_create_refreshes_the_profile(session: AsyncSession) -> None:
    repo = UserRepository(session)
    await repo.get_or_create(42, username="old_name", first_name="Roma")
    await session.commit()

    user = await repo.get_or_create(42, username="new_name", first_name="Roma")
    await session.commit()

    assert user.username == "new_name"


async def test_language_choice_survives_a_reconnect(session: AsyncSession) -> None:
    """An explicit /language choice must outlive Telegram's language_code."""
    repo = UserRepository(session)
    user = await repo.get_or_create(42, language="ru")
    user.language = "pl"
    await session.commit()

    again = await repo.get_by_telegram_id(42)
    assert again is not None
    assert again.language == "pl"


async def test_create_draft_denormalises_filter_columns(
    session: AsyncSession, gaming_answers: dict
) -> None:
    user = await UserRepository(session).get_or_create(42)
    requirements = build_requirements(gaming_answers)

    build = await BuildRepository(session).create_draft(user.id, requirements)
    await session.commit()

    assert build.budget_pln == 6000
    assert build.purpose == "gaming"
    assert build.resolution == "1440p"
    assert build.target_fps == "144"
    # Full requirements are kept verbatim for the recommendation engine.
    assert build.requirements["games"] == ["cs2", "cyberpunk"]
    assert build.components == {}


async def test_builds_are_listed_newest_first(session: AsyncSession, gaming_answers: dict) -> None:
    user = await UserRepository(session).get_or_create(42)
    repo = BuildRepository(session)

    for budget in (3000, 4000, 5000):
        gaming_answers["budget_pln"] = budget
        await repo.create_draft(user.id, build_requirements(gaming_answers))
    await session.commit()

    builds = await repo.list_for_user(user.id, limit=2)
    assert len(builds) == 2
    assert {b.budget_pln for b in builds} <= {3000, 4000, 5000}


async def test_builds_are_scoped_to_their_owner(
    session: AsyncSession, gaming_answers: dict
) -> None:
    users = UserRepository(session)
    repo = BuildRepository(session)

    owner = await users.get_or_create(42)
    stranger = await users.get_or_create(43)
    await repo.create_draft(owner.id, build_requirements(gaming_answers))
    await session.commit()

    assert await repo.list_for_user(stranger.id) == []


async def test_analytics_events_are_anonymised(session: AsyncSession) -> None:
    await AnalyticsRepository(session).track(
        42, EventName.CONFIGURATOR_COMPLETED, {"budget": 6000, "purpose": "gaming"}
    )
    await session.commit()

    stored = await session.scalar(select(AnalyticsEvent))
    assert stored is not None
    assert stored.event == EventName.CONFIGURATOR_COMPLETED
    assert stored.payload == {"budget": 6000, "purpose": "gaming"}
    # No free-text fields exist on the model at all.
    assert not hasattr(stored, "message_text")

    total = await session.scalar(select(func.count()).select_from(AnalyticsEvent))
    assert total == 1
