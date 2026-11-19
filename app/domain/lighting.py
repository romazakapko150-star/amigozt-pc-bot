"""What a build can actually light up, and what the customer asked for.

Two different questions were being answered by one flag, which is how a
machine ends up described as "RGB" because somebody ticked a checkbox:

* **capability** - does any part in this build physically emit light? That
  is a fact about the hardware, read from the catalogue and nowhere else.
* **intent** - did the customer ask for the lighting to be the point of the
  picture? That is a preference, and it cannot conjure an LED into a case
  that has none.

Both travel together as a :class:`LightingPlan`, and everything downstream -
the build card, the visual spec, the fingerprint, the image prompt - reads
that one object. So the description, the picture and the parts list can no
longer disagree with each other.

Nothing here infers. A part with no lighting field in its spec is *unknown*,
not unlit: graphics cards carry no such field, so a build is never told its
card glows, and never told it does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.components import Component, ComponentCategory

#: Parts whose spec records whether they light up. Anything outside this set
#: has no lighting data at all and is reported as unknown rather than dark.
LIT_CATEGORIES: tuple[ComponentCategory, ...] = (
    ComponentCategory.CASE,
    ComponentCategory.COOLER,
    ComponentCategory.RAM,
    ComponentCategory.FANS,
)

#: Desk items that can glow. They light the room, not the machine, so they
#: are tracked separately from the tower.
LIT_PERIPHERAL_CATEGORIES: tuple[ComponentCategory, ...] = (
    ComponentCategory.KEYBOARD,
    ComponentCategory.MOUSE,
    ComponentCategory.HEADSET,
    ComponentCategory.MICROPHONE,
    ComponentCategory.MOUSEPAD,
    ComponentCategory.SPEAKERS,
)


class LightingState(StrEnum):
    """How lighting should be presented for one configuration."""

    #: Nothing in the build emits light, and nobody asked for any.
    NONE = "none"
    #: Parts can glow but the customer did not make it a priority.
    AVAILABLE = "available"
    #: Parts can glow and the customer asked for it: show it off.
    REQUESTED = "requested"
    #: The customer asked for lighting these parts cannot produce.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class LightingCapabilities:
    """What this collection of parts can physically light up."""

    #: Categories that really emit light, e.g. ``("case", "ram")``.
    lit: tuple[str, ...] = ()
    #: Of those, the ones with addressable (per-LED) lighting.
    addressable: tuple[str, ...] = ()
    #: Lit desk items, kept apart from the tower's own lighting.
    lit_peripherals: tuple[str, ...] = ()
    #: The board can drive strips and fans even if nothing lit is fitted.
    header_capable: bool = False
    #: Categories present in the build whose spec says nothing about light.
    unknown: tuple[str, ...] = ()

    @property
    def any_lit(self) -> bool:
        """True when at least one part in the tower actually glows."""
        return bool(self.lit)

    @property
    def any_addressable(self) -> bool:
        return bool(self.addressable)

    @property
    def expandable(self) -> bool:
        """Nothing glows yet, but the board could drive lighting if added."""
        return not self.any_lit and self.header_capable


@dataclass(frozen=True, slots=True)
class LightingPlan:
    """Capability plus intent: the single answer everything downstream uses."""

    capabilities: LightingCapabilities
    requested: bool
    state: LightingState

    @property
    def show_lighting(self) -> bool:
        """Whether the picture and the copy may speak of lighting at all."""
        return self.state in {LightingState.AVAILABLE, LightingState.REQUESTED}

    @property
    def emphasise(self) -> bool:
        """Whether the lighting should be the point of the photograph."""
        return self.state is LightingState.REQUESTED

    @property
    def promised_but_missing(self) -> bool:
        """The customer asked for light these parts cannot produce."""
        return self.state is LightingState.UNAVAILABLE

    @property
    def lit_parts(self) -> tuple[str, ...]:
        return self.capabilities.lit if self.show_lighting else ()


def _is_lit(component: Component) -> bool | None:
    """True/False when the spec records it, ``None`` when it says nothing."""
    value = getattr(component.spec, "rgb", None)
    return None if value is None else bool(value)


def _is_addressable(component: Component) -> bool:
    connector = getattr(component.spec, "argb_connector", None)
    return connector is not None and str(connector) not in {"none", "None", ""}


def _drives_lighting(component: Component) -> bool:
    spec = component.spec
    headers = (getattr(spec, "argb_5v_headers", None) or 0) + (
        getattr(spec, "rgb_12v_headers", None) or 0
    )
    return headers > 0


def describe_lighting(parts: dict[ComponentCategory, Component]) -> LightingCapabilities:
    """What these parts can light up, from catalogue data only."""
    lit: list[str] = []
    addressable: list[str] = []
    peripherals: list[str] = []
    unknown: list[str] = []

    for category, component in parts.items():
        glows = _is_lit(component)
        if category in LIT_CATEGORIES:
            if glows:
                lit.append(category.value)
                if _is_addressable(component):
                    addressable.append(category.value)
            elif glows is None:
                unknown.append(category.value)
        elif category in LIT_PERIPHERAL_CATEGORIES:
            if glows:
                peripherals.append(category.value)
        elif glows is None:
            # Graphics cards, boards, drives: no lighting field exists, so we
            # neither claim nor deny that they glow.
            unknown.append(category.value)

    board = parts.get(ComponentCategory.MOTHERBOARD)
    return LightingCapabilities(
        lit=tuple(sorted(lit)),
        addressable=tuple(sorted(addressable)),
        lit_peripherals=tuple(sorted(peripherals)),
        header_capable=bool(board is not None and _drives_lighting(board)),
        unknown=tuple(sorted(unknown)),
    )


def plan_lighting(parts: dict[ComponentCategory, Component], *, requested: bool) -> LightingPlan:
    """Combine what the parts can do with what the customer asked for.

    ``requested`` covers both routes a customer has to ask for lighting: the
    RGB/looks priority and an RGB aesthetic. The result never promises light
    the hardware cannot make.
    """
    capabilities = describe_lighting(parts)
    if capabilities.any_lit:
        state = LightingState.REQUESTED if requested else LightingState.AVAILABLE
    else:
        state = LightingState.UNAVAILABLE if requested else LightingState.NONE
    return LightingPlan(capabilities=capabilities, requested=requested, state=state)
