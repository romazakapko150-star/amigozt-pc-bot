"""User requirements collected by the configurator.

This is the single contract between the Telegram layer and the (Phase 2)
recommendation engine: the bot produces a ``BuildRequirements``, the engine
consumes it. Nothing here depends on aiogram or on the database.

Component-level wishes carry a status:

* ``LOCKED``    - the customer chose this exact part; the engine never
                  swaps it without asking;
* ``PREFERRED`` - keep it when it fits and the budget allows, drop it
                  otherwise;
* ``FLEXIBLE``  - anything else; changed first when a conflict appears.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.components import ComponentCategory
from app.domain.enums import (
    KNOWN_GAMES,
    MAX_BUDGET_PLN,
    MAX_PRIORITIES,
    MIN_BUDGET_PLN,
    Aesthetics,
    CpuBrand,
    GpuBrand,
    Priority,
    Purpose,
    Resolution,
    TargetFps,
)

MAX_GAMES = 10
MAX_GAME_NAME_LEN = 40


class ComponentStatus(StrEnum):
    LOCKED = "locked"
    PREFERRED = "preferred"
    FLEXIBLE = "flexible"


def _clean_choices(raw: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        category = ComponentCategory(str(key)).value
        component_id = " ".join(str(value).split())
        if component_id:
            cleaned[category] = component_id
    return cleaned


class BuildRequirements(BaseModel):
    """Everything the user told us, normalised."""

    model_config = ConfigDict(use_enum_values=False, validate_assignment=True)

    budget_pln: int = Field(ge=MIN_BUDGET_PLN, le=MAX_BUDGET_PLN)
    purpose: Purpose
    games: list[str] = Field(default_factory=list, max_length=MAX_GAMES)
    resolution: Resolution = Resolution.FHD
    target_fps: TargetFps | None = None
    #: The primary priority. Kept as a single value so every caller written
    #: against the one-choice configurator keeps working; it always mirrors
    #: ``priorities[0]``.
    priority: Priority = Priority.PRICE_PERFORMANCE
    #: Everything the customer ticked, in the order they ticked it.
    priorities: list[Priority] = Field(default_factory=list, max_length=MAX_PRIORITIES)
    aesthetics: Aesthetics = Aesthetics.BLACK
    wifi: bool = False
    bluetooth: bool = False
    # ``None`` means "let the system decide" - the optimizer picks the best
    # capacity for the remaining budget.
    storage_gb: int | None = None
    ram_gb: int | None = None
    cpu_brand: CpuBrand = CpuBrand.ANY
    gpu_brand: GpuBrand = GpuBrand.ANY
    #: category value -> component id the customer fixed / would like.
    locked: dict[str, str] = Field(default_factory=dict)
    preferred: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sync_priorities(self) -> BuildRequirements:
        """Keep ``priority`` and ``priorities`` telling the same story.

        Old callers pass only ``priority``; the configurator passes only
        ``priorities``. Whichever arrives, both end up populated, with no
        duplicates and the primary choice first.
        """
        chosen: list[Priority] = []
        for item in self.priorities:
            value = Priority(item)
            if value not in chosen:
                chosen.append(value)
        if not chosen:
            chosen = [self.priority]
        elif self.priority not in chosen and "priority" in self.model_fields_set:
            # A single-value caller wins the primary slot only when it was
            # given explicitly; otherwise the first tick is the primary.
            chosen.insert(0, self.priority)
        if chosen[0] is not self.priority or list(self.priorities) != chosen:
            object.__setattr__(self, "priority", chosen[0])
            object.__setattr__(self, "priorities", chosen[:MAX_PRIORITIES])
        return self

    def wants(self, priority: Priority) -> bool:
        """True when the customer ticked this priority (in any position)."""
        return priority in self.priorities

    @field_validator("games")
    @classmethod
    def _clean_games(cls, games: list[str]) -> list[str]:
        cleaned: list[str] = []
        for game in games:
            name = " ".join(game.split())[:MAX_GAME_NAME_LEN]
            if name and name not in cleaned:
                cleaned.append(name)
        return cleaned

    @field_validator("locked", "preferred")
    @classmethod
    def _clean_component_choices(cls, raw: dict[str, str]) -> dict[str, str]:
        return _clean_choices(raw)

    @property
    def game_titles(self) -> list[str]:
        """Human readable game names (known keys resolved to display names)."""
        return [KNOWN_GAMES.get(g, g) for g in self.games]

    @property
    def needs_gaming_performance(self) -> bool:
        return self.purpose.is_gaming or bool(self.games)

    # --- component statuses -------------------------------------------------

    def locked_id(self, category: ComponentCategory) -> str | None:
        return self.locked.get(category.value)

    def preferred_id(self, category: ComponentCategory) -> str | None:
        return self.preferred.get(category.value)

    def status_of(self, category: ComponentCategory) -> ComponentStatus:
        if category.value in self.locked:
            return ComponentStatus.LOCKED
        if category.value in self.preferred:
            return ComponentStatus.PREFERRED
        return ComponentStatus.FLEXIBLE

    @property
    def locked_categories(self) -> set[ComponentCategory]:
        return {ComponentCategory(key) for key in self.locked}
