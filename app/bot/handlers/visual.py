"""Build visualisation: show the machine, then let the customer recolour it.

Two entry points share one renderer: a build the customer configured (a
``builds`` row) and a ready build from the shelf. Both resolve their component
ids through the catalogue, pick a default look from the real parts, and offer
the same colour/style picker.

The AI path is the :class:`~app.services.ai.Visualizer`: a saved render is
served from its cache with no API call; a missing one is generated once while
the customer sees a short "creating..." status. When the API is off or fails,
the schematic card takes over and the caption says so - the build, the price
and the order button are never held hostage by a picture.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Sequence
from decimal import Decimal
from html import escape
from pathlib import Path

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import NavAction, NavCB, VisualCB
from app.bot.keyboards.common import chunk, markup
from app.bot.utils import MAX_CAPTION, send_photo_card
from app.config import Settings, get_settings
from app.db.models import Build, EventName, ReadyBuild, User, VisualizationStatus
from app.domain.components import Component, ComponentCategory
from app.domain.enums import Aesthetics
from app.domain.labels import format_price_pln
from app.i18n import t
from app.services.ai import VisualizationResult, Visualizer
from app.services.analytics import AnalyticsService
from app.services.catalog import get_catalog
from app.services.media import (
    ACCENT_EMOJI,
    BUILD_IMAGE_DIR,
    Style,
    VisualPreset,
    accent_label,
    default_preset,
    parse_preset,
    preset_title,
    render_build_image,
    with_accent,
    with_style,
)
from app.services.visuals import ComponentVisualizer

logger = logging.getLogger(__name__)

router = Router(name="visual")

Parts = dict[ComponentCategory, Component]


class Kind:
    BUILD = "b"
    READY = "r"


def visual_button(
    kind: str, build_id: int, lang: str, *, recolour: bool = False
) -> InlineKeyboardButton:
    """The entry button other cards embed."""
    key = (
        "visual.recolour" if recolour else ("visual.look" if kind == Kind.READY else "visual.show")
    )
    return InlineKeyboardButton(
        text=t(lang, key), callback_data=VisualCB(kind=kind, id=build_id, preset="").pack()
    )


def picker_keyboard(
    kind: str, build_id: int, current: VisualPreset, lang: str
) -> InlineKeyboardMarkup:
    """Accent colours in two columns, then the style toggle, then navigation."""
    accents = [
        InlineKeyboardButton(
            text=(
                f"• {accent_label(accent, lang)}"
                if accent is current.accent
                else accent_label(accent, lang)
            ),
            callback_data=VisualCB(
                kind=kind, id=build_id, preset=with_accent(current, accent).key
            ).pack(),
        )
        for accent in ACCENT_EMOJI
    ]

    styles = [
        InlineKeyboardButton(
            text=("• " if current.style is style else "") + t(lang, f"visual.style_{style.value}"),
            callback_data=VisualCB(
                kind=kind, id=build_id, preset=with_style(current, style).key
            ).pack(),
        )
        for style in Style
    ]

    return markup(
        *chunk(accents, 2),
        styles,
        [
            InlineKeyboardButton(
                text=t(lang, "nav.menu"), callback_data=NavCB(action=NavAction.MENU).pack()
            )
        ],
    )


def ai_caption(title: str, price: Decimal | None, lang: str, *, picker_hint: bool = False) -> str:
    """Caption under an AI render: title, price, the honesty note, optionally the picker hint."""
    caption = f"<b>{escape(title)}</b>"
    if price is not None:
        caption += f"\n💰 {format_price_pln(price)}"
    caption += f"\n\n{t(lang, 'visual.caption_ai')}"
    if picker_hint:
        caption += f"\n\n{t(lang, 'visual.pick')}"
    return caption


def get_visualizer(settings: Settings | None = None) -> Visualizer:
    """The visualiser handlers use. Tests swap this for one with a fake generator."""
    return Visualizer.from_settings(settings or get_settings())


def get_component_visualizer(settings: Settings | None = None) -> ComponentVisualizer:
    """Product-photo source for catalogue cards. Tests swap this out."""
    return ComponentVisualizer.from_settings(settings or get_settings())


async def send_component_visual(
    message: Message,
    session: AsyncSession,
    component: Component,
    *,
    caption: str,
    keyboard: InlineKeyboardMarkup | None,
    settings: Settings | None = None,
) -> bool:
    """Send the stored product photo of one catalogue item, if the library
    has one. Never generates, never spends money; False means show the
    plain text card instead."""
    visualizer = get_component_visualizer(settings)
    visual = await visualizer.status_for(session, component)
    if visual is None:
        return False
    result = VisualizationResult(
        status=VisualizationStatus.READY,
        path=Path(visual.image_path or ""),
        record=visual,
        cache_hit=True,
        fingerprint=visual.fingerprint,
    )
    sent = await _send_visual_photo(message, result, caption, keyboard)
    if sent:
        with contextlib.suppress(Exception):
            await visualizer.library(session).mark_used(visual)
    return sent


async def component_image_paths(
    session: AsyncSession,
    components: Sequence[Component],
    settings: Settings | None = None,
) -> dict[str, Path]:
    """Stored photo per component id, for the ones the library already has.

    Read-only and free: a component with no visual is simply absent from the
    result, and the caller draws a placeholder tile for it.
    """
    visualizer = get_component_visualizer(settings)
    found: dict[str, Path] = {}
    for component in components:
        visual = await visualizer.status_for(session, component)
        if visual is None or not visual.is_ready:
            continue
        path = Path(visual.image_path or "")
        if path.is_file():
            found[component.id] = path
    return found


async def shelf_image_paths(
    session: AsyncSession,
    builds: Sequence[ReadyBuild],
    settings: Settings | None = None,
) -> dict[int, Path]:
    """Stored render per shelf build id, for the ones already in the library.

    Read-only and free, and it asks for the same key the shelf card uses, so
    a page of thumbnails never triggers a paid render.
    """
    visualizer = get_visualizer(settings)
    found: dict[int, Path] = {}
    for build in builds:
        parts = _resolve_parts(build.components or {})
        if not parts:
            continue
        try:
            aesthetics: Aesthetics | None = Aesthetics(build.style)
        except ValueError:
            aesthetics = None
        preset = default_preset(parts, aesthetics)
        visual = await visualizer.status_for(session, parts, preset, build.visual_priorities)
        if visual is None or not visual.is_ready:
            continue
        path = Path(visual.image_path or "")
        if path.is_file():
            found[build.id] = path
    return found


async def send_ai_visualization(
    message: Message,
    session: AsyncSession,
    parts: Parts,
    preset: VisualPreset,
    *,
    caption: str,
    keyboard: InlineKeyboardMarkup | None,
    lang: str,
    build_id: int | None = None,
    ready_build_id: int | None = None,
    settings: Settings | None = None,
    priorities: Sequence[str] | None = None,
) -> VisualizationResult | None:
    """Send the AI render of ``parts`` in ``preset``; None when AI is off.

    A cached render goes out immediately. Otherwise a status line is shown,
    the image is generated (one paid call), the status line is removed and
    the photo follows. On failure the status line becomes "temporarily
    unavailable" and the result reports it; the caller falls back.
    """
    visualizer = get_visualizer(settings)
    if not visualizer.enabled:
        return None

    cached = await visualizer.status_for(session, parts, preset, priorities)
    cache_hit = cached is not None and cached.is_ready and Path(cached.image_path or "").is_file()

    status: Message | None = None
    if not cache_hit:
        try:
            status = await message.answer(t(lang, "visual.generating"))
        except TelegramAPIError:
            status = None

    result = await visualizer.get_or_create(
        session,
        parts,
        preset,
        build_id=build_id,
        ready_build_id=ready_build_id,
        priorities=priorities,
    )

    if result.ok:
        sent = await _send_visual_photo(message, result, caption, keyboard)
        if status is not None:
            await _drop(status)
        if sent:
            return result
        result.status = "failed"
        result.error = "telegram refused the photo"
        return result

    if status is not None:
        with contextlib.suppress(TelegramAPIError):
            await status.edit_text(t(lang, "visual.unavailable"))
    return result


async def _send_visual_photo(
    message: Message,
    result: VisualizationResult,
    caption: str,
    keyboard: InlineKeyboardMarkup | None,
) -> bool:
    record = result.record
    file_id = record.telegram_file_id if record is not None else None
    fits = len(caption) <= MAX_CAPTION
    for attempt in (file_id, None):
        if attempt is None and result.path is None:
            return False
        photo = attempt if attempt is not None else FSInputFile(result.path)  # type: ignore[arg-type]
        try:
            if fits:
                sent = await message.answer_photo(photo, caption=caption, reply_markup=keyboard)
            else:
                sent = await message.answer_photo(photo)
                await message.answer(caption, reply_markup=keyboard)
        except (TelegramAPIError, OSError):
            if attempt is not None:
                # Stale file_id (bot token rotated, file purged): upload again.
                logger.info("Cached Telegram file_id rejected; re-uploading the render")
                if record is not None:
                    record.telegram_file_id = None
                continue
            logger.exception("Could not send the AI visualisation")
            return False
        if attempt is None and record is not None and sent.photo:
            record.telegram_file_id = sent.photo[-1].file_id
        return True
    return False


async def _drop(message: Message) -> None:
    try:
        await message.delete()
    except TelegramAPIError:
        with contextlib.suppress(TelegramAPIError):
            await message.edit_text("✅")


def _resolve_parts(components: dict) -> Parts:
    catalog = get_catalog()
    parts: Parts = {}
    for raw_category, component_id in components.items():
        try:
            category = ComponentCategory(raw_category)
        except ValueError:
            continue
        component = catalog.get(str(component_id))
        if component is not None:
            parts[category] = component
    return parts


async def _load(session: AsyncSession, kind: str, build_id: int, user: User | None):  # type: ignore[no-untyped-def]
    """(title, parts, price, aesthetics, priorities) for either kind, or None."""
    if kind == Kind.READY:
        ready = await session.get(ReadyBuild, build_id)
        if ready is None:
            return None
        try:
            aesthetics: Aesthetics | None = Aesthetics(ready.style)
        except ValueError:
            aesthetics = None
        shelf_priorities = ready.visual_priorities
        return (
            ready.name,
            _resolve_parts(ready.components),
            ready.reference_price_pln,
            aesthetics,
            shelf_priorities,
        )

    build = await session.get(Build, build_id)
    if build is None or (user is not None and build.user_id != user.id):
        # A customer must not be able to render someone else's build by id.
        return None
    aesthetics = None
    raw = (build.requirements or {}).get("aesthetics")
    if raw:
        try:
            aesthetics = Aesthetics(raw)
        except ValueError:
            aesthetics = None
    title = build.title or "AmigoZT PC"
    stored = (build.requirements or {}).get("priorities") or []
    priorities = [str(p) for p in stored if isinstance(p, str)]
    return (
        title,
        _resolve_parts(build.components or {}),
        build.total_price_pln,
        aesthetics,
        priorities,
    )


def _schematic(title, parts, price, preset: VisualPreset, lang: str):  # type: ignore[no-untyped-def]
    """The drawn card; None only when even that could not be produced."""
    try:
        return render_build_image(
            title,
            parts,
            price,
            subtitle=preset_title(preset, lang),
            preset=preset,
            footer=t(lang, "visual.image_footer"),
            output_dir=BUILD_IMAGE_DIR,
        )
    except Exception:
        logger.exception("Schematic render failed for %s", title)
        return None


@router.callback_query(VisualCB.filter())
async def show_visual(
    callback: CallbackQuery,
    callback_data: VisualCB,
    session: AsyncSession,
    lang: str,
    user: User | None = None,
    settings: Settings | None = None,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    loaded = await _load(session, callback_data.kind, callback_data.id, user)
    if loaded is None:
        await callback.answer(t(lang, "visual.stale"), show_alert=True)
        return

    title, parts, price, aesthetics, priorities = loaded
    if not parts:
        await callback.answer(t(lang, "visual.stale"), show_alert=True)
        return

    preset = parse_preset(callback_data.preset) or default_preset(parts, aesthetics)

    await AnalyticsService(session).track(
        callback.from_user.id,
        EventName.VISUAL_SHOWN,
        kind=callback_data.kind,
        build_id=callback_data.id,
        preset=preset.key,
    )
    await callback.answer()

    keyboard = picker_keyboard(callback_data.kind, callback_data.id, preset, lang)
    is_shelf = callback_data.kind == Kind.READY
    result = await send_ai_visualization(
        callback.message,
        session,
        parts,
        preset,
        caption=ai_caption(title, price, lang, picker_hint=True),
        keyboard=keyboard,
        lang=lang,
        settings=settings,
        build_id=None if is_shelf else callback_data.id,
        ready_build_id=callback_data.id if is_shelf else None,
        priorities=priorities,
    )
    if result is not None and result.ok:
        return

    image = _schematic(title, parts, price, preset, lang)
    if image is None:
        await callback.message.answer(t(lang, "common.error"), reply_markup=keyboard)
        return

    caption = f"<b>{escape(title)}</b>"
    if price is not None:
        caption += f"\n💰 {format_price_pln(price)}"
    caption += f"\n\n{t(lang, 'visual.caption')}\n\n{t(lang, 'visual.pick')}"
    await send_photo_card(callback.message, image, caption, keyboard)
