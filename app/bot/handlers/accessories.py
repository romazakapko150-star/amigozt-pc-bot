"""Accessory catalogue: monitors, input devices, audio and furniture.

Same addressing trick as the comparison flow - items are referenced by their
position in a stable, price-sorted list, because a component id plus a prefix
would not fit Telegram's 64-byte callback_data limit.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import AccessoryCB, MenuAction, MenuCB, NavAction, NavCB
from app.bot.handlers import visual as visual_handlers
from app.bot.keyboards.common import chunk, markup, mobile_rows
from app.bot.utils import safe_edit, show_photo
from app.bot.views.accessories import ACCESSORY_ORDER, render_categories, render_item, render_list
from app.db.models import EventName
from app.domain.components import Component, ComponentCategory
from app.domain.labels import format_price_pln
from app.i18n import t
from app.services.analytics import AnalyticsService
from app.services.catalog import get_catalog
from app.services.media import BUILD_IMAGE_DIR
from app.services.media.catalog_grid import GridEntry, render_catalog_grid
from app.services.pricing import EstimatePriceProvider

logger = logging.getLogger(__name__)

router = Router(name="accessories")


async def _list_grid(
    session: AsyncSession,
    category: ComponentCategory,
    items: list[Component],
    lang: str,
) -> Path | None:
    """The list page drawn as one image: photo, number and price per product."""
    prices = _prices()
    photos = await visual_handlers.component_image_paths(session, items)
    entries = [
        GridEntry(
            index=index,
            name=component.name,
            price_text=(
                f"≈{format_price_pln(prices[component.id])}" if component.id in prices else "—"
            ),
            image_path=photos.get(component.id),
        )
        for index, component in enumerate(items, start=1)
    ]
    if not any(entry.image_path for entry in entries):
        # Nothing to show yet: the plain text list is better than empty tiles.
        return None
    try:
        return render_catalog_grid(
            t(lang, f"part.{category.value}"),
            entries,
            output_dir=BUILD_IMAGE_DIR,
            footer=t(lang, "visual.image_footer"),
        )
    except Exception:
        logger.exception("Could not render the %s list grid", category.value)
        return None


MAX_ITEMS = 12


class Action:
    CATEGORIES = "c"
    LIST = "l"
    ITEM = "i"


@lru_cache(maxsize=1)
def _prices() -> dict[str, Decimal]:
    catalog = get_catalog()
    offers = EstimatePriceProvider().get_offers([c.id for c in catalog])
    return {cid: found[0].price_pln for cid, found in offers.items() if found}


@lru_cache(maxsize=len(ComponentCategory))
def _items(category: ComponentCategory) -> tuple[Component, ...]:
    """Cheapest first. Cached: the ordering backs the callback payloads."""
    prices = _prices()
    parts = sorted(get_catalog().by_category(category), key=lambda c: prices.get(c.id, Decimal(0)))
    return tuple(parts[:MAX_ITEMS])


def categories_keyboard(lang: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=t(lang, f"part.{category.value}"),
            callback_data=AccessoryCB(action=Action.LIST, category=category.value, pick="").pack(),
        )
        for category in ACCESSORY_ORDER
        if _items(category)
    ]
    return markup(
        *mobile_rows(buttons, 2),
        [
            InlineKeyboardButton(
                text=t(lang, "nav.menu"), callback_data=NavCB(action=NavAction.MENU).pack()
            )
        ],
    )


def list_keyboard(category: ComponentCategory, lang: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=str(position + 1),
            callback_data=AccessoryCB(
                action=Action.ITEM, category=category.value, pick=str(position)
            ).pack(),
        )
        for position in range(len(_items(category)))
    ]
    return markup(
        *chunk(buttons, 6),
        [
            InlineKeyboardButton(
                text=t(lang, "nav.back"),
                callback_data=AccessoryCB(action=Action.CATEGORIES, category="", pick="").pack(),
            ),
            InlineKeyboardButton(
                text=t(lang, "nav.menu"), callback_data=NavCB(action=NavAction.MENU).pack()
            ),
        ],
    )


def item_keyboard(category: ComponentCategory, lang: str) -> InlineKeyboardMarkup:
    return markup(
        [
            InlineKeyboardButton(
                text=t(lang, "nav.back"),
                callback_data=AccessoryCB(
                    action=Action.LIST, category=category.value, pick=""
                ).pack(),
            ),
            InlineKeyboardButton(
                text=t(lang, "nav.menu"), callback_data=NavCB(action=NavAction.MENU).pack()
            ),
        ]
    )


@router.message(Command("accessories"))
async def cmd_accessories(message: Message, lang: str) -> None:
    await message.answer(render_categories(lang), reply_markup=categories_keyboard(lang))


@router.callback_query(MenuCB.filter(F.action == MenuAction.ACCESSORIES))
async def open_accessories(callback: CallbackQuery, session: AsyncSession, lang: str) -> None:
    await AnalyticsService(session).track(callback.from_user.id, EventName.ACCESSORIES_OPENED)
    await safe_edit(callback, render_categories(lang), categories_keyboard(lang))
    await callback.answer()


@router.callback_query(AccessoryCB.filter())
async def navigate(
    callback: CallbackQuery, callback_data: AccessoryCB, session: AsyncSession, lang: str
) -> None:
    if callback_data.action == Action.CATEGORIES:
        await safe_edit(callback, render_categories(lang), categories_keyboard(lang))
        await callback.answer()
        return

    try:
        category = ComponentCategory(callback_data.category)
    except ValueError:
        await callback.answer()
        return

    items = _items(category)

    if callback_data.action == Action.LIST:
        text = render_list(category, list(items), _prices(), lang)
        keyboard = list_keyboard(category, lang)
        if isinstance(callback.message, Message):
            grid = await _list_grid(session, category, list(items), lang)
            if grid is not None:
                await show_photo(callback, grid, text, keyboard)
                await callback.answer()
                return
        await safe_edit(callback, text, keyboard)

    elif callback_data.action == Action.ITEM:
        if not callback_data.pick.isdigit():
            await callback.answer()
            return
        position = int(callback_data.pick)
        if not 0 <= position < len(items):
            await callback.answer()
            return

        component = items[position]
        await AnalyticsService(session).track(
            callback.from_user.id,
            EventName.ACCESSORY_VIEWED,
            category=category.value,
            component_id=component.id,
        )
        caption = render_item(component, _prices().get(component.id), lang)
        keyboard = item_keyboard(category, lang)
        if isinstance(callback.message, Message) and await visual_handlers.send_component_visual(
            callback.message, session, component, caption=caption, keyboard=keyboard
        ):
            await callback.answer()
            return
        await safe_edit(callback, caption, keyboard)

    await callback.answer()
