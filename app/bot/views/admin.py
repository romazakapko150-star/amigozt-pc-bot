"""Admin-facing rendering.

The admin interface is internal tooling for the shop owner, so its chrome is
Russian only and deliberately stays out of ``app/i18n`` - translating it four
ways would be waste, and the locale-parity test would then be enforcing
something nobody reads. Enum labels still come from ``t()`` because they are
already translated for the customer side.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from html import escape

from app.bot.views.compatibility import render_compatibility, render_compatibility_short
from app.db.models import Build, Lead, ReadyBuild, User
from app.db.repositories.stats_repo import AdminStats
from app.domain.enums import LEAD_STATUS_BADGES, LeadStatus, Purpose
from app.domain.labels import format_price_pln, format_ram, format_storage
from app.domain.requirements import BuildRequirements
from app.i18n import t
from app.services.catalog import get_catalog
from app.services.compatibility.gate import check_components

#: Enum labels in the admin interface are rendered in this language.
ADMIN_LANG = "ru"

STATUS_TITLES: dict[LeadStatus, str] = {
    LeadStatus.NEW: "Новая",
    LeadStatus.IN_PROGRESS: "В работе",
    LeadStatus.CONTACTED: "Связались",
    LeadStatus.COMPLETED: "Завершена",
    LeadStatus.CANCELLED: "Отклонена",
}

PANEL_TITLE = "<b>AmigoZT PC — админ-панель</b>"
NO_LEADS = "Заявок пока нет."
NO_BUILDS = "Сборок пока нет."
LEAD_NOT_FOUND = "Заявка не найдена."

#: Phase 2 replaces this with the generated part list.
COMPONENTS_PENDING = "<i>подбор комплектующих подключается на следующем этапе</i>"


def status_label(status: LeadStatus) -> str:
    return f"{LEAD_STATUS_BADGES[status]} {STATUS_TITLES[status]}"


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.strftime("%d.%m.%Y %H:%M UTC")


def _customer_line(user: User) -> str:
    name = escape(user.first_name or "—")
    username = f"@{escape(user.username)}" if user.username else "без username"
    return f"{name} · {username} · <code>{user.telegram_id}</code>"


def _requirements_of(build: Build | None) -> BuildRequirements | None:
    if build is None or not build.requirements:
        return None
    try:
        return BuildRequirements(**build.requirements)
    except (TypeError, ValueError):
        return None


def _compatibility_snapshot(lead: Lead, build: Build | None) -> tuple[dict, bool] | None:
    """``(snapshot, computed_now)`` - the frozen report, or a live check for
    leads created before reports were stored."""
    snapshot = getattr(lead, "compatibility_snapshot", None) or {}
    if snapshot.get("checks"):
        return snapshot, False
    if build is not None and build.components:
        return check_components(build.components).snapshot(), True
    return None


def render_lead_card(
    lead: Lead, user: User, build: Build | None, *, compact_compatibility: bool = False
) -> str:
    """Full lead card: who, what they asked for, and what we picked."""
    status = lead.status_enum
    lines = [
        f"<b>Заявка #{lead.id}</b> · {status_label(status)}",
        f"<i>{_fmt_dt(lead.created_at)}</i>",
        "",
        "<b>Клиент</b>",
        _customer_line(user),
    ]

    if lead.contact:
        lines.append(f"Контакт: {escape(lead.contact)}")

    requirements = _requirements_of(build)
    if requirements is None:
        lines.extend(["", "<b>Требования</b>", "— не сохранены"])
    else:
        lines.extend(
            [
                "",
                "<b>Требования</b>",
                f"• Бюджет: <b>{format_price_pln(requirements.budget_pln)}</b>",
                f"• Назначение: {t(ADMIN_LANG, f'purpose.{requirements.purpose.value}')}",
                f"• Разрешение: {t(ADMIN_LANG, f'resolution.{requirements.resolution.value}')}",
            ]
        )
        if requirements.target_fps is not None:
            lines.append(f"• Целевой FPS: {requirements.target_fps.value}")
        if requirements.games:
            titles = ", ".join(escape(title) for title in requirements.game_titles)
            lines.append(f"• Игры: {titles}")
        lines.append(f"• Приоритет: {t(ADMIN_LANG, f'priority.{requirements.priority.value}')}")
        lines.append(
            f"• Внешний вид: {t(ADMIN_LANG, f'aesthetics.{requirements.aesthetics.value}')}"
        )
        connectivity = []
        if requirements.wifi:
            connectivity.append("Wi-Fi")
        if requirements.bluetooth:
            connectivity.append("Bluetooth")
        lines.append(f"• Подключение: {', '.join(connectivity) or 'не требуется'}")
        lines.append(
            "• Накопитель: "
            + (format_storage(requirements.storage_gb) if requirements.storage_gb else "авто")
        )
        lines.append(
            "• Память: " + (format_ram(requirements.ram_gb) if requirements.ram_gb else "авто")
        )
        lines.append(f"• CPU: {requirements.cpu_brand.value}")
        lines.append(f"• GPU: {requirements.gpu_brand.value}")

    lines.extend(["", "<b>Сборка</b>"])
    if build is None:
        lines.append("— не привязана")
    else:
        lines.append(f"ID сборки: <code>{build.id}</code>")
        if build.components:
            catalog = get_catalog()
            for category, component_id in build.components.items():
                component = catalog.get(str(component_id))
                name = component.name if component else str(component_id)
                lines.append(f"• {escape(str(category).upper())}: {escape(name)}")
        else:
            lines.append(f"• Комплектующие: {COMPONENTS_PENDING}")
        total = build.total_price_pln
        lines.append(
            f"• Итоговая цена: <b>{format_price_pln(float(total))}</b>"
            if total is not None
            else "• Итоговая цена: не рассчитана"
        )

    if lead.pricing_snapshot:
        lines.extend(["", *render_economics(lead.pricing_snapshot)])

    compatibility = _compatibility_snapshot(lead, build)
    if compatibility is not None:
        snapshot, live = compatibility
        if compact_compatibility:
            lines.extend(["", render_compatibility_short(snapshot)])
        else:
            lines.extend(["", *render_compatibility(snapshot)])
        if live:
            lines.append("<i>(проверено сейчас — заявка создана до сохранения отчётов)</i>")

    if lead.comment:
        lines.extend(["", "<b>Комментарий</b>", escape(lead.comment)])

    if lead.assigned_admin_id:
        lines.extend(["", f"Ответственный: <code>{lead.assigned_admin_id}</code>"])

    return "\n".join(lines)


def _money(value: object) -> str:
    try:
        return format_price_pln(Decimal(str(value)))
    except (ArithmeticError, ValueError, TypeError):
        return "—"


def render_economics(snapshot: dict) -> list[str]:
    """The owner's side of an order, from the frozen pricing snapshot.

    Never reaches a customer: this is only ever embedded in admin cards.
    """
    hours = snapshot.get("estimated_total_hours", 0)
    level = str(snapshot.get("complexity_level", "—"))
    statuses = snapshot.get("price_statuses") or {}
    status_text = ", ".join(f"{k}: {v}" for k, v in statuses.items()) or "—"

    lines = [
        "<b>💼 Экономика заказа</b>",
        f"Цена клиенту: <b>{_money(snapshot.get('sale_price_pln'))}</b>",
        "",
        f"• Закупка (best purchase): {_money(snapshot.get('purchase_cost_pln'))}",
        f"• Прибыль на комплектующих: <b>{_money(snapshot.get('product_profit_pln'))}</b>",
        f"• Сборка ({snapshot.get('assembly_tier', '—')}): "
        f"<b>{_money(snapshot.get('assembly_fee_pln'))}</b>",
        f"• Другие услуги: {_money(snapshot.get('other_services_pln', 0))}",
        f"• Округление итога: +{_money(snapshot.get('rounding_uplift_pln'))}",
        "",
        f"• <b>Валовая прибыль: {_money(snapshot.get('gross_profit_pln'))}</b>",
        f"• Операционные расходы (оценка): −{_money(snapshot.get('operating_costs_pln'))}",
        f"• <b>Чистая прибыль (оценка): {_money(snapshot.get('net_profit_pln'))}</b>",
        f"• Маржа: {snapshot.get('margin_percent', '—')}%",
        f"• Статус: <b>{snapshot.get('profit_tier', '—')}</b>",
        "",
        f"• Время: {hours} ч · сложность {level.upper()}"
        f" ({snapshot.get('complexity_score', '—')})"
        f" · {_money(snapshot.get('profit_per_hour_pln'))}/ч",
        f"• Позиция маржи в диапазонах: {_percent(snapshot.get('margin_position'))}",
        f"• Статус цен: {status_text}",
    ]

    items = snapshot.get("items") or {}
    if items:
        lines.append("")
        lines.append("<i>Прибыль по позициям (рынок → клиент)</i>")
        for category, item in items.items():
            lines.append(
                f"• {str(category).upper()}: {_money(item.get('market_price'))} → "
                f"{_money(item.get('customer_price'))} · <b>+{_money(item.get('profit'))}</b> "
                f"({item.get('margin_percent', '—')}%, {item.get('price_status', '—')})"
            )
        lines.append("")
        lines.append("<i>Лучшие поставщики</i>")
        lines.append("• не проверено — источники закупки ещё не подключены")

    unpriced = snapshot.get("unpriced") or {}
    if unpriced:
        lines.append("")
        lines.append("<i>Без цены</i>")
        lines.extend(
            f"• {str(category).upper()}: {item.get('price_status', 'unknown')}"
            for category, item in unpriced.items()
        )

    factors = snapshot.get("complexity_factors") or []
    if factors:
        lines.append("")
        lines.append("<i>Что усложняет сборку</i>")
        lines.extend(
            f"• {escape(str(f.get('detail', '')))} (+{f.get('minutes', 0)} мин)" for f in factors
        )

    warnings = snapshot.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("<b>⚠️ Предупреждения</b>")
        lines.extend(f"• {escape(str(w))}" for w in warnings)

    adjustments = snapshot.get("adjustments") or []
    if adjustments:
        lines.append("")
        lines.append("<i>Корректировки</i>")
        lines.extend(f"• {escape(str(a))}" for a in adjustments)

    lines.append("")
    lines.append(f"<b>ОЖИДАЕМАЯ ПРИБЫЛЬ: {_money(snapshot.get('gross_profit_pln'))}</b>")
    return lines


def _percent(value: object) -> str:
    try:
        return f"{Decimal(str(value)) * 100:.0f}%"
    except (ArithmeticError, ValueError, TypeError):
        return "—"


RANKING_TITLES: dict[str, str] = {
    "profit": "💰 Самые прибыльные",
    "hour_best": "⏱ Лучшая прибыль в час",
    "hour_worst": "🐢 Худшая прибыль в час",
    "complex": "🧩 Самые сложные",
    "longest": "⏳ Самые долгие",
    "revenue": "📈 Самая высокая выручка",
    "margin_low": "📉 Самая низкая маржа",
}


def render_rankings(sort: str, builds: list[ReadyBuild]) -> str:
    title = RANKING_TITLES.get(sort, sort)
    if not builds:
        return f"<b>{title}</b>\n\nНет данных — пересейте полку: seed_ready_builds."

    lines = [f"<b>{title}</b>", ""]
    for index, build in enumerate(builds, start=1):
        lines.append(
            f"<b>{index}.</b> {escape(build.name)}\n"
            f"     {_money(build.reference_price_pln)} · "
            f"прибыль {_money(build.gross_profit_pln)} · "
            f"{_money(build.profit_per_hour_pln)}/ч · "
            f"{build.estimated_hours} ч · {str(build.complexity_level or '—').upper()}"
        )
    return "\n".join(lines)


def render_lead_row(lead: Lead, user: User, build: Build | None) -> str:
    """One line in the leads list."""
    budget = format_price_pln(build.budget_pln) if build and build.budget_pln else "—"
    username = f"@{escape(user.username)}" if user.username else str(user.telegram_id)
    return (
        f"{LEAD_STATUS_BADGES[lead.status_enum]} <b>#{lead.id}</b> · {username} · "
        f"{budget} · {_fmt_dt(lead.created_at)}"
    )


def render_leads_list(rows: list[tuple[Lead, User, Build | None]]) -> str:
    if not rows:
        return f"{PANEL_TITLE}\n\n{NO_LEADS}"
    body = "\n".join(render_lead_row(lead, user, build) for lead, user, build in rows)
    return f"<b>Заявки</b> ({len(rows)})\n\n{body}\n\nОткрой заявку кнопкой ниже."


def render_builds_list(builds: list[Build]) -> str:
    if not builds:
        return f"{PANEL_TITLE}\n\n{NO_BUILDS}"

    lines = [f"<b>Последние сборки</b> ({len(builds)})", ""]
    for build in builds:
        try:
            purpose = t(ADMIN_LANG, f"purpose.{Purpose(build.purpose or '').value}")
        except ValueError:
            purpose = "—"
        budget = format_price_pln(build.budget_pln) if build.budget_pln else "—"
        lines.append(
            f"• <b>#{build.id}</b> · {purpose} · {budget} · "
            f"{build.resolution or '—'} · {_fmt_dt(build.created_at)}"
        )
    return "\n".join(lines)


def render_stats(stats: AdminStats) -> str:
    lines = [
        "<b>Статистика</b>",
        "",
        f"👤 Пользователей: <b>{stats.users_total}</b> (за 7 дней: {stats.users_last_7d})",
        f"🖥 Сборок: <b>{stats.builds_total}</b>",
        f"🛒 Заявок: <b>{stats.leads_total}</b>",
        "",
        "<b>Воронка конфигуратора</b>",
        f"• Запусков: {stats.configurators_started}",
        f"• Завершений: {stats.configurators_completed}",
        f"• Конверсия: {stats.completion_rate:.0%}",
    ]

    if stats.leads_by_status:
        lines.extend(["", "<b>Заявки по статусам</b>"])
        for raw_status, count in sorted(stats.leads_by_status.items()):
            try:
                label = status_label(LeadStatus(raw_status))
            except ValueError:
                label = raw_status
            lines.append(f"• {label}: {count}")

    if stats.top_budgets:
        lines.extend(["", "<b>Популярные бюджеты</b>"])
        lines.extend(
            f"• {format_price_pln(budget)} — {count}" for budget, count in stats.top_budgets
        )

    if stats.top_purposes:
        lines.extend(["", "<b>Популярные назначения</b>"])
        for raw_purpose, count in stats.top_purposes:
            try:
                label = t(ADMIN_LANG, f"purpose.{Purpose(raw_purpose).value}")
            except ValueError:
                label = raw_purpose
            lines.append(f"• {label} — {count}")

    return "\n".join(lines)


def render_notification(lead: Lead, user: User, build: Build | None) -> str:
    # The alert keeps compatibility to one line; the full table is one tap
    # away on the lead card.
    card = render_lead_card(lead, user, build, compact_compatibility=True)
    return f"🔔 <b>Новая заявка</b>\n\n{card}"


def render_blocked_custom_order(build_id: int, telegram_id: int, snapshot: dict) -> str:
    """Admin alert: a configured build failed the compatibility gate at order time."""
    return (
        "⛔ Заказ заблокирован проверкой совместимости "
        f"(сборка <code>{build_id}</code>, клиент <code>{telegram_id}</code>)\n"
        + render_compatibility_short(snapshot)
    )


def render_blocked_shelf_order(name: str, slug: str, snapshot: dict) -> str:
    """Admin alert: a shelf build stopped being buildable."""
    return (
        f"⛔ Готовая сборка <b>{name}</b> (<code>{slug}</code>) больше не "
        "проходит проверку совместимости — заказ заблокирован\n"
        + render_compatibility_short(snapshot)
    )
