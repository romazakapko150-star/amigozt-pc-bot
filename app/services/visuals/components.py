"""Product visuals: one honest picture per catalogue component.

A component visual is *not* a build visual: the same RTX 5080 has one
product picture and appears in many build pictures. The prompt is built
from catalogue facts only - brand, model, category, colour, size, RGB,
wireless - and asks for a studio product photo of *that* model. Where a
verified reference photo exists it is passed along; nothing is invented.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models.build_visualization import Visual, VisualEntityType
from app.domain.components import (
    CaseSpec,
    Component,
    ComponentCategory,
    CoolerSpec,
    CoolerType,
    CpuSpec,
    FanSpec,
    GpuSpec,
    MonitorSpec,
    MotherboardSpec,
    PeripheralSpec,
    PsuSpec,
    RamSpec,
    SsdSpec,
)
from app.services.media.ai_visual import (
    NO_LETTERING,
    ImageGenerator,
    OpenAIImageGenerator,
    VisualPrompt,
)
from app.services.media.paths import AI_IMAGE_DIR
from app.services.visuals.library import VisualizationResult, VisualLibrary, VisualRequest

logger = logging.getLogger(__name__)

#: Bump when the product prompt wording changes. Existing visuals keep
#: serving until an explicit --upgrade-prompt batch re-renders them.
COMPONENT_PROMPT_VERSION = "3"

#: How each category is framed and lit. A graphics card and a chair are not
#: photographed the same way, and the parts of a product a buyer looks at
#: first are the ones the prompt has to name.
CATEGORY_PRESENTATION: dict[ComponentCategory, str] = {
    ComponentCategory.GPU: (
        "three-quarter view from slightly above showing the full length of the card, "
        "the exact cooler shroud design, the real number of fans, the backplate edge "
        "and the PCIe bracket"
    ),
    ComponentCategory.MOTHERBOARD: (
        "flat top-down view at a slight angle showing the real PCB layout: VRM "
        "heatsinks around the socket, the DIMM slots, the M.2 heatsinks, the chipset "
        "cover and the rear IO shroud"
    ),
    ComponentCategory.RAM: (
        "the modules standing upright side by side, the exact heat-spreader shape and "
        "the light bar along the top edge if this kit has one"
    ),
    ComponentCategory.CPU: (
        "the retail box standing behind the processor, the chip resting in front of it "
        "with its heat spreader facing the camera"
    ),
    ComponentCategory.CASE: (
        "three-quarter front view, empty, the side panel in place so its material and "
        "the front intake design are both visible"
    ),
    ComponentCategory.COOLER: (
        "three-quarter view showing the fin stack or the pump block, the fans, and the "
        "mounting hardware laid out beside it"
    ),
    ComponentCategory.PSU: (
        "three-quarter view with the fan grille and the modular connector panel both "
        "visible, its cables coiled tidily beside the unit"
    ),
    ComponentCategory.SSD: (
        "close macro view of the bare drive, the label readable but not enlarged"
    ),
    ComponentCategory.MONITOR: (
        "front three-quarter view on its own stand, the real bezel proportions, the "
        "stand and its base exactly as this model has them, the screen showing a clean "
        "dark desktop"
    ),
    ComponentCategory.KEYBOARD: (
        "three-quarter view from above showing the full layout and the key profile"
    ),
    ComponentCategory.MOUSE: (
        "three-quarter view showing the shell shape, the buttons and the scroll wheel"
    ),
    ComponentCategory.HEADSET: (
        "three-quarter view standing upright, the headband and one earcup facing the camera"
    ),
    ComponentCategory.CHAIR: ("three-quarter view showing the backrest, the armrests and the base"),
    ComponentCategory.DESK: (
        "three-quarter view of the empty desk showing the top surface and the frame"
    ),
}

#: What each category is, in the words an image model understands.
CATEGORY_WORDS: dict[ComponentCategory, str] = {
    ComponentCategory.CPU: "boxed desktop processor, the retail box standing next to the CPU",
    ComponentCategory.GPU: "desktop graphics card",
    ComponentCategory.MOTHERBOARD: "desktop motherboard seen from above at a slight angle",
    ComponentCategory.RAM: "desktop memory kit, the modules standing upright",
    ComponentCategory.SSD: "M.2 NVMe SSD drive",
    ComponentCategory.PSU: "ATX power supply unit with its modular cables tidily beside it",
    ComponentCategory.CASE: "desktop PC case, empty, three-quarter view",
    ComponentCategory.COOLER: "CPU cooler",
    ComponentCategory.FANS: "pack of PC case fans",
    ComponentCategory.MONITOR: "computer monitor on its own stand",
    ComponentCategory.KEYBOARD: "computer keyboard",
    ComponentCategory.MOUSE: "computer mouse",
    ComponentCategory.HEADSET: "gaming headset",
    ComponentCategory.MICROPHONE: "desktop USB microphone on its stand",
    ComponentCategory.WEBCAM: "webcam",
    ComponentCategory.SPEAKERS: "pair of desktop speakers",
    ComponentCategory.MOUSEPAD: "mouse pad lying flat",
    ComponentCategory.DESK: "computer desk, empty, three-quarter view",
    ComponentCategory.CHAIR: "gaming chair, three-quarter view",
    ComponentCategory.LIGHTING: "desk lighting accessory",
    ComponentCategory.WIFI_ADAPTER: "Wi-Fi adapter",
    ComponentCategory.BLUETOOTH_ADAPTER: "Bluetooth adapter",
    ComponentCategory.OPERATING_SYSTEM: "software box",
    ComponentCategory.OTHER: "computer accessory",
}


@dataclass(frozen=True, slots=True)
class ComponentVisualSpec:
    component_id: str
    category: ComponentCategory
    brand: str
    model: str
    colour: str | None
    rgb: bool | None
    facts: tuple[str, ...]
    reference_url: str | None

    @property
    def name(self) -> str:
        return f"{self.brand} {self.model}"


def describe_component(component: Component) -> ComponentVisualSpec:
    """Facts worth drawing, taken from the typed spec - nothing else."""
    spec = component.spec
    colour: str | None = None
    rgb: bool | None = None
    facts: list[str] = []

    raw_colour = getattr(spec, "colour", None)
    if raw_colour is not None and raw_colour.value != "other":
        colour = raw_colour.value
    if hasattr(spec, "rgb"):
        rgb = bool(spec.rgb)

    if isinstance(spec, GpuSpec):
        fans = "triple-fan" if spec.length_mm >= 300 else "dual-fan"
        facts.append(
            f"{fans} cooler shroud, {spec.vram_gb} GB card, about {spec.length_mm} mm long"
        )
    elif isinstance(spec, CaseSpec):
        facts.append(
            f"{'/'.join(ff.value for ff in spec.form_factors)} mid-tower with a "
            f"{spec.side_panel or 'tempered glass'} side panel"
        )
        if spec.included_fans:
            size = f"{spec.included_fan_size_mm} mm " if spec.included_fan_size_mm else ""
            facts.append(f"{spec.included_fans} {size}fans pre-installed")
    elif isinstance(spec, CoolerSpec):
        if spec.cooler_type is CoolerType.AIO:
            facts.append(
                f"all-in-one liquid cooler with a {spec.radiator_mm} mm radiator, "
                f"{spec.fans or 'its'} fans and the pump block"
            )
        else:
            facts.append(
                f"tower air cooler about {spec.height_mm} mm tall with {spec.fans or 1} fan(s)"
            )
    elif isinstance(spec, RamSpec):
        facts.append(
            f"{spec.modules} x {spec.total_capacity_gb // spec.modules} GB "
            f"{spec.memory_type.value} modules, "
            f"{'with RGB light bars' if spec.rgb else 'plain heat spreaders, no lighting'}"
        )
    elif isinstance(spec, SsdSpec):
        facts.append(f"{spec.capacity_gb} GB {spec.form_factor or spec.interface} drive")
    elif isinstance(spec, PsuSpec):
        facts.append(
            f"{spec.wattage} W {spec.modular} unit, {spec.efficiency}, {spec.length_mm} mm deep"
        )
    elif isinstance(spec, MotherboardSpec):
        facts.append(
            f"{spec.form_factor.value} board with the {spec.chipset} chipset, "
            f"{spec.socket.value} socket"
        )
    elif isinstance(spec, CpuSpec):
        facts.append(f"{spec.socket.value} processor, {spec.cores} cores")
    elif isinstance(spec, MonitorSpec):
        facts.append(
            f"{spec.size_inch:g}-inch {spec.panel} panel, {spec.resolution}, "
            f"{spec.refresh_hz} Hz, {'curved' if spec.curved else 'flat'}"
        )
    elif isinstance(spec, FanSpec):
        facts.append(f"{spec.count} x {spec.size_mm} mm fans")
    elif isinstance(spec, PeripheralSpec):
        facts.append(spec.summary)
        facts.append("wireless, no cable" if spec.wireless else "wired")
        facts.extend(spec.highlights[:3])

    return ComponentVisualSpec(
        component_id=component.id,
        category=component.category,
        brand=component.brand,
        model=component.model,
        colour=colour,
        rgb=rgb,
        facts=tuple(facts),
        reference_url=component.image_url if component.image_verified else None,
    )


def component_identity(spec: ComponentVisualSpec) -> str:
    """What is depicted: this exact product in this colour."""
    material = "|".join(
        ["component", spec.component_id, spec.brand, spec.model, spec.colour or "-"]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def component_fingerprint(
    spec: ComponentVisualSpec, *, model: str, prompt_version: str = COMPONENT_PROMPT_VERSION
) -> str:
    """The exact render: identity + prompt version + image model."""
    material = "|".join([component_identity(spec), f"v{prompt_version}", model])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def build_component_prompt(spec: ComponentVisualSpec) -> VisualPrompt:
    words = CATEGORY_WORDS.get(spec.category, "computer product")
    facts: list[str] = [f"{spec.name}: {words}"]
    if spec.colour:
        facts.append(f"{spec.colour} colour exactly as the real product")
    if spec.rgb is True:
        facts.append("with its real RGB lighting switched on in a soft default rainbow")
    elif spec.rgb is False and spec.category in {
        ComponentCategory.CASE,
        ComponentCategory.COOLER,
        ComponentCategory.RAM,
        ComponentCategory.FANS,
        ComponentCategory.KEYBOARD,
        ComponentCategory.MOUSE,
        ComponentCategory.HEADSET,
    }:
        facts.append("no RGB lighting - this model has none")
    facts.extend(spec.facts)
    if spec.reference_url:
        facts.append("match the exact shape, colour and design shown in the reference image")

    presentation = CATEGORY_PRESENTATION.get(
        spec.category, "centred three-quarter view showing the whole product"
    )
    text = (
        "Premium commercial product photograph of a single real product, exactly this model "
        "and nothing else, shot for a high-end PC store catalogue. "
        + NO_LETTERING
        + " "
        + ". ".join(f[0].upper() + f[1:] for f in facts)
        + f". Framing: {presentation}"
        + ". Professional studio product photography: clean bright seamless background with "
        "a soft gradient, large softbox key light with gentle fill, controlled specular "
        "highlights on metal and plastic, physically plausible reflections and soft "
        "contact shadows, accurate materials, true proportions, sharp focus across the "
        "product with a natural shallow depth of field, presentation-ready. "
        "No people, no hands, no captions, no watermark, no packaging text. " + NO_LETTERING
    )
    return VisualPrompt(text=text, facts=tuple(facts))


class ComponentVisualizer:
    """Product pictures through the Visual Library."""

    def __init__(
        self,
        generator: ImageGenerator,
        *,
        output_dir: Path = AI_IMAGE_DIR,
        max_attempts: int = 2,
        timeout_seconds: float = 90.0,
        cost_per_call_usd: Decimal = Decimal("0.04"),
        references_enabled: bool = False,
        enabled: bool = True,
        model: str | None = None,
        on_demand: bool = False,
    ) -> None:
        self._generator = generator
        self._output_dir = output_dir
        self._max_attempts = max_attempts
        self._timeout = timeout_seconds
        self._cost = cost_per_call_usd
        self._references_enabled = references_enabled
        self._enabled = enabled
        self._model = model or getattr(generator, "model", None) or generator.name
        self.on_demand = on_demand

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> ComponentVisualizer:
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
            cost_per_call_usd=cfg.ai_image_cost_usd,
            references_enabled=cfg.ai_reference_images_enabled,
            enabled=cfg.ai_visualization_enabled,
            model=cfg.image_model,
            on_demand=cfg.visual_on_demand_components,
        )

    @property
    def enabled(self) -> bool:
        return self._enabled and self._generator.enabled

    @property
    def model(self) -> str:
        return self._model

    def library(self, session: AsyncSession) -> VisualLibrary:
        return VisualLibrary(
            session,
            self._generator,
            output_dir=self._output_dir,
            max_attempts=self._max_attempts,
            timeout_seconds=self._timeout,
            cost_per_call_usd=self._cost,
            enabled=self._enabled,
        )

    def request_for(self, component: Component) -> VisualRequest:
        spec = describe_component(component)
        references: list[Path] = []
        if self._references_enabled and spec.reference_url:
            from app.services.ai.visualizer import ReferenceImage, _download_reference

            try:
                path = _download_reference(
                    ReferenceImage(
                        component_id=component.id,
                        category=component.category,
                        url=spec.reference_url,
                        source=component.image_source,
                        verified=True,
                    )
                )
            except Exception:
                logger.warning("Reference image for %s unavailable", component.id)
                path = None
            if path is not None:
                references.append(path)
        return VisualRequest(
            entity_type=VisualEntityType.COMPONENT,
            entity_id=component.id,
            entity_slug=component.id,
            category=component.category.value,
            identity_key=component_identity(spec),
            fingerprint=component_fingerprint(spec, model=self._model),
            prompt=build_component_prompt(spec),
            model=self._model,
            prompt_version=COMPONENT_PROMPT_VERSION,
            provider=self._generator.name,
            preset_key="product",
            components={"component": component.id, "facts": list(spec.facts)},
            references=tuple(references),
        )

    def fingerprint_for(self, component: Component) -> str:
        return component_fingerprint(describe_component(component), model=self._model)

    async def status_for(self, session: AsyncSession, component: Component) -> Visual | None:
        """The usable picture of this product, or None. Never generates."""
        request = self.request_for(component)
        return await self.library(session).get(request)

    async def get_or_create(
        self,
        session: AsyncSession,
        component: Component,
        *,
        force: bool = False,
        allow_generation: bool | None = None,
    ) -> VisualizationResult:
        request = self.request_for(component)
        allowed = self.on_demand if allow_generation is None else allow_generation
        return await self.library(session).get_or_generate(
            request, force=force, allow_generation=allowed
        )
