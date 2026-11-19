from __future__ import annotations

import pytest

from app.bot.callbacks import CfgCB, NavAction, NavCB
from app.bot.flows.configurator import StepId
from app.bot.keyboards.common import language_kb, main_menu_kb
from app.bot.keyboards.configurator import keyboard_for_step
from app.i18n import SUPPORTED_LANGUAGES

TELEGRAM_CALLBACK_DATA_LIMIT = 64

QUESTION_STEPS = [step for step in StepId if step is not StepId.SUMMARY]


def _all_buttons(markup) -> list:
    return [button for row in markup.inline_keyboard for button in row]


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
@pytest.mark.parametrize("step", list(StepId))
def test_every_step_renders_a_non_empty_keyboard(step: StepId, lang: str) -> None:
    markup = keyboard_for_step(step, {"purpose": "gaming"}, lang)
    assert _all_buttons(markup), f"{step} produced no buttons"


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
@pytest.mark.parametrize("step", list(StepId))
def test_callback_data_fits_telegram_limit(step: StepId, lang: str) -> None:
    for button in _all_buttons(keyboard_for_step(step, {"purpose": "gaming"}, lang)):
        assert button.callback_data is not None
        encoded = button.callback_data.encode("utf-8")
        assert len(encoded) <= TELEGRAM_CALLBACK_DATA_LIMIT, button.callback_data


@pytest.mark.parametrize("step", QUESTION_STEPS)
def test_question_steps_offer_back_and_cancel(step: StepId) -> None:
    markup = keyboard_for_step(step, {"purpose": "gaming"}, "ru")
    actions = set()
    for button in _all_buttons(markup):
        try:
            actions.add(NavCB.unpack(button.callback_data or "").action)
        except (ValueError, TypeError):
            continue
    assert {NavAction.BACK, NavAction.CANCEL} <= actions


@pytest.mark.parametrize("step", QUESTION_STEPS)
def test_answer_buttons_are_tagged_with_their_own_step(step: StepId) -> None:
    """Stale-tap protection compares this tag against the current step."""
    for button in _all_buttons(keyboard_for_step(step, {"purpose": "gaming"}, "ru")):
        try:
            payload = CfgCB.unpack(button.callback_data or "")
        except (ValueError, TypeError):
            continue
        assert payload.step == step.value


def test_selected_games_are_marked() -> None:
    markup = keyboard_for_step(StepId.GAMES, {"games": ["cs2"]}, "ru")
    labels = [button.text for button in _all_buttons(markup)]
    assert any(label.startswith("✅") and "CS2" in label for label in labels)
    assert not any(label.startswith("✅") and "Valorant" in label for label in labels)


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_main_menu_has_all_entries(lang: str) -> None:
    buttons = _all_buttons(main_menu_kb(lang))
    assert len(buttons) == 10
    assert all(button.text.strip() for button in buttons)


def test_language_picker_lists_every_locale() -> None:
    assert len(_all_buttons(language_kb())) == len(SUPPORTED_LANGUAGES)
