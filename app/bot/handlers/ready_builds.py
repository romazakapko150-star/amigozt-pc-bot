"""The "Ready-made builds" shelf.

Browsing is paginated because a Telegram message that lists fifty machines is
unreadable on a phone and hits the message length limit. Each entry is one
short line; the full card only appears when a build is opened.
"""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import MenuAction, MenuCB, NavAction, NavCB, ReadyCB
from app.bot.handlers.visual import (
    Kind,
    send_ai_visualization,
    shelf_image_paths,
    visual_button,
)
from app.bot.keyboards.common import back_to_menu_kb, chunk, markup, mobile_rows
from app.bot.utils import safe_edit, send_photo_card, show_photo
from app.bot.views.admin import render_blocked_shelf_order
from app.bot.views.build import render_order_blocked
from app.bot.views.ready_builds import (
    parts_from,
    render_build_page,
    render_filters,
    render_list,
    shelf_description,
)
from app.config import Settings, get_settings
from app.db.models import Build, EventName, ReadyBuild, User
from app.db.repositories import ReadyBuildRepository
from app.domain.enums import Aesthetics
from app.domain.labels import format_price_pln
from app.i18n import t
from app.services.analytics import AnalyticsService
from app.services.catalog import get_catalog
from app.services.compatibility.gate import check_components
from app.services.leads import LeadService
from app.services.media import BUILD_IMAGE_DIR, default_preset, render_build_image
from app.services.media.brand import BrandAsset, get_brand_assets
from app.services.media.catalog_grid import GridEntry, render_catalog_grid
from app.services.notifications import AdminNotifier

logger = logging.getLogger(__name__)

router = Router(name="ready_builds")

PAGE_SIZE = 5

#: Budget shelves, as (key, ceiling in PLN or None for "and up").
BUDGET_BANDS: tuple[tuple[str, int | None], ...] = (
    ("6000", 6000),
    ("9000", 9000),
    ("13000", 13000),
    ("plus", None),
)


class Action:
    FILTERS = "f"
    LIST = "l"
    OPEN = "o"
    BUDGET = "b"
    ORDER = "r"


def _band_ceiling(value: str) -> int | None:
    for key, ceiling in BUDGET_BANDS:
        if key == value:
            return ceiling
    return None


async def _show_filters(callback: CallbackQuery, session: AsyncSession, lang: str) -> None:
    repo = ReadyBuildRepository(session)
    categories = await repo.categories()
    total = await repo.count()

    buttons = [
        InlineKeyboardButton(
            text=t(lang, f"ready.cat.{category}"),
            callback_data=ReadyCB(action=Action.LIST, value=category, page=0).pack(),
        )
        for category, _ in categories
    ]

    budget_buttons = [
        InlineKeyboardButton(
            text=(
                t(lang, "ready.budget.under", value=f"{ceiling // 1000}K")
                if ceiling
                else t(lang, "ready.budget.over", value="13K")
            ),
            callback_data=ReadyCB(action=Action.BUDGET, value=key, page=0).pack(),
        )
        for key, ceiling in BUDGET_BANDS
    ]

    keyboard = markup(
        [
            InlineKeyboardButton(
                text=t(lang, "ready.all"),
                callback_data=ReadyCB(action=Action.LIST, value="", page=0).pack(),
            )
        ],
        *mobile_rows(buttons, 2),
        *chunk(budget_buttons, 2),
        [
            InlineKeyboardButton(
                text=t(lang, "nav.menu"),
                callback_data=NavCB(action=NavAction.MENU).pack(),
            )
        ],
    )
    await safe_edit(callback, render_filters(total, lang), keyboard)


async def _show_list(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
    *,
    category: str | None,
    max_price: int | None,
    page: int,
    filter_action: str,
    filter_value: str,
) -> None:
    repo = ReadyBuildRepository(session)
    total = await repo.count(category=category, max_price_pln=max_price)
    pages = max(1, -(-total // PAGE_SIZE))
    page = max(0, min(page, pages - 1))

    builds = await repo.fetch(
        category=category, max_price_pln=max_price, limit=PAGE_SIZE, offset=page * PAGE_SIZE
    )

    keyboard = _list_keyboard(builds, lang, page, pages, filter_action, filter_value)
    text = render_list(builds, total, page + 1, pages, lang)
    grid = await _shelf_grid(session, builds, lang)
    if grid is not None:
        await show_photo(callback, grid, text, keyboard)
        return
    await safe_edit(callback, text, keyboard)


async def _shelf_grid(session: AsyncSession, builds: list[ReadyBuild], lang: str) -> Path | None:
    """The shelf page drawn as one image: each build's render beside its price."""
    if not builds:
        return None
    photos = await shelf_image_paths(session, builds)
    entries = [
        GridEntry(
            index=index,
            name=build.name,
            price_text=(
                format_price_pln(build.reference_price_pln)
                if build.reference_price_pln is not None
                else "—"
            ),
            image_path=photos.get(build.id),
        )
        for index, build in enumerate(builds, start=1)
    ]
    if not any(entry.image_path for entry in entries):
        return None
    try:
        return render_catalog_grid(
            t(lang, "ready.title"),
            entries,
            output_dir=BUILD_IMAGE_DIR,
            footer=t(lang, "visual.image_footer"),
        )
    except Exception:
        logger.exception("Could not render the shelf grid")
        return None


def _list_keyboard(
    builds: list[ReadyBuild],
    lang: str,
    page: int,
    pages: int,
    filter_action: str,
    filter_value: str,
) -> InlineKeyboardMarkup:
    open_buttons = [
        InlineKeyboardButton(
            text=f"{index}",
            callback_data=ReadyCB(action=Action.OPEN, value=str(build.id), page=page).pack(),
        )
        for index, build in enumerate(builds, start=1)
    ]

    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text=t(lang, "ready.prev"),
                callback_data=ReadyCB(
                    action=filter_action, value=filter_value, page=page - 1
                ).pack(),
            )
        )
    if page + 1 < pages:
        navigation.append(
            InlineKeyboardButton(
                text=t(lang, "ready.next"),
                callback_data=ReadyCB(
                    action=filter_action, value=filter_value, page=page + 1
                ).pack(),
            )
        )

    return markup(
        *chunk(open_buttons, 5),
        navigation,
        [
            InlineKeyboardButton(
                text=t(lang, "nav.back"),
                callback_data=ReadyCB(action=Action.FILTERS, value="", page=0).pack(),
            ),
            InlineKeyboardButton(
                text=t(lang, "nav.menu"),
                callback_data=NavCB(action=NavAction.MENU).pack(),
            ),
        ],
    )


@router.callback_query(MenuCB.filter(F.action == MenuAction.PRESETS))
async def open_shelf(callback: CallbackQuery, session: AsyncSession, lang: str) -> None:
    await AnalyticsService(session).track(callback.from_user.id, EventName.READY_BUILDS_OPENED)
    await _show_filters(callback, session, lang)
    await callback.answer()


@router.callback_query(ReadyCB.filter())
async def navigate(
    callback: CallbackQuery,
    callback_data: ReadyCB,
    session: AsyncSession,
    lang: str,
    user: User | None = None,
    settings: Settings | None = None,
) -> None:
    action = callback_data.action

    if action == Action.FILTERS:
        await _show_filters(callback, session, lang)

    elif action == Action.LIST:
        await _show_list(
            callback,
            session,
            lang,
            category=callback_data.value or None,
            max_price=None,
            page=callback_data.page,
            filter_action=Action.LIST,
            filter_value=callback_data.value,
        )

    elif action == Action.BUDGET:
        ceiling = _band_ceiling(callback_data.value)
        await _show_list(
            callback,
            session,
            lang,
            category=None,
            max_price=ceiling,
            page=callback_data.page,
            filter_action=Action.BUDGET,
            filter_value=callback_data.value,
        )

    elif action == Action.OPEN:
        await _open_build(callback, session, lang, callback_data)

    elif action == Action.ORDER:
        await _order_build(callback, session, lang, callback_data, settings)

    await callback.answer()


async def _open_build(
    callback: CallbackQuery, session: AsyncSession, lang: str, data: ReadyCB
) -> None:
    if not data.value.isdigit():
        return

    build = await ReadyBuildRepository(session).get(int(data.value))
    if build is None:
        await callback.answer(t(lang, "ready.stale"), show_alert=True)
        return

    catalog = get_catalog()
    missing = [cid for cid in build.components.values() if catalog.get(cid) is None]
    if missing:
        # The shelf references a part the catalogue no longer has. Say so
        # rather than rendering a half-empty card.
        logger.warning("Ready build %s references unknown components: %s", build.slug, missing)
        await callback.answer(t(lang, "ready.stale"), show_alert=True)
        return

    await AnalyticsService(session).track(
        callback.from_user.id, EventName.READY_BUILD_VIEWED, ready_build_id=build.id
    )

    keyboard = markup(
        [
            InlineKeyboardButton(
                text=t(lang, "order.button"),
                callback_data=ReadyCB(action=Action.ORDER, value=str(build.id), page=0).pack(),
            )
        ],
        [visual_button(Kind.READY, build.id, lang, recolour=True)],
        [
            InlineKeyboardButton(
                text=t(lang, "nav.back"),
                callback_data=ReadyCB(action=Action.LIST, value="", page=data.page).pack(),
            ),
            InlineKeyboardButton(
                text=t(lang, "nav.menu"),
                callback_data=NavCB(action=NavAction.MENU).pack(),
            ),
        ],
    )

    caption = render_build_page(build, catalog, lang)
    if not isinstance(callback.message, Message):
        return

    # The AI render of this exact machine, cached after the first time. When
    # it is off or fails, the schematic card below carries the same caption.
    parts = parts_from(build, catalog)
    try:
        aesthetics: Aesthetics | None = Aesthetics(build.style)
    except ValueError:
        aesthetics = None
    result = await send_ai_visualization(
        callback.message,
        session,
        parts,
        default_preset(parts, aesthetics),
        caption=f"{caption}\n\n{t(lang, 'visual.caption_ai')}",
        keyboard=keyboard,
        lang=lang,
        ready_build_id=build.id,
    )
    if result is not None and result.ok:
        return

    # A text message cannot be edited into a photo, so the card arrives as a
    # new message under the list the customer was browsing.
    try:
        image = render_build_image(
            build.name,
            parts_from(build, catalog),
            build.reference_price_pln,
            subtitle=shelf_description(build, lang),
            footer=t(lang, "visual.image_footer"),
            output_dir=BUILD_IMAGE_DIR,
        )
    except Exception:
        logger.exception("Could not render an image for %s", build.slug)
        if not await get_brand_assets().send(
            callback.message, BrandAsset.BUILD_DEFAULT, caption, keyboard, respect_cooldown=False
        ):
            await callback.message.answer(caption, reply_markup=keyboard)
        return

    await send_photo_card(callback.message, image, caption, keyboard)


async def _order_build(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
    data: ReadyCB,
    settings: Settings | None,
) -> None:
    """Turn a shelf entry into a real lead, same as a configured build."""
    if not data.value.isdigit() or callback.message is None:
        return

    user: User | None = None
    ready = await ReadyBuildRepository(session).get(int(data.value))
    if ready is None:
        await callback.answer(t(lang, "ready.stale"), show_alert=True)
        return

    from app.db.repositories import UserRepository

    user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer(t(lang, "common.error"), show_alert=True)
        return

    # The gate: a shelf entry is re-checked against today's catalogue before
    # it can become an order. A stale entry blocks here and alerts the admin.
    gate = check_components(ready.components)
    if not gate.compatible:
        if isinstance(callback.message, Message):
            await callback.message.answer(
                render_order_blocked(gate.customer_reason_codes(), lang),
                reply_markup=back_to_menu_kb(lang),
            )
        admin_ids = settings.admin_ids if settings is not None else get_settings().admin_ids
        if callback.bot is not None:
            await AdminNotifier(callback.bot, admin_ids).notify_text(
                render_blocked_shelf_order(ready.name, ready.slug, gate.snapshot())
            )
        return

    # A shelf order still becomes a Build row, so admins and analytics see one
    # kind of order regardless of where it came from.
    build = Build(
        user_id=user.id,
        tier=ready.tier,
        title=ready.name,
        requirements={
            "budget_pln": ready.budget_max_pln,
            "purpose": ready.purpose,
            "resolution": ready.resolution,
            "target_fps": ready.target_fps,
            "cpu_brand": ready.cpu_brand,
            "gpu_brand": ready.gpu_brand,
            "aesthetics": ready.style,
            "wifi": ready.wifi,
            "bluetooth": ready.bluetooth,
            "ram_gb": ready.ram_gb,
            "storage_gb": ready.storage_gb,
            "source": "ready_build",
            "ready_build_slug": ready.slug,
        },
        components=dict(ready.components),
        estimated_fps={},
        budget_pln=ready.budget_max_pln,
        purpose=ready.purpose,
        resolution=ready.resolution,
        target_fps=ready.target_fps,
        total_price_pln=ready.reference_price_pln,
        is_saved=True,
    )
    session.add(build)
    await session.flush()

    lead, linked, created = await LeadService(session).request_order(
        user,
        build.id,
        pricing_snapshot=ready.pricing_snapshot,
        compatibility_snapshot=gate.snapshot(),
    )
    if not created:
        await callback.message.answer(t(lang, "order.exists", lead_id=lead.id))
        return

    await AnalyticsService(session).track(
        callback.from_user.id,
        EventName.READY_BUILD_ORDERED,
        ready_build_id=ready.id,
        lead_id=lead.id,
    )

    # Commit before notifying so an admin never gets a card for a lead that a
    # rollback would erase.
    await session.commit()

    created_text = t(lang, "order.created", lead_id=lead.id)
    if not (
        isinstance(callback.message, Message)
        and await get_brand_assets().send(
            callback.message, BrandAsset.ORDER_CONFIRMATION, created_text, back_to_menu_kb(lang)
        )
    ):
        await callback.message.answer(created_text, reply_markup=back_to_menu_kb(lang))

    admin_ids = settings.admin_ids if settings is not None else get_settings().admin_ids
    if callback.bot is not None:
        await AdminNotifier(callback.bot, admin_ids).notify_new_lead(lead, user, linked)


__all__ = ["router"]
