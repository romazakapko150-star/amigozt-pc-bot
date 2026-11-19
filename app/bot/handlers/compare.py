"""Component comparison.

Two taps to a result: pick a category, pick two parts. The selection travels
in the callback payload rather than the FSM, so it cannot collide with the
configurator's state and survives a restart mid-comparison.

Parts are addressed by their position in the price-sorted list, not by id:
two component ids do not fit inside Telegram's 64-byte callback_data limit.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from functools import lru_cache

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import CompareCB, MenuAction, MenuCB, NavAction, NavCB
from app.bot.keyboards.common import markup, mobile_rows
from app.bot.utils import safe_edit
from app.bot.views.compare import COMPARABLE, render_comparison
from app.db.models import EventName
from app.domain.components import Component, ComponentCategory
from app.i18n import t
from app.services.analytics import AnalyticsService
from app.services.catalog import get_catalog
from app.services.pricing import EstimatePriceProvider

logger = logging.getLogger(__name__)

router = Router(name="compare")

#: A longer list does not fit comfortably on a phone.
MAX_OPTIONS = 16


class Action:
    CATEGORIES = "c"
    FIRST = "1"
    SECOND = "2"
    RESULT = "r"


@lru_cache(maxsize=1)
def _prices() -> dict[str, Decimal]:
    catalog = get_catalog()
    offers = EstimatePriceProvider().get_offers([c.id for c in catalog])
    return {cid: found[0].price_pln for cid, found in offers.items() if found}


@lru_cache(maxsize=len(ComponentCategory))
def _options(category: ComponentCategory) -> tuple[Component, ...]:
    """Cheapest first, so the list reads like a ladder.

    Cached because both the catalogue and the estimate prices are static for
    the life of the process; the ordering must stay stable because callback
    payloads reference positions in it.
    """
    prices = _prices()
    parts = sorted(get_catalog().by_category(category), key=lambda c: prices.get(c.id, Decimal(0)))
    return tuple(parts[:MAX_OPTIONS])


def _resolve(category: ComponentCategory, index: str) -> Component | None:
    if not index.isdigit():
        return None
    options = _options(category)
    position = int(index)
    return options[position] if 0 <= position < len(options) else None


def _intro(lang: str, prompt_key: str) -> str:
    return f"{t(lang, 'cmp.title')}\n\n{t(lang, prompt_key)}"


def _nav_row(lang: str, back_to: str, category: str = "") -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=t(lang, "nav.back"),
            callback_data=CompareCB(action=back_to, category=category, pick="").pack(),
        ),
        InlineKeyboardButton(
            text=t(lang, "nav.menu"), callback_data=NavCB(action=NavAction.MENU).pack()
        ),
    ]


def categories_keyboard(lang: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=t(lang, f"part.{category.value}"),
            callback_data=CompareCB(action=Action.FIRST, category=category.value, pick="").pack(),
        )
        for category in COMPARABLE
    ]
    return markup(
        *mobile_rows(buttons, 2),
        [
            InlineKeyboardButton(
                text=t(lang, "nav.menu"), callback_data=NavCB(action=NavAction.MENU).pack()
            )
        ],
    )


def options_keyboard(
    category: ComponentCategory, first_index: str, lang: str
) -> InlineKeyboardMarkup:
    """List of parts. Picking one either starts or completes the pair."""
    buttons = []
    for position, component in enumerate(_options(category)):
        if str(position) == first_index:
            continue
        pick = f"{first_index}-{position}" if first_index else str(position)
        buttons.append(
            InlineKeyboardButton(
                text=component.model[:30],
                callback_data=CompareCB(
                    action=Action.RESULT if first_index else Action.SECOND,
                    category=category.value,
                    pick=pick,
                ).pack(),
            )
        )

    back_to = Action.FIRST if first_index else Action.CATEGORIES
    return markup(
        *mobile_rows(buttons, 1),
        _nav_row(lang, back_to, category.value if first_index else ""),
    )


@router.message(Command("compare"))
async def cmd_compare(message: Message, lang: str) -> None:
    await message.answer(_intro(lang, "cmp.pick_category"), reply_markup=categories_keyboard(lang))


@router.callback_query(MenuCB.filter(F.action == MenuAction.COMPARE))
async def open_compare(callback: CallbackQuery, session: AsyncSession, lang: str) -> None:
    await AnalyticsService(session).track(callback.from_user.id, EventName.COMPARE_OPENED)
    await safe_edit(callback, _intro(lang, "cmp.pick_category"), categories_keyboard(lang))
    await callback.answer()


@router.callback_query(CompareCB.filter())
async def navigate(
    callback: CallbackQuery, callback_data: CompareCB, session: AsyncSession, lang: str
) -> None:
    action = callback_data.action

    if action == Action.CATEGORIES:
        await safe_edit(callback, _intro(lang, "cmp.pick_category"), categories_keyboard(lang))
        await callback.answer()
        return

    try:
        category = ComponentCategory(callback_data.category)
    except ValueError:
        await callback.answer()
        return

    if action == Action.FIRST:
        await safe_edit(
            callback,
            _intro(lang, "cmp.pick_first"),
            options_keyboard(category, "", lang),
        )

    elif action == Action.SECOND:
        await safe_edit(
            callback,
            _intro(lang, "cmp.pick_second"),
            options_keyboard(category, callback_data.pick, lang),
        )

    elif action == Action.RESULT:
        await _show_result(callback, callback_data, category, session, lang)
        return

    await callback.answer()


async def _show_result(
    callback: CallbackQuery,
    data: CompareCB,
    category: ComponentCategory,
    session: AsyncSession,
    lang: str,
) -> None:
    if "-" not in data.pick:
        await callback.answer()
        return

    first_index, second_index = data.pick.split("-", 1)
    left = _resolve(category, first_index)
    right = _resolve(category, second_index)

    if left is None or right is None:
        await callback.answer(t(lang, "common.error"), show_alert=True)
        return
    if left.id == right.id:
        await callback.answer(t(lang, "cmp.same"), show_alert=True)
        return

    await AnalyticsService(session).track(
        callback.from_user.id, EventName.COMPARE_RESULT, category=category.value
    )

    keyboard = markup(
        [
            InlineKeyboardButton(
                text=t(lang, "cmp.reset"),
                callback_data=CompareCB(action=Action.CATEGORIES, category="", pick="").pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=t(lang, "nav.menu"), callback_data=NavCB(action=NavAction.MENU).pack()
            )
        ],
    )
    await safe_edit(callback, render_comparison(left, right, lang, _prices()), keyboard)
    await callback.answer()
