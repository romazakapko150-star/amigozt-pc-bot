"""Admin interface.

Authorization is applied to the router's observers rather than to individual
handlers, so nothing in this module can be reached by a non-admin - including
forged callback payloads.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import AdminAction, AdminCB, LeadAction, LeadCB, RankCB
from app.bot.filters import IsAdmin
from app.bot.handlers import visual as visual_handlers
from app.bot.keyboards.admin import (
    admin_home_kb,
    back_home_row,
    contact_link_kb,
    lead_actions_kb,
    leads_list_kb,
    rankings_kb,
)
from app.bot.keyboards.common import markup
from app.bot.utils import safe_edit
from app.bot.views.admin import (
    LEAD_NOT_FOUND,
    PANEL_TITLE,
    render_builds_list,
    render_lead_card,
    render_leads_list,
    render_rankings,
    render_stats,
    status_label,
)
from app.bot.views.visuals import render_visual_library
from app.config import get_settings
from app.db.models import Build, EventName
from app.db.repositories import (
    LeadRepository,
    ReadyBuildRepository,
    StatsRepository,
    VisualizationRepository,
)
from app.domain.enums import Aesthetics, LeadStatus
from app.services.analytics import AnalyticsService
from app.services.catalog import get_catalog
from app.services.compatibility.gate import parts_from_ids
from app.services.media import default_preset
from app.services.visuals import ComponentVisualizer
from app.services.visuals import batch as visual_batch

logger = logging.getLogger(__name__)

router = Router(name="admin")

# Every handler below is admin-only.
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

LEADS_PAGE_SIZE = 8
BUILDS_PAGE_SIZE = 10

#: Which status each admin action moves the lead to.
_ACTION_STATUS: dict[str, LeadStatus] = {
    LeadAction.TAKE: LeadStatus.IN_PROGRESS,
    LeadAction.CONTACT: LeadStatus.CONTACTED,
    LeadAction.REJECT: LeadStatus.CANCELLED,
    LeadAction.COMPLETE: LeadStatus.COMPLETED,
}


def _home_text() -> str:
    return (
        f"{PANEL_TITLE}\n\n"
        "Здесь видно новые заявки, последние сборки и статистику.\n"
        "Команды: /admin · /leads"
    )


# --- entry points -------------------------------------------------------------


@router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession) -> None:
    if message.from_user is not None:
        await AnalyticsService(session).track(message.from_user.id, EventName.ADMIN_OPENED)
    await message.answer(_home_text(), reply_markup=admin_home_kb())


@router.callback_query(AdminCB.filter())
async def admin_navigation(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    action = callback_data.action

    if action == AdminAction.HOME:
        await safe_edit(callback, _home_text(), admin_home_kb())
    elif action == AdminAction.LEADS:
        await safe_edit(callback, *await _leads_view(session))
    elif action == AdminAction.BUILDS:
        await safe_edit(callback, await _builds_text(session), markup(back_home_row()))
    elif action == AdminAction.STATS:
        stats = await StatsRepository(session).collect()
        await safe_edit(callback, render_stats(stats), markup(back_home_row()))
    elif action == AdminAction.RANKINGS:
        await _show_ranking(callback, session, "profit")

    await callback.answer()


RANKING_LIMIT = 10


async def _show_ranking(callback: CallbackQuery, session: AsyncSession, sort: str) -> None:
    builds = await ReadyBuildRepository(session).ranked(sort, limit=RANKING_LIMIT)
    await safe_edit(callback, render_rankings(sort, builds), rankings_kb(active=sort))


@router.callback_query(RankCB.filter())
async def ranking(callback: CallbackQuery, callback_data: RankCB, session: AsyncSession) -> None:
    await _show_ranking(callback, session, callback_data.sort)
    await callback.answer()


@router.message(Command("visuals"))
async def cmd_visuals(message: Message, session: AsyncSession) -> None:
    """Visual Library overview: coverage, cache hits, API calls, spend."""
    settings = get_settings()
    visualizer = visual_handlers.get_visualizer(settings)
    repo = VisualizationRepository(session)
    inv = await visual_batch.inventory(session, settings=settings)
    await message.answer(
        render_visual_library(
            inv.summary(),
            await repo.stats(),
            await repo.list_recent(10),
            enabled=visualizer.enabled,
            model=visualizer.model,
            cost_per_call=settings.ai_image_cost_usd,
            per_category=inv.by_category(),
        )
    )


@router.message(Command("visual_retry_failed"))
async def cmd_visual_retry_failed(message: Message, session: AsyncSession) -> None:
    """Retry visuals that previously failed - capped, one paid call each."""
    parts_arg = (message.text or "").split()
    limit = int(parts_arg[1]) if len(parts_arg) > 1 and parts_arg[1].isdigit() else 5
    limit = max(1, min(limit, 10))
    failed = await VisualizationRepository(session).list_failed(limit)
    if not failed:
        await message.answer("Проваленных визуализаций нет.")
        return
    await message.answer(
        f"⚠️ Повтор {len(failed)} визуализаций запускай через "
        "<code>python -m scripts.generate_visual_library --dry-run</code>, затем без --dry-run. "
        "В боте перегенерация — по одной: /visual_regen или /visual_regen_component."
    )


@router.message(Command("visual_disable"))
async def cmd_visual_disable(message: Message, session: AsyncSession) -> None:
    """Hide one visual from customers by fingerprint; the file is kept."""
    arg = (message.text or "").split(maxsplit=1)
    if len(arg) < 2:
        await message.answer("Использование: /visual_disable <fingerprint>")
        return
    repo = VisualizationRepository(session)
    row = await repo.get_by_fingerprint(arg[1].strip())
    if row is None:
        await message.answer("Визуализация с таким fingerprint не найдена.")
        return
    await repo.invalidate(row, "disabled by admin")
    await message.answer(
        f"🚫 Визуализация <code>{row.fingerprint}</code> скрыта. Файл сохранён, "
        "можно вернуть повторной генерацией."
    )


@router.message(Command("visual_regen_component"))
async def cmd_visual_regen_component(message: Message, session: AsyncSession) -> None:
    """Re-render one product's picture; the old one survives a failure."""
    arg = (message.text or "").split(maxsplit=1)
    if len(arg) < 2:
        await message.answer("Использование: /visual_regen_component <id компонента>")
        return
    component = get_catalog().get(arg[1].strip())
    if component is None:
        await message.answer("Компонент не найден в каталоге.")
        return
    visualizer = ComponentVisualizer.from_settings(get_settings())
    if not visualizer.enabled:
        await message.answer("AI-визуализация выключена или нет OPENAI_API_KEY.")
        return
    status = await message.answer(f"🎨 Перерисовываю <b>{component.name}</b>…")
    result = await visualizer.get_or_create(session, component, force=True, allow_generation=True)
    if result.ok and result.path is not None:
        await status.edit_text(f"✅ Готово · {result.api_calls} вызов(а) API")
        await message.answer_photo(FSInputFile(result.path), caption=component.name)
    else:
        await status.edit_text(
            f"❌ Не удалось: {result.error or 'неизвестная ошибка'}. Старое фото сохранено."
        )


@router.message(Command("visual_regen"))
async def cmd_visual_regen(message: Message, session: AsyncSession, lang: str) -> None:
    """Re-render one ready build's default look; the old image survives a failure."""
    argument = (message.text or "").split(maxsplit=1)
    if len(argument) < 2:
        await message.answer("Использование: /visual_regen <id или slug готовой сборки>")
        return
    target = argument[1].strip()
    repo = ReadyBuildRepository(session)
    ready = await repo.get(int(target)) if target.isdigit() else await repo.get_by_slug(target)
    if ready is None:
        await message.answer("Готовая сборка не найдена.")
        return

    parts, unknown = parts_from_ids(ready.components, get_catalog())
    if unknown:
        await message.answer(f"В сборке неизвестные компоненты: {', '.join(unknown)}")
        return
    try:
        aesthetics: Aesthetics | None = Aesthetics(ready.style)
    except ValueError:
        aesthetics = None
    preset = default_preset(parts, aesthetics)

    visualizer = visual_handlers.get_visualizer(get_settings())
    if not visualizer.enabled:
        await message.answer("AI-визуализация выключена или нет OPENAI_API_KEY.")
        return

    status = await message.answer(f"🎨 Перерисовываю <b>{ready.name}</b>…")
    result = await visualizer.get_or_create(
        session, parts, preset, ready_build_id=ready.id, force=True
    )
    if result.ok and result.path is not None:
        await status.edit_text(
            f"✅ Готово: <code>{result.fingerprint}</code> · {result.api_calls} вызов(а) API"
        )
        await message.answer_photo(FSInputFile(result.path), caption=f"{ready.name} · {preset.key}")
    else:
        await status.edit_text(
            f"❌ Не удалось: {result.error or 'неизвестная ошибка'}\n"
            "Старое изображение (если было) сохранено."
        )


@router.message(Command("leads"))
async def cmd_leads(message: Message, session: AsyncSession) -> None:
    text, keyboard = await _leads_view(session)
    await message.answer(text, reply_markup=keyboard)


# --- views --------------------------------------------------------------------


async def _leads_view(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    rows = await LeadRepository(session).list_recent(limit=LEADS_PAGE_SIZE)
    text = render_leads_list(rows)
    keyboard = leads_list_kb([lead for lead, _, _ in rows])
    return text, keyboard


async def _builds_text(session: AsyncSession) -> str:
    stmt = select(Build).order_by(Build.created_at.desc()).limit(BUILDS_PAGE_SIZE)
    builds = list(await session.scalars(stmt))
    return render_builds_list(builds)


# --- lead actions -------------------------------------------------------------


@router.callback_query(LeadCB.filter())
async def lead_action(
    callback: CallbackQuery, callback_data: LeadCB, session: AsyncSession
) -> None:
    repo = LeadRepository(session)
    context = await repo.load_context(callback_data.lead_id)

    if context is None:
        await callback.answer(LEAD_NOT_FOUND, show_alert=True)
        return

    lead, user, build = context
    action = callback_data.action
    admin_id = callback.from_user.id

    if action == LeadAction.CONTACT and lead.status_enum is LeadStatus.NEW:
        # Opening a brand-new lead should not silently mark it as contacted;
        # the admin gets the full card and decides.
        await safe_edit(callback, render_lead_card(lead, user, build), lead_actions_kb(lead))
        await callback.answer()
        return

    new_status = _ACTION_STATUS.get(action)
    if new_status is None:
        await callback.answer()
        return

    updated = await repo.set_status(lead.id, new_status, admin_id=admin_id)
    if updated is None:  # pragma: no cover - deleted between load and update
        await callback.answer(LEAD_NOT_FOUND, show_alert=True)
        return

    await AnalyticsService(session).track(
        admin_id,
        EventName.LEAD_STATUS_CHANGED,
        lead_id=lead.id,
        status=new_status.value,
    )
    logger.info("Lead #%s -> %s by admin %s", lead.id, new_status.value, admin_id)

    if action == LeadAction.CONTACT:
        await safe_edit(
            callback,
            render_lead_card(updated, user, build),
            contact_link_kb(user.telegram_id, user.username),
        )
    else:
        await safe_edit(callback, render_lead_card(updated, user, build), lead_actions_kb(updated))

    await callback.answer(status_label(new_status))
