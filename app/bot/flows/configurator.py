"""Configurator flow definition.

Pure logic on purpose: this module knows the order of the questions, which
questions apply to a given answer set, and how to turn collected answers into
a :class:`BuildRequirements`. It imports nothing from aiogram, which makes the
whole conversation graph unit-testable without a Telegram server.

The step list is data, not control flow, so adding or reordering a question is
a one-line change and the "Back" button keeps working automatically.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.domain.enums import (
    Aesthetics,
    CpuBrand,
    GpuBrand,
    Priority,
    Purpose,
    Resolution,
    TargetFps,
)
from app.domain.requirements import BuildRequirements

#: Key used inside the FSM data to remember the path the user walked, so that
#: "Back" works even across conditionally skipped steps.
HISTORY_KEY = "_history"

#: Monitors offered on the MONITOR step, in the order shown. The callback
#: carries the position, so the list has to survive between messages.
MONITOR_OPTIONS_KEY = "_monitor_options"

#: The peripheral category the customer is currently browsing, and the
#: products offered inside it. Like the monitor step, the buttons carry a
#: position rather than an id, so the list has to live in the FSM.
PICK_CATEGORY_KEY = "_pick_category"
PICK_OPTIONS_KEY = "_pick_options"

#: Steps answered up-front by an entry point (e.g. the "Gaming PC" menu button
#: pre-selects the purpose). They are removed from the question graph so the
#: user is not asked something they already implicitly answered.
PREFILLED_KEY = "_prefilled"


class StepId(StrEnum):
    BUDGET = "budget"
    PURPOSE = "purpose"
    GAMES = "games"
    RESOLUTION = "resolution"
    FPS = "fps"
    PRIORITY = "priority"
    AESTHETICS = "aesthetics"
    CONNECTIVITY = "connectivity"
    STORAGE = "storage"
    RAM = "ram"
    CPU = "cpu"
    GPU = "gpu"
    MONITOR = "monitor"
    PERIPHERALS = "peripherals"
    SUMMARY = "summary"


Answers = dict[str, Any]


def _is_gaming(answers: Answers) -> bool:
    raw = answers.get("purpose")
    if raw is None:
        return False
    try:
        return Purpose(raw).is_gaming
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class Step:
    id: StepId
    #: Whether this step should be asked given the answers collected so far.
    applies: Callable[[Answers], bool] = lambda _: True


#: Ordered question graph. ``SUMMARY`` is a terminal pseudo-step.
STEPS: tuple[Step, ...] = (
    Step(StepId.BUDGET),
    Step(StepId.PURPOSE),
    Step(StepId.GAMES, _is_gaming),
    Step(StepId.RESOLUTION),
    Step(StepId.FPS, _is_gaming),
    Step(StepId.PRIORITY),
    Step(StepId.AESTHETICS),
    Step(StepId.CONNECTIVITY),
    Step(StepId.STORAGE),
    Step(StepId.RAM),
    Step(StepId.CPU),
    Step(StepId.GPU),
    # The desk around the machine. Both are skippable: a customer who only
    # wants a tower is never made to answer them.
    Step(StepId.MONITOR),
    Step(StepId.PERIPHERALS),
    Step(StepId.SUMMARY),
)

_STEPS_BY_ID: dict[StepId, Step] = {step.id: step for step in STEPS}

FIRST_STEP: StepId = STEPS[0].id
LAST_STEP: StepId = STEPS[-1].id


def applicable_steps(answers: Answers) -> list[StepId]:
    """Steps that are relevant for the answers collected so far."""
    prefilled = set(answers.get(PREFILLED_KEY) or ())
    return [step.id for step in STEPS if step.id.value not in prefilled and step.applies(answers)]


def next_step(current: StepId, answers: Answers) -> StepId:
    """The step following ``current``, skipping non-applicable questions."""
    order = applicable_steps(answers)
    if current not in order:
        # ``current`` became irrelevant (e.g. purpose changed from gaming to
        # work while standing on GAMES): resume at the next still-valid step.
        remaining = [s for s in order if _index(s) > _index(current)]
        return remaining[0] if remaining else LAST_STEP
    position = order.index(current)
    return order[position + 1] if position + 1 < len(order) else LAST_STEP


def previous_step(current: StepId, answers: Answers) -> StepId | None:
    """The step preceding ``current``, or ``None`` if it is the first one."""
    order = applicable_steps(answers)
    if current not in order:
        earlier = [s for s in order if _index(s) < _index(current)]
        return earlier[-1] if earlier else None
    position = order.index(current)
    return order[position - 1] if position > 0 else None


def progress(current: StepId, answers: Answers) -> tuple[int, int]:
    """1-based ``(current, total)`` position, counting question steps only."""
    order = [s for s in applicable_steps(answers) if s is not StepId.SUMMARY]
    total = len(order)
    if current not in order:
        return total, total
    return order.index(current) + 1, total


def _index(step_id: StepId) -> int:
    return list(_STEPS_BY_ID).index(step_id)


# --- history -----------------------------------------------------------------


def push_history(answers: Answers, step: StepId) -> None:
    history: list[str] = answers.setdefault(HISTORY_KEY, [])
    if not history or history[-1] != step.value:
        history.append(step.value)


def pop_history(answers: Answers) -> StepId | None:
    """Remove the current step from the trail and return the previous one."""
    history: list[str] = answers.get(HISTORY_KEY) or []
    if len(history) < 2:
        return None
    history.pop()
    try:
        return StepId(history[-1])
    except ValueError:  # pragma: no cover - corrupted state
        return None


# --- answers -> domain --------------------------------------------------------


def build_requirements(answers: Answers) -> BuildRequirements:
    """Convert raw FSM answers into a validated domain object.

    Raises ``pydantic.ValidationError`` when mandatory answers are missing,
    which the handler layer turns into a restart rather than a traceback.
    """
    target_fps = answers.get("target_fps")
    return BuildRequirements(
        budget_pln=answers["budget_pln"],
        purpose=Purpose(answers["purpose"]),
        games=list(answers.get("games") or []),
        resolution=Resolution(answers.get("resolution") or Resolution.FHD),
        target_fps=TargetFps(target_fps) if target_fps else None,
        priority=Priority(answers.get("priority") or Priority.PRICE_PERFORMANCE),
        priorities=[Priority(p) for p in (answers.get("priorities") or [])],
        aesthetics=Aesthetics(answers.get("aesthetics") or Aesthetics.BLACK),
        wifi=bool(answers.get("wifi", False)),
        bluetooth=bool(answers.get("bluetooth", False)),
        storage_gb=answers.get("storage_gb"),
        ram_gb=answers.get("ram_gb"),
        cpu_brand=CpuBrand(answers.get("cpu_brand") or CpuBrand.ANY),
        gpu_brand=GpuBrand(answers.get("gpu_brand") or GpuBrand.ANY),
    )
