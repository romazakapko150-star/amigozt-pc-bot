"""The monitor step must actually move the conversation on.

Regression cover for a step that looked alive and was not: the offered
monitors were computed while rendering the keyboard, *after* the FSM had
already been saved, so the list never reached storage. The next tap read an
empty list, failed its bounds check and returned silently - the customer saw
a step that swallowed every press.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey

from app.bot.callbacks import (
    PICK_PREFIX,
    VALUE_BACK_TO_LIST,
    VALUE_CLEAR,
    VALUE_DONE,
    VALUE_SKIP,
    CfgCB,
    NavAction,
    NavCB,
)
from app.bot.flows.configurator import (
    MONITOR_OPTIONS_KEY,
    PICK_CATEGORY_KEY,
    PICK_OPTIONS_KEY,
    StepId,
)
from app.bot.middlewares import ThrottlingMiddleware
from app.bot.states import Configurator
from app.db.models import Base
from app.domain.components import ComponentCategory
from tests.fake_telegram import CHAT_ID, USER_ID, callback_update, make_bot

ANSWERS = {
    "current_step": StepId.MONITOR.value,
    "budget_pln": 9000,
    "purpose": "gaming",
    "games": ["cs2"],
    "resolution": "1440p",
    "target_fps": "144",
    "priorities": ["silence", "looks"],
    "priority": "silence",
    "aesthetics": "black_rgb",
    "wifi": True,
    "bluetooth": True,
    "storage_gb": 1000,
    "ram_gb": 32,
    "cpu_brand": "any",
    "gpu_brand": "any",
}


@pytest_asyncio.fixture
async def bot(dispatcher: Dispatcher, bot_engine) -> AsyncIterator[Bot]:  # type: ignore[no-untyped-def]
    async with bot_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    telegram_bot = make_bot()
    for middleware in dispatcher.update.outer_middleware:
        if isinstance(middleware, ThrottlingMiddleware):
            middleware.reset()
    key = StorageKey(bot_id=telegram_bot.id, chat_id=CHAT_ID, user_id=USER_ID)
    await dispatcher.storage.set_state(key, None)
    await dispatcher.storage.set_data(key, {})
    yield telegram_bot
    await telegram_bot.session.close()


def _key(bot: Bot) -> StorageKey:
    return StorageKey(bot_id=bot.id, chat_id=CHAT_ID, user_id=USER_ID)


#: The trail "Back" walks, as the real flow would have built it.
HISTORY = [
    StepId.BUDGET.value,
    StepId.PURPOSE.value,
    StepId.GAMES.value,
    StepId.RESOLUTION.value,
    StepId.FPS.value,
    StepId.PRIORITY.value,
    StepId.AESTHETICS.value,
    StepId.CONNECTIVITY.value,
    StepId.STORAGE.value,
    StepId.RAM.value,
    StepId.CPU.value,
    StepId.GPU.value,
]


async def _stand_on_monitor(bot: Bot, dispatcher: Dispatcher, **overrides: object) -> StorageKey:
    """Arrive at the monitor step the way the flow does: from the GPU answer."""
    key = _key(bot)
    await dispatcher.storage.set_state(key, Configurator.active)
    await dispatcher.storage.set_data(
        key,
        {**ANSWERS, **overrides, "current_step": StepId.GPU.value, "_history": list(HISTORY)},
    )
    await _tap(bot, dispatcher, StepId.GPU, "any", 7000)
    return key


async def _tap(bot: Bot, dispatcher: Dispatcher, step: StepId, value: str, update_id: int) -> None:
    await dispatcher.feed_update(
        bot,
        callback_update(CfgCB(step=step.value, value=value).pack(), update_id=update_id, bot=bot),
    )


# --- the bug -------------------------------------------------------------------


async def test_the_offered_monitors_survive_into_the_state(
    bot: Bot, dispatcher: Dispatcher
) -> None:
    """The callback carries a position, so the list it indexes must be stored."""
    key = await _stand_on_monitor(bot, dispatcher)
    data = await dispatcher.storage.get_data(key)
    assert data["current_step"] == StepId.MONITOR.value
    assert data.get(MONITOR_OPTIONS_KEY), "the offered monitors were never persisted"


async def test_picking_a_monitor_selects_it_and_moves_on(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    offered = (await dispatcher.storage.get_data(key))[MONITOR_OPTIONS_KEY]
    assert offered

    await _tap(bot, dispatcher, StepId.MONITOR, "0", 7001)
    data = await dispatcher.storage.get_data(key)
    assert data["setup"][ComponentCategory.MONITOR.value] == offered[0]
    assert data["current_step"] == StepId.MONITOR.value, "ticking must not skip the step"

    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_SKIP, 7002)
    assert (await dispatcher.storage.get_data(key))["current_step"] == StepId.PERIPHERALS.value


@pytest.mark.parametrize("position", [0, 1, 2])
async def test_every_offered_position_is_selectable(
    bot: Bot, dispatcher: Dispatcher, position: int
) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    offered = (await dispatcher.storage.get_data(key))[MONITOR_OPTIONS_KEY]
    if position >= len(offered):
        pytest.skip("fewer monitors offered than positions tested")
    await _tap(bot, dispatcher, StepId.MONITOR, str(position), 7100 + position)
    data = await dispatcher.storage.get_data(key)
    assert data["setup"][ComponentCategory.MONITOR.value] == offered[position]


async def test_no_monitor_moves_on_without_buying_a_screen(
    bot: Bot, dispatcher: Dispatcher
) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_SKIP, 7200)
    data = await dispatcher.storage.get_data(key)
    assert data["current_step"] == StepId.PERIPHERALS.value
    assert ComponentCategory.MONITOR.value not in (data.get("setup") or {})


async def test_a_chosen_monitor_can_be_unticked(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, "0", 7300)
    assert (await dispatcher.storage.get_data(key))["setup"]
    await _tap(bot, dispatcher, StepId.MONITOR, "0", 7301)
    data = await dispatcher.storage.get_data(key)
    assert ComponentCategory.MONITOR.value not in (data.get("setup") or {})


async def test_an_out_of_range_position_is_ignored_not_crashing(
    bot: Bot, dispatcher: Dispatcher
) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, "99", 7400)
    data = await dispatcher.storage.get_data(key)
    assert data["current_step"] == StepId.MONITOR.value
    assert not (data.get("setup") or {})


# --- navigation out of the step --------------------------------------------------


async def test_back_from_the_monitor_step_returns_to_the_gpu_question(
    bot: Bot, dispatcher: Dispatcher
) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    await dispatcher.feed_update(
        bot, callback_update(NavCB(action=NavAction.BACK).pack(), update_id=7500, bot=bot)
    )
    assert (await dispatcher.storage.get_data(key))["current_step"] == StepId.GPU.value


async def test_back_into_the_monitor_step_still_offers_monitors(
    bot: Bot, dispatcher: Dispatcher
) -> None:
    """Returning to the step must restock the list the callbacks index into."""
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_SKIP, 7600)
    await dispatcher.feed_update(
        bot, callback_update(NavCB(action=NavAction.BACK).pack(), update_id=7601, bot=bot)
    )
    data = await dispatcher.storage.get_data(key)
    assert data["current_step"] == StepId.MONITOR.value
    assert data.get(MONITOR_OPTIONS_KEY), "the offer was not restocked on the way back"
    await _tap(bot, dispatcher, StepId.MONITOR, "0", 7602)
    assert (await dispatcher.storage.get_data(key))["setup"]


async def test_the_step_survives_a_changed_resolution(bot: Bot, dispatcher: Dispatcher) -> None:
    """Going back and asking for 4K must re-offer screens that can show it."""
    key = await _stand_on_monitor(bot, dispatcher)
    before = (await dispatcher.storage.get_data(key))[MONITOR_OPTIONS_KEY]

    await _stand_on_monitor(bot, dispatcher, resolution="4k")
    after = (await dispatcher.storage.get_data(key))[MONITOR_OPTIONS_KEY]
    assert after and after != before


# --- and out the other side ------------------------------------------------------


async def test_monitor_then_peripherals_then_the_card(bot: Bot, dispatcher: Dispatcher) -> None:
    """The whole tail of the flow, which the stuck step used to block."""
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, "0", 7800)
    # "Continue" keeps the screen; "No monitor" would have cleared it.
    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_DONE, 7801)

    data = await dispatcher.storage.get_data(key)
    assert data["current_step"] == StepId.PERIPHERALS.value

    # Peripherals take two taps now: open the category, then pick a product.
    await _tap(bot, dispatcher, StepId.PERIPHERALS, ComponentCategory.MOUSE.value, 7802)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, f"{PICK_PREFIX}0", 7803)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, VALUE_DONE, 7804)

    data = await dispatcher.storage.get_data(key)
    assert data["current_step"] == StepId.SUMMARY.value
    setup = data["setup"]
    assert ComponentCategory.MONITOR.value in setup
    assert ComponentCategory.MOUSE.value in setup


async def test_the_confirm_button_appears_only_once_a_screen_is_picked(
    bot: Bot, dispatcher: Dispatcher
) -> None:
    """Without it, choosing a monitor is a dead end: nothing means "carry on"."""
    from app.bot.keyboards.configurator import keyboard_for_step
    from app.i18n import t

    offered = ["gigabyte-m27q"]
    empty = keyboard_for_step(StepId.MONITOR, {MONITOR_OPTIONS_KEY: offered, "setup": {}}, "en")
    labels = [b.text for row in empty.inline_keyboard for b in row]
    assert not any(t("en", "cfg.monitor.continue") in label for label in labels)

    picked = keyboard_for_step(
        StepId.MONITOR,
        {MONITOR_OPTIONS_KEY: offered, "setup": {ComponentCategory.MONITOR.value: offered[0]}},
        "en",
    )
    labels = [b.text for row in picked.inline_keyboard for b in row]
    assert any(t("en", "cfg.monitor.continue") in label for label in labels)
    assert any(t("en", "cfg.monitor.skip") in label for label in labels)


async def test_continue_keeps_the_screen_and_moves_on(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    offered = (await dispatcher.storage.get_data(key))[MONITOR_OPTIONS_KEY]
    await _tap(bot, dispatcher, StepId.MONITOR, "1", 7900)
    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_DONE, 7901)
    data = await dispatcher.storage.get_data(key)
    assert data["current_step"] == StepId.PERIPHERALS.value
    assert data["setup"][ComponentCategory.MONITOR.value] == offered[1]


# --- choosing a peripheral, rather than being given one --------------------------


async def test_tapping_a_category_opens_its_products(bot: Bot, dispatcher: Dispatcher) -> None:
    """The customer chooses the mouse; the system only suggests an order."""
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_SKIP, 8000)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, ComponentCategory.MOUSE.value, 8001)

    data = await dispatcher.storage.get_data(key)
    assert data[PICK_CATEGORY_KEY] == ComponentCategory.MOUSE.value
    assert len(data[PICK_OPTIONS_KEY]) > 1, "a shelf with one item is not a choice"
    assert not (data.get("setup") or {}), "opening a category must not buy anything"


async def test_picking_a_number_stores_that_exact_product(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_SKIP, 8100)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, ComponentCategory.MOUSE.value, 8101)
    offered = (await dispatcher.storage.get_data(key))[PICK_OPTIONS_KEY]

    await _tap(bot, dispatcher, StepId.PERIPHERALS, f"{PICK_PREFIX}1", 8102)
    data = await dispatcher.storage.get_data(key)
    assert data["setup"][ComponentCategory.MOUSE.value] == offered[1]
    assert PICK_CATEGORY_KEY not in data, "picking closes the shelf"


async def test_the_suggested_model_is_offered_first(bot: Bot, dispatcher: Dispatcher) -> None:
    """The old automatic choice survives as the ordering, not as a decision."""
    from app.bot.handlers.configurator import _category_offer, _partial_requirements
    from app.services.recommendation.setup import suggest_for

    answers = dict(ANSWERS)
    offered = _category_offer(ComponentCategory.MOUSE.value, answers)
    suggested = suggest_for(ComponentCategory.MOUSE, _partial_requirements(answers))
    assert suggested is not None
    assert offered[0].id == suggested.id


async def test_a_choice_can_be_removed_again(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_SKIP, 8200)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, ComponentCategory.MOUSE.value, 8201)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, f"{PICK_PREFIX}0", 8202)
    assert (await dispatcher.storage.get_data(key))["setup"]

    await _tap(bot, dispatcher, StepId.PERIPHERALS, ComponentCategory.MOUSE.value, 8203)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, VALUE_CLEAR, 8204)
    data = await dispatcher.storage.get_data(key)
    assert ComponentCategory.MOUSE.value not in (data.get("setup") or {})


async def test_leaving_a_category_keeps_what_was_chosen(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_SKIP, 8300)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, ComponentCategory.MOUSE.value, 8301)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, f"{PICK_PREFIX}0", 8302)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, ComponentCategory.HEADSET.value, 8303)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, VALUE_BACK_TO_LIST, 8304)

    data = await dispatcher.storage.get_data(key)
    assert PICK_CATEGORY_KEY not in data
    assert ComponentCategory.MOUSE.value in data["setup"]
    assert ComponentCategory.HEADSET.value not in data["setup"]


async def test_an_out_of_range_pick_is_ignored(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_SKIP, 8400)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, ComponentCategory.MOUSE.value, 8401)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, f"{PICK_PREFIX}99", 8402)
    data = await dispatcher.storage.get_data(key)
    assert not (data.get("setup") or {})
    assert data[PICK_CATEGORY_KEY] == ComponentCategory.MOUSE.value


async def test_done_advances_even_with_a_shelf_open(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_monitor(bot, dispatcher)
    await _tap(bot, dispatcher, StepId.MONITOR, VALUE_SKIP, 8500)
    await _tap(bot, dispatcher, StepId.PERIPHERALS, VALUE_DONE, 8501)
    data = await dispatcher.storage.get_data(key)
    assert data["current_step"] == StepId.SUMMARY.value
    assert PICK_CATEGORY_KEY not in data


def test_every_pick_callback_fits_telegrams_limit() -> None:
    """callback_data is capped at 64 bytes; positions keep us far inside it."""
    for value in (f"{PICK_PREFIX}9", VALUE_CLEAR, VALUE_BACK_TO_LIST, "mouse"):
        packed = CfgCB(step=StepId.PERIPHERALS.value, value=value).pack()
        assert len(packed.encode("utf-8")) <= 64, packed
