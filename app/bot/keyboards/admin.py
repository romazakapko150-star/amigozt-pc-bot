from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import AdminAction, AdminCB, LeadAction, LeadCB, RankCB
from app.bot.keyboards.common import Row, chunk, markup
from app.db.models import Lead
from app.domain.enums import LeadStatus

MAX_LEAD_BUTTONS = 8


def _admin_btn(text: str, action: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=AdminCB(action=action).pack())


def admin_home_kb() -> InlineKeyboardMarkup:
    return markup(
        [_admin_btn("🛒 Новые заявки", AdminAction.LEADS)],
        [_admin_btn("🖥 Последние сборки", AdminAction.BUILDS)],
        [_admin_btn("📊 Статистика", AdminAction.STATS)],
        [_admin_btn("📈 Прибыльность сборок", AdminAction.RANKINGS)],
    )


def back_home_row() -> Row:
    return [_admin_btn("⬅️ В админ-панель", AdminAction.HOME)]


def leads_list_kb(leads: list[Lead]) -> InlineKeyboardMarkup:
    """One button per lead, so the admin can open a full card."""
    buttons = [
        InlineKeyboardButton(
            text=f"#{lead.id}",
            callback_data=LeadCB(lead_id=lead.id, action=LeadAction.CONTACT).pack(),
        )
        for lead in leads[:MAX_LEAD_BUTTONS]
    ]
    return markup(*chunk(buttons, 4), back_home_row())


def lead_actions_kb(lead: Lead) -> InlineKeyboardMarkup:
    """Actions available for a lead, given its current status."""
    status = lead.status_enum
    rows: list[Row] = []

    def button(text: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=text, callback_data=LeadCB(lead_id=lead.id, action=action).pack()
        )

    if status is LeadStatus.NEW:
        rows.append([button("✅ Взять заявку", LeadAction.TAKE)])

    if status.is_open:
        contact_row = [button("📞 Связаться", LeadAction.CONTACT)]
        if status is not LeadStatus.NEW:
            contact_row.append(button("🏁 Завершить", LeadAction.COMPLETE))
        rows.append(contact_row)
        rows.append([button("❌ Отклонить", LeadAction.REJECT)])

    rows.append(back_home_row())
    return markup(*rows)


def contact_link_kb(telegram_id: int, username: str | None) -> InlineKeyboardMarkup:
    """Deep link that opens a private chat with the customer."""
    url = f"https://t.me/{username}" if username else f"tg://user?id={telegram_id}"
    return markup(
        [InlineKeyboardButton(text="💬 Открыть чат с клиентом", url=url)],
        back_home_row(),
    )


RANKING_BUTTONS: tuple[tuple[str, str], ...] = (
    ("💰 Прибыль", "profit"),
    ("⏱ Лучшие /ч", "hour_best"),
    ("🐢 Худшие /ч", "hour_worst"),
    ("🧩 Сложные", "complex"),
    ("⏳ Долгие", "longest"),
    ("📈 Выручка", "revenue"),
    ("📉 Низкая маржа", "margin_low"),
)


def rankings_kb(active: str | None = None) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"• {label}" if key == active else label,
            callback_data=RankCB(sort=key).pack(),
        )
        for label, key in RANKING_BUTTONS
    ]
    return markup(*chunk(buttons, 2), back_home_row())
