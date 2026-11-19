"""Helpers shared by the rule modules."""

from __future__ import annotations

from typing import TypeVar

from app.domain.components import Component, ComponentCategory, Position

Parts = dict[ComponentCategory, Component]

S = TypeVar("S")


def spec_of(parts: Parts, category: ComponentCategory, expected: type[S]) -> S | None:
    component = parts.get(category)
    if component is None:
        return None
    spec = component.spec
    return spec if isinstance(spec, expected) else None


def verified(parts: Parts, *categories: ComponentCategory) -> bool:
    """True only when every named part carries manufacturer-verified specs."""
    for category in categories:
        component = parts.get(category)
        if component is None or not component.spec_verified:
            return False
    return True


#: Fan-width families: a rail that takes the bigger radiator takes the
#: smaller one of the same width (two of three fan positions used).
_FAMILIES: tuple[tuple[int, ...], ...] = ((120, 240, 360, 480), (140, 280, 420))


def radiator_fits(size_mm: int, supported: list[int]) -> tuple[bool, bool]:
    """``(fits, derived)``: fits when listed, or when a larger radiator of the
    same fan width is listed (``derived`` is then True)."""
    if size_mm in supported:
        return True, False
    for family in _FAMILIES:
        if size_mm in family and any(s in supported and s > size_mm for s in family):
            return True, True
    return False, False


#: Where a radiator goes by preference: the top keeps the GPU bay free.
RADIATOR_POSITION_PREFERENCE: tuple[Position, ...] = (
    Position.TOP,
    Position.FRONT,
    Position.SIDE,
    Position.BOTTOM,
    Position.REAR,
)


def choose_radiator_position(
    positions: dict[Position, list[int]], size_mm: int
) -> tuple[Position | None, bool]:
    """First preferred position that takes ``size_mm``; ``derived`` as above."""
    for position in RADIATOR_POSITION_PREFERENCE:
        supported = positions.get(position)
        if not supported:
            continue
        fits, derived = radiator_fits(size_mm, supported)
        if fits:
            return position, derived
    return None, False


def version_number(label: str | None) -> float | None:
    """'2.1b' -> 2.1, '1.4a' -> 1.4, None -> None."""
    if not label:
        return None
    digits = ""
    for char in label:
        if char.isdigit() or (char == "." and "." not in digits):
            digits += char
        elif digits:
            break
    try:
        return float(digits) if digits else None
    except ValueError:
        return None
