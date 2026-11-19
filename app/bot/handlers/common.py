from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import LangCB, MenuAction, MenuCB, NavAction, NavCB
from app.bot.keyboards.common import back_to_menu_kb, language_kb, main_menu_kb
from app.bot.utils import safe_edit
from app.db.models import EventName, User
from app.i18n import LOCALES, t
from app.services.analytics import AnalyticsService
from app.services.media.brand import BrandAsset, get_brand_assets

router = Router(name="common")


def _greeting(lang: str) -> str:
    return f"{t(lang, 'start.title')}\n\n{t(lang, 'start.tagline')}\n\n{t(lang, 'menu.prompt')}"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, lang: str) -> None:
    await state.clear()
    if message.from_user is not None:
        await AnalyticsService(session).track(message.from_user.id, EventName.START)
    greeting = _greeting(lang)
    # The welcome carries the brand image; if it cannot be sent (file missing,
    # upload error, just shown) the same greeting goes out as text.
    shown = await get_brand_assets().send(message, BrandAsset.MAIN, greeting, main_menu_kb(lang))
    if not shown:
        await message.answer(greeting, reply_markup=main_menu_kb(lang))


@router.message(Command("help"))
async def cmd_help(message: Message, lang: str) -> None:
    await message.answer(t(lang, "help.text"), reply_markup=back_to_menu_kb(lang))


@router.message(Command("language"))
async def cmd_language(message: Message, lang: str) -> None:
    await message.answer(t(lang, "lang.prompt"), reply_markup=language_kb())


@router.callback_query(NavCB.filter(F.action == NavAction.MENU))
async def back_to_menu(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await safe_edit(callback, _greeting(lang), main_menu_kb(lang))
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == MenuAction.ABOUT))
async def show_about(callback: CallbackQuery, lang: str) -> None:
    await safe_edit(callback, t(lang, "about.text"), back_to_menu_kb(lang))
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == MenuAction.HELP))
async def show_help(callback: CallbackQuery, lang: str) -> None:
    await safe_edit(callback, t(lang, "help.text"), back_to_menu_kb(lang))
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == MenuAction.LANGUAGE))
async def show_language_picker(callback: CallbackQuery, lang: str) -> None:
    await safe_edit(callback, t(lang, "lang.prompt"), language_kb())
    await callback.answer()


@router.callback_query(LangCB.filter())
async def set_language(callback: CallbackQuery, callback_data: LangCB, user: User | None) -> None:
    code = callback_data.code
    if code not in LOCALES:
        await callback.answer()
        return

    if user is not None:
        user.language = code  # committed by DbSessionMiddleware

    await callback.answer(t(code, "lang.changed"))
    await safe_edit(callback, _greeting(code), main_menu_kb(code))
