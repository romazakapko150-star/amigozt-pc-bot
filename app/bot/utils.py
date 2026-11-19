from __future__ import annotations

import contextlib
import logging
from pathlib import Path

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

logger = logging.getLogger(__name__)


async def safe_edit(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit the message behind a tapped button, falling back to a new message.

    Telegram rejects an edit when the content is byte-identical ("message is
    not modified"), which happens on double taps - that is not an error.
    """
    message = callback.message
    if not isinstance(message, Message):
        if callback.from_user is not None and callback.bot is not None:
            await callback.bot.send_message(callback.from_user.id, text, reply_markup=reply_markup)
        return

    try:
        if message.photo and len(text) <= MAX_CAPTION:
            # The conversation lives in a photo's caption (brand header, build
            # card): keep editing in place instead of stacking new messages.
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        logger.debug("edit failed (%s), sending a new message", exc)
        await message.answer(text, reply_markup=reply_markup)


#: Telegram truncates a photo caption past this; longer text is sent separately.
MAX_CAPTION = 1024


async def send_photo_card(
    message: Message,
    image: Path,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Send a rendered card as a photo, degrading to text if that fails.

    A missing font, a full disk or a Telegram upload error must never cost the
    customer the build they just configured - the text card still gets through.
    """
    fits = len(caption) <= MAX_CAPTION

    try:
        photo = FSInputFile(image)
        if fits:
            await message.answer_photo(photo, caption=caption, reply_markup=reply_markup)
        else:
            # Caption too long: photo first, then the full card as text.
            await message.answer_photo(photo)
            await message.answer(caption, reply_markup=reply_markup)
    except (TelegramAPIError, OSError):
        logger.exception("Could not send the build image; falling back to text")
        await message.answer(caption, reply_markup=reply_markup)


async def show_photo(
    callback: CallbackQuery,
    image: Path,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Put ``image`` on the message behind a tapped button.

    A photo message has its media swapped in place, so paging through a
    catalogue does not stack a new message per tap. A text message cannot be
    edited into a photo, so that one is replaced: the old text is deleted and
    the photo takes its place, which keeps the conversation to one card.
    """
    message = callback.message
    if not isinstance(message, Message):
        return

    fits = len(caption) <= MAX_CAPTION
    shown = caption if fits else caption[: MAX_CAPTION - 1] + "…"
    photo = FSInputFile(image)

    try:
        if message.photo:
            # The bot's default parse mode does not reach a media caption:
            # without this the customer reads the HTML tags themselves.
            await message.edit_media(
                InputMediaPhoto(media=photo, caption=shown, parse_mode=ParseMode.HTML),
                reply_markup=reply_markup,
            )
            return
        await message.answer_photo(photo, caption=shown, reply_markup=reply_markup)
        with contextlib.suppress(TelegramAPIError):
            await message.delete()
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        logger.debug("photo edit failed (%s), falling back to text", exc)
        await safe_edit(callback, caption, reply_markup)
    except (TelegramAPIError, OSError):
        logger.exception("Could not show the catalogue image; falling back to text")
        await safe_edit(callback, caption, reply_markup)
