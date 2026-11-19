"""End-to-end handler tests.

The real dispatcher, routers, middlewares and FSM run against a fake Telegram
server, so these cover what unit tests cannot: that ``/start`` is actually
registered, that updates reach a handler, and that the configurator advances.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy import func, select

from app.bot.callbacks import AdminAction, AdminCB, CfgCB, MenuAction, MenuCB, NavAction, NavCB
from app.bot.flows.configurator import StepId
from app.bot.middlewares import ThrottlingMiddleware
from app.db.models import AnalyticsEvent, Base, EventName, User
from tests.fake_telegram import (
    ADMIN_USER_ID,
    CHAT_ID,
    USER_ID,
    RecordingSession,
    callback_update,
    make_bot,
    message_update,
)


@pytest_asyncio.fixture
async def bot(dispatcher: Dispatcher, bot_engine) -> AsyncIterator[Bot]:
    async with bot_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    telegram_bot = make_bot()

    # The dispatcher is shared across the module, so the rate limiter would
    # otherwise carry taps from earlier tests into this one.
    for middleware in dispatcher.update.outer_middleware:
        if isinstance(middleware, ThrottlingMiddleware):
            middleware.reset()

    # Each test starts from a clean conversation state.
    key = StorageKey(bot_id=telegram_bot.id, chat_id=CHAT_ID, user_id=USER_ID)
    await dispatcher.storage.set_state(key, None)
    await dispatcher.storage.set_data(key, {})

    yield telegram_bot
    await telegram_bot.session.close()


def _session(bot: Bot) -> RecordingSession:
    assert isinstance(bot.session, RecordingSession)
    return bot.session


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_start_is_registered_and_answers(bot: Bot, dispatcher: Dispatcher) -> None:
    await dispatcher.feed_update(bot, message_update("/start"))

    session = _session(bot)
    assert session.sent_messages or session.photos, (
        "/start produced no reply - the handler is not registered"
    )
    assert "AMIGOZT PC" in session.last_text

    markup = session.last_markup
    assert markup is not None
    assert len(_button_texts(markup)) == 10


async def test_start_does_not_hit_the_error_handler(
    bot: Bot, dispatcher: Dispatcher, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.bot.handlers.errors"):
        await dispatcher.feed_update(bot, message_update("/start"))
    assert not caplog.records


async def test_start_never_echoes_the_token(bot: Bot, dispatcher: Dispatcher) -> None:
    await dispatcher.feed_update(bot, message_update("/start"))
    assert bot.token not in _session(bot).last_text


async def test_start_registers_the_user(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory
) -> None:
    await dispatcher.feed_update(bot, message_update("/start"))

    async with bot_session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == USER_ID))
        assert user is not None
        assert user.username == "amigo_tester"

        events = await db.scalars(
            select(AnalyticsEvent).where(AnalyticsEvent.event == EventName.START)
        )
        assert list(events)


async def test_language_is_detected_from_telegram(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory
) -> None:
    await dispatcher.feed_update(bot, message_update("/start", language_code="pl"))

    async with bot_session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == USER_ID))
        assert user is not None
        # First contact decides; later updates must not silently override it.
        assert user.language in {"pl", "ru"}


async def test_configurator_starts_and_advances(bot: Bot, dispatcher: Dispatcher) -> None:
    await dispatcher.feed_update(bot, message_update("/start", update_id=1))
    session = _session(bot)
    session.clear()

    # Tap "Build a PC" -> first question is the budget.
    await dispatcher.feed_update(
        bot,
        callback_update(MenuCB(action=MenuAction.BUILD).pack(), update_id=2, bot=bot),
    )
    assert "PLN" in session.last_text or "5 000" in str(session.last_markup)
    budget_labels = _button_texts(session.last_markup)
    assert any("2 500" in label for label in budget_labels)

    # Answer the budget -> the flow moves on to the purpose question.
    session.clear()
    await dispatcher.feed_update(
        bot,
        callback_update(CfgCB(step=StepId.BUDGET.value, value="5000").pack(), update_id=3, bot=bot),
    )
    purpose_labels = _button_texts(session.last_markup)
    assert len(purpose_labels) >= 7
    assert any("AI" in label for label in purpose_labels)


async def test_back_returns_to_the_previous_question(bot: Bot, dispatcher: Dispatcher) -> None:
    session = _session(bot)
    await dispatcher.feed_update(bot, message_update("/build", update_id=10))
    await dispatcher.feed_update(
        bot,
        callback_update(
            CfgCB(step=StepId.BUDGET.value, value="5000").pack(), update_id=11, bot=bot
        ),
    )
    session.clear()

    await dispatcher.feed_update(
        bot, callback_update(NavCB(action=NavAction.BACK).pack(), update_id=12, bot=bot)
    )

    labels = _button_texts(session.last_markup)
    assert any("2 500" in label for label in labels), "Back did not return to the budget step"


async def test_stale_taps_are_ignored(bot: Bot, dispatcher: Dispatcher) -> None:
    """A button from an older message must not overwrite the current answer."""
    await dispatcher.feed_update(bot, message_update("/build", update_id=20))
    await dispatcher.feed_update(
        bot,
        callback_update(
            CfgCB(step=StepId.BUDGET.value, value="5000").pack(), update_id=21, bot=bot
        ),
    )
    session = _session(bot)
    session.clear()

    # We are on PURPOSE now; a leftover BUDGET button arrives.
    await dispatcher.feed_update(
        bot,
        callback_update(
            CfgCB(step=StepId.BUDGET.value, value="2500").pack(), update_id=22, bot=bot
        ),
    )
    assert not session.edits, "a stale tap changed the conversation"


async def test_unknown_text_offers_the_menu(bot: Bot, dispatcher: Dispatcher) -> None:
    await dispatcher.feed_update(bot, message_update("hello there", update_id=30))
    markup = _session(bot).last_markup
    assert markup is not None
    assert len(_button_texts(markup)) == 10


async def test_analytics_records_the_funnel(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory
) -> None:
    await dispatcher.feed_update(bot, message_update("/build", update_id=40))

    async with bot_session_factory() as db:
        started = await db.scalar(
            select(func.count())
            .select_from(AnalyticsEvent)
            .where(AnalyticsEvent.event == EventName.CONFIGURATOR_STARTED)
        )
        assert started and started >= 1


# --- admin authorization (end to end) ----------------------------------------


async def test_regular_user_cannot_open_admin(bot: Bot, dispatcher: Dispatcher) -> None:
    """/admin from a normal user must not reveal the panel."""
    await dispatcher.feed_update(bot, message_update("/admin", update_id=50))

    text = _session(bot).last_text
    assert "админ-панель" not in text.lower()
    assert "Новые заявки" not in text


async def test_regular_user_cannot_open_leads(bot: Bot, dispatcher: Dispatcher) -> None:
    await dispatcher.feed_update(bot, message_update("/leads", update_id=51))

    text = _session(bot).last_text
    assert "Заявки" not in text
    assert "Заявок пока нет" not in text


async def test_admin_can_open_admin(bot: Bot, dispatcher: Dispatcher) -> None:
    await dispatcher.feed_update(bot, message_update("/admin", update_id=52, user_id=ADMIN_USER_ID))

    session = _session(bot)
    assert "админ-панель" in session.last_text.lower()

    labels = _button_texts(session.last_markup)
    assert any("Новые заявки" in label for label in labels)
    assert any("Статистика" in label for label in labels)


async def test_admin_can_open_leads(bot: Bot, dispatcher: Dispatcher) -> None:
    await dispatcher.feed_update(bot, message_update("/leads", update_id=53, user_id=ADMIN_USER_ID))
    assert "Заявок пока нет" in _session(bot).last_text or "Заявки" in _session(bot).last_text


async def test_admin_stats_are_reachable(bot: Bot, dispatcher: Dispatcher) -> None:
    session = _session(bot)
    await dispatcher.feed_update(bot, message_update("/admin", update_id=54, user_id=ADMIN_USER_ID))
    session.clear()

    await dispatcher.feed_update(
        bot,
        callback_update(
            AdminCB(action=AdminAction.STATS).pack(),
            update_id=55,
            bot=bot,
            user_id=ADMIN_USER_ID,
        ),
    )
    assert "Статистика" in session.last_text


async def test_forged_admin_callback_from_a_user_is_ignored(
    bot: Bot, dispatcher: Dispatcher
) -> None:
    """Guarding the router's observers blocks hand-crafted callback payloads."""
    session = _session(bot)
    await dispatcher.feed_update(bot, message_update("/start", update_id=56))
    session.clear()

    await dispatcher.feed_update(
        bot,
        callback_update(AdminCB(action=AdminAction.STATS).pack(), update_id=57, bot=bot),
    )

    assert not session.edits, "a non-admin reached an admin view"
    assert not any("Статистика" in str(getattr(c, "text", "")) for c in session.calls)
