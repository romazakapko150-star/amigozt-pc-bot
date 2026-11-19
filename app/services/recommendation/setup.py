"""The desk around the PC: a monitor and the peripherals the customer wants.

The configurator asks for the machine first and the setup second, because
the two answer different questions: the tower has a budget and a
compatibility engine behind it, while a mouse only has to suit the same
taste. So this module never touches the build - it offers catalogue items
per category, keeps the customer's picks, and prices them as their own
line.

Everything here is data in, data out: no aiogram, no database. What the
customer picked travels as ``{category value: component id}``, which is
what the FSM stores, what the build card renders, and what the visualiser
turns into a fingerprint - adding a monitor changes the picture because it
changes that mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.components import (
    Component,
    ComponentCategory,
    MonitorSpec,
    PeripheralSpec,
)
from app.domain.enums import Priority, Resolution
from app.domain.requirements import BuildRequirements
from app.services.catalog import Catalog, get_catalog

PriceBook = dict[str, Decimal]

#: The desk, in the order the customer is asked about it. The monitor comes
#: first and has its own step: it is the one accessory that changes what the
#: machine is *for*.
MONITOR_CATEGORY = ComponentCategory.MONITOR

PERIPHERAL_CATEGORIES: tuple[ComponentCategory, ...] = (
    ComponentCategory.KEYBOARD,
    ComponentCategory.MOUSE,
    ComponentCategory.HEADSET,
    ComponentCategory.MOUSEPAD,
    ComponentCategory.MICROPHONE,
    ComponentCategory.WEBCAM,
    ComponentCategory.SPEAKERS,
)

SETUP_CATEGORIES: tuple[ComponentCategory, ...] = (MONITOR_CATEGORY, *PERIPHERAL_CATEGORIES)

#: How many monitors to offer. More than this stops being a choice and
#: becomes a catalogue.
MAX_MONITOR_OPTIONS = 6

#: Resolutions a monitor must be able to show for that target.
_RESOLUTION_PIXELS: dict[str, int] = {
    "1920x1080": 1920 * 1080,
    "2560x1440": 2560 * 1440,
    "3440x1440": 3440 * 1440,
    "3840x2160": 3840 * 2160,
}

_TARGET_PIXELS: dict[Resolution, int] = {
    Resolution.FHD: 1920 * 1080,
    Resolution.QHD: 2560 * 1440,
    Resolution.UHD: 3840 * 2160,
}


@dataclass(frozen=True, slots=True)
class SetupSelection:
    """What the customer added around the tower."""

    items: dict[ComponentCategory, Component] = field(default_factory=dict)
    prices: PriceBook = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.items)

    @property
    def monitor(self) -> Component | None:
        return self.items.get(MONITOR_CATEGORY)

    @property
    def total_pln(self) -> Decimal:
        """What the extras cost. Unpriced items simply do not add anything."""
        return sum(
            (self.prices[c.id] for c in self.items.values() if c.id in self.prices),
            Decimal(0),
        )

    @property
    def has_unpriced_item(self) -> bool:
        return any(c.id not in self.prices for c in self.items.values())

    def as_payload(self) -> dict[str, str]:
        """The FSM/database shape: category value -> component id."""
        return {category.value: component.id for category, component in self.items.items()}


def _price_of(component: Component, prices: PriceBook) -> Decimal:
    return prices.get(component.id, Decimal("999999"))


def _monitor_pixels(component: Component) -> int | None:
    spec = component.spec
    if not isinstance(spec, MonitorSpec):
        return None
    return _RESOLUTION_PIXELS.get(spec.resolution.replace(" ", ""))


def monitor_options(
    requirements: BuildRequirements,
    *,
    catalog: Catalog | None = None,
    prices: PriceBook | None = None,
    limit: int = MAX_MONITOR_OPTIONS,
) -> list[Component]:
    """Monitors worth showing for these requirements, best fit first.

    A monitor that cannot display the resolution the customer asked for is
    not offered at all - selling a 1080p panel to someone who chose 4K would
    be the one recommendation the machine cannot make honest.
    """
    cat = catalog or get_catalog()
    book = prices if prices is not None else {}
    target = _TARGET_PIXELS.get(requirements.resolution, _TARGET_PIXELS[Resolution.FHD])
    wants_fps = requirements.wants(Priority.MAX_FPS)

    candidates: list[Component] = []
    for component in cat.by_category(MONITOR_CATEGORY):
        if component.discontinued:
            continue
        pixels = _monitor_pixels(component)
        if pixels is not None and pixels < target:
            continue
        candidates.append(component)

    def rank(component: Component) -> tuple[int, Decimal]:
        spec = component.spec
        score = 0
        if isinstance(spec, MonitorSpec):
            pixels = _monitor_pixels(component)
            # An exact match beats a bigger panel the customer did not ask for.
            if pixels == target:
                score -= 2
            if wants_fps and spec.refresh_hz >= 240:
                score -= 2
            elif spec.refresh_hz >= 144:
                score -= 1
        return score, _price_of(component, book)

    candidates.sort(key=rank)
    return candidates[:limit]


def suggest_for(
    category: ComponentCategory,
    requirements: BuildRequirements,
    *,
    catalog: Catalog | None = None,
    prices: PriceBook | None = None,
) -> Component | None:
    """The item this customer most likely wants in that category.

    Cheapest first, nudged by the taste they already told us about: a white
    build gets white peripherals, an RGB build gets lit ones, and someone
    who asked for quiet is not handed the loudest mechanical keyboard.
    """
    cat = catalog or get_catalog()
    book = prices if prices is not None else {}
    wants_white = requirements.aesthetics.is_white
    wants_rgb = requirements.aesthetics.wants_rgb or requirements.wants(Priority.LOOKS)
    quiet = requirements.wants(Priority.SILENCE)

    def rank(component: Component) -> tuple[int, Decimal]:
        spec = component.spec
        score = 0
        colour = getattr(spec, "colour", None)
        if wants_white and colour is not None and colour.value == "white":
            score -= 3
        if isinstance(spec, PeripheralSpec):
            if wants_rgb and spec.rgb:
                score -= 2
            if not wants_rgb and not spec.rgb:
                score -= 1
            if quiet and any(
                "silent" in h.lower() or "quiet" in h.lower() for h in spec.highlights
            ):
                score -= 2
        return score, _price_of(component, book)

    candidates = [c for c in cat.by_category(category) if not c.discontinued]
    if not candidates:
        return None
    return min(candidates, key=rank)


def resolve(
    payload: dict[str, str] | None,
    *,
    catalog: Catalog | None = None,
    prices: Mapping[str, Decimal] | None = None,
) -> SetupSelection:
    """Turn the stored ``{category: id}`` mapping back into components.

    An id that is no longer in the catalogue is dropped rather than
    guessed at, so a retired product cannot reappear on a card.
    """
    cat = catalog or get_catalog()
    items: dict[ComponentCategory, Component] = {}
    for raw_category, component_id in (payload or {}).items():
        try:
            category = ComponentCategory(raw_category)
        except ValueError:
            continue
        if category not in SETUP_CATEGORIES:
            continue
        component = cat.get(component_id)
        if component is not None and component.category is category:
            items[category] = component
    return SetupSelection(items=items, prices=dict(prices or {}))


def with_setup(
    parts: dict[ComponentCategory, Component], selection: SetupSelection
) -> dict[ComponentCategory, Component]:
    """The build plus the desk - what the picture and the card describe.

    The PC parts always win: the setup may only add categories the tower
    does not have.
    """
    merged = dict(parts)
    for category, component in selection.items.items():
        merged.setdefault(category, component)
    return merged
