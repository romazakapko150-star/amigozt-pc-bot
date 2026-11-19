from __future__ import annotations

import pytest

from app.bot.flows.configurator import StepId, build_requirements
from app.bot.views.configurator import render_question, render_summary
from app.i18n import SUPPORTED_LANGUAGES

MAX_TELEGRAM_MESSAGE = 4096


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
@pytest.mark.parametrize("step", [s for s in StepId if s is not StepId.SUMMARY])
def test_every_question_renders(step: StepId, lang: str) -> None:
    text = render_question(step, {"purpose": "gaming"}, lang)
    assert text.strip()
    assert len(text) <= MAX_TELEGRAM_MESSAGE
    # A missing translation would leak the raw key into the message.
    assert not text.strip().endswith(".q")


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_summary_renders_in_every_language(lang: str, gaming_answers: dict) -> None:
    text = render_summary(build_requirements(gaming_answers), lang)

    assert "6 000 PLN" in text
    assert "144 FPS" in text
    assert "CS2" in text
    assert len(text) <= MAX_TELEGRAM_MESSAGE


def test_summary_escapes_user_supplied_game_titles(gaming_answers: dict) -> None:
    """A custom game title must never inject HTML into the message."""
    gaming_answers["games"] = ["<b>pwned</b>"]
    text = render_summary(build_requirements(gaming_answers), "ru")

    assert "<b>pwned</b>" not in text
    assert "&lt;b&gt;pwned&lt;/b&gt;" in text


def test_summary_reports_auto_choices(gaming_answers: dict) -> None:
    gaming_answers["storage_gb"] = None
    gaming_answers["ram_gb"] = None
    text = render_summary(build_requirements(gaming_answers), "en")
    assert text.count("my choice") == 2


def test_progress_header_is_present() -> None:
    assert "1" in render_question(StepId.BUDGET, {"purpose": "gaming"}, "en")


def test_gaming_and_office_flows_report_different_totals() -> None:
    gaming = render_question(StepId.BUDGET, {"purpose": "gaming"}, "en")
    office = render_question(StepId.BUDGET, {"purpose": "work"}, "en")
    assert gaming != office
