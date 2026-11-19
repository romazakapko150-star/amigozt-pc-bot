"""Visual presets, the picker keyboard, and the visualisation handler."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey

from app.bot.callbacks import VisualCB
from app.bot.handlers.visual import Kind, picker_keyboard, visual_button
from app.bot.middlewares import ThrottlingMiddleware
from app.db.models import Base, ReadyBuild, ReadyBuildStatus
from app.domain.components import ComponentCategory
from app.domain.enums import Aesthetics
from app.services.catalog import get_catalog
from app.services.media import (
    PRESETS,
    PRESETS_BY_KEY,
    Accent,
    CaseFinish,
    Style,
    VisualPreset,
    cache_key,
    default_preset,
    parse_preset,
    render_build_image,
    with_accent,
    with_style,
)
from tests.fake_telegram import CHAT_ID, USER_ID, RecordingSession, callback_update, make_bot

TELEGRAM_CALLBACK_LIMIT = 64
C = ComponentCategory


@pytest.fixture(scope="module")
def catalog():  # type: ignore[no-untyped-def]
    return get_catalog()


@pytest.fixture(scope="module")
def black_rgb(catalog):  # type: ignore[no-untyped-def]
    return {
        C.CPU: catalog.require("amd-ryzen-7-7800x3d"),
        C.GPU: catalog.require("amd-rx-9070-xt"),
        C.MOTHERBOARD: catalog.require("asus-tuf-b650-plus-wifi"),
        C.RAM: catalog.require("corsair-vengeance-rgb-32-ddr5-6000"),
        C.SSD: catalog.require("wd-black-sn850x-2tb"),
        C.PSU: catalog.require("corsair-rm750e"),
        C.CASE: catalog.require("lianli-lancool-216-black"),
        C.COOLER: catalog.require("arctic-liquid-freezer-iii-360"),
    }


@pytest.fixture(scope="module")
def white_plain(catalog, black_rgb):  # type: ignore[no-untyped-def]
    parts = dict(black_rgb)
    parts[C.CASE] = catalog.require("fractal-north-white")
    parts[C.RAM] = catalog.require("kingston-fury-beast-32-ddr5-6000")
    parts[C.COOLER] = catalog.require("thermalright-peerless-assassin-120-white")
    return parts


# --- registry -----------------------------------------------------------------


def test_registry_is_large_and_distinct() -> None:
    assert len(PRESETS) >= 40
    assert len({preset.key for preset in PRESETS}) == len(PRESETS)


def test_registry_covers_every_finish_accent_and_style() -> None:
    assert {p.finish for p in PRESETS} == set(CaseFinish)
    assert {p.accent for p in PRESETS} == set(Accent)
    assert {p.style for p in PRESETS} == set(Style)


def test_parse_round_trips_every_key() -> None:
    for preset in PRESETS:
        assert parse_preset(preset.key) == preset
    assert parse_preset("") is None
    assert parse_preset("not-a-preset") is None
    assert PRESETS_BY_KEY[PRESETS[0].key] is PRESETS[0]


def test_with_accent_and_style_keep_the_rest() -> None:
    base = VisualPreset(CaseFinish.BLACK, Accent.RED, Style.GAMING)
    assert with_accent(base, Accent.CYAN) == VisualPreset(
        CaseFinish.BLACK, Accent.CYAN, Style.GAMING
    )
    assert with_style(base, Style.MINIMAL) == VisualPreset(
        CaseFinish.BLACK, Accent.RED, Style.MINIMAL
    )


# --- defaults follow the real parts -----------------------------------------


def test_white_case_gets_a_white_finish(white_plain) -> None:  # type: ignore[no-untyped-def]
    assert default_preset(white_plain).finish is CaseFinish.WHITE


def test_rgb_parts_default_to_rainbow(black_rgb) -> None:  # type: ignore[no-untyped-def]
    assert default_preset(black_rgb).accent is Accent.RAINBOW


def test_plain_parts_do_not_get_rgb(white_plain) -> None:  # type: ignore[no-untyped-def]
    preset = default_preset(white_plain)
    assert preset.accent is not Accent.RAINBOW


def test_white_on_white_is_avoided(white_plain) -> None:  # type: ignore[no-untyped-def]
    """A white accent vanishes inside a white case."""
    preset = default_preset(white_plain)
    assert not (preset.finish is CaseFinish.WHITE and preset.accent is Accent.WHITE)


def test_minimal_request_turns_the_lights_down(black_rgb) -> None:  # type: ignore[no-untyped-def]
    assert default_preset(black_rgb, Aesthetics.MINIMAL).style is Style.MINIMAL
    assert default_preset(black_rgb, Aesthetics.GAMING).style is Style.GAMING


def test_the_case_wins_over_the_stated_aesthetic(white_plain) -> None:  # type: ignore[no-untyped-def]
    """The drawing must show the case the customer is actually getting."""
    assert default_preset(white_plain, Aesthetics.BLACK).finish is CaseFinish.WHITE


# --- rendering ----------------------------------------------------------------


def test_every_preset_renders(tmp_path: Path, black_rgb) -> None:  # type: ignore[no-untyped-def]
    for preset in PRESETS:
        path = render_build_image("P", black_rgb, Decimal(1), preset=preset, output_dir=tmp_path)
        assert path.exists() and path.stat().st_size > 5000


def test_presets_produce_different_images(tmp_path: Path, black_rgb) -> None:  # type: ignore[no-untyped-def]
    red = render_build_image(
        "P", black_rgb, Decimal(1), preset=PRESETS_BY_KEY["black-red-gaming"], output_dir=tmp_path
    )
    blue = render_build_image(
        "P", black_rgb, Decimal(1), preset=PRESETS_BY_KEY["black-blue-gaming"], output_dir=tmp_path
    )
    assert red != blue
    assert red.read_bytes() != blue.read_bytes()


def test_cache_key_includes_the_preset(black_rgb) -> None:  # type: ignore[no-untyped-def]
    a = cache_key("T", black_rgb, Decimal(1), PRESETS[0])
    b = cache_key("T", black_rgb, Decimal(1), PRESETS[1])
    assert a != b


# --- keyboard -----------------------------------------------------------------


def test_picker_callbacks_fit_telegram() -> None:
    preset = PRESETS_BY_KEY["white-purple-gaming"]
    markup = picker_keyboard(Kind.READY, 9_999_999, preset, "ru")
    for row in markup.inline_keyboard:
        for button in row:
            assert len(button.callback_data.encode()) <= TELEGRAM_CALLBACK_LIMIT


def test_picker_offers_every_accent_and_both_styles() -> None:
    preset = PRESETS[0]
    markup = picker_keyboard(Kind.BUILD, 1, preset, "en")
    payloads = [
        VisualCB.unpack(b.callback_data)
        for row in markup.inline_keyboard
        for b in row
        if b.callback_data and b.callback_data.startswith("v:")
    ]
    accents = {parse_preset(p.preset).accent for p in payloads}  # type: ignore[union-attr]
    styles = {parse_preset(p.preset).style for p in payloads}  # type: ignore[union-attr]
    assert accents == set(Accent)
    assert styles == set(Style)


def test_picker_marks_the_current_choice() -> None:
    preset = PRESETS_BY_KEY["black-green-minimal"]
    labels = [
        b.text for row in picker_keyboard(Kind.BUILD, 1, preset, "ru").inline_keyboard for b in row
    ]
    assert any(label.startswith("• ") and "Зелёный" in label for label in labels)
    assert any(label.startswith("• ") and "Minimal" in label for label in labels)


def test_entry_buttons_differ_by_scenario() -> None:
    build = visual_button(Kind.BUILD, 5, "ru")
    ready = visual_button(Kind.READY, 5, "ru")
    assert build.text != ready.text
    assert VisualCB.unpack(build.callback_data).kind == Kind.BUILD  # type: ignore[arg-type]
    assert VisualCB.unpack(ready.callback_data).kind == Kind.READY  # type: ignore[arg-type]


# --- handler, end to end ------------------------------------------------------


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


async def _shelf_entry(bot_session_factory, components: dict) -> int:  # type: ignore[no-untyped-def]
    async with bot_session_factory() as db:
        row = ReadyBuild(
            slug=f"visual-test-{uuid.uuid4().hex[:8]}",
            name="AmigoZT Visual Test",
            category="gaming",
            tags=[],
            purpose="gaming",
            resolution="1440p",
            tier="optimal",
            budget_min_pln=6000,
            budget_max_pln=8000,
            cpu_brand="any",
            gpu_brand="any",
            style="white_rgb",
            components=components,
            reference_price_pln=Decimal(7499),
            status=ReadyBuildStatus.ACTIVE,
        )
        db.add(row)
        await db.commit()
        return int(row.id)


async def test_ready_build_visual_sends_a_photo_with_the_picker(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory, black_rgb
) -> None:  # type: ignore[no-untyped-def]
    build_id = await _shelf_entry(
        bot_session_factory, {c.value: p.id for c, p in black_rgb.items()}
    )
    session: RecordingSession = bot.session  # type: ignore[assignment]
    session.clear()

    await dispatcher.feed_update(
        bot,
        callback_update(
            VisualCB(kind=Kind.READY, id=build_id, preset="").pack(), update_id=901, bot=bot
        ),
    )

    photos = session.of_type("SendPhoto")
    assert photos, "no photo was sent"
    caption = str(getattr(photos[0], "caption", ""))
    assert "AmigoZT Visual Test" in caption
    assert "не фото" in caption
    markup = getattr(photos[0], "reply_markup", None)
    assert markup is not None
    assert any("🌈" in b.text for row in markup.inline_keyboard for b in row)


async def test_recolour_uses_the_requested_preset(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory, black_rgb
) -> None:  # type: ignore[no-untyped-def]
    build_id = await _shelf_entry(
        bot_session_factory, {c.value: p.id for c, p in black_rgb.items()}
    )
    session: RecordingSession = bot.session  # type: ignore[assignment]
    session.clear()

    await dispatcher.feed_update(
        bot,
        callback_update(
            VisualCB(kind=Kind.READY, id=build_id, preset="black-red-minimal").pack(),
            update_id=902,
            bot=bot,
        ),
    )

    photos = session.of_type("SendPhoto")
    assert photos
    markup = getattr(photos[0], "reply_markup", None)
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert any(label.startswith("• ") and "Красный" in label for label in labels)
    assert any(label.startswith("• ") and "Minimal" in label for label in labels)


async def test_unknown_build_is_rejected_politely(bot: Bot, dispatcher: Dispatcher) -> None:
    session: RecordingSession = bot.session  # type: ignore[assignment]
    session.clear()
    await dispatcher.feed_update(
        bot,
        callback_update(
            VisualCB(kind=Kind.READY, id=424242, preset="").pack(), update_id=903, bot=bot
        ),
    )
    assert not session.of_type("SendPhoto")
    answers = session.of_type("AnswerCallbackQuery")
    assert answers and getattr(answers[-1], "show_alert", False)
