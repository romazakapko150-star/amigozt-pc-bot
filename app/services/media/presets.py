"""Visual presets for build images.

A preset is *how the machine is lit and styled*, separate from *what is in
it*. The parts come from the build; the preset decides the case finish, the
accent colour of fans, memory and pump, and how loud the lighting is.

The registry is the product: case colour x accent x style, every combination
a distinct look a customer can pick. Data-driven details (AIO vs air tower,
GPU length, fan count) are layered on top by the renderer, so two builds with
the same preset still look like their own parts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.components import CaseSpec, Colour, Component, ComponentCategory, RamSpec
from app.domain.enums import Aesthetics

RGB = tuple[int, int, int]


class CaseFinish(StrEnum):
    BLACK = "black"
    WHITE = "white"


class Accent(StrEnum):
    RED = "red"
    BLUE = "blue"
    PURPLE = "purple"
    PINK = "pink"
    GREEN = "green"
    ORANGE = "orange"
    YELLOW = "yellow"
    CYAN = "cyan"
    WHITE = "white"
    SILVER = "silver"
    GOLD = "gold"
    RAINBOW = "rainbow"


class Style(StrEnum):
    #: Full glow: lit fans, lit memory, under-GPU strip.
    GAMING = "gaming"
    #: Restrained: fans tinted, no strips, no memory glow.
    MINIMAL = "minimal"


#: The colours each accent is drawn with. Rainbow cycles through several.
ACCENT_COLOURS: dict[Accent, tuple[RGB, ...]] = {
    Accent.RED: ((255, 64, 64),),
    Accent.BLUE: ((72, 132, 255),),
    Accent.PURPLE: ((160, 96, 255),),
    Accent.PINK: ((255, 96, 190),),
    Accent.GREEN: ((72, 220, 120),),
    Accent.ORANGE: ((255, 150, 48),),
    Accent.YELLOW: ((255, 220, 64),),
    Accent.CYAN: ((64, 220, 255),),
    Accent.WHITE: ((236, 240, 248),),
    Accent.SILVER: ((196, 202, 212),),
    Accent.GOLD: ((232, 190, 84),),
    Accent.RAINBOW: (
        (255, 74, 74),
        (255, 170, 48),
        (255, 230, 64),
        (72, 220, 120),
        (64, 200, 255),
        (160, 96, 255),
        (255, 96, 190),
    ),
}

#: The colour swatch shown before the translated name. Emoji carry the colour
#: so the button text stays short enough for two columns on a phone.
ACCENT_EMOJI: dict[Accent, str] = {
    Accent.RED: "🔴",
    Accent.BLUE: "🔵",
    Accent.PURPLE: "🟣",
    Accent.PINK: "🩷",
    Accent.GREEN: "🟢",
    Accent.ORANGE: "🟠",
    Accent.YELLOW: "🟡",
    Accent.CYAN: "🩵",
    Accent.WHITE: "⚪",
    Accent.SILVER: "🩶",
    Accent.GOLD: "🟤",
    Accent.RAINBOW: "🌈",
}


def accent_label(accent: Accent, lang: str) -> str:
    """Swatch plus the colour's name in the customer's language."""
    from app.i18n import t

    return f"{ACCENT_EMOJI[accent]} {t(lang, f'accent.{accent.value}')}"


def preset_title(preset: VisualPreset, lang: str) -> str:
    """ "Black / Red - gaming", translated."""
    from app.i18n import t

    finish = t(lang, f"finish.{preset.finish.value}")
    style = t(lang, f"visual.style_{preset.style.value}")
    return f"{finish} / {t(lang, f'accent.{preset.accent.value}')} · {style}"


@dataclass(frozen=True, slots=True)
class VisualPreset:
    finish: CaseFinish
    accent: Accent
    style: Style

    @property
    def key(self) -> str:
        return f"{self.finish.value}-{self.accent.value}-{self.style.value}"

    @property
    def colours(self) -> tuple[RGB, ...]:
        return ACCENT_COLOURS[self.accent]

    @property
    def glow(self) -> bool:
        return self.style is Style.GAMING

    @property
    def title(self) -> str:
        """Language-neutral label for logs, caches and admin tooling.

        Customer-facing copy goes through :func:`preset_title` instead.
        """
        style = "gaming" if self.style is Style.GAMING else "minimal"
        return f"{self.finish.value} / {self.accent.value} · {style}"


#: Every preset, in a stable order. Keys are what callbacks and caches use.
PRESETS: tuple[VisualPreset, ...] = tuple(
    VisualPreset(finish, accent, style)
    for finish in CaseFinish
    for style in Style
    for accent in Accent
)

PRESETS_BY_KEY: dict[str, VisualPreset] = {preset.key: preset for preset in PRESETS}


def parse_preset(key: str | None) -> VisualPreset | None:
    if not key:
        return None
    return PRESETS_BY_KEY.get(key)


def default_preset(
    parts: dict[ComponentCategory, Component],
    aesthetics: Aesthetics | None = None,
) -> VisualPreset:
    """The look a build gets before the customer picks one.

    The case decides the finish - a white case is white whatever the customer
    said. RGB parts default to rainbow, which is what they ship looking like;
    non-RGB parts get a quiet white accent. A "minimal" request turns the
    lighting down.
    """
    case = parts.get(ComponentCategory.CASE)
    case_spec = case.spec if case is not None and isinstance(case.spec, CaseSpec) else None
    ram = parts.get(ComponentCategory.RAM)
    ram_spec = ram.spec if ram is not None and isinstance(ram.spec, RamSpec) else None

    if case_spec is not None:
        finish = CaseFinish.WHITE if case_spec.colour is Colour.WHITE else CaseFinish.BLACK
    elif aesthetics is not None and aesthetics.is_white:
        finish = CaseFinish.WHITE
    else:
        finish = CaseFinish.BLACK

    has_rgb = bool(case_spec and case_spec.rgb) or bool(ram_spec and ram_spec.rgb)
    if aesthetics is not None:
        has_rgb = has_rgb or aesthetics.wants_rgb

    style = Style.MINIMAL if aesthetics is Aesthetics.MINIMAL else Style.GAMING
    accent = Accent.RAINBOW if has_rgb else Accent.WHITE
    if accent is Accent.WHITE and finish is CaseFinish.WHITE:
        # White-on-white disappears; a cool blue is the usual fallback look.
        accent = Accent.CYAN
    return VisualPreset(finish, accent, style)


def with_accent(preset: VisualPreset, accent: Accent) -> VisualPreset:
    return VisualPreset(preset.finish, accent, preset.style)


def with_style(preset: VisualPreset, style: Style) -> VisualPreset:
    return VisualPreset(preset.finish, preset.accent, style)
