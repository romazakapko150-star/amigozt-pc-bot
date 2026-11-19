from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from aiogram.types import User as TgUser

from app.i18n import normalize_language, t

MAX_TRACKED_USERS = 20_000


class ThrottlingMiddleware(BaseMiddleware):
    """Per-user token bucket.

    Protects the bot (and the database) from button spam and from scripted
    flooding. ``burst`` allows a short run of fast taps - real users double-tap
    buttons all the time - while ``rate`` caps the sustained throughput.
    """

    def __init__(self, rate: float = 1.5, burst: int = 8) -> None:
        self._rate = rate
        self._burst = float(burst)
        self._buckets: dict[int, tuple[float, float]] = {}

    def _allow(self, user_id: int, now: float) -> bool:
        tokens, last_seen = self._buckets.get(user_id, (self._burst, now))
        tokens = min(self._burst, tokens + (now - last_seen) * self._rate)

        if tokens < 1.0:
            self._buckets[user_id] = (tokens, now)
            return False

        self._buckets[user_id] = (tokens - 1.0, now)
        return True

    def reset(self, user_id: int | None = None) -> None:
        """Forget rate-limit history, for one user or for everyone."""
        if user_id is None:
            self._buckets.clear()
        else:
            self._buckets.pop(user_id, None)

    def _prune(self, now: float) -> None:
        if len(self._buckets) <= MAX_TRACKED_USERS:
            return
        cutoff = now - 300
        self._buckets = {uid: state for uid, state in self._buckets.items() if state[1] > cutoff}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        now = time.monotonic()
        self._prune(now)

        if self._allow(tg_user.id, now):
            return await handler(event, data)

        # Tell the user why nothing happened, but only for taps: silently
        # dropping spammed text messages avoids an echo loop.
        inner = getattr(event, "event", event)
        if isinstance(inner, CallbackQuery):
            lang = normalize_language(tg_user.language_code)
            await inner.answer(t(lang, "common.rate_limited"), show_alert=False)
        return None
