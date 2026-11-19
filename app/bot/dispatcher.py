from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.handlers import build_router
from app.bot.middlewares import DbSessionMiddleware, ThrottlingMiddleware, UserMiddleware
from app.config import Settings
from app.i18n import LOCALES, t

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    """Telegram client. The token is read from settings and never logged."""
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> Dispatcher:
    # MemoryStorage is fine for a single-process MVP; swapping in RedisStorage
    # is a one-line change once the bot runs on more than one worker.
    dispatcher = Dispatcher(storage=MemoryStorage())

    # Outer middlewares run once per update, before filters are evaluated,
    # so throttling rejects floods before any database work happens.
    dispatcher.update.outer_middleware(ThrottlingMiddleware(rate=settings.rate_limit_per_second))
    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    dispatcher.update.outer_middleware(UserMiddleware())

    # Available to every handler and filter as a `settings` argument
    # (IsAdmin reads ADMIN_TELEGRAM_IDS from it).
    dispatcher["settings"] = settings

    dispatcher.include_router(build_router())
    return dispatcher


async def set_bot_commands(bot: Bot) -> None:
    """Publishes the command list shown in Telegram's menu, per language."""
    commands = [
        ("start", "menu.build"),
        ("build", "menu.build"),
        ("budget", "menu.budget"),
        ("mybuilds", "menu.mybuilds"),
        ("language", "menu.language"),
        ("help", "menu.help"),
    ]

    for language in LOCALES:
        await bot.set_my_commands(
            [
                BotCommand(command=command, description=_strip_emoji(t(language, key)))
                for command, key in commands
            ],
            scope=BotCommandScopeDefault(),
            language_code=language,
        )


async def set_bot_profile(bot: Bot) -> None:
    """Fill in the description an empty chat shows, and the profile bio.

    Telegram rejects an update that would not change anything, and neither
    field is worth failing a startup over, so both are attempted per
    language and a refusal is logged and stepped over.
    """
    for language in LOCALES:
        for setter, key in (
            (bot.set_my_description, "bot.description"),
            (bot.set_my_short_description, "bot.short_description"),
        ):
            try:
                await setter(t(language, key), language_code=language)
            except TelegramAPIError as exc:
                logger.debug("Could not set %s for %s: %s", key, language, exc)

    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except TelegramAPIError as exc:
        logger.debug("Could not set the menu button: %s", exc)


def _strip_emoji(text: str) -> str:
    """Telegram command descriptions must be plain text, 1-256 chars."""
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch in " -/,.").strip()
    return cleaned[:256] or "AmigoZT PC"
