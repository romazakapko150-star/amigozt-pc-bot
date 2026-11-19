from __future__ import annotations

import pytest

from app.bot.flows.configurator import (
    FIRST_STEP,
    HISTORY_KEY,
    PREFILLED_KEY,
    StepId,
    applicable_steps,
    build_requirements,
    next_step,
    pop_history,
    previous_step,
    progress,
    push_history,
)
from app.domain.enums import CpuBrand, GpuBrand, Purpose, Resolution, TargetFps


def test_first_step_is_budget() -> None:
    assert FIRST_STEP is StepId.BUDGET


def test_gaming_flow_asks_about_games_and_fps() -> None:
    steps = applicable_steps({"purpose": "gaming"})
    assert StepId.GAMES in steps
    assert StepId.FPS in steps


@pytest.mark.parametrize("purpose", ["work", "design", "ai_ml", "workstation"])
def test_non_gaming_flow_skips_games_and_fps(purpose: str) -> None:
    steps = applicable_steps({"purpose": purpose})
    assert StepId.GAMES not in steps
    assert StepId.FPS not in steps


def test_streaming_and_universal_count_as_gaming() -> None:
    for purpose in ("gaming_streaming", "universal"):
        assert StepId.GAMES in applicable_steps({"purpose": purpose})


def test_next_step_skips_inapplicable_questions() -> None:
    assert next_step(StepId.PURPOSE, {"purpose": "work"}) is StepId.RESOLUTION
    assert next_step(StepId.PURPOSE, {"purpose": "gaming"}) is StepId.GAMES
    assert next_step(StepId.RESOLUTION, {"purpose": "work"}) is StepId.PRIORITY


def test_flow_terminates_at_summary() -> None:
    # The machine is configured first, then the desk around it.
    assert next_step(StepId.GPU, {"purpose": "gaming"}) is StepId.MONITOR
    assert next_step(StepId.MONITOR, {"purpose": "gaming"}) is StepId.PERIPHERALS
    assert next_step(StepId.PERIPHERALS, {"purpose": "gaming"}) is StepId.SUMMARY
    assert next_step(StepId.SUMMARY, {"purpose": "gaming"}) is StepId.SUMMARY


def test_previous_step_of_first_step_is_none() -> None:
    assert previous_step(StepId.BUDGET, {}) is None


def test_previous_step_skips_inapplicable_questions() -> None:
    assert previous_step(StepId.PRIORITY, {"purpose": "work"}) is StepId.RESOLUTION
    assert previous_step(StepId.PRIORITY, {"purpose": "gaming"}) is StepId.FPS


def test_step_that_became_irrelevant_resumes_forward() -> None:
    """User stands on GAMES, then changes the purpose to a non-gaming one."""
    answers = {"purpose": "work"}
    assert next_step(StepId.GAMES, answers) is StepId.RESOLUTION


def test_prefilled_steps_are_not_asked() -> None:
    answers = {"purpose": Purpose.GAMING.value, PREFILLED_KEY: [StepId.PURPOSE.value]}
    steps = applicable_steps(answers)
    assert StepId.PURPOSE not in steps
    assert next_step(StepId.BUDGET, answers) is StepId.GAMES


def test_progress_counts_only_questions() -> None:
    gaming_current, gaming_total = progress(StepId.BUDGET, {"purpose": "gaming"})
    work_current, work_total = progress(StepId.BUDGET, {"purpose": "work"})

    assert gaming_current == work_current == 1
    assert gaming_total > work_total
    assert StepId.SUMMARY not in applicable_steps({"purpose": "gaming"})[:-1]


def test_history_round_trip() -> None:
    answers: dict = {}
    push_history(answers, StepId.BUDGET)
    push_history(answers, StepId.PURPOSE)
    push_history(answers, StepId.RESOLUTION)

    assert pop_history(answers) is StepId.PURPOSE
    assert pop_history(answers) is StepId.BUDGET
    # Nothing left before the first step.
    assert pop_history(answers) is None
    assert answers[HISTORY_KEY] == [StepId.BUDGET.value]


def test_history_ignores_repeated_pushes() -> None:
    answers: dict = {}
    push_history(answers, StepId.GAMES)
    push_history(answers, StepId.GAMES)
    assert answers[HISTORY_KEY] == [StepId.GAMES.value]


def test_build_requirements_from_complete_answers(gaming_answers: dict) -> None:
    requirements = build_requirements(gaming_answers)

    assert requirements.budget_pln == 6000
    assert requirements.purpose is Purpose.GAMING
    assert requirements.resolution is Resolution.QHD
    assert requirements.target_fps is TargetFps.FPS_144
    assert requirements.cpu_brand is CpuBrand.AMD
    assert requirements.gpu_brand is GpuBrand.NVIDIA
    assert requirements.wifi and requirements.bluetooth
    assert requirements.game_titles == ["CS2", "Cyberpunk 2077"]


def test_build_requirements_defaults_optional_answers() -> None:
    requirements = build_requirements({"budget_pln": 3000, "purpose": "work"})

    assert requirements.resolution is Resolution.FHD
    assert requirements.target_fps is None
    assert requirements.storage_gb is None  # "choose for me"
    assert requirements.ram_gb is None
    assert requirements.cpu_brand is CpuBrand.ANY


def test_build_requirements_rejects_incomplete_answers() -> None:
    with pytest.raises((KeyError, ValueError)):
        build_requirements({"purpose": "gaming"})


def test_flow_covers_every_step_id() -> None:
    """Guards against adding a StepId without wiring it into the graph."""
    reachable = set(applicable_steps({"purpose": "gaming"}))
    assert reachable == set(StepId)
