"""Multi-select priorities: the customer may care about several things.

The old configurator forced one choice. These tests pin the new contract:
several ticks survive the FSM, reach ``BuildRequirements`` in order, and
every ticked priority is visible to the part pickers - while code written
against the single ``priority`` field keeps working unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey

from app.bot.callbacks import VALUE_DONE, CfgCB
from app.bot.flows.configurator import StepId, build_requirements
from app.bot.keyboards.configurator import keyboard_for_step
from app.bot.middlewares import ThrottlingMiddleware
from app.bot.states import Configurator
from app.bot.views.configurator import render_question
from app.db.models import Base
from app.domain.enums import MAX_PRIORITIES, PRIORITY_ORDER, BuildTier, Priority, Purpose
from app.domain.requirements import BuildRequirements
from app.i18n import LOCALES, SUPPORTED_LANGUAGES, t
from app.services.catalog import get_catalog
from app.services.pricing import EstimatePriceProvider
from app.services.recommendation import generate_variants
from tests.fake_telegram import CHAT_ID, USER_ID, callback_update, make_bot

# --- domain -------------------------------------------------------------------


def _requirements(**kwargs: object) -> BuildRequirements:
    fields: dict[str, object] = {"budget_pln": 8000, "purpose": Purpose.GAMING}
    fields.update(kwargs)
    return BuildRequirements(**fields)  # type: ignore[arg-type]


def test_several_priorities_are_kept_in_the_order_they_were_ticked() -> None:
    reqs = _requirements(priorities=[Priority.SILENCE, Priority.LOOKS, Priority.MAX_FPS])
    assert reqs.priorities == [Priority.SILENCE, Priority.LOOKS, Priority.MAX_FPS]
    assert all(reqs.wants(p) for p in reqs.priorities)


def test_the_first_tick_becomes_the_primary_priority() -> None:
    """Everything written against the single field keeps reading something true."""
    reqs = _requirements(priorities=[Priority.COOLING, Priority.SILENCE])
    assert reqs.priority is Priority.COOLING


def test_a_single_value_caller_still_works() -> None:
    reqs = _requirements(priority=Priority.SILENCE)
    assert reqs.priority is Priority.SILENCE
    assert reqs.priorities == [Priority.SILENCE]
    assert reqs.wants(Priority.SILENCE)


def test_an_explicit_primary_leads_the_ticked_list() -> None:
    reqs = _requirements(priority=Priority.COOLING, priorities=[Priority.SILENCE])
    assert reqs.priority is Priority.COOLING
    assert reqs.priorities == [Priority.COOLING, Priority.SILENCE]


def test_the_default_is_still_price_performance() -> None:
    reqs = _requirements()
    assert reqs.priority is Priority.PRICE_PERFORMANCE
    assert reqs.priorities == [Priority.PRICE_PERFORMANCE]


def test_duplicates_collapse() -> None:
    reqs = _requirements(priorities=[Priority.SILENCE, Priority.SILENCE, Priority.LOOKS])
    assert reqs.priorities == [Priority.SILENCE, Priority.LOOKS]


def test_too_many_priorities_are_refused() -> None:
    with pytest.raises(ValueError):
        _requirements(priorities=list(PRIORITY_ORDER))


def test_answers_carry_every_tick_into_the_requirements() -> None:
    answers = {
        "budget_pln": 7000,
        "purpose": "gaming",
        "priorities": ["silence", "looks", "max_fps"],
        "priority": "silence",
    }
    reqs = build_requirements(answers)
    assert reqs.priorities == [Priority.SILENCE, Priority.LOOKS, Priority.MAX_FPS]


# --- the picker ---------------------------------------------------------------


def test_the_keyboard_offers_every_priority_and_a_done_button() -> None:
    markup = keyboard_for_step(StepId.PRIORITY, {}, "en")
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert len(PRIORITY_ORDER) == 9
    for priority in PRIORITY_ORDER:
        assert any(t("en", f"priority.{priority.value}") in label for label in labels)
    assert any(t("en", "nav.done") in label for label in labels)


def test_ticked_priorities_are_shown_as_ticked() -> None:
    markup = keyboard_for_step(StepId.PRIORITY, {"priorities": ["silence"]}, "en")
    labels = [b.text for row in markup.inline_keyboard for b in row]
    quiet = next(label for label in labels if t("en", "priority.silence") in label)
    loud = next(label for label in labels if t("en", "priority.cooling") in label)
    assert quiet.startswith("☑️")
    assert loud.startswith("☐")


def test_the_question_says_several_may_be_picked() -> None:
    """The hint counts what is ticked, so it is compared after formatting."""
    for language in SUPPORTED_LANGUAGES:
        text = render_question(StepId.PRIORITY, {"priorities": ["silence"]}, language)
        assert t(language, "cfg.priority.hint", count=1, max=MAX_PRIORITIES) in text
        assert "{count}" not in text and "{max}" not in text


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_priority_is_translated(language: str) -> None:
    for priority in Priority:
        key = f"priority.{priority.value}"
        assert key in LOCALES[language], f"{language} is missing {key}"


# --- the flow through Telegram -------------------------------------------------


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


async def _stand_on_the_priority_step(bot: Bot, dispatcher: Dispatcher) -> StorageKey:
    """Put the FSM exactly where the configurator asks for priorities."""
    key = StorageKey(bot_id=bot.id, chat_id=CHAT_ID, user_id=USER_ID)
    await dispatcher.storage.set_state(key, Configurator.active)
    await dispatcher.storage.set_data(
        key, {"current_step": StepId.PRIORITY.value, "budget_pln": 8000, "purpose": "gaming"}
    )
    return key


async def _tick(bot: Bot, dispatcher: Dispatcher, value: str, update_id: int) -> None:
    await dispatcher.feed_update(
        bot,
        callback_update(
            CfgCB(step=StepId.PRIORITY.value, value=value).pack(), update_id=update_id, bot=bot
        ),
    )


async def test_ticking_three_priorities_keeps_all_three_in_the_state(
    bot: Bot, dispatcher: Dispatcher
) -> None:
    key = await _stand_on_the_priority_step(bot, dispatcher)
    for index, value in enumerate(("silence", "looks", "max_fps"), start=6001):
        await _tick(bot, dispatcher, value, index)

    data = await dispatcher.storage.get_data(key)
    assert data["priorities"] == ["silence", "looks", "max_fps"]
    assert data["priority"] == "silence"
    assert data["current_step"] == StepId.PRIORITY.value, "ticking must not advance the step"


async def test_ticking_the_same_priority_twice_unticks_it(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_the_priority_step(bot, dispatcher)
    await _tick(bot, dispatcher, "silence", 6101)
    await _tick(bot, dispatcher, "silence", 6102)
    data = await dispatcher.storage.get_data(key)
    assert data["priorities"] == []


async def test_done_moves_on_and_an_empty_pick_does_not(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_the_priority_step(bot, dispatcher)
    await _tick(bot, dispatcher, VALUE_DONE, 6201)
    assert (await dispatcher.storage.get_data(key))["current_step"] == StepId.PRIORITY.value

    await _tick(bot, dispatcher, "cooling", 6202)
    await _tick(bot, dispatcher, VALUE_DONE, 6203)
    data = await dispatcher.storage.get_data(key)
    assert data["current_step"] != StepId.PRIORITY.value
    assert data["priorities"] == ["cooling"]


async def test_the_limit_stops_at_the_configured_maximum(bot: Bot, dispatcher: Dispatcher) -> None:
    key = await _stand_on_the_priority_step(bot, dispatcher)
    for index, priority in enumerate(PRIORITY_ORDER, start=6301):
        await _tick(bot, dispatcher, priority.value, index)
    data = await dispatcher.storage.get_data(key)
    assert len(data["priorities"]) == MAX_PRIORITIES


# --- the generator listens to every tick ---------------------------------------


def _build(reqs: BuildRequirements):  # type: ignore[no-untyped-def]
    """Builds for these requirements, cheapest tier first."""
    catalog = get_catalog()
    prices = {
        cid: offers[0].price_pln
        for cid, offers in EstimatePriceProvider().get_offers([c.id for c in catalog]).items()
    }
    variants = generate_variants(
        reqs,
        catalog,
        prices,
        # The component budget, not the customer price: labour and margin
        # sit on top and are the pricing engine's business, not the
        # generator's.
        acquisition_budget_pln=Decimal(reqs.budget_pln) * Decimal("0.7"),
    )
    order = (BuildTier.OPTIMAL, BuildTier.PERFORMANCE, BuildTier.BUDGET)
    return [variants[tier] for tier in order if tier in variants]


def test_quiet_and_rgb_and_performance_are_all_honoured() -> None:
    """Three ticks: the build must answer all three, not only the first."""
    from app.domain.components import CaseSpec, CoolerSpec
    from app.domain.components import ComponentCategory as C

    reqs = _requirements(
        budget_pln=12000,
        priorities=[Priority.SILENCE, Priority.LOOKS, Priority.MAX_FPS],
    )
    options = _build(reqs)
    assert options, "a 12 000 PLN gaming build must exist"
    parts = options[0].parts

    cooler = parts.get(C.COOLER)
    case = parts.get(C.CASE)
    assert cooler is not None and case is not None
    cooler_spec = cooler.spec
    case_spec = case.spec
    assert isinstance(cooler_spec, CoolerSpec) and isinstance(case_spec, CaseSpec)
    cpu_spec = parts[C.CPU].spec
    # Quiet: real headroom over the processor's draw.
    assert cooler_spec.tdp_rating_w >= getattr(cpu_spec, "max_power_w", 0)
    # Looks: something in the machine is actually lit.
    assert case_spec.rgb or cooler_spec.rgb or getattr(parts[C.RAM].spec, "rgb", False)


def test_low_power_consumption_prefers_a_more_efficient_supply() -> None:
    from app.domain.components import ComponentCategory as C
    from app.domain.components import PsuSpec

    plain = _build(_requirements(budget_pln=9000))
    green = _build(_requirements(budget_pln=9000, priorities=[Priority.EFFICIENCY]))
    assert plain and green

    def rank(option) -> int:  # type: ignore[no-untyped-def]
        spec = option.parts[C.PSU].spec
        assert isinstance(spec, PsuSpec)
        order = {"80+ bronze": 1, "80+ gold": 3, "80+ platinum": 4}
        return order.get(spec.efficiency.lower(), 0)

    assert rank(green[0]) >= rank(plain[0])


def test_the_price_of_caring_about_something_stays_inside_the_budget() -> None:
    """Preferences may reorder parts; they must never blow the component budget."""
    reqs = _requirements(
        budget_pln=9000,
        priorities=[Priority.SILENCE, Priority.COOLING, Priority.UPGRADEABILITY],
    )
    ceiling = Decimal(9000) * Decimal("0.7")
    options = _build(reqs)
    assert options
    for option in options:
        assert option.acquisition_cost_pln <= ceiling
