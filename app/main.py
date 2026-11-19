"""Entry point: ``python -m app.main``."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot.dispatcher import (
    create_bot,
    create_dispatcher,
    set_bot_commands,
    set_bot_profile,
)
from app.config import Settings, get_settings
from app.db.session import create_engine, create_session_factory
from app.logging_setup import setup_logging

logger = logging.getLogger(__name__)


async def _shutdown(bot: Bot, dispatcher: Dispatcher, engine: object) -> None:
    await dispatcher.storage.close()
    await bot.session.close()
    dispose = getattr(engine, "dispose", None)
    if dispose is not None:
        await dispose()


async def run() -> None:
    settings: Settings = get_settings()
    setup_logging(settings.log_level, secrets=[settings.bot_token])

    logger.info("Starting AmigoZT PC bot (environment=%s)", settings.environment)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings, session_factory)

    me = await bot.get_me()
    logger.info("Connected to Telegram as @%s (id=%s)", me.username, me.id)

    await set_bot_commands(bot)
    await set_bot_profile(bot)

    try:
        # Updates queued while the bot was offline. Dropping them is the
        # default (a tap on a keyboard that has since changed would reach the
        # wrong handler); DROP_PENDING_UPDATES=false answers the backlog
        # instead, which is what you want after planned downtime.
        if settings.drop_pending_updates:
            logger.info("Dropping updates queued while the bot was offline")
        else:
            logger.info("Keeping the queued updates: the backlog will be answered")
        await bot.delete_webhook(drop_pending_updates=settings.drop_pending_updates)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await _shutdown(bot, dispatcher, engine)
        logger.info("Bot stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Shutdown requested")


if __name__ == "__main__":
    main()
