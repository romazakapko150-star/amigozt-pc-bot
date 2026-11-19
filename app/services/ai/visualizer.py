"""PC Visualizer: one AI render per exact configuration and look.

    parts + preset  ->  BuildVisualSpec (structured facts)  ->  fingerprint
                                                                 |
            cache hit (build_visualizations row + file)  <-------+-------> miss
                 |                                                          |
          return the saved image                       prompt -> image API -> file -> row

The spec is built from catalogue facts only (names, colour, glass panel,
fan count, radiator position from the compatibility engine, GPU length
class, RGB memory), so the prompt cannot describe parts the customer did
not choose. Nothing produced here is ever presented as a photograph: the
captions shown with it say "AI visualization".

Money rules: the fingerprint covers every part, the colour, the style, the
prompt version and the model - identical machines share one paid render,
a changed GPU or case gets a new one, and a fingerprint that already failed
``max_attempts`` times is not retried automatically.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models.build_visualization import Visual, VisualEntityType
from app.domain.components import (
    CaseSpec,
    Colour,
    Component,
    ComponentCategory,
    CoolerSpec,
    CoolerType,
    FanSpec,
    GpuSpec,
    MotherboardSpec,
    RamSpec,
)
from app.domain.lighting import LightingPlan, plan_lighting
from app.services.compatibility.rules.common import choose_radiator_position
from app.services.media.ai_visual import (
    ACCENT_WORDS,
    NO_LETTERING,
    ImageGenerator,
    OpenAIImageGenerator,
    VisualPrompt,
)
from app.services.media.paths import AI_IMAGE_DIR
from app.services.media.presets import Accent, CaseFinish, Style, VisualPreset
from app.services.visuals.library import VisualizationResult, VisualLibrary, VisualRequest

logger = logging.getLogger(__name__)

Parts = dict[ComponentCategory, Component]

#: Bump whenever the prompt wording changes: every build then re-renders once.
PROMPT_VERSION = "5"

#: Parts that change what the machine looks like (and therefore the cache key).
FINGERPRINT_CATEGORIES: tuple[ComponentCategory, ...] = (
    ComponentCategory.CPU,
    ComponentCategory.COOLER,
    ComponentCategory.MOTHERBOARD,
    ComponentCategory.RAM,
    ComponentCategory.GPU,
    ComponentCategory.SSD,
    ComponentCategory.PSU,
    ComponentCategory.CASE,
    ComponentCategory.FANS,
    # Visually significant peripherals: they join the identity only when the
    # customer adds them, so the fingerprints of pure-PC builds do not move.
    ComponentCategory.MONITOR,
    ComponentCategory.KEYBOARD,
    ComponentCategory.MOUSE,
    ComponentCategory.HEADSET,
    ComponentCategory.MICROPHONE,
    ComponentCategory.WEBCAM,
    ComponentCategory.SPEAKERS,
    ComponentCategory.MOUSEPAD,
    ComponentCategory.DESK,
    ComponentCategory.CHAIR,
)

#: Priorities that change what a photograph of the machine would show, and
#: the clause each adds to the prompt. A priority outside this map (best
#: price/performance, upgrade room, low power draw, versatility) is a
#: commercial preference: it steers which parts get chosen - and those parts
#: are already in the identity - but it does not restyle the photo, so it is
#: deliberately kept out of the visual signature. Otherwise every commercial
#: tick would buy another copy of an identical picture.
VISUAL_PRIORITY_WORDS: dict[str, str] = {
    "looks": (
        "the build is presented as a show piece: the lighting is the point of the "
        "photograph, its glow clearly visible through the glass and reflected on the "
        "surface below"
    ),
    "silence": (
        "presented as a calm, quiet machine: still fans, restrained even lighting, "
        "no dramatic glare, a composed and understated shot"
    ),
    "cooling": (
        "presented as a cooling-first build: the fans, the radiator and the airflow "
        "path through the case are the clearest things in the frame"
    ),
    "compact": (
        "framed tightly to read as a small, dense machine, the tower filling the frame "
        "with little empty space around it"
    ),
}

#: Parts whose real photo helps the model most, in priority order.
REFERENCE_CATEGORIES: tuple[ComponentCategory, ...] = (
    ComponentCategory.CASE,
    ComponentCategory.GPU,
    ComponentCategory.COOLER,
    ComponentCategory.RAM,
    ComponentCategory.MOTHERBOARD,
)
MAX_REFERENCES = 4
REFERENCE_DIR = AI_IMAGE_DIR / "refs"
REFERENCE_DOWNLOAD_TIMEOUT = 20


@dataclass(frozen=True, slots=True)
class ReferenceImage:
    component_id: str
    category: ComponentCategory
    url: str
    source: str | None
    verified: bool


@dataclass(frozen=True, slots=True)
class BuildVisualSpec:
    """Everything the image model is told, as structured facts."""

    components: dict[str, str]
    names: dict[str, str]
    finish: CaseFinish
    accent: Accent
    style: Style
    case_colour: str
    side_panel: str
    case_rgb: bool
    included_fans: int
    fan_size_mm: int | None
    extra_fans: int
    gpu_length_mm: int | None
    gpu_slots: float | None
    cooler_type: str | None
    cooler_colour: str | None
    cooler_rgb: bool
    cooler_fans: int | None
    radiator_mm: int
    radiator_position: str | None
    ram_modules: int
    ram_rgb: bool
    board_form_factor: str | None
    extra_fans_rgb: bool = False
    references: tuple[ReferenceImage, ...] = ()
    #: The customer's ticked priorities, filtered to the ones that change the
    #: photograph and sorted, so the same wishes always produce the same key.
    visual_priorities: tuple[str, ...] = ()
    #: What the parts can light up and what the customer asked for. The single
    #: answer the card, the prompt and the picture all read.
    lighting: LightingPlan = field(default_factory=lambda: plan_lighting({}, requested=False))

    @property
    def lighting_signature(self) -> str:
        """How the lighting will be photographed: off, present, or featured.

        Two configurations that will be lit the same way share one render.
        "Asked for RGB but nothing glows" is photographed exactly like "no
        RGB at all", so both map to ``off``.
        """
        if not self.lit_parts:
            return "off"
        return "featured" if self.lighting.emphasise else "present"

    @property
    def lit_parts(self) -> tuple[str, ...]:
        """Parts really described as lit, in the words the prompt uses.

        Derived from :attr:`lighting`, so a part is only ever called lit when
        the catalogue says it emits light *and* the plan allows showing it.
        """
        if not self.lighting.show_lighting:
            return ()
        lit: list[str] = []
        if self.case_rgb or self.extra_fans_rgb:
            lit.append("fans")
        if self.ram_rgb:
            lit.append("memory")
        if self.cooler_rgb:
            lit.append("pump" if self.cooler_type == "aio" else "cooler")
        return tuple(lit)

    @property
    def has_rgb(self) -> bool:
        return bool(self.lit_parts)

    def as_dict(self) -> dict:
        return {
            "components": dict(self.components),
            "names": dict(self.names),
            "finish": self.finish.value,
            "accent": self.accent.value,
            "style": self.style.value,
            "case_colour": self.case_colour,
            "side_panel": self.side_panel,
            "fans": self.included_fans + self.extra_fans,
            "cooler": self.cooler_type,
            "radiator_position": self.radiator_position,
            "references": [r.component_id for r in self.references],
            "priorities": list(self.visual_priorities),
        }


def _spec(parts: Parts, category: ComponentCategory, expected: type):  # type: ignore[no-untyped-def]
    component = parts.get(category)
    if component is None:
        return None
    return component.spec if isinstance(component.spec, expected) else None


def visual_priorities_of(priorities: Iterable[str] | None) -> tuple[str, ...]:
    """The ticked priorities that change the picture, sorted and de-duplicated."""
    if not priorities:
        return ()
    chosen = {str(p) for p in priorities if str(p) in VISUAL_PRIORITY_WORDS}
    return tuple(sorted(chosen))


def describe_build(
    parts: Parts,
    preset: VisualPreset,
    *,
    include_references: bool = True,
    priorities: Iterable[str] | None = None,
) -> BuildVisualSpec:
    """Structured description of one build in one look, from catalogue facts."""
    wanted = visual_priorities_of(priorities)
    # Only the customer asks for lighting. The preset's "gaming" style is a
    # rendering choice made *because* parts glow - reading it as a request
    # would make every lit build claim the customer wanted a light show.
    wants_light = "looks" in wanted
    lighting = plan_lighting(parts, requested=wants_light)
    # A wish the hardware cannot grant changes nothing in the photograph, so
    # it must not change the key either: the customer is told the truth on
    # the card instead, and the dark render is reused.
    signature = (
        tuple(p for p in wanted if p != "looks") if not lighting.capabilities.any_lit else wanted
    )
    case_spec = _spec(parts, ComponentCategory.CASE, CaseSpec)
    gpu_spec = _spec(parts, ComponentCategory.GPU, GpuSpec)
    cooler_spec = _spec(parts, ComponentCategory.COOLER, CoolerSpec)
    ram_spec = _spec(parts, ComponentCategory.RAM, RamSpec)
    board_spec = _spec(parts, ComponentCategory.MOTHERBOARD, MotherboardSpec)
    fans_spec = _spec(parts, ComponentCategory.FANS, FanSpec)

    if case_spec is not None and case_spec.colour is not Colour.OTHER:
        case_colour = case_spec.colour.value
    else:
        case_colour = preset.finish.value

    side_panel = case_spec.side_panel if case_spec and case_spec.side_panel else "tempered glass"

    cooler_type = None
    radiator_mm = 0
    radiator_position = None
    if cooler_spec is not None:
        cooler_type = cooler_spec.cooler_type.value
        if cooler_spec.cooler_type is CoolerType.AIO and cooler_spec.radiator_mm:
            radiator_mm = cooler_spec.radiator_mm
            if case_spec is not None and case_spec.radiator_positions:
                position, _ = choose_radiator_position(case_spec.radiator_positions, radiator_mm)
                radiator_position = position.value if position is not None else None
            else:
                radiator_position = "top"

    cooler_rgb = bool(cooler_spec and cooler_spec.rgb)
    extra_fans_rgb = bool(fans_spec and fans_spec.rgb)
    has_lighting = (
        bool(case_spec and case_spec.rgb)
        or bool(ram_spec and ram_spec.rgb)
        or cooler_rgb
        or extra_fans_rgb
    )
    # A build with no lit part has no colour to show: the accent collapses
    # to the neutral one so every colour choice shares one honest render.
    accent = preset.accent if has_lighting else Accent.WHITE

    references: tuple[ReferenceImage, ...] = ()
    if include_references:
        found = []
        for category in REFERENCE_CATEGORIES:
            component = parts.get(category)
            if component is None or not component.image_url or not component.image_verified:
                continue
            found.append(
                ReferenceImage(
                    component_id=component.id,
                    category=category,
                    url=component.image_url,
                    source=component.image_source,
                    verified=component.image_verified,
                )
            )
        references = tuple(found[:MAX_REFERENCES])

    return BuildVisualSpec(
        components={
            category.value: component.id
            for category, component in parts.items()
            if category in FINGERPRINT_CATEGORIES
        },
        names={category.value: component.name for category, component in parts.items()},
        finish=preset.finish,
        accent=accent,
        style=preset.style,
        case_colour=case_colour,
        side_panel=side_panel,
        case_rgb=bool(case_spec and case_spec.rgb),
        included_fans=case_spec.included_fans if case_spec else 0,
        fan_size_mm=case_spec.included_fan_size_mm if case_spec else None,
        extra_fans=fans_spec.count if fans_spec else 0,
        gpu_length_mm=gpu_spec.length_mm if gpu_spec else None,
        gpu_slots=gpu_spec.slots if gpu_spec else None,
        cooler_type=cooler_type,
        cooler_colour=cooler_spec.colour.value if cooler_spec else None,
        cooler_rgb=cooler_rgb,
        cooler_fans=(cooler_spec.fans if cooler_spec and cooler_spec.fans else None),
        radiator_mm=radiator_mm,
        radiator_position=radiator_position,
        ram_modules=ram_spec.modules if ram_spec else 0,
        ram_rgb=bool(ram_spec and ram_spec.rgb),
        board_form_factor=board_spec.form_factor.value if board_spec else None,
        extra_fans_rgb=extra_fans_rgb,
        references=references,
        visual_priorities=signature,
        lighting=lighting,
    )


def identity(spec: BuildVisualSpec) -> str:
    """What is depicted: every visible part and the look. No prompt version."""
    material = "|".join(
        [
            *(f"{category}={spec.components[category]}" for category in sorted(spec.components)),
            spec.finish.value,
            spec.accent.value,
            spec.style.value,
            # The lighting signature is deliberately *not* added here: it is a
            # pure function of the part ids and the priorities above, so
            # adding it would change every existing key without telling two
            # different-looking builds apart - and orphan a paid render each.
            "wants:" + ",".join(spec.visual_priorities),
            "refs:" + ",".join(sorted(r.component_id for r in spec.references)),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def fingerprint(spec: BuildVisualSpec, *, model: str, prompt_version: str = PROMPT_VERSION) -> str:
    """The exact render: identity + prompt version + image model.

    A lookup that misses the fingerprint still finds an older-version render
    of the same identity, so bumping PROMPT_VERSION never re-renders the
    catalogue by itself.
    """
    material = "|".join([identity(spec), f"v{prompt_version}", model])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _gpu_size_words(length_mm: int | None, slots: float | None) -> str:
    if length_mm is None:
        return "a"
    if length_mm >= 300:
        size = "a large triple-fan"
    elif length_mm >= 250:
        size = "a dual-fan"
    else:
        size = "a compact dual-fan"
    if slots is not None and slots >= 3:
        size += " thick"
    return size


#: How each peripheral joins the picture when it is part of the setup.
_PERIPHERAL_WORDS: dict[str, str] = {
    "monitor": (
        "beside the tower, its {name} monitor switched on, showing a clean, elegant "
        "abstract wallpaper"
    ),
    "keyboard": "the real {name} keyboard on the desk in front of the tower",
    "mouse": "the real {name} mouse to the right of the keyboard",
    "mousepad": "the {name} mousepad under the keyboard and mouse",
    "headset": "the {name} headset resting on a stand beside the monitor",
    "microphone": "the {name} microphone standing on the desk",
    "webcam": "the {name} webcam clipped to the top of the monitor",
    "speakers": "the {name} speakers flanking the setup",
    "desk": "the whole setup standing on the real {name} desk",
    "chair": "the {name} chair in front of the desk",
}


def build_prompt(spec: BuildVisualSpec) -> VisualPrompt:
    """The prompt for the image model, every sentence traceable to a fact."""
    facts: list[str] = []
    names = spec.names

    case_name = names.get("case", "mid-tower PC case")
    facts.append(
        f"{spec.case_colour} {case_name} mid-tower PC case with a {spec.side_panel} side "
        "panel, shown from the glass side"
    )

    total_fans = spec.included_fans + spec.extra_fans
    if total_fans:
        size = f"{spec.fan_size_mm} mm " if spec.fan_size_mm else ""
        facts.append(f"{total_fans} {size}case fans visible through the glass")

    if "gpu" in names:
        facts.append(
            f"{_gpu_size_words(spec.gpu_length_mm, spec.gpu_slots)} {names['gpu']} graphics card "
            "mounted horizontally in the top PCIe slot"
        )

    cooler_colour = f"{spec.cooler_colour} " if spec.cooler_colour in {"black", "white"} else ""
    if spec.cooler_type == "aio" and "cooler" in names:
        where = spec.radiator_position or "top"
        facts.append(
            f"{cooler_colour}{names['cooler']} all-in-one liquid cooler with its "
            f"{spec.radiator_mm} mm radiator and fans mounted at the {where} of the case "
            "and the pump block on the CPU"
        )
    elif "cooler" in names:
        fan_words = {1: "single-fan ", 2: "dual-fan "}.get(spec.cooler_fans or 0, "")
        facts.append(
            f"{cooler_colour}{names['cooler']} {fan_words}tower air cooler standing on the CPU"
        )

    if "ram" in names:
        modules = spec.ram_modules or 2
        lit = "with RGB light bars" if spec.ram_rgb else "without lighting"
        facts.append(f"{modules} {names['ram']} memory modules {lit}")

    if "motherboard" in names:
        form = f"{spec.board_form_factor} " if spec.board_form_factor else ""
        facts.append(f"{form}{names['motherboard']} motherboard behind the components")

    if "psu" in names:
        facts.append(f"{names['psu']} power supply hidden under the shroud, tidy cable management")

    facts.append("no visible drives, the SSD sits under the motherboard heatsink")

    lit_parts = spec.lit_parts
    if not lit_parts:
        facts.append(
            "no RGB lighting anywhere: plain unlit fans and parts, only the natural studio light"
        )
    elif spec.lighting.emphasise:
        accent = ACCENT_WORDS[spec.accent]
        what = ", ".join(lit_parts[:-1]) + (" and " if len(lit_parts) > 1 else "") + lit_parts[-1]
        addressable = spec.lighting.capabilities.addressable
        facts.append(
            f"the {what} clearly and brightly lit in {accent}"
            + (", each LED individually addressable" if addressable else "")
            + f", the {accent} glow unmistakable through the glass and reflected on the "
            "desk and the inside of the case; the lighting is the first thing the eye "
            "meets, while nothing without its own LEDs is lit"
        )
    else:
        accent = ACCENT_WORDS[spec.accent]
        what = ", ".join(lit_parts[:-1]) + (" and " if len(lit_parts) > 1 else "") + lit_parts[-1]
        if spec.style is Style.GAMING:
            facts.append(
                f"the {what} glowing {accent}, the {accent} glow reflecting softly on the "
                "glass and the desk; nothing else is lit"
            )
        else:
            facts.append(
                f"subtle {accent} lighting on the {what} only, restrained and clean, "
                "no light strips"
            )
    for key, template in _PERIPHERAL_WORDS.items():
        if key in names:
            facts.append(template.format(name=names[key]))

    for priority in spec.visual_priorities:
        facts.append(VISUAL_PRIORITY_WORDS[priority])

    facts.append(
        "every part unbranded and unmarked: no logos, no model names, no stickers "
        "and no lettering anywhere on the case, the graphics card, the board or the fans"
    )

    if spec.references:
        facts.append(
            "match the exact shape, colour and design of the products shown in the reference "
            "images; do not substitute other models"
        )

    text = (
        "Photorealistic product photograph of a custom-built desktop gaming PC, exactly these "
        "parts and nothing else. "
        # Stated up front as well as at the end: buried at the tail of a long
        # prompt the model drifts and paints invented brand text on the case
        # and the card, which is the one failure we cannot ship.
        + NO_LETTERING
        + " "
        + ". ".join(fact[0].upper() + fact[1:] for fact in facts)
        + ". Professional commercial product photography for a premium PC store: "
        "three-quarter front view on a clean studio surface, bright soft key light "
        "with gentle fill, controlled highlights on glass and metal, realistic "
        "reflections, true colours and materials, shallow depth of field, sharp "
        "focus on the components. No people, no captions, no watermark. "
        "Every surface stays blank where a logo or a label would be: no words, "
        "no letters, no numbers anywhere in the image."
    )
    return VisualPrompt(text=text, facts=tuple(facts))


class Visualizer:
    """Turns parts + look into a saved image through the Visual Library.

    Identical machines share one paid render; a build without one is
    rendered once (with the library's lock, retry and attempt limits) and
    served from disk and by Telegram file_id ever after.
    """

    #: Kept for code written against the first version; the library owns
    #: the real locks now.
    _lock: asyncio.Lock | None = None
    MIN_INTERVAL_SECONDS = 1.0

    def __init__(
        self,
        generator: ImageGenerator,
        *,
        output_dir: Path = AI_IMAGE_DIR,
        max_attempts: int = 2,
        timeout_seconds: float = 90.0,
        references_enabled: bool = False,
        enabled: bool = True,
        model: str | None = None,
        cost_per_call_usd: Decimal = Decimal("0.04"),
    ) -> None:
        self._generator = generator
        self._output_dir = output_dir
        self._max_attempts = max(1, max_attempts)
        self._timeout = timeout_seconds
        self._references_enabled = references_enabled
        self._enabled = enabled
        self._model = model or getattr(generator, "model", None) or generator.name
        self._cost = cost_per_call_usd

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> Visualizer:
        cfg = settings or get_settings()
        generator = OpenAIImageGenerator(
            cfg.openai_key,
            model=cfg.image_model,
            size=cfg.ai_image_size,
            quality=cfg.ai_image_quality,
            timeout_seconds=float(cfg.ai_image_timeout_seconds),
        )
        return cls(
            generator,
            max_attempts=cfg.ai_image_max_attempts,
            timeout_seconds=float(cfg.ai_image_timeout_seconds),
            references_enabled=cfg.ai_reference_images_enabled,
            enabled=cfg.ai_visualization_enabled,
            model=cfg.image_model,
            cost_per_call_usd=cfg.ai_image_cost_usd,
        )

    @property
    def enabled(self) -> bool:
        return self._enabled and self._generator.enabled

    @property
    def model(self) -> str:
        return self._model

    def library(self, session: AsyncSession) -> VisualLibrary:
        lib = VisualLibrary(
            session,
            self._generator,
            output_dir=self._output_dir,
            max_attempts=self._max_attempts,
            timeout_seconds=self._timeout,
            cost_per_call_usd=self._cost,
            enabled=self._enabled,
            min_interval_seconds=self.MIN_INTERVAL_SECONDS,
        )
        return lib

    # --- keys (never paid) ------------------------------------------------------

    def describe(
        self, parts: Parts, preset: VisualPreset, priorities: Iterable[str] | None = None
    ) -> BuildVisualSpec:
        return describe_build(
            parts,
            preset,
            include_references=self._references_enabled,
            priorities=priorities,
        )

    def identity_for(
        self, parts: Parts, preset: VisualPreset, priorities: Iterable[str] | None = None
    ) -> str:
        return identity(self.describe(parts, preset, priorities))

    def fingerprint_for(
        self, parts: Parts, preset: VisualPreset, priorities: Iterable[str] | None = None
    ) -> str:
        return fingerprint(self.describe(parts, preset, priorities), model=self._model)

    async def request_for(
        self,
        parts: Parts,
        preset: VisualPreset,
        *,
        build_id: int | None = None,
        ready_build_id: int | None = None,
        priorities: Iterable[str] | None = None,
    ) -> tuple[VisualRequest, BuildVisualSpec]:
        spec = self.describe(parts, preset, priorities)
        key = identity(spec)
        references = await self._prepare_references(spec) if spec.references else []
        if ready_build_id is not None:
            entity_type, entity_id = VisualEntityType.READY_BUILD, str(ready_build_id)
        elif build_id is not None:
            entity_type, entity_id = VisualEntityType.BUILD, str(build_id)
        else:
            entity_type, entity_id = VisualEntityType.BUILD, key
        request = VisualRequest(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_slug=None,
            category="build",
            identity_key=key,
            fingerprint=fingerprint(spec, model=self._model),
            prompt=build_prompt(spec),
            model=self._model,
            prompt_version=PROMPT_VERSION,
            provider=self._generator.name,
            preset_key=preset.key,
            components=dict(spec.components),
            references=tuple(references),
            build_id=build_id,
            ready_build_id=ready_build_id,
        )
        return request, spec

    async def status_for(
        self,
        session: AsyncSession,
        parts: Parts,
        preset: VisualPreset,
        priorities: Iterable[str] | None = None,
    ) -> Visual | None:
        """The usable render of this machine (exact or an older prompt version)."""
        spec = self.describe(parts, preset, priorities)
        found, _ = await self.library(session).find(
            identity(spec), fingerprint(spec, model=self._model)
        )
        return found

    # --- the main entry point ---------------------------------------------------

    async def get_or_create(
        self,
        session: AsyncSession,
        parts: Parts,
        preset: VisualPreset,
        *,
        build_id: int | None = None,
        ready_build_id: int | None = None,
        force: bool = False,
        priorities: Iterable[str] | None = None,
    ) -> VisualizationResult:
        """Saved image for this machine and look, generating it once if needed.

        Cache hit: one row lookup and a file check, no API call. Miss: one
        paid request (plus at most one retry on a transient error).
        """
        request, spec = await self.request_for(
            parts,
            preset,
            build_id=build_id,
            ready_build_id=ready_build_id,
            priorities=priorities,
        )
        result = await self.library(session).get_or_generate(request, force=force)
        result.spec = spec
        return result

    async def _prepare_references(self, spec: BuildVisualSpec) -> list[Path]:
        """Local copies of verified product photos, fetched once and reused."""
        paths: list[Path] = []
        for reference in spec.references:
            try:
                path = await asyncio.to_thread(_download_reference, reference)
            except Exception:
                logger.warning("Reference image for %s unavailable", reference.component_id)
                continue
            if path is not None:
                paths.append(path)
        return paths


def _download_reference(reference: ReferenceImage) -> Path | None:
    if not reference.url.lower().startswith(("http://", "https://")):
        return None
    suffix = Path(reference.url.split("?")[0]).suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = REFERENCE_DIR / f"{reference.component_id}{suffix}"
    if target.is_file():
        return target
    request = urllib.request.Request(reference.url, headers={"User-Agent": "AmigoZT-PC/1.0"})
    with urllib.request.urlopen(request, timeout=REFERENCE_DOWNLOAD_TIMEOUT) as response:
        data = response.read()
    if not data:
        return None
    target.write_bytes(data)
    return target
