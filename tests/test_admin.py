"""Admin interface: authorization, leads, notifications, rendering."""

from __future__ import annotations

import pytest
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import IsAdmin
from app.bot.keyboards.admin import lead_actions_kb
from app.bot.views.admin import (
    render_builds_list,
    render_lead_card,
    render_leads_list,
    render_stats,
    status_label,
)
from app.config import Settings
from app.db.repositories import BuildRepository, LeadRepository, StatsRepository, UserRepository
from app.domain.enums import LeadStatus
from app.services.leads import LeadService
from app.services.notifications import AdminNotifier
from tests.fake_telegram import FAKE_TOKEN

ADMIN_ID = 7_000_000_001
OTHER_ADMIN_ID = 7_000_000_002
CUSTOMER_ID = 555_123_456


def _settings(admin_ids: str = f"{ADMIN_ID},{OTHER_ADMIN_ID}") -> Settings:
    return Settings(  # type: ignore[call-arg]
        telegram_bot_token=FAKE_TOKEN, admin_telegram_ids=admin_ids
    )


def _tg_user(user_id: int) -> TgUser:
    return TgUser(id=user_id, is_bot=False, first_name="Someone", username="someone")


def _event(user_id: int) -> Message:
    from datetime import UTC, datetime

    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=user_id, type="private"),
        from_user=_tg_user(user_id),
        text="/admin",
    )


# --- authorization ------------------------------------------------------------


async def test_admin_passes_the_filter() -> None:
    assert await IsAdmin()(_event(ADMIN_ID), _tg_user(ADMIN_ID), _settings()) is True


async def test_regular_user_is_rejected() -> None:
    assert await IsAdmin()(_event(CUSTOMER_ID), _tg_user(CUSTOMER_ID), _settings()) is False


async def test_empty_admin_list_means_nobody_is_admin() -> None:
    """An unconfigured ADMIN_TELEGRAM_IDS must not open the panel to everyone."""
    settings = _settings(admin_ids="")
    assert await IsAdmin()(_event(ADMIN_ID), _tg_user(ADMIN_ID), settings) is False


async def test_filter_rejects_updates_without_a_user() -> None:
    assert await IsAdmin()(_event(ADMIN_ID), None, _settings()) is False


@pytest.mark.parametrize("raw", ["7000000001", " 7000000001 ", "7000000001,999"])
async def test_admin_ids_parsed_from_env_string(raw: str) -> None:
    assert ADMIN_ID in _settings(admin_ids=raw).admin_ids


# --- lead creation ------------------------------------------------------------


async def _make_build(session: AsyncSession, gaming_answers: dict):  # type: ignore[no-untyped-def]
    from app.bot.flows.configurator import build_requirements

    user = await UserRepository(session).get_or_create(
        CUSTOMER_ID, username="customer", first_name="Kris"
    )
    build = await BuildRepository(session).create_draft(user.id, build_requirements(gaming_answers))
    await session.commit()
    return user, build


async def test_order_creates_a_new_lead(session: AsyncSession, gaming_answers: dict) -> None:
    user, build = await _make_build(session, gaming_answers)

    lead, linked_build, created = await LeadService(session).request_order(user, build.id)
    await session.commit()

    assert created is True
    assert lead.id is not None
    assert lead.status == LeadStatus.NEW.value
    assert lead.build_id == build.id
    assert linked_build is not None and linked_build.is_saved is True


async def test_double_tap_does_not_create_a_second_lead(
    session: AsyncSession, gaming_answers: dict
) -> None:
    user, build = await _make_build(session, gaming_answers)
    service = LeadService(session)

    first, _, created_first = await service.request_order(user, build.id)
    second, _, created_second = await service.request_order(user, build.id)
    await session.commit()

    assert created_first is True
    assert created_second is False
    assert first.id == second.id


async def test_a_closed_lead_does_not_block_a_new_one(
    session: AsyncSession, gaming_answers: dict
) -> None:
    user, build = await _make_build(session, gaming_answers)
    service = LeadService(session)
    repo = LeadRepository(session)

    first, _, _ = await service.request_order(user, build.id)
    await repo.set_status(first.id, LeadStatus.CANCELLED)
    await session.commit()

    second, _, created = await service.request_order(user, build.id)
    await session.commit()

    assert created is True
    assert second.id != first.id


async def test_order_without_a_build_still_creates_a_lead(session: AsyncSession) -> None:
    user = await UserRepository(session).get_or_create(CUSTOMER_ID)
    lead, build, created = await LeadService(session).request_order(user, None)
    await session.commit()

    assert created is True
    assert build is None
    assert lead.build_id is None


# --- status transitions -------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [LeadStatus.IN_PROGRESS, LeadStatus.CONTACTED, LeadStatus.COMPLETED, LeadStatus.CANCELLED],
)
async def test_status_can_be_changed(
    session: AsyncSession, gaming_answers: dict, status: LeadStatus
) -> None:
    user, build = await _make_build(session, gaming_answers)
    repo = LeadRepository(session)
    lead, _, _ = await LeadService(session).request_order(user, build.id)
    await session.commit()

    updated = await repo.set_status(lead.id, status, admin_id=ADMIN_ID)
    await session.commit()

    assert updated is not None
    assert updated.status_enum is status
    assert updated.assigned_admin_id == ADMIN_ID


async def test_status_change_on_a_missing_lead_returns_none(session: AsyncSession) -> None:
    assert await LeadRepository(session).set_status(999_999, LeadStatus.COMPLETED) is None


async def test_lead_keyboard_reflects_the_status(
    session: AsyncSession, gaming_answers: dict
) -> None:
    user, build = await _make_build(session, gaming_answers)
    repo = LeadRepository(session)
    lead, _, _ = await LeadService(session).request_order(user, build.id)
    await session.commit()

    new_labels = [b.text for row in lead_actions_kb(lead).inline_keyboard for b in row]
    assert any("Взять заявку" in label for label in new_labels)

    closed = await repo.set_status(lead.id, LeadStatus.COMPLETED)
    await session.commit()
    assert closed is not None
    closed_labels = [b.text for row in lead_actions_kb(closed).inline_keyboard for b in row]
    assert not any("Взять заявку" in label for label in closed_labels)
    assert not any("Отклонить" in label for label in closed_labels)


# --- notifications ------------------------------------------------------------


class _StubBot:
    """Records send_message calls instead of talking to Telegram."""

    def __init__(self, failing_ids: set[int] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self._failing_ids = failing_ids or set()

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        if chat_id in self._failing_ids:
            from aiogram.exceptions import TelegramForbiddenError

            raise TelegramForbiddenError(method=None, message="blocked")  # type: ignore[arg-type]
        self.sent.append((chat_id, text))


async def test_notification_reaches_every_admin(
    session: AsyncSession, gaming_answers: dict
) -> None:
    user, build = await _make_build(session, gaming_answers)
    lead, _, _ = await LeadService(session).request_order(user, build.id)
    await session.commit()

    bot = _StubBot()
    delivered = await AdminNotifier(bot, [ADMIN_ID, OTHER_ADMIN_ID]).notify_new_lead(  # type: ignore[arg-type]
        lead, user, build
    )

    assert delivered == 2
    assert {chat_id for chat_id, _ in bot.sent} == {ADMIN_ID, OTHER_ADMIN_ID}


async def test_notification_contains_every_required_field(
    session: AsyncSession, gaming_answers: dict
) -> None:
    user, build = await _make_build(session, gaming_answers)
    lead, _, _ = await LeadService(session).request_order(user, build.id)
    lead.comment = "Нужен к пятнице"
    await session.commit()

    bot = _StubBot()
    await AdminNotifier(bot, [ADMIN_ID]).notify_new_lead(lead, user, build)  # type: ignore[arg-type]
    _, text = bot.sent[0]

    assert f"#{lead.id}" in text  # lead id
    assert "@customer" in text  # username
    assert str(CUSTOMER_ID) in text  # telegram id
    assert "Kris" in text  # first name
    assert "6 000 PLN" in text  # budget
    assert "1440p" in text  # resolution
    assert "144" in text  # target fps
    assert "CS2" in text  # requirements
    assert str(build.id) in text  # selected build
    assert "Комплектующие" in text  # components section
    assert "цена" in text.lower()  # total price
    assert "Нужен к пятнице" in text  # comment
    assert "UTC" in text  # date/time


async def test_a_blocked_admin_does_not_break_delivery(
    session: AsyncSession, gaming_answers: dict
) -> None:
    """One admin blocking the bot must not stop the others being notified."""
    user, build = await _make_build(session, gaming_answers)
    lead, _, _ = await LeadService(session).request_order(user, build.id)
    await session.commit()

    bot = _StubBot(failing_ids={ADMIN_ID})
    delivered = await AdminNotifier(bot, [ADMIN_ID, OTHER_ADMIN_ID]).notify_new_lead(  # type: ignore[arg-type]
        lead, user, build
    )

    assert delivered == 1
    assert bot.sent[0][0] == OTHER_ADMIN_ID


async def test_notifier_without_admins_is_a_noop(
    session: AsyncSession, gaming_answers: dict
) -> None:
    user, build = await _make_build(session, gaming_answers)
    lead, _, _ = await LeadService(session).request_order(user, build.id)
    await session.commit()

    bot = _StubBot()
    assert await AdminNotifier(bot, []).notify_new_lead(lead, user, build) == 0  # type: ignore[arg-type]
    assert bot.sent == []


# --- rendering ----------------------------------------------------------------


async def test_lead_card_escapes_user_supplied_text(
    session: AsyncSession, gaming_answers: dict
) -> None:
    gaming_answers["games"] = ["<b>xss</b>"]
    user, build = await _make_build(session, gaming_answers)
    user.first_name = "<script>alert(1)</script>"
    lead, _, _ = await LeadService(session).request_order(user, build.id)
    await session.commit()

    text = render_lead_card(lead, user, build)
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "<b>xss</b>" not in text


async def test_lead_card_survives_a_lead_without_a_build(session: AsyncSession) -> None:
    user = await UserRepository(session).get_or_create(CUSTOMER_ID, username=None)
    lead, _, _ = await LeadService(session).request_order(user, None)
    await session.commit()

    text = render_lead_card(lead, user, None)
    assert f"#{lead.id}" in text
    assert "без username" in text


async def test_leads_list_rendering(session: AsyncSession, gaming_answers: dict) -> None:
    user, build = await _make_build(session, gaming_answers)
    await LeadService(session).request_order(user, build.id)
    await session.commit()

    rows = await LeadRepository(session).list_recent(limit=10)
    text = render_leads_list(rows)

    assert "Заявки" in text
    assert "@customer" in text
    assert "6 000 PLN" in text


async def test_empty_leads_list_says_so() -> None:
    assert "Заявок пока нет" in render_leads_list([])


async def test_builds_list_rendering(session: AsyncSession, gaming_answers: dict) -> None:
    _, build = await _make_build(session, gaming_answers)
    text = render_builds_list([build])

    assert f"#{build.id}" in text
    assert "6 000 PLN" in text
    assert "1440p" in text


async def test_stats_rendering(session: AsyncSession, gaming_answers: dict) -> None:
    user, build = await _make_build(session, gaming_answers)
    await LeadService(session).request_order(user, build.id)
    await session.commit()

    stats = await StatsRepository(session).collect()
    text = render_stats(stats)

    assert stats.users_total == 1
    assert stats.builds_total == 1
    assert stats.leads_total == 1
    assert "Статистика" in text
    assert "Конверсия" in text


async def test_stats_completion_rate_handles_no_traffic(session: AsyncSession) -> None:
    stats = await StatsRepository(session).collect()
    assert stats.completion_rate == 0.0


@pytest.mark.parametrize("status", list(LeadStatus))
def test_every_status_has_a_label(status: LeadStatus) -> None:
    label = status_label(status)
    assert label.strip()
    assert status.value not in label  # a human title, not the raw enum value
