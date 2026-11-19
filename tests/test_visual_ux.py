"""AI visualisation in the Telegram flow: ready builds, custom builds, failures, admin."""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import FSInputFile

from app.bot.callbacks import VALUE_GENERATE, ReadyCB
from app.bot.flows.configurator import StepId
from app.bot.handlers.ready_builds import Action
from app.bot.middlewares import ThrottlingMiddleware
from app.db.models import Base, ReadyBuild, ReadyBuildStatus
from app.domain.components import ComponentCategory
from app.services.ai import Visualizer
from app.services.catalog import get_catalog
from tests.fake_telegram import (
    ADMIN_USER_ID,
    CHAT_ID,
    FAKE_PHOTO_FILE_ID,
    USER_ID,
    RecordingSession,
    callback_update,
    make_bot,
    message_update,
)
from tests.test_e2e_configurator import Walker, _walk_to_cpu_step
from tests.test_visualizer import FakeGenerator

C = ComponentCategory


@pytest.fixture
def generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture
def fake_visualizer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, generator: FakeGenerator):  # type: ignore[no-untyped-def]
    visualizer = Visualizer(generator, output_dir=tmp_path, model="gpt-image-1")
    visualizer.MIN_INTERVAL_SECONDS = 0.0
    Visualizer._lock = None
    monkeypatch.setattr("app.bot.handlers.visual.get_visualizer", lambda settings=None: visualizer)
    return visualizer


@pytest_asyncio.fixture
async def bot(dispatcher: Dispatcher, bot_engine) -> AsyncIterator[Bot]:  # type: ignore[no-untyped-def]
    async with bot_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    telegram_bot = make_bot()
    for middleware in dispatcher.update.outer_middleware:
        if isinstance(middleware, ThrottlingMiddleware):
            middleware.reset()
    key = StorageKey(bot_id=telegram_bot.id, chat_id=CHAT_ID, user_id=USER_ID)
    await dispatcher.storage.set_state(key, None)
    await dispatcher.storage.set_data(key, {})
    yield telegram_bot
    await telegram_bot.session.close()


def _session(bot: Bot) -> RecordingSession:
    assert isinstance(bot.session, RecordingSession)
    return bot.session


def _labels(markup) -> list[str]:  # type: ignore[no-untyped-def]
    return [b.text for row in markup.inline_keyboard for b in row] if markup else []


async def _shelf_entry(
    bot_session_factory, *, style: str = "black_rgb", ram: str = "kingston-fury-beast-32-ddr5-6000"
) -> int:  # type: ignore[no-untyped-def]
    """A shelf entry; ``style`` / ``ram`` vary the visual fingerprint per test,
    because the test database is shared across the module."""
    catalog = get_catalog()
    components = {
        "cpu": "amd-ryzen-7-7800x3d",
        "motherboard": "asus-tuf-b650-plus-wifi",
        "ram": ram,
        "ssd": "samsung-990-evo-1tb",
        "gpu": "amd-rx-9070",
        "cooler": "thermalright-peerless-assassin-120-se",
        "case": "lianli-lancool-216-black",
        "psu": "corsair-rm750e",
    }
    assert all(catalog.get(cid) for cid in components.values())
    async with bot_session_factory() as db:
        row = ReadyBuild(
            slug=f"ux-test-{uuid.uuid4().hex[:8]}",
            name="AmigoZT UX Test",
            category="gaming",
            tags=[],
            purpose="gaming",
            resolution="1440p",
            tier="optimal",
            budget_min_pln=6000,
            budget_max_pln=8000,
            cpu_brand="any",
            gpu_brand="any",
            style=style,
            components=components,
            reference_price_pln=Decimal(7499),
            status=ReadyBuildStatus.ACTIVE,
        )
        db.add(row)
        await db.commit()
        return int(row.id)


async def _open(bot: Bot, dispatcher: Dispatcher, build_id: int, update_id: int) -> None:
    await dispatcher.feed_update(
        bot,
        callback_update(
            ReadyCB(action=Action.OPEN, value=str(build_id), page=0).pack(),
            update_id=update_id,
            bot=bot,
        ),
    )


# --- ready builds ---------------------------------------------------------------------


async def test_ready_build_card_is_the_ai_render_with_the_order_button(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory, fake_visualizer, generator
) -> None:  # type: ignore[no-untyped-def]
    build_id = await _shelf_entry(bot_session_factory)
    session = _session(bot)
    session.clear()

    await _open(bot, dispatcher, build_id, 701)

    photos = session.photos
    assert len(photos) == 1, "expected exactly one photo: the AI render"
    assert isinstance(photos[0].photo, FSInputFile)  # first time: upload
    caption = str(getattr(photos[0], "caption", ""))
    assert "AmigoZT UX Test" in caption and "AI" in caption
    labels = _labels(getattr(photos[0], "reply_markup", None))
    assert any("🛒" in label for label in labels)
    assert len(generator.calls) == 1
    # The status line was shown while generating and then removed.
    assert any("🎨" in str(getattr(c, "text", "")) for c in session.sent_messages)
    assert session.of_type("DeleteMessage")


async def test_opening_the_same_build_again_is_a_cache_hit_with_file_id(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory, fake_visualizer, generator
) -> None:  # type: ignore[no-untyped-def]
    build_id = await _shelf_entry(bot_session_factory, style="minimal")
    await _open(bot, dispatcher, build_id, 702)
    assert len(generator.calls) == 1
    session = _session(bot)
    session.clear()

    await _open(bot, dispatcher, build_id, 703)

    assert len(generator.calls) == 1, "a second open must not pay for a second render"
    photos = session.photos
    assert len(photos) == 1
    assert photos[0].photo == FAKE_PHOTO_FILE_ID  # reused Telegram file_id, no upload
    assert not any("🎨" in str(getattr(c, "text", "")) for c in session.sent_messages)


async def test_failed_render_falls_back_to_the_schematic_and_keeps_ordering(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory, monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    broken = FakeGenerator(payload=None, error="InternalServerError: boom")
    visualizer = Visualizer(broken, output_dir=tmp_path, max_attempts=1)
    visualizer.MIN_INTERVAL_SECONDS = 0.0
    monkeypatch.setattr("app.bot.handlers.visual.get_visualizer", lambda settings=None: visualizer)
    build_id = await _shelf_entry(bot_session_factory, ram="corsair-vengeance-64-ddr5-6000")
    session = _session(bot)
    session.clear()

    await _open(bot, dispatcher, build_id, 704)

    photos = session.photos
    assert len(photos) == 1 and isinstance(photos[0].photo, FSInputFile)  # the schematic
    caption = str(getattr(photos[0], "caption", ""))
    assert "AmigoZT UX Test" in caption
    assert any("🛒" in label for label in _labels(getattr(photos[0], "reply_markup", None)))
    edits = session.of_type("EditMessageText")
    assert any("недоступна" in str(getattr(e, "text", "")) for e in edits)


async def test_ai_off_means_no_status_message_and_the_schematic(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory
) -> None:  # type: ignore[no-untyped-def]
    build_id = await _shelf_entry(bot_session_factory)
    session = _session(bot)
    session.clear()
    await _open(bot, dispatcher, build_id, 705)
    assert len(session.photos) == 1
    assert not any("🎨" in str(getattr(c, "text", "")) for c in session.sent_messages)


# --- custom builds ----------------------------------------------------------------------


async def test_custom_build_gets_its_visualization_before_ordering(
    bot: Bot, dispatcher: Dispatcher, fake_visualizer, generator
) -> None:  # type: ignore[no-untyped-def]
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)
    await walker.tap(StepId.CPU, "amd")
    await walker.tap(StepId.GPU, "any")
    await walker.skip_the_desk()

    session = _session(bot)
    session.clear()
    await walker.tap(StepId.SUMMARY, VALUE_GENERATE)

    photos = session.photos
    assert len(photos) == 2, "expected the build card and then the AI render"
    ai_caption = str(getattr(photos[1], "caption", ""))
    assert "AI" in ai_caption and "PLN" in ai_caption
    labels = _labels(getattr(photos[1], "reply_markup", None))
    assert any("🛒" in label for label in labels) and any("🔄" in label for label in labels)
    assert len(generator.calls) >= 1


# --- admin ----------------------------------------------------------------------------------


async def test_admin_sees_the_visualization_store(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory, fake_visualizer
) -> None:  # type: ignore[no-untyped-def]
    import os

    os.environ["ADMIN_TELEGRAM_IDS"] = str(ADMIN_USER_ID)
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        build_id = await _shelf_entry(bot_session_factory)
        await _open(bot, dispatcher, build_id, 901)
        session = _session(bot)
        session.clear()
        await dispatcher.feed_update(
            bot, message_update("/visuals", update_id=902, user_id=ADMIN_USER_ID)
        )
        text = session.last_text
        assert "Visual Library" in text
        ready = re.search(r"VISUALS EXISTING: <b>(\d+)</b>", text)
        assert ready is not None and int(ready.group(1)) >= 1
        assert "включён" in text
        # the per-type breakdown of what the library holds; other tests in
        # this process may have stored component visuals too, so only the
        # shelf entry is asserted on
        assert "библиотеке:" in text
        assert re.search(r"полка (\d+)✅", text) is not None
    finally:
        os.environ["ADMIN_TELEGRAM_IDS"] = ""
        get_settings.cache_clear()
