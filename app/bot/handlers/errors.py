"""Global error handling.

Users see a short, friendly message; the full traceback goes to the developer
log only. Nothing from the exception text is ever forwarded to Telegram.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, ErrorEvent, Message

from app.bot.keyboards.common import back_to_menu_kb
from app.i18n import DEFAULT_LANGUAGE, normalize_language, t

logger = logging.getLogger(__name__)

router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    logger.exception(
        "Unhandled error while processing update %s",
        event.update.update_id,
        exc_info=event.exception,
    )

    lang = DEFAULT_LANGUAGE
    user = event.update.event.from_user if hasattr(event.update.event, "from_user") else None
    if user is not None:
        lang = normalize_language(user.language_code)

    text = t(lang, "common.error")
    try:
        inner = event.update.event
        if isinstance(inner, CallbackQuery):
            await inner.answer(text, show_alert=True)
        elif isinstance(inner, Message):
            await inner.answer(text, reply_markup=back_to_menu_kb(lang))
    except TelegramAPIError:
        logger.warning("Could not deliver the error notice to the user")

    # Returning True marks the error as handled so polling continues.
    return True
