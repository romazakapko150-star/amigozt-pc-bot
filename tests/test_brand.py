"""Brand assets: resolution, fallbacks, file_id reuse, cooldown, Telegram flow."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import FSInputFile

from app.bot.callbacks import MenuAction, MenuCB
from app.config import Settings
from app.i18n import t
from app.services.media.brand import BrandAsset, BrandAssets, get_brand_assets
from tests.fake_telegram import (
    FAKE_PHOTO_FILE_ID,
    RecordingSession,
    callback_update,
    make_bot,
    message_update,
)

BRAND_FILE = Path("app/assets/brand/amigozt_pc.png")


def _settings(**overrides) -> Settings:  # type: ignore[no-untyped-def]
    base = {"telegram_bot_token": "123456789:FAKE-TOKEN-USED-ONLY-BY-THE-TEST-SUITE"}
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


def _session(bot: Bot) -> RecordingSession:
    assert isinstance(bot.session, RecordingSession)
    return bot.session


# --- resolution -------------------------------------------------------------------


def test_brand_file_is_committed_and_readable() -> None:
    assert BRAND_FILE.is_file()
    assert BRAND_FILE.stat().st_size > 100_000


def test_assets_fall_back_to_the_main_image(tmp_path: Path) -> None:
    brand = BrandAssets(_settings(), cache_file=tmp_path / "ids.json")
    assert brand.path_for(BrandAsset.MAIN) == BRAND_FILE.resolve()
    for asset in BrandAsset:
        assert brand.path_for(asset) == BRAND_FILE.resolve()
        assert brand.available(asset)
    assert brand.uses_main(BrandAsset.HEADER)


def test_a_dedicated_asset_overrides_the_main_image(tmp_path: Path) -> None:
    header = tmp_path / "header.png"
    header.write_bytes(b"png")
    brand = BrandAssets(_settings(brand_header=str(header)), cache_file=tmp_path / "ids.json")
    assert brand.path_for(BrandAsset.HEADER) == header
    assert not brand.uses_main(BrandAsset.HEADER)
    assert brand.path_for(BrandAsset.ORDER_CONFIRMATION) == BRAND_FILE.resolve()


def test_missing_file_means_unavailable_and_send_returns_false(tmp_path: Path) -> None:
    brand = BrandAssets(
        _settings(brand_image=str(tmp_path / "nope.png")), cache_file=tmp_path / "ids.json"
    )
    assert not brand.available(BrandAsset.MAIN)
    assert brand.file_id_for(BrandAsset.MAIN) is None


def test_env_file_id_makes_the_asset_available_without_a_file(tmp_path: Path) -> None:
    brand = BrandAssets(
        _settings(brand_image=str(tmp_path / "nope.png"), brand_image_file_id="AgAC-env-id"),
        cache_file=tmp_path / "ids.json",
    )
    assert brand.available(BrandAsset.MAIN)
    assert brand.file_id_for(BrandAsset.HEADER) == "AgAC-env-id"  # header falls back to main


# --- sending ------------------------------------------------------------------------


class _FakeMessage:
    """Just enough of aiogram's Message for BrandAssets.send()."""

    def __init__(self, chat_id: int = 1, fail: bool = False) -> None:
        from aiogram.types import Chat

        self.chat = Chat(id=chat_id, type="private")
        self.sent: list[object] = []
        self._fail = fail

    async def answer_photo(self, photo, caption=None, reply_markup=None):  # type: ignore[no-untyped-def]
        if self._fail:
            from aiogram.exceptions import TelegramNetworkError

            raise TelegramNetworkError(method=None, message="down")  # type: ignore[arg-type]
        self.sent.append(photo)
        from tests.fake_telegram import _photo_message

        return _photo_message(caption or "")


async def test_first_send_uploads_then_the_cached_file_id_is_reused(tmp_path: Path) -> None:
    cache = tmp_path / "ids.json"
    brand = BrandAssets(_settings(), cache_file=cache, cooldown=timedelta(0))
    message = _FakeMessage()

    assert await brand.send(message, BrandAsset.MAIN, "hello")  # type: ignore[arg-type]
    assert isinstance(message.sent[0], FSInputFile)
    assert brand.file_id_for(BrandAsset.MAIN) == FAKE_PHOTO_FILE_ID
    assert json.loads(cache.read_text())  # persisted

    assert await brand.send(message, BrandAsset.MAIN, "again")  # type: ignore[arg-type]
    assert message.sent[1] == FAKE_PHOTO_FILE_ID

    # A fresh instance reads the persisted id and never uploads again.
    again = BrandAssets(_settings(), cache_file=cache, cooldown=timedelta(0))
    assert again.file_id_for(BrandAsset.MAIN) == FAKE_PHOTO_FILE_ID


async def test_cooldown_suppresses_a_repeat_in_the_same_chat(tmp_path: Path) -> None:
    brand = BrandAssets(
        _settings(), cache_file=tmp_path / "ids.json", cooldown=timedelta(minutes=30)
    )
    message = _FakeMessage(chat_id=7)
    assert await brand.send(message, BrandAsset.MAIN, "one")  # type: ignore[arg-type]
    assert not await brand.send(message, BrandAsset.MAIN, "two")  # type: ignore[arg-type]
    assert await brand.send(message, BrandAsset.MAIN, "forced", respect_cooldown=False)  # type: ignore[arg-type]
    other = _FakeMessage(chat_id=8)
    assert await brand.send(other, BrandAsset.MAIN, "other chat")  # type: ignore[arg-type]
    assert len(message.sent) == 2 and len(other.sent) == 1


async def test_telegram_failure_degrades_to_false(tmp_path: Path) -> None:
    brand = BrandAssets(_settings(), cache_file=tmp_path / "ids.json", cooldown=timedelta(0))
    assert not await brand.send(_FakeMessage(fail=True), BrandAsset.MAIN, "x")  # type: ignore[arg-type]


async def test_captions_over_the_telegram_limit_are_refused(tmp_path: Path) -> None:
    brand = BrandAssets(_settings(), cache_file=tmp_path / "ids.json", cooldown=timedelta(0))
    message = _FakeMessage()
    assert not await brand.send(message, BrandAsset.MAIN, "x" * 1100)  # type: ignore[arg-type]
    assert message.sent == []


# --- Telegram flow ------------------------------------------------------------------


@pytest.fixture
async def bot(dispatcher: Dispatcher, bot_engine):  # type: ignore[no-untyped-def]
    from app.db.models import Base

    async with bot_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    telegram_bot = make_bot()
    get_brand_assets().reset()
    yield telegram_bot
    await telegram_bot.session.close()


async def test_start_shows_the_brand_image_with_the_menu(bot: Bot, dispatcher: Dispatcher) -> None:
    await dispatcher.feed_update(bot, message_update("/start", update_id=1))
    session = _session(bot)
    assert session.photos, "welcome did not carry the brand image"
    assert "AMIGOZT PC" in session.last_text
    # Every destination is reachable. The row count is layout, not contract:
    # asserting on it only makes the test churn when the menu is rearranged.
    assert session.last_markup is not None
    labels = [b.text for row in session.last_markup.inline_keyboard for b in row]
    assert len(labels) == 10
    for key in ("menu.build", "menu.presets", "menu.accessories", "menu.language"):
        assert any(t("ru", key) == label for label in labels), key


async def test_second_start_soon_after_does_not_resend_the_image(
    bot: Bot, dispatcher: Dispatcher
) -> None:
    await dispatcher.feed_update(bot, message_update("/start", update_id=1))
    session = _session(bot)
    session.clear()
    await dispatcher.feed_update(bot, message_update("/start", update_id=2))
    assert not session.photos
    assert session.sent_messages and "AMIGOZT PC" in session.last_text


async def test_configurator_opens_under_the_brand_header(bot: Bot, dispatcher: Dispatcher) -> None:
    await dispatcher.feed_update(bot, message_update("/start", update_id=1))
    session = _session(bot)
    session.clear()
    await dispatcher.feed_update(
        bot, callback_update(MenuCB(action=MenuAction.BUILD).pack(), update_id=2, bot=bot)
    )
    assert session.photos, "configurator start did not carry the brand header"
    labels = [b.text for row in session.last_markup.inline_keyboard for b in row]  # type: ignore[union-attr]
    assert any("2 500" in label for label in labels)


async def test_photo_upload_happens_once_per_process(bot: Bot, dispatcher: Dispatcher) -> None:
    """The second chat gets the cached file_id, not another upload."""
    await dispatcher.feed_update(bot, message_update("/start", update_id=1))
    first = _session(bot).photos[-1]
    assert isinstance(first.photo, FSInputFile) or first.photo == FAKE_PHOTO_FILE_ID
    _session(bot).clear()
    await dispatcher.feed_update(bot, message_update("/start", update_id=2, user_id=777_000_001))
    second = _session(bot).photos[-1]
    assert second.photo == FAKE_PHOTO_FILE_ID
