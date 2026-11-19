"""Configurator handlers.

Responsibilities are deliberately thin: parse the tapped value, validate it,
write it into the FSM data and ask the flow module what comes next. All
ordering logic lives in ``app.bot.flows.configurator``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import (
    PICK_PREFIX,
    VALUE_AUTO,
    VALUE_BACK_TO_LIST,
    VALUE_CLEAR,
    VALUE_CUSTOM,
    VALUE_DONE,
    VALUE_GENERATE,
    VALUE_ORDER,
    VALUE_ORDER_BACK,
    VALUE_ORDER_CONFIRM,
    VALUE_SAVE,
    VALUE_SKIP,
    CfgCB,
    MenuAction,
    MenuCB,
    NavAction,
    NavCB,
)
from app.bot.flows.configurator import (
    FIRST_STEP,
    MONITOR_OPTIONS_KEY,
    PICK_CATEGORY_KEY,
    PICK_OPTIONS_KEY,
    PREFILLED_KEY,
    Answers,
    StepId,
    build_requirements,
    next_step,
    pop_history,
    push_history,
)
from app.bot.handlers import visual as visual_handlers
from app.bot.handlers.visual import Kind, ai_caption, send_ai_visualization, visual_button
from app.bot.keyboards.common import back_to_menu_kb, main_menu_kb, markup, nav_row
from app.bot.keyboards.configurator import keyboard_for_step, order_confirm_kb
from app.bot.states import Configurator
from app.bot.utils import safe_edit, send_photo_card, show_photo
from app.bot.views.admin import render_blocked_custom_order
from app.bot.views.build import (
    components_payload,
    render_build_card,
    render_no_build,
    render_order_blocked,
)
from app.bot.views.configurator import (
    estimate_prices,
    render_budget_error,
    render_order_confirmation,
    render_question,
    render_summary,
)
from app.config import Settings, get_settings
from app.db.models import EventName, User
from app.db.repositories import BuildRepository
from app.domain.components import Component, ComponentCategory
from app.domain.enums import (
    MAX_BUDGET_PLN,
    MAX_PRIORITIES,
    MIN_BUDGET_PLN,
    Aesthetics,
    CpuBrand,
    GpuBrand,
    Priority,
    Purpose,
    Resolution,
    TargetFps,
)
from app.domain.labels import format_price_pln
from app.domain.requirements import MAX_GAME_NAME_LEN, MAX_GAMES, BuildRequirements
from app.i18n import t
from app.services.analytics import AnalyticsService
from app.services.catalog import get_catalog
from app.services.compatibility.gate import GateResult, check_components
from app.services.leads import LeadService
from app.services.media import BUILD_IMAGE_DIR, default_preset, render_build_image
from app.services.media.brand import BrandAsset, get_brand_assets
from app.services.media.build_image import render_build_thumbnail
from app.services.media.catalog_grid import GridEntry, render_catalog_grid
from app.services.notifications import AdminNotifier
from app.services.recommendation import BuildOption, BuildService, Parts
from app.services.recommendation.setup import (
    PERIPHERAL_CATEGORIES,
    SetupSelection,
    monitor_options,
    resolve,
    suggest_for,
    with_setup,
)

logger = logging.getLogger(__name__)

router = Router(name="configurator")

CURRENT_STEP_KEY = "current_step"

#: Products offered per peripheral category. More than this and the numbered
#: keyboard stops fitting on a phone.
MAX_PICK_OPTIONS = 10

#: Steps whose answer is a plain enum value stored under a single key.
_ENUM_STEPS: dict[StepId, tuple[str, Any]] = {
    StepId.PURPOSE: ("purpose", Purpose),
    StepId.RESOLUTION: ("resolution", Resolution),
    StepId.FPS: ("target_fps", TargetFps),
    StepId.AESTHETICS: ("aesthetics", Aesthetics),
    StepId.CPU: ("cpu_brand", CpuBrand),
    StepId.GPU: ("gpu_brand", GpuBrand),
}

_CONNECTIVITY_MAP: dict[str, tuple[bool, bool]] = {
    "wifi_bt": (True, True),
    "wifi": (True, False),
    "bt": (False, True),
    "none": (False, False),
}


# --- helpers -----------------------------------------------------------------


def parse_budget(text: str) -> int | None:
    """Extract a PLN amount from free text, e.g. 5 500 zl -> 5500."""
    digits = re.sub(r"[^\d]", "", text or "")
    if not digits or len(digits) > 7:
        return None
    value = int(digits)
    if not MIN_BUDGET_PLN <= value <= MAX_BUDGET_PLN:
        return None
    return value


def _safe_int(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def _reset_gaming_answers(answers: Answers, purpose: Purpose) -> None:
    """Switching to a non-gaming purpose drops answers that no longer apply."""
    if not purpose.is_gaming:
        answers.pop("games", None)
        answers.pop("target_fps", None)


async def _load_state(state: FSMContext) -> tuple[StepId, Answers]:
    answers = await state.get_data()
    try:
        step = StepId(answers.get(CURRENT_STEP_KEY, FIRST_STEP.value))
    except ValueError:  # pragma: no cover - corrupted state
        step = FIRST_STEP
    return step, answers


def _partial_requirements(answers: Answers) -> BuildRequirements:
    """Requirements from what has been answered so far.

    The setup steps run before the summary, so the answer set is complete
    enough for taste (colour, RGB, quiet) but is validated leniently: a
    missing field must not break a picker.
    """
    try:
        return build_requirements(answers)
    except (ValidationError, KeyError, ValueError):
        return BuildRequirements(
            budget_pln=int(answers.get("budget_pln") or MIN_BUDGET_PLN),
            purpose=Purpose(answers.get("purpose") or Purpose.UNIVERSAL),
        )


def _prepare_step(step: StepId, answers: Answers) -> bool:
    """Fill in whatever the step needs to be answerable. True when it changed.

    The monitor step offers a shortlist and its buttons carry a position in
    that list, so the list has to exist in the FSM before the customer can
    tap anything. It is recomputed every time the step is shown: they may
    have gone back and changed the resolution the offer depends on.
    """
    if step is StepId.PERIPHERALS:
        open_category = answers.get(PICK_CATEGORY_KEY)
        if not open_category:
            return answers.pop(PICK_OPTIONS_KEY, None) is not None
        offered = [c.id for c in _category_offer(open_category, answers)]
        if answers.get(PICK_OPTIONS_KEY) == offered:
            return False
        answers[PICK_OPTIONS_KEY] = offered
        return True

    if step is not StepId.MONITOR:
        return False
    offered = [component.id for component in monitor_options(_partial_requirements(answers))]
    if answers.get(MONITOR_OPTIONS_KEY) == offered:
        return False
    answers[MONITOR_OPTIONS_KEY] = offered
    return True


def _category_offer(category_value: str, answers: Answers) -> list[Component]:
    """Everything on offer in this category, the best fit for the build first.

    The old behaviour picked one model silently; that judgement survives as
    the ordering, so the recommendation is still the first thing they see.
    """
    try:
        category = ComponentCategory(category_value)
    except ValueError:
        return []
    catalog = get_catalog()
    items = [c for c in catalog.by_category(category) if not c.discontinued]
    suggested = suggest_for(category, _partial_requirements(answers))
    if suggested is not None:
        items.sort(key=lambda c: (c.id != suggested.id, c.name))
    return items[:MAX_PICK_OPTIONS]


async def _step_grid(
    step: StepId, answers: Answers, session: AsyncSession, lang: str
) -> Path | None:
    """A contact sheet of what this step is about, or ``None``.

    The monitor step shows what is on offer, in the order the buttons are
    numbered; the peripherals step shows what has been picked so far.
    """
    catalog = get_catalog()
    if step is StepId.MONITOR:
        offered = answers.get(MONITOR_OPTIONS_KEY) or []
        components = [c for c in (catalog.get(cid) for cid in offered) if c is not None]
        title = t(lang, "part.monitor")
    elif step is StepId.PERIPHERALS:
        open_category = answers.get(PICK_CATEGORY_KEY)
        if open_category:
            # Browsing a category: show what is on offer, in button order.
            offered = answers.get(PICK_OPTIONS_KEY) or []
            components = [c for c in (catalog.get(cid) for cid in offered) if c is not None]
            title = t(lang, f"part.{open_category}")
        else:
            setup = answers.get("setup") or {}
            picked = [cid for c, cid in setup.items() if c != ComponentCategory.MONITOR.value]
            components = [c for c in (catalog.get(cid) for cid in picked) if c is not None]
            title = t(lang, "setup.title")
    else:
        return None

    if not components:
        return None

    photos = await visual_handlers.component_image_paths(session, components)
    if not photos:
        return None

    prices = estimate_prices()
    entries = [
        GridEntry(
            index=index,
            name=component.name,
            price_text=(
                f"≈{format_price_pln(prices[component.id])}" if component.id in prices else "—"
            ),
            image_path=photos.get(component.id),
        )
        for index, component in enumerate(components, start=1)
    ]
    try:
        return render_catalog_grid(
            title, entries, output_dir=BUILD_IMAGE_DIR, footer=t(lang, "visual.image_footer")
        )
    except Exception:
        logger.exception("Could not render the %s step grid", step.value)
        return None


async def _show_step(
    event: CallbackQuery | Message,
    step: StepId,
    answers: Answers,
    lang: str,
    state: FSMContext | None = None,
    session: AsyncSession | None = None,
) -> None:
    """Render a step, persisting anything it had to prepare first.

    ``state`` is not optional in practice - a step that prepares data and
    does not save it is exactly the bug this signature exists to prevent -
    but it stays keyword-defaulted so a pure re-render can skip the write.
    """
    if _prepare_step(step, answers) and state is not None:
        await state.set_data(answers)
    text = render_question(step, answers, lang)
    keyboard = keyboard_for_step(step, answers, lang)

    if isinstance(event, CallbackQuery):
        if session is not None:
            grid = await _step_grid(step, answers, session, lang)
            if grid is not None:
                await show_photo(event, grid, text, keyboard)
                return
        await safe_edit(event, text, keyboard)
    else:
        await event.answer(text, reply_markup=keyboard)


async def _goto(
    event: CallbackQuery | Message,
    state: FSMContext,
    step: StepId,
    answers: Answers,
    lang: str,
    session: AsyncSession | None = None,
) -> None:
    push_history(answers, step)
    answers[CURRENT_STEP_KEY] = step.value
    await state.set_state(Configurator.active)
    await state.set_data(answers)
    await _show_step(event, step, answers, lang, state, session)


async def start_configurator(
    event: CallbackQuery | Message,
    state: FSMContext,
    session: AsyncSession,
    lang: str,
    telegram_id: int,
    prefilled: Answers | None = None,
) -> None:
    await state.clear()
    answers: Answers = dict(prefilled or {})
    entry = answers.get(PREFILLED_KEY)
    await AnalyticsService(session).track(
        telegram_id, EventName.CONFIGURATOR_STARTED, entry=entry or "menu"
    )
    if await _start_with_brand(event, state, answers, lang, session):
        return
    await _goto(event, state, FIRST_STEP, answers, lang)


async def _start_with_brand(
    event: CallbackQuery | Message,
    state: FSMContext,
    answers: Answers,
    lang: str,
    session: AsyncSession | None = None,
) -> bool:
    """Open the configurator under the brand header: the first question is the
    photo's caption, and every later step edits that caption in place.

    Returns False when the brand image is unavailable or was shown to this
    chat recently; the caller then opens the plain text flow.
    """
    target = event if isinstance(event, Message) else event.message
    if not isinstance(target, Message):
        return False
    brand = get_brand_assets()
    if not brand.available(BrandAsset.HEADER) or not brand.should_send(
        target.chat.id, BrandAsset.HEADER
    ):
        return False

    push_history(answers, FIRST_STEP)
    answers[CURRENT_STEP_KEY] = FIRST_STEP.value
    await state.set_state(Configurator.active)
    await state.set_data(answers)

    text = render_question(FIRST_STEP, answers, lang)
    keyboard = keyboard_for_step(FIRST_STEP, answers, lang)
    if not await brand.send(target, BrandAsset.HEADER, text, keyboard):
        await _show_step(event, FIRST_STEP, answers, lang, state, session)
    return True


async def _advance(
    event: CallbackQuery | Message,
    state: FSMContext,
    current: StepId,
    answers: Answers,
    lang: str,
    session: AsyncSession,
    user: User | None,
    telegram_id: int,
) -> None:
    await AnalyticsService(session).track(
        telegram_id, EventName.CONFIGURATOR_STEP, step=current.value
    )
    upcoming = next_step(current, answers)
    if upcoming is StepId.SUMMARY:
        await _show_summary(event, state, answers, lang, session, user, telegram_id)
        return
    await _goto(event, state, upcoming, answers, lang)


async def _show_summary(
    event: CallbackQuery | Message,
    state: FSMContext,
    answers: Answers,
    lang: str,
    session: AsyncSession,
    user: User | None,
    telegram_id: int,
) -> None:
    try:
        requirements = build_requirements(answers)
    except (ValidationError, KeyError, ValueError):
        logger.warning("Incomplete configurator answers, restarting", exc_info=True)
        await start_configurator(event, state, session, lang, telegram_id)
        return

    if user is not None:
        build = await BuildRepository(session).create_draft(user.id, requirements)
        answers["build_id"] = build.id

    await AnalyticsService(session).track(
        telegram_id,
        EventName.CONFIGURATOR_COMPLETED,
        budget=requirements.budget_pln,
        purpose=requirements.purpose.value,
        resolution=requirements.resolution.value,
        games=len(requirements.games),
    )

    push_history(answers, StepId.SUMMARY)
    answers[CURRENT_STEP_KEY] = StepId.SUMMARY.value
    await state.set_state(Configurator.active)
    await state.set_data(answers)

    options = _summary_options(requirements)
    text = render_summary(requirements, lang, answers, options)
    keyboard = keyboard_for_step(StepId.SUMMARY, answers, lang)

    preview = await _variants_preview(options, requirements, lang, session)
    if preview is not None and isinstance(event, CallbackQuery):
        await show_photo(event, preview, text, keyboard)
        return
    if isinstance(event, CallbackQuery):
        await safe_edit(event, text, keyboard)
    else:
        await event.answer(text, reply_markup=keyboard)


def _summary_options(requirements: BuildRequirements) -> list[BuildOption]:
    """The builds these requirements allow. Local and free - never an API call."""
    try:
        return BuildService().build_options(requirements)
    except Exception:
        logger.exception("Could not price the summary variants")
        return []


async def _variants_preview(
    options: list[BuildOption],
    requirements: BuildRequirements,
    lang: str,
    session: AsyncSession | None = None,
) -> Path | None:
    """One picture of the variants on offer, drawn locally.

    Deliberately the schematic renderer rather than the photographic one: a
    customer may reach this screen many times while adjusting answers, and
    each distinct machine would otherwise be a paid render. The photograph
    is still produced - once - for the build they go on to choose.
    """
    if not options:
        return None
    visualizer = visual_handlers.get_visualizer()
    entries: list[GridEntry] = []
    for index, option in enumerate(options, start=1):
        preset = default_preset(option.parts, requirements.aesthetics)
        image: Path | None = None
        if session is not None:
            # A machine the library has already photographed shows its real
            # picture; this costs nothing and improves as the library grows.
            wants = [p.value for p in requirements.priorities]
            stored = await visualizer.status_for(session, option.parts, preset, wants)
            if stored is not None and stored.is_ready:
                candidate = Path(stored.image_path or "")
                if candidate.is_file():
                    image = candidate
        try:
            image = image or render_build_thumbnail(
                option.parts, preset, output_dir=BUILD_IMAGE_DIR
            )
        except Exception:
            logger.exception("Could not draw the %s variant", option.tier.value)
            continue
        entries.append(
            GridEntry(
                index=index,
                name=t(lang, f"build.tier.{option.tier.value}"),
                price_text=format_price_pln(option.client_price_pln),
                image_path=image,
            )
        )
    if not entries:
        return None
    try:
        return render_catalog_grid(
            t(lang, "summary.variants"),
            entries,
            output_dir=BUILD_IMAGE_DIR,
            footer=t(lang, "visual.image_footer"),
        )
    except Exception:
        logger.exception("Could not render the variants preview")
        return None


# --- entry points -------------------------------------------------------------


@router.message(Command("build", "budget"))
async def cmd_build(message: Message, state: FSMContext, session: AsyncSession, lang: str) -> None:
    if message.from_user is None:
        return
    await start_configurator(message, state, session, lang, message.from_user.id)


@router.callback_query(
    MenuCB.filter(F.action.in_({MenuAction.BUILD, MenuAction.BUDGET, MenuAction.GAMES}))
)
async def menu_start(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    session: AsyncSession,
    lang: str,
) -> None:
    prefilled: Answers | None = None
    if callback_data.action == MenuAction.GAMES:
        prefilled = {
            "purpose": Purpose.GAMING.value,
            PREFILLED_KEY: [StepId.PURPOSE.value],
        }

    await start_configurator(callback, state, session, lang, callback.from_user.id, prefilled)
    await callback.answer()


# --- navigation ---------------------------------------------------------------


@router.callback_query(Configurator.active, NavCB.filter(F.action == NavAction.RESTART))
async def nav_restart(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    await start_configurator(callback, state, session, lang, callback.from_user.id)
    await callback.answer()


@router.callback_query(Configurator.active, NavCB.filter(F.action == NavAction.CANCEL))
@router.callback_query(Configurator.waiting_budget, NavCB.filter(F.action == NavAction.CANCEL))
@router.callback_query(Configurator.waiting_game, NavCB.filter(F.action == NavAction.CANCEL))
async def nav_cancel(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    await AnalyticsService(session).track(callback.from_user.id, EventName.CONFIGURATOR_CANCELLED)
    await state.clear()
    await safe_edit(callback, t(lang, "common.cancelled"), main_menu_kb(lang))
    await callback.answer()


@router.callback_query(Configurator.active, NavCB.filter(F.action == NavAction.BACK))
async def nav_back(
    callback: CallbackQuery, state: FSMContext, lang: str, session: AsyncSession
) -> None:
    _, answers = await _load_state(state)
    previous = pop_history(answers)

    if previous is None:
        # Already at the first question: "Back" means leaving the configurator.
        await state.clear()
        await safe_edit(callback, t(lang, "menu.prompt"), main_menu_kb(lang))
        await callback.answer()
        return

    answers[CURRENT_STEP_KEY] = previous.value
    await state.set_data(answers)
    await _show_step(callback, previous, answers, lang, state, session)
    await callback.answer()


@router.callback_query(Configurator.waiting_budget, NavCB.filter(F.action == NavAction.BACK))
@router.callback_query(Configurator.waiting_game, NavCB.filter(F.action == NavAction.BACK))
async def nav_back_from_text_input(
    callback: CallbackQuery, state: FSMContext, lang: str, session: AsyncSession
) -> None:
    """Leaving a free-text prompt returns to the step that opened it."""
    step, answers = await _load_state(state)
    await state.set_state(Configurator.active)
    await _show_step(callback, step, answers, lang, state, session)
    await callback.answer()


# --- answers ------------------------------------------------------------------


async def _handle_summary_action(
    callback: CallbackQuery,
    value: str,
    answers: Answers,
    lang: str,
    session: AsyncSession,
    user: User | None,
    settings: Settings | None,
    telegram_id: int,
) -> None:
    """Actions offered on the final card.

    Ordering is a two-step action - card, then an explicit confirmation - so a
    mis-tap on a phone cannot create a lead the customer did not intend.
    """
    if not isinstance(callback.message, Message):
        return

    requirements = _safe_requirements(answers)

    if value == VALUE_ORDER:
        if requirements is None:
            await callback.message.answer(
                t(lang, "order.expired"), reply_markup=back_to_menu_kb(lang)
            )
            return
        confirmation = render_order_confirmation(requirements, lang)
        confirm_kb = order_confirm_kb(lang)
        # On a text-only screen the confirmation arrives under the brand image;
        # inside a photo caption (brand header / build card) it edits in place.
        if not callback.message.photo and await get_brand_assets().send(
            callback.message, BrandAsset.ORDER_CONFIRMATION, confirmation, confirm_kb
        ):
            return
        await safe_edit(callback, confirmation, confirm_kb)
        return

    if value == VALUE_ORDER_CONFIRM:
        await _create_lead(callback, answers, lang, session, user, settings)
        return

    if value == VALUE_ORDER_BACK:
        if requirements is None:
            await callback.message.answer(
                t(lang, "order.expired"), reply_markup=back_to_menu_kb(lang)
            )
            return
        await safe_edit(
            callback,
            render_summary(requirements, lang, answers),
            keyboard_for_step(StepId.SUMMARY, answers, lang),
        )
        return

    if value == VALUE_SAVE:
        await _save_build(callback, answers, lang, session)
        return

    await _generate_build(callback, answers, lang, session, user, telegram_id)


async def _generate_build(
    callback: CallbackQuery,
    answers: Answers,
    lang: str,
    session: AsyncSession,
    user: User | None,
    telegram_id: int,
) -> None:
    """Run the recommendation engine and show a real, priced build card."""
    if not isinstance(callback.message, Message):
        return

    requirements = _safe_requirements(answers)
    if requirements is None:
        await callback.message.answer(t(lang, "order.expired"), reply_markup=back_to_menu_kb(lang))
        return

    service = BuildService()
    try:
        option = service.recommended_option(requirements)
    except Exception:
        # A generator failure is ours, not the customer's: log the detail,
        # show them a plain message.
        logger.exception("Build generation failed for telegram_id=%s", telegram_id)
        await callback.message.answer(
            t(lang, "build.none_generic"), reply_markup=back_to_menu_kb(lang)
        )
        return

    if option is None:
        minimum = service.minimum_customer_price_pln(requirements)
        await callback.message.answer(
            render_no_build(minimum, lang), reply_markup=back_to_menu_kb(lang)
        )
        return

    await _persist_build(session, answers, option, _setup_selection(answers, service))
    # Frozen commercial breakdown travels with the draft so the lead can
    # snapshot exactly what this build was supposed to earn.
    answers["pricing_snapshot"] = option.quote.as_snapshot()
    await AnalyticsService(session).track(
        telegram_id,
        EventName.BUILD_GENERATED,
        tier=option.tier.value,
        total_pln=float(option.customer_total_pln),
    )

    selection = _setup_selection(answers, service)
    # The desk joins the parts map, so the picture and its fingerprint cover
    # the monitor and peripherals the customer actually chose.
    shown_parts = with_setup(option.parts, selection)
    caption = render_build_card(option, lang, selection)
    keyboard = keyboard_for_step(StepId.SUMMARY, answers, lang)
    build_id = answers.get("build_id")
    if build_id is not None:
        keyboard = markup(
            [visual_button(Kind.BUILD, int(build_id), lang)], *keyboard.inline_keyboard
        )

    try:
        image = render_build_image(
            t(lang, f"build.tier.{option.tier.value}"),
            shown_parts,
            option.customer_total_pln + selection.total_pln,
            footer=t(lang, "visual.image_footer"),
            output_dir=BUILD_IMAGE_DIR,
        )
    except Exception:
        logger.exception("Could not render an image for the generated build")
        # No build picture: the brand image keeps the card visual, text otherwise.
        if not await get_brand_assets().send(
            callback.message, BrandAsset.BUILD_DEFAULT, caption, keyboard, respect_cooldown=False
        ):
            await callback.message.answer(caption, reply_markup=keyboard)
        await _send_build_visualization(
            callback.message, session, option, answers, lang, shown_parts
        )
        return

    await send_photo_card(callback.message, image, caption, keyboard)
    await _send_build_visualization(callback.message, session, option, answers, lang, shown_parts)


async def _send_build_visualization(
    message: Message,
    session: AsyncSession,
    option: BuildOption,
    answers: Answers,
    lang: str,
    parts: Parts | None = None,
) -> None:
    """After the card: what this exact machine will look like, before ordering.

    The card above already carries the parts, the price and the order button,
    so a slow or failed render costs the customer nothing but the picture.
    """
    requirements = _safe_requirements(answers)
    aesthetics = requirements.aesthetics if requirements is not None else None
    # The desk is part of the picture when the customer chose one.
    shown = parts if parts is not None else option.parts
    preset = default_preset(shown, aesthetics)
    build_id = answers.get("build_id")
    keyboard = markup(
        [_summary_button(VALUE_ORDER, t(lang, "order.button"))],
        [
            InlineKeyboardButton(
                text=t(lang, "visual.btn_change"),
                callback_data=NavCB(action=NavAction.BACK).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=t(lang, "nav.menu"), callback_data=NavCB(action=NavAction.MENU).pack()
            )
        ],
    )
    try:
        await send_ai_visualization(
            message,
            session,
            shown,
            preset,
            # What the customer said they care about shapes the photograph
            # too, so it belongs in the key that finds or buys it.
            priorities=[p.value for p in requirements.priorities] if requirements else None,
            caption=ai_caption(t(lang, "visual.ai_title"), option.client_price_pln, lang),
            keyboard=keyboard,
            lang=lang,
            build_id=int(build_id) if build_id is not None else None,
        )
    except Exception:
        # Belt and braces: nothing about a picture may break the configurator.
        logger.exception("Build visualisation failed unexpectedly")


def _summary_button(value: str, text: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=CfgCB(step=StepId.SUMMARY.value, value=value).pack()
    )


def _setup_selection(answers: Answers, service: BuildService) -> SetupSelection:
    """What the customer added around the tower, priced from the same book."""
    return resolve(answers.get("setup"), catalog=service.catalog, prices=service.price_book())


async def _persist_build(
    session: AsyncSession,
    answers: Answers,
    option: BuildOption,
    setup: SetupSelection | None = None,
) -> None:
    """Store the generated parts and the customer price on the draft build.

    The desk is stored with the machine: the admin who fulfils the order has
    to see the monitor and the peripherals that were quoted, and the price
    on the row has to be the one the customer was shown.
    """
    build_id = answers.get("build_id")
    if build_id is None:
        return
    build = await BuildRepository(session).get(build_id)
    if build is None:
        return

    extras = setup or SetupSelection()
    build.tier = option.tier.value
    build.title = f"AmigoZT {t('en', f'build.tier.{option.tier.value}').split(' ', 1)[-1]}"
    build.components = {**components_payload(option), **extras.as_payload()}
    build.total_price_pln = option.client_price_pln + extras.total_pln


def _safe_requirements(answers: Answers) -> BuildRequirements | None:
    try:
        return build_requirements(answers)
    except (ValidationError, KeyError, ValueError):
        logger.warning("Summary action on incomplete answers", exc_info=True)
        return None


async def _save_build(
    callback: CallbackQuery, answers: Answers, lang: str, session: AsyncSession
) -> None:
    build_id = answers.get("build_id")
    if build_id is None:
        return
    build = await BuildRepository(session).get(build_id)
    if build is None:
        return
    build.is_saved = True
    await AnalyticsService(session).track(
        callback.from_user.id, EventName.BUILD_SAVED, build_id=build_id
    )
    await callback.answer(t(lang, "nav.done"))


def order_blocked_kb(lang: str) -> InlineKeyboardMarkup:
    """Offered when the pre-order check fails: pick again, or leave."""
    return markup(
        [
            InlineKeyboardButton(
                text=t(lang, "order.btn_regenerate"),
                callback_data=CfgCB(step=StepId.SUMMARY.value, value=VALUE_GENERATE).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=t(lang, "nav.menu"), callback_data=NavCB(action=NavAction.MENU).pack()
            )
        ],
    )


async def _create_lead(
    callback: CallbackQuery,
    answers: Answers,
    lang: str,
    session: AsyncSession,
    user: User | None,
    settings: Settings | None,
) -> None:
    """Turns the finished configuration into a lead and alerts the admins."""
    if not isinstance(callback.message, Message):
        return

    build_id = answers.get("build_id")
    if user is None or build_id is None:
        await callback.message.answer(t(lang, "order.expired"), reply_markup=back_to_menu_kb(lang))
        return

    telegram_id = callback.from_user.id
    analytics = AnalyticsService(session)
    await analytics.track(telegram_id, EventName.ORDER_CLICKED, build_id=build_id)

    # The gate: the stored parts are resolved and checked again right now.
    # A build that is not physically and electrically buildable never
    # becomes a lead, whatever the card said when it was generated.
    stored = await BuildRepository(session).get(build_id)
    gate: GateResult | None = None
    if stored is not None and stored.components:
        gate = check_components(stored.components)
        if not gate.compatible:
            await callback.message.answer(
                render_order_blocked(gate.customer_reason_codes(), lang),
                reply_markup=order_blocked_kb(lang),
            )
            admin_ids = settings.admin_ids if settings is not None else get_settings().admin_ids
            if callback.bot is not None:
                await AdminNotifier(callback.bot, admin_ids).notify_text(
                    render_blocked_custom_order(int(build_id), telegram_id, gate.snapshot())
                )
            return

    lead, build, created = await LeadService(session).request_order(
        user,
        build_id,
        pricing_snapshot=answers.get("pricing_snapshot"),
        compatibility_snapshot=gate.snapshot() if gate is not None else None,
    )

    if not created:
        await callback.message.answer(
            t(lang, "order.exists", lead_id=lead.id), reply_markup=back_to_menu_kb(lang)
        )
        return

    await analytics.track(telegram_id, EventName.LEAD_CREATED, lead_id=lead.id)

    # Commit before notifying: an admin must never receive a card for a lead
    # that a later rollback would erase. The middleware's commit is then a no-op.
    await session.commit()

    created_text = t(lang, "order.created", lead_id=lead.id)
    if not await get_brand_assets().send(
        callback.message, BrandAsset.ORDER_CONFIRMATION, created_text, back_to_menu_kb(lang)
    ):
        await callback.message.answer(created_text, reply_markup=back_to_menu_kb(lang))

    admin_ids = settings.admin_ids if settings is not None else get_settings().admin_ids
    if callback.bot is not None:
        await AdminNotifier(callback.bot, admin_ids).notify_new_lead(lead, user, build)


@router.callback_query(Configurator.active, CfgCB.filter())
async def on_answer(
    callback: CallbackQuery,
    callback_data: CfgCB,
    state: FSMContext,
    session: AsyncSession,
    lang: str,
    user: User | None = None,
    settings: Settings | None = None,
) -> None:
    step, answers = await _load_state(state)
    telegram_id = callback.from_user.id

    # A tap on a stale message must not overwrite an answer given since.
    if callback_data.step != step.value:
        await callback.answer()
        return

    value = callback_data.value

    match step:
        case StepId.BUDGET:
            if value == VALUE_CUSTOM:
                await state.set_state(Configurator.waiting_budget)
                await safe_edit(
                    callback, t(lang, "cfg.budget.custom_prompt"), markup(nav_row(lang))
                )
                await callback.answer()
                return
            budget = parse_budget(value)
            if budget is None:
                await callback.answer()
                return
            answers["budget_pln"] = budget

        case StepId.GAMES:
            if value == VALUE_CUSTOM:
                await state.set_state(Configurator.waiting_game)
                await safe_edit(callback, t(lang, "cfg.games.custom_prompt"), markup(nav_row(lang)))
                await callback.answer()
                return
            if value != VALUE_DONE:
                games: list[str] = list(answers.get("games") or [])
                if value in games:
                    games.remove(value)
                elif len(games) >= MAX_GAMES:
                    await callback.answer(t(lang, "cfg.games.limit", max=MAX_GAMES))
                    return
                else:
                    games.append(value)
                answers["games"] = games
                await state.set_data(answers)
                await _show_step(callback, step, answers, lang, state, session)
                await callback.answer()
                return

        case StepId.PRIORITY:
            if value != VALUE_DONE:
                chosen: list[str] = list(answers.get("priorities") or [])
                try:
                    picked = Priority(value)
                except ValueError:
                    await callback.answer()
                    return
                if picked.value in chosen:
                    chosen.remove(picked.value)
                elif len(chosen) >= MAX_PRIORITIES:
                    await callback.answer(t(lang, "cfg.priority.limit", max=MAX_PRIORITIES))
                    return
                else:
                    chosen.append(picked.value)
                answers["priorities"] = chosen
                # The primary priority mirrors the first tick, so everything
                # written against the single-choice flow keeps working.
                answers["priority"] = chosen[0] if chosen else None
                await state.set_data(answers)
                await _show_step(callback, step, answers, lang, state, session)
                await callback.answer()
                return
            if not answers.get("priorities"):
                await callback.answer(t(lang, "cfg.priority.pick_one"))
                return

        case StepId.MONITOR:
            if value == VALUE_SKIP:
                # "No monitor": forget any screen that was ticked, then move on.
                answers.setdefault("setup", {}).pop(ComponentCategory.MONITOR.value, None)
            elif value != VALUE_DONE:
                offered: list[str] = answers.get(MONITOR_OPTIONS_KEY) or []
                index = _safe_int(value)
                if index is None or not 0 <= index < len(offered):
                    await callback.answer()
                    return
                setup: dict[str, str] = dict(answers.get("setup") or {})
                monitor_id = offered[index]
                if setup.get(ComponentCategory.MONITOR.value) == monitor_id:
                    setup.pop(ComponentCategory.MONITOR.value, None)
                else:
                    setup[ComponentCategory.MONITOR.value] = monitor_id
                answers["setup"] = setup
                await state.set_data(answers)
                await _show_step(callback, step, answers, lang, state, session)
                await callback.answer()
                return
            # VALUE_DONE keeps the chosen screen; both fall through to advance.

        case StepId.PERIPHERALS:
            open_category = answers.get(PICK_CATEGORY_KEY)

            if value == VALUE_BACK_TO_LIST:
                answers.pop(PICK_CATEGORY_KEY, None)
                await state.set_data(answers)
                await _show_step(callback, step, answers, lang, state, session)
                await callback.answer()
                return

            if value == VALUE_CLEAR and open_category:
                setup_now: dict[str, str] = dict(answers.get("setup") or {})
                setup_now.pop(open_category, None)
                answers["setup"] = setup_now
                answers.pop(PICK_CATEGORY_KEY, None)
                await state.set_data(answers)
                await _show_step(callback, step, answers, lang, state, session)
                await callback.answer()
                return

            if open_category and value.startswith(PICK_PREFIX):
                offered_ids: list[str] = answers.get(PICK_OPTIONS_KEY) or []
                position = _safe_int(value[len(PICK_PREFIX) :])
                if position is None or not 0 <= position < len(offered_ids):
                    await callback.answer()
                    return
                picked_setup: dict[str, str] = dict(answers.get("setup") or {})
                picked_setup[open_category] = offered_ids[position]
                answers["setup"] = picked_setup
                # Chosen: close the shelf and show the category list again.
                answers.pop(PICK_CATEGORY_KEY, None)
                await state.set_data(answers)
                await _show_step(callback, step, answers, lang, state, session)
                await callback.answer()
                return

            if value != VALUE_DONE:
                try:
                    category = ComponentCategory(value)
                except ValueError:
                    await callback.answer()
                    return
                if category not in PERIPHERAL_CATEGORIES:
                    await callback.answer()
                    return
                if not _category_offer(category.value, answers):
                    await callback.answer(t(lang, "cfg.peripherals.none"))
                    return
                # Open that category rather than deciding for the customer.
                answers[PICK_CATEGORY_KEY] = category.value
                await state.set_data(answers)
                await _show_step(callback, step, answers, lang, state, session)
                await callback.answer()
                return

            # Done: leave any open shelf behind before advancing.
            answers.pop(PICK_CATEGORY_KEY, None)
            answers.pop(PICK_OPTIONS_KEY, None)

        case StepId.CONNECTIVITY:
            mapping = _CONNECTIVITY_MAP.get(value)
            if mapping is None:
                await callback.answer()
                return
            answers["wifi"], answers["bluetooth"] = mapping

        case StepId.STORAGE | StepId.RAM:
            key = "storage_gb" if step is StepId.STORAGE else "ram_gb"
            answers[key] = None if value == VALUE_AUTO else _safe_int(value)

        case StepId.SUMMARY:
            await callback.answer()
            await _handle_summary_action(
                callback, value, answers, lang, session, user, settings, telegram_id
            )
            return

        case _:
            mapped = _ENUM_STEPS.get(step)
            if mapped is None:
                await callback.answer()
                return
            key, enum_type = mapped
            try:
                answers[key] = enum_type(value).value
            except ValueError:
                logger.warning("Rejected value %r for step %s", value, step.value)
                await callback.answer()
                return
            if step is StepId.PURPOSE:
                _reset_gaming_answers(answers, Purpose(value))

    await callback.answer()
    await _advance(callback, state, step, answers, lang, session, user, telegram_id)


# --- free text ----------------------------------------------------------------


@router.message(Configurator.waiting_budget, F.text)
async def on_custom_budget(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    lang: str,
    user: User | None = None,
) -> None:
    if message.from_user is None:
        return

    budget = parse_budget(message.text or "")
    if budget is None:
        await message.answer(render_budget_error(lang), reply_markup=markup(nav_row(lang)))
        return

    _, answers = await _load_state(state)
    answers["budget_pln"] = budget
    await state.set_state(Configurator.active)
    await _advance(
        message, state, StepId.BUDGET, answers, lang, session, user, message.from_user.id
    )


@router.message(Configurator.waiting_game, F.text)
async def on_custom_game(
    message: Message, state: FSMContext, lang: str, session: AsyncSession
) -> None:
    title = " ".join((message.text or "").split())[:MAX_GAME_NAME_LEN]
    if not title:
        await message.answer(t(lang, "cfg.games.invalid"), reply_markup=markup(nav_row(lang)))
        return

    _, answers = await _load_state(state)
    games: list[str] = list(answers.get("games") or [])

    if len(games) >= MAX_GAMES:
        await message.answer(t(lang, "cfg.games.limit", max=MAX_GAMES))
    elif title not in games:
        games.append(title)
        answers["games"] = games

    await state.set_state(Configurator.active)
    await state.set_data(answers)
    await _show_step(message, StepId.GAMES, answers, lang, state, session)
