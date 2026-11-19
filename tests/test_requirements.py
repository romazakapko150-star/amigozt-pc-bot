from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.enums import MAX_BUDGET_PLN, MIN_BUDGET_PLN, Purpose, Resolution
from app.domain.requirements import MAX_GAMES, BuildRequirements


def _requirements(**overrides: object) -> BuildRequirements:
    payload: dict = {"budget_pln": 5000, "purpose": Purpose.GAMING}
    payload.update(overrides)
    return BuildRequirements(**payload)  # type: ignore[arg-type]


@pytest.mark.parametrize("budget", [MIN_BUDGET_PLN, 5000, MAX_BUDGET_PLN])
def test_budget_within_bounds_is_accepted(budget: int) -> None:
    assert _requirements(budget_pln=budget).budget_pln == budget


@pytest.mark.parametrize("budget", [0, -1, MIN_BUDGET_PLN - 1, MAX_BUDGET_PLN + 1])
def test_budget_outside_bounds_is_rejected(budget: int) -> None:
    with pytest.raises(ValidationError):
        _requirements(budget_pln=budget)


def test_game_titles_are_deduplicated_and_trimmed() -> None:
    requirements = _requirements(games=["  CS2  ", "CS2", "Dota   2"])
    assert requirements.games == ["CS2", "Dota 2"]


def test_game_title_length_is_capped() -> None:
    requirements = _requirements(games=["x" * 500])
    assert len(requirements.games[0]) <= 40


def test_too_many_games_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _requirements(games=[f"game {i}" for i in range(MAX_GAMES + 1)])


def test_known_game_keys_resolve_to_display_names() -> None:
    requirements = _requirements(games=["cs2", "My Indie Game"])
    assert requirements.game_titles == ["CS2", "My Indie Game"]


def test_needs_gaming_performance() -> None:
    assert _requirements(purpose=Purpose.GAMING).needs_gaming_performance
    assert not _requirements(purpose=Purpose.WORK).needs_gaming_performance
    # An office build with games listed still needs a capable GPU.
    assert _requirements(purpose=Purpose.WORK, games=["cs2"]).needs_gaming_performance


def test_serialises_to_json_safe_payload(gaming_answers: dict) -> None:
    """The requirements are persisted into a JSON column verbatim."""
    payload = _requirements(resolution=Resolution.UHD).model_dump(mode="json")
    assert payload["resolution"] == "4k"
    assert isinstance(payload["purpose"], str)
    assert BuildRequirements(**payload).resolution is Resolution.UHD
