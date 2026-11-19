"""Last-resort router: registered after every other one."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.common import main_menu_kb
from app.i18n import t

router = Router(name="fallback")


@router.callback_query()
async def unknown_callback(callback: CallbackQuery, lang: str) -> None:
    """Old keyboards from a previous bot version land here."""
    await callback.answer(t(lang, "common.unknown_action"), show_alert=False)


@router.message(F.text)
async def unknown_message(message: Message, lang: str) -> None:
    """Phase 4 replaces this with the natural-language AI assistant."""
    await message.answer(t(lang, "menu.prompt"), reply_markup=main_menu_kb(lang))
