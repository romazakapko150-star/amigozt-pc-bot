"""End-to-end walks through the configurator.

These drive the real dispatcher and assert on the FSM contents after each
step, so a preference silently lost between steps fails the test - passing
pytest is not the same as the user flow actually working.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy import select

from app.bot.callbacks import (
    VALUE_DONE,
    VALUE_GENERATE,
    VALUE_ORDER,
    VALUE_ORDER_BACK,
    VALUE_ORDER_CONFIRM,
    VALUE_SKIP,
    CfgCB,
    NavAction,
    NavCB,
)
from app.bot.flows.configurator import StepId
from app.bot.middlewares import ThrottlingMiddleware
from app.db.models import Base, Build, Lead
from app.domain.enums import CpuBrand, GpuBrand
from app.services.compatibility import LABEL_BUILDABLE
from tests.fake_telegram import (
    ADMIN_USER_ID,
    CHAT_ID,
    USER_ID,
    RecordingSession,
    callback_update,
    make_bot,
    message_update,
)

#: The gaming path, in the order the flow asks for it.
BASE_ANSWERS: list[tuple[StepId, str]] = [
    # 6 000, not 5 000: at five the cheapest wifi + 32 GB + RGB build lands
    # within a złoty of the ceiling, so any catalogue change tips these tests
    # into "no build possible" and stops testing the order flow at all.
    (StepId.BUDGET, "6000"),
    (StepId.PURPOSE, "gaming"),
    (StepId.GAMES, "cs2"),
    (StepId.GAMES, VALUE_DONE),
    (StepId.RESOLUTION, "1440p"),
    (StepId.FPS, "144"),
    # Priorities are a multi-select now: tick two, then close the step.
    (StepId.PRIORITY, "price_performance"),
    (StepId.PRIORITY, "silence"),
    (StepId.PRIORITY, VALUE_DONE),
    (StepId.AESTHETICS, "black_rgb"),
    (StepId.CONNECTIVITY, "wifi_bt"),
    (StepId.STORAGE, "1000"),
    (StepId.RAM, "32"),
]


@pytest_asyncio.fixture
async def bot(dispatcher: Dispatcher, bot_engine) -> AsyncIterator[Bot]:
    async with bot_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    telegram_bot = make_bot()
    _reset_throttling(dispatcher)

    key = StorageKey(bot_id=telegram_bot.id, chat_id=CHAT_ID, user_id=USER_ID)
    await dispatcher.storage.set_state(key, None)
    await dispatcher.storage.set_data(key, {})

    yield telegram_bot
    await telegram_bot.session.close()


def _reset_throttling(dispatcher: Dispatcher) -> None:
    for middleware in dispatcher.update.outer_middleware:
        if isinstance(middleware, ThrottlingMiddleware):
            middleware.reset()


def _session(bot: Bot) -> RecordingSession:
    assert isinstance(bot.session, RecordingSession)
    return bot.session


def _buttons(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


class Walker:
    """Drives one conversation and keeps the update ids unique."""

    def __init__(self, bot: Bot, dispatcher: Dispatcher, user_id: int = USER_ID) -> None:
        self._bot = bot
        self._dispatcher = dispatcher
        self._user_id = user_id
        self._next_id = 1000

    async def _feed(self, update) -> None:  # type: ignore[no-untyped-def]
        _reset_throttling(self._dispatcher)
        await self._dispatcher.feed_update(self._bot, update)

    async def command(self, text: str) -> None:
        self._next_id += 1
        await self._feed(message_update(text, update_id=self._next_id, user_id=self._user_id))

    async def tap(self, step: StepId, value: str) -> None:
        self._next_id += 1
        await self._feed(
            callback_update(
                CfgCB(step=step.value, value=value).pack(),
                update_id=self._next_id,
                bot=self._bot,
                user_id=self._user_id,
            )
        )

    async def nav(self, action: str) -> None:
        self._next_id += 1
        await self._feed(
            callback_update(
                NavCB(action=action).pack(),
                update_id=self._next_id,
                bot=self._bot,
                user_id=self._user_id,
            )
        )

    async def state(self) -> dict:
        key = StorageKey(bot_id=self._bot.id, chat_id=self._user_id, user_id=self._user_id)
        return await self._dispatcher.storage.get_data(key)

    async def answer_base_with_fps(self, fps: str) -> None:
        for step, value in BASE_ANSWERS:
            await self.tap(step, fps if step is StepId.FPS else value)

    async def skip_the_desk(self) -> None:
        """Walk past the monitor and peripherals steps without buying either."""
        await self.tap(StepId.MONITOR, VALUE_SKIP)
        await self.tap(StepId.PERIPHERALS, VALUE_DONE)


async def _walk_to_cpu_step(walker: Walker, fps: str = "144") -> None:
    await walker.command("/build")
    await walker.answer_base_with_fps(fps)


# --- TEST 1 / TEST 2: AMD and Intel reach the final card ----------------------


@pytest.mark.parametrize(
    ("cpu_value", "expected"),
    [("amd", CpuBrand.AMD), ("intel", CpuBrand.INTEL)],
)
async def test_cpu_preference_survives_to_the_final_card(
    bot: Bot, dispatcher: Dispatcher, cpu_value: str, expected: CpuBrand
) -> None:
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)

    # The CPU question must actually be on screen at this point.
    session = _session(bot)
    labels = _buttons(session.last_markup)
    assert any("Ryzen" in label for label in labels)
    assert any("Intel" in label for label in labels)

    await walker.tap(StepId.CPU, cpu_value)

    # Stored immediately, before the next question is even answered.
    state = await walker.state()
    assert state["cpu_brand"] == expected.value
    assert state["current_step"] == StepId.GPU.value

    await walker.tap(StepId.GPU, "any")

    await walker.skip_the_desk()

    # Still there on the final card, and not silently replaced.
    state = await walker.state()
    assert state["cpu_brand"] == expected.value
    assert state["current_step"] == StepId.SUMMARY.value


@pytest.mark.parametrize("cpu_value", ["amd", "intel"])
async def test_final_card_shows_the_order_cta(
    bot: Bot, dispatcher: Dispatcher, cpu_value: str
) -> None:
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)
    await walker.tap(StepId.CPU, cpu_value)
    await walker.tap(StepId.GPU, "any")
    await walker.skip_the_desk()

    session = _session(bot)
    text = session.last_text
    labels = _buttons(session.last_markup)

    assert "✅" in text, "the final step must be marked as complete"
    assert any("🛒" in label for label in labels), "no order CTA on the final card"
    # The CTA is the first, full-width button.
    assert "🛒" in session.last_markup.inline_keyboard[0][0].text
    assert len(session.last_markup.inline_keyboard[0]) == 1


@pytest.mark.parametrize(
    ("cpu_value", "brand_label"), [("amd", "AMD Ryzen"), ("intel", "Intel Core")]
)
async def test_chosen_cpu_brand_is_named_on_the_card(
    bot: Bot, dispatcher: Dispatcher, cpu_value: str, brand_label: str
) -> None:
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)
    await walker.tap(StepId.CPU, cpu_value)
    await walker.tap(StepId.GPU, "any")
    await walker.skip_the_desk()

    assert brand_label in _session(bot).last_text


@pytest.mark.parametrize("cpu_value", ["amd", "intel"])
async def test_cpu_preference_is_persisted_with_the_build(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory, cpu_value: str
) -> None:
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)
    await walker.tap(StepId.CPU, cpu_value)
    await walker.tap(StepId.GPU, "nvidia")
    await walker.skip_the_desk()

    async with bot_session_factory() as db:
        build = await db.scalar(select(Build).order_by(Build.id.desc()))
        assert build is not None
        assert build.requirements["cpu_brand"] == cpu_value
        assert build.requirements["gpu_brand"] == GpuBrand.NVIDIA.value


@pytest.mark.parametrize("cpu_value", ["amd", "intel"])
async def test_cpu_choice_never_dead_ends(bot: Bot, dispatcher: Dispatcher, cpu_value: str) -> None:
    """After picking a CPU the user must get a next question with a keyboard."""
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)

    session = _session(bot)
    session.clear()
    await walker.tap(StepId.CPU, cpu_value)

    assert session.calls, "no reply at all after choosing a CPU"
    assert session.last_text.strip(), "empty message after choosing a CPU"
    assert session.last_markup is not None, "no keyboard after choosing a CPU"
    # The same question must not be asked twice.
    assert "процессор" not in session.last_text.lower()


# --- TEST 3: Back changes the answer -----------------------------------------


async def test_back_from_gpu_lets_the_user_switch_cpu_brand(
    bot: Bot, dispatcher: Dispatcher
) -> None:
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)

    await walker.tap(StepId.CPU, "amd")
    assert (await walker.state())["cpu_brand"] == CpuBrand.AMD.value

    await walker.nav(NavAction.BACK)
    state = await walker.state()
    assert state["current_step"] == StepId.CPU.value
    # Going back must not wipe the answers given earlier.
    assert state["budget_pln"] == 6000
    assert state["target_fps"] == "144"

    await walker.tap(StepId.CPU, "intel")
    await walker.tap(StepId.GPU, "any")
    await walker.skip_the_desk()

    state = await walker.state()
    assert state["cpu_brand"] == CpuBrand.INTEL.value
    assert "Intel Core" in _session(bot).last_text


async def test_back_does_not_reset_the_configurator(bot: Bot, dispatcher: Dispatcher) -> None:
    walker = Walker(bot, dispatcher)
    await walker.command("/build")
    await walker.tap(StepId.BUDGET, "6000")
    await walker.tap(StepId.PURPOSE, "gaming")

    await walker.nav(NavAction.BACK)
    state = await walker.state()

    assert state["current_step"] == StepId.PURPOSE.value
    assert state["budget_pln"] == 6000


# --- TEST 4: Start over clears everything ------------------------------------


async def test_restart_clears_the_previous_preferences(bot: Bot, dispatcher: Dispatcher) -> None:
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)
    await walker.tap(StepId.CPU, "amd")
    await walker.tap(StepId.GPU, "nvidia")
    await walker.skip_the_desk()

    await walker.nav(NavAction.RESTART)

    state = await walker.state()
    assert state["current_step"] == StepId.BUDGET.value
    for stale_key in ("cpu_brand", "gpu_brand", "budget_pln", "target_fps", "games"):
        assert stale_key not in state, f"{stale_key} leaked into the new session"


async def test_restart_then_a_different_cpu_brand(bot: Bot, dispatcher: Dispatcher) -> None:
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)
    await walker.tap(StepId.CPU, "amd")

    await walker.nav(NavAction.RESTART)
    await walker.answer_base_with_fps("240")
    await walker.tap(StepId.CPU, "intel")
    await walker.tap(StepId.GPU, "any")
    await walker.skip_the_desk()

    state = await walker.state()
    assert state["cpu_brand"] == CpuBrand.INTEL.value
    assert state["target_fps"] == "240"


# --- TEST 5: order flow -------------------------------------------------------


async def test_order_requires_an_explicit_confirmation(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory
) -> None:
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)
    await walker.tap(StepId.CPU, "amd")
    await walker.tap(StepId.GPU, "any")
    await walker.skip_the_desk()

    await walker.tap(StepId.SUMMARY, VALUE_ORDER)

    labels = _buttons(_session(bot).last_markup)
    assert any("✅" in label for label in labels)

    # Nothing is created until the customer confirms.
    async with bot_session_factory() as db:
        assert await db.scalar(select(Lead)) is None


async def test_cancelling_the_confirmation_returns_to_the_card(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory
) -> None:
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)
    await walker.tap(StepId.CPU, "amd")
    await walker.tap(StepId.GPU, "any")
    await walker.skip_the_desk()

    await walker.tap(StepId.SUMMARY, VALUE_ORDER)
    await walker.tap(StepId.SUMMARY, VALUE_ORDER_BACK)

    labels = _buttons(_session(bot).last_markup)
    assert any("🛒" in label for label in labels), "the card did not come back"

    async with bot_session_factory() as db:
        assert await db.scalar(select(Lead)) is None


async def test_confirmed_order_creates_a_lead_and_notifies_the_admin(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory
) -> None:
    walker = Walker(bot, dispatcher)
    await _walk_to_cpu_step(walker)
    await walker.tap(StepId.CPU, "amd")
    await walker.tap(StepId.GPU, "any")
    await walker.skip_the_desk()

    session = _session(bot)
    await walker.tap(StepId.SUMMARY, VALUE_ORDER)
    session.clear()
    await walker.tap(StepId.SUMMARY, VALUE_ORDER_CONFIRM)

    async with bot_session_factory() as db:
        lead = await db.scalar(select(Lead).order_by(Lead.id.desc()))
        assert lead is not None
        assert lead.build_id is not None

    outgoing = [call for call in session.calls if type(call).__name__ == "SendMessage"]
    recipients = {getattr(call, "chat_id", None) for call in outgoing}

    assert USER_ID in recipients, "the customer got no confirmation"
    assert ADMIN_USER_ID in recipients, "the admin was not notified"

    admin_text = next(
        str(getattr(call, "text", ""))
        for call in outgoing
        if getattr(call, "chat_id", None) == ADMIN_USER_ID
    )
    assert f"#{lead.id}" in admin_text
    assert "AMD" in admin_text or "amd" in admin_text


# --- TEST 6 / TEST 7: high frame-rate targets --------------------------------


@pytest.mark.parametrize("fps", ["500+", "700+"])
async def test_high_fps_targets_are_selectable(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory, fps: str
) -> None:
    walker = Walker(bot, dispatcher)
    await walker.command("/build")
    await walker.answer_base_with_fps(fps)
    await walker.tap(StepId.CPU, "amd")
    await walker.tap(StepId.GPU, "any")
    await walker.skip_the_desk()

    state = await walker.state()
    assert state["target_fps"] == fps
    assert f"{fps} FPS" in _session(bot).last_text

    async with bot_session_factory() as db:
        build = await db.scalar(select(Build).order_by(Build.id.desc()))
        assert build is not None
        assert build.target_fps == fps


async def test_fps_keyboard_offers_the_high_targets(bot: Bot, dispatcher: Dispatcher) -> None:
    walker = Walker(bot, dispatcher)
    await walker.command("/build")
    await walker.tap(StepId.BUDGET, "6000")
    await walker.tap(StepId.PURPOSE, "gaming")
    await walker.tap(StepId.GAMES, VALUE_DONE)
    await walker.tap(StepId.RESOLUTION, "1080p")

    labels = _buttons(_session(bot).last_markup)
    assert "500+ FPS" in labels
    assert "700+ FPS" in labels


# --- TEST 8: the pre-order compatibility gate ---------------------------------


async def _generate_and_order(walker: Walker) -> None:
    await _walk_to_cpu_step(walker)
    await walker.tap(StepId.CPU, "amd")
    await walker.tap(StepId.GPU, "any")
    await walker.skip_the_desk()
    await walker.tap(StepId.SUMMARY, VALUE_GENERATE)


async def test_confirmed_order_freezes_a_buildable_compatibility_report(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory
) -> None:
    walker = Walker(bot, dispatcher)
    await _generate_and_order(walker)

    session = _session(bot)
    await walker.tap(StepId.SUMMARY, VALUE_ORDER)
    session.clear()
    await walker.tap(StepId.SUMMARY, VALUE_ORDER_CONFIRM)

    async with bot_session_factory() as db:
        lead = await db.scalar(select(Lead).order_by(Lead.id.desc()))
        assert lead is not None
        snapshot = lead.compatibility_snapshot
        assert snapshot["compatible"] is True
        assert snapshot["final"] == LABEL_BUILDABLE
        assert snapshot["checks"] and snapshot["power"]["recommended_w"] > 0

    admin_text = next(
        str(getattr(call, "text", ""))
        for call in session.calls
        if type(call).__name__ == "SendMessage" and getattr(call, "chat_id", None) == ADMIN_USER_ID
    )
    assert "BUILDABLE" in admin_text


async def test_a_build_that_became_incompatible_cannot_be_ordered(
    bot: Bot, dispatcher: Dispatcher, bot_session_factory
) -> None:
    """Parts change after generation: the gate blocks, no lead, admin alerted."""
    walker = Walker(bot, dispatcher)
    await _generate_and_order(walker)

    async with bot_session_factory() as db:
        build = await db.scalar(select(Build).order_by(Build.id.desc()))
        assert build is not None and build.components
        tampered = dict(build.components)
        tampered["gpu"] = "nvidia-rtx-5090"  # far beyond the chosen PSU
        build.components = tampered
        await db.commit()
        leads_before = len(list(await db.scalars(select(Lead))))

    session = _session(bot)
    await walker.tap(StepId.SUMMARY, VALUE_ORDER)
    session.clear()
    await walker.tap(StepId.SUMMARY, VALUE_ORDER_CONFIRM)

    async with bot_session_factory() as db:
        leads_after = len(list(await db.scalars(select(Lead))))
    assert leads_after == leads_before, "a lead was created for an incompatible build"

    outgoing = [call for call in session.calls if type(call).__name__ == "SendMessage"]
    customer_texts = [
        str(getattr(call, "text", ""))
        for call in outgoing
        if getattr(call, "chat_id", None) == USER_ID
    ]
    assert any("⚠️" in text for text in customer_texts), customer_texts
    admin_texts = [
        str(getattr(call, "text", ""))
        for call in outgoing
        if getattr(call, "chat_id", None) == ADMIN_USER_ID
    ]
    assert any("заблокирован" in text for text in admin_texts), admin_texts

    labels = [
        label
        for call in outgoing
        if getattr(call, "chat_id", None) == USER_ID and getattr(call, "reply_markup", None)
        for label in _buttons(call.reply_markup)
    ]
    assert any("🔄" in label for label in labels), "no way to pick again"
