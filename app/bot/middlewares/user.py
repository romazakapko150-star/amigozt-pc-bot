from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import UserRepository
from app.i18n import DEFAULT_LANGUAGE, normalize_language


class UserMiddleware(BaseMiddleware):
    """Resolves the domain user and the active interface language.

    Injects ``user`` (ORM object) and ``lang`` (str) into the handler context.
    The stored language always wins over Telegram's ``language_code`` so that
    an explicit choice made via /language is never overwritten.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        session: AsyncSession | None = data.get("session")

        if tg_user is None or tg_user.is_bot or session is None:
            data.setdefault("lang", DEFAULT_LANGUAGE)
            return await handler(event, data)

        repo = UserRepository(session)
        existing = await repo.get_by_telegram_id(tg_user.id)
        language = (
            existing.language if existing is not None else normalize_language(tg_user.language_code)
        )

        user = await repo.get_or_create(
            tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            language=language,
        )

        data["user"] = user
        data["lang"] = user.language
        return await handler(event, data)
