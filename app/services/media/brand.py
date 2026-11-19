"""Brand assets: the official AmigoZT PC imagery and how it reaches Telegram.

One place knows where the images live, which Telegram ``file_id`` each was
last uploaded under, and when a chat last saw one - so handlers ask for
"the brand header" and never touch paths, uploads or repeat-suppression.

Rules the service enforces:

* the image file is never modified - it is sent as-is;
* after the first successful upload the returned ``file_id`` is reused
  (memory + a small JSON cache under ``media/``), keyed by the file's size
  and mtime so replacing the PNG invalidates the cached id automatically;
* ``BRAND_IMAGE_FILE_ID`` from the environment short-circuits uploads;
* the same asset is not re-sent to the same chat inside a cooldown window;
* a missing file or a Telegram error makes ``send()`` return ``False`` and
  the caller falls back to its plain-text message. Branding never blocks a
  customer.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

from app.config import Settings, get_settings
from app.services.media.paths import MEDIA_ROOT

logger = logging.getLogger(__name__)

#: Telegram truncates a photo caption past this.
MAX_CAPTION = 1024

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_FILE = MEDIA_ROOT / "brand_file_ids.json"


class BrandAsset(StrEnum):
    MAIN = "main"
    AVATAR = "avatar"
    HEADER = "header"
    BUILD_DEFAULT = "build_default"
    ORDER_CONFIRMATION = "order_confirmation"


class BrandAssets:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        cache_file: Path | None = DEFAULT_CACHE_FILE,
        cooldown: timedelta | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self._paths: dict[BrandAsset, Path | None] = {
            BrandAsset.MAIN: _resolve(cfg.brand_image),
            BrandAsset.AVATAR: _resolve(cfg.brand_avatar),
            BrandAsset.HEADER: _resolve(cfg.brand_header),
            BrandAsset.BUILD_DEFAULT: _resolve(cfg.brand_build_default),
            BrandAsset.ORDER_CONFIRMATION: _resolve(cfg.brand_order_confirmation),
        }
        self._env_file_id = (cfg.brand_image_file_id or "").strip() or None
        self._cooldown = (
            cooldown
            if cooldown is not None
            else timedelta(minutes=cfg.brand_resend_cooldown_minutes)
        )
        self._cache_file = cache_file
        self._file_ids: dict[str, str] = _load_cache(cache_file)
        self._last_sent: dict[tuple[int, BrandAsset], datetime] = {}

    # --- resolution -------------------------------------------------------

    def path_for(self, asset: BrandAsset) -> Path | None:
        """The asset's own file, or the main image when none is configured."""
        return self._paths.get(asset) or self._paths[BrandAsset.MAIN]

    def uses_main(self, asset: BrandAsset) -> bool:
        return self._paths.get(asset) is None

    def available(self, asset: BrandAsset) -> bool:
        if self.file_id_for(asset) is not None:
            return True
        path = self.path_for(asset)
        return path is not None and path.is_file()

    # --- file ids ---------------------------------------------------------

    def cache_key(self, asset: BrandAsset) -> str | None:
        path = self.path_for(asset)
        if path is None or not path.is_file():
            return None
        stat = path.stat()
        return f"{asset.value}:{stat.st_size}:{stat.st_mtime_ns}"

    def file_id_for(self, asset: BrandAsset) -> str | None:
        if self._env_file_id and (asset is BrandAsset.MAIN or self.uses_main(asset)):
            return self._env_file_id
        key = self.cache_key(asset)
        return self._file_ids.get(key) if key else None

    def remember_file_id(self, asset: BrandAsset, file_id: str) -> None:
        key = self.cache_key(asset)
        if key is None:
            return
        self._file_ids[key] = file_id
        _save_cache(self._cache_file, self._file_ids)

    def forget_file_id(self, asset: BrandAsset) -> None:
        key = self.cache_key(asset)
        if key and self._file_ids.pop(key, None) is not None:
            _save_cache(self._cache_file, self._file_ids)

    # --- repeat suppression -------------------------------------------------

    def should_send(self, chat_id: int, asset: BrandAsset) -> bool:
        last = self._last_sent.get((chat_id, asset))
        if last is None or self._cooldown <= timedelta(0):
            return True
        return datetime.now(UTC) - last >= self._cooldown

    def mark_sent(self, chat_id: int, asset: BrandAsset) -> None:
        self._last_sent[(chat_id, asset)] = datetime.now(UTC)

    def use_cache_file(self, cache_file: Path | None) -> None:
        """Point the id cache at another file - or at nothing.

        ``None`` isolates the process completely: no ids are read from disk
        and none are written back, so a test run neither inherits the real
        bot's Telegram ids nor writes its own into ``media/``.
        """
        self._cache_file = cache_file
        self._file_ids = _load_cache(cache_file)

    def reset(self) -> None:
        """Forget cooldowns and in-memory ids (tests, or after a rebrand)."""
        self._last_sent.clear()
        self._file_ids = _load_cache(self._cache_file)

    # --- sending ----------------------------------------------------------

    async def send(
        self,
        message: Message,
        asset: BrandAsset,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        *,
        respect_cooldown: bool = True,
    ) -> bool:
        """Send the asset as a photo with ``caption``. False = caller sends text."""
        if not self.available(asset) or len(caption) > MAX_CAPTION:
            return False
        chat_id = message.chat.id
        if respect_cooldown and not self.should_send(chat_id, asset):
            return False

        file_id = self.file_id_for(asset)
        sent = await self._send_photo(message, asset, file_id, caption, reply_markup)
        if sent is None and file_id is not None and file_id != self._env_file_id:
            # The cached id went stale (bot token rotated, file purged): upload again.
            self.forget_file_id(asset)
            sent = await self._send_photo(message, asset, None, caption, reply_markup)
        if sent is None:
            return False

        if file_id is None and sent.photo:
            self.remember_file_id(asset, sent.photo[-1].file_id)
        self.mark_sent(chat_id, asset)
        return True

    async def _send_photo(
        self,
        message: Message,
        asset: BrandAsset,
        file_id: str | None,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None,
    ) -> Message | None:
        try:
            if file_id is not None:
                return await message.answer_photo(
                    file_id, caption=caption, reply_markup=reply_markup
                )
            path = self.path_for(asset)
            if path is None:
                return None
            return await message.answer_photo(
                FSInputFile(path), caption=caption, reply_markup=reply_markup
            )
        except (TelegramAPIError, OSError):
            logger.exception("Could not send brand asset %s", asset.value)
            return None


def _resolve(raw: str | None) -> Path | None:
    value = (raw or "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_cache(cache_file: Path | None) -> dict[str, str]:
    if cache_file is None or not cache_file.is_file():
        return {}
    try:
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Unreadable brand file-id cache at %s, ignoring", cache_file)
        return {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _save_cache(cache_file: Path | None, data: dict[str, str]) -> None:
    if cache_file is None:
        return
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        logger.warning("Could not persist the brand file-id cache", exc_info=True)


@lru_cache(maxsize=1)
def get_brand_assets() -> BrandAssets:
    return BrandAssets()
