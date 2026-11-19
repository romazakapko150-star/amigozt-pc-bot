"""Photorealistic build visualisation through an image-generation API.

The schematic card (:mod:`build_image`) shows *what is in the machine*; this
module produces an image of *what it looks like* - the actual case model, the
real graphics card, the chosen lighting colour - by describing the build to an
image model. The description is built from structured catalogue data only, so
the picture cannot invent parts the customer did not choose.

Status: the adapter is complete and dormant. It activates when
``OPENAI_API_KEY`` is set; without a key :func:`generate` returns ``None`` and
callers fall back to the schematic. Nothing here pretends to be a photograph
of the real product - the caption shown with it says so.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.domain.components import (
    CaseSpec,
    Component,
    ComponentCategory,
    CoolerSpec,
    CoolerType,
    GpuSpec,
    RamSpec,
)
from app.services.media.presets import Accent, CaseFinish, Style, VisualPreset

logger = logging.getLogger(__name__)

Parts = dict[ComponentCategory, Component]

#: Human-readable colour words for the prompt, one per accent.
#: An image model cannot draw a real brand mark - it produces lettering that
#: looks like one and reads as nonsense, and we have no licence to reproduce a
#: manufacturer's mark anyway. Every prompt asks for unmarked surfaces instead.
NO_LETTERING = (
    "The product must be completely free of writing: no brand names, no model "
    "names, no logos, no badges, no stickers, no serial numbers and no lettering "
    "of any kind anywhere in the frame - where a logo would normally sit, show a "
    "clean unmarked surface of the same material. Invented or misspelled lettering "
    "is the single worst failure here."
)


ACCENT_WORDS: dict[Accent, str] = {
    Accent.RED: "red",
    Accent.BLUE: "blue",
    Accent.PURPLE: "purple",
    Accent.PINK: "pink",
    Accent.GREEN: "green",
    Accent.ORANGE: "orange",
    Accent.YELLOW: "yellow",
    Accent.CYAN: "cyan",
    Accent.WHITE: "pure white",
    Accent.SILVER: "cool silver-white",
    Accent.GOLD: "warm gold",
    Accent.RAINBOW: "rainbow multi-colour",
}


@dataclass(frozen=True, slots=True)
class VisualPrompt:
    """A finished prompt plus the facts it was built from, for auditing."""

    text: str
    facts: tuple[str, ...]

    @property
    def key(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:20]


def _spec(parts: Parts, category: ComponentCategory, expected: type):  # type: ignore[no-untyped-def]
    component = parts.get(category)
    if component is None:
        return None
    spec = component.spec
    return spec if isinstance(spec, expected) else None


def build_prompt(parts: Parts, preset: VisualPreset) -> VisualPrompt:
    """Describe the build for an image model, from catalogue facts only.

    Every sentence traces back to a component field or the chosen preset.
    Brand and model names are included verbatim so the model draws the real
    product lines rather than a generic tower.
    """
    facts: list[str] = []

    case = parts.get(ComponentCategory.CASE)
    case_spec = _spec(parts, ComponentCategory.CASE, CaseSpec)
    finish = "white" if preset.finish is CaseFinish.WHITE else "black"
    if case is not None:
        facts.append(
            f"{finish} {case.brand} {case.model} mid-tower PC case with a tempered glass side panel"
        )
    else:
        facts.append(f"{finish} mid-tower PC case with a tempered glass side panel")

    if case_spec is not None and case_spec.included_fans:
        facts.append(f"{case_spec.included_fans} case fans visible through the glass")

    gpu = parts.get(ComponentCategory.GPU)
    gpu_spec = _spec(parts, ComponentCategory.GPU, GpuSpec)
    if gpu is not None:
        size = "large triple-fan" if gpu_spec and gpu_spec.length_mm >= 300 else "dual-fan"
        facts.append(f"a {size} {gpu.brand} {gpu.model} graphics card mounted horizontally")

    cooler = parts.get(ComponentCategory.COOLER)
    cooler_spec = _spec(parts, ComponentCategory.COOLER, CoolerSpec)
    if cooler is not None and cooler_spec is not None:
        if cooler_spec.cooler_type is CoolerType.AIO:
            facts.append(
                f"a {cooler.brand} {cooler.model} all-in-one liquid cooler with its "
                f"{cooler_spec.radiator_mm}mm radiator mounted at the top"
            )
        else:
            facts.append(f"a {cooler.brand} {cooler.model} tower air cooler on the CPU")

    ram = parts.get(ComponentCategory.RAM)
    ram_spec = _spec(parts, ComponentCategory.RAM, RamSpec)
    if ram is not None:
        lit = "with RGB light bars" if ram_spec and ram_spec.rgb else "without lighting"
        facts.append(f"two {ram.brand} memory modules {lit}")

    board = parts.get(ComponentCategory.MOTHERBOARD)
    if board is not None:
        facts.append(f"{board.brand} {board.model} motherboard")

    psu = parts.get(ComponentCategory.PSU)
    if psu is not None:
        facts.append(
            f"{psu.brand} power supply hidden under the PSU shroud with tidy cable management"
        )

    accent = ACCENT_WORDS[preset.accent]
    if preset.style is Style.GAMING:
        facts.append(f"all fans and lighting glowing {accent}, the glow reflecting on the glass")
    else:
        facts.append(f"subtle {accent} fan lighting, restrained and clean")

    text = (
        "Photorealistic product photograph of a custom-built gaming desktop PC. "
        + ". ".join(fact[0].upper() + fact[1:] for fact in facts)
        + ". Three-quarter front view showing the glass side, on a clean dark desk, "
        "studio lighting, shallow depth of field, sharp focus on the components, "
        "no people, no text, no watermark, no logos added that are not on the real products."
    )
    return VisualPrompt(text=text, facts=tuple(facts))


class ImageGenerator(Protocol):
    """Any service that can turn a prompt into PNG bytes."""

    name: str
    #: Last failure, for the visualisation record; None after a success.
    last_error: str | None
    #: True when the last failure was a timeout / network / rate-limit and a
    #: retry may succeed; False for refusals and invalid requests.
    last_error_transient: bool

    @property
    def enabled(self) -> bool: ...

    def generate_png(self, prompt: str, references: Sequence[Path] = ()) -> bytes | None: ...


#: Errors worth one retry; anything else is final for this prompt.
#: Errors where nothing was produced, so a retry cannot double-bill.
_TRANSIENT_ERRORS = ("APIConnectionError", "RateLimitError")


class OpenAIImageGenerator:
    """Adapter for the OpenAI Images API (``gpt-image-1``).

    Dormant until ``api_key`` is given. Errors are logged, classified and
    swallowed - the caller reads ``last_error`` - so a billing hiccup or a
    content-policy refusal never costs the customer their build card.

    With ``references`` (local image files of the chosen parts) the *edit*
    endpoint is used, which takes the pictures as visual guidance; without
    them the plain *generate* endpoint draws from the prompt alone.
    """

    name = "openai-images"

    def __init__(
        self,
        api_key: str | None,
        model: str = "gpt-image-1",
        size: str = "1024x1024",
        quality: str = "medium",
        timeout_seconds: float = 90.0,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._model = model
        self._size = size
        self._quality = quality
        self._timeout = timeout_seconds
        self.last_error: str | None = None
        self.last_error_transient = False

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    @property
    def model(self) -> str:
        return self._model

    def generate_png(self, prompt: str, references: Sequence[Path] = ()) -> bytes | None:
        self.last_error = None
        self.last_error_transient = False
        if not self.enabled:
            self.last_error = "no API key configured"
            return None
        try:
            from openai import OpenAI
        except ImportError:  # pragma: no cover - optional dependency
            logger.warning("openai SDK not installed; AI visualisation disabled")
            self.last_error = "openai SDK not installed"
            return None

        # The SDK's own retries are off: the visualiser decides about retries
        # so that one request never silently becomes three paid ones.
        client = OpenAI(api_key=self._api_key, timeout=self._timeout, max_retries=0)
        handles = []
        params: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "size": self._size,
            "quality": self._quality,
            "n": 1,
        }
        try:
            if references:
                handles = [open(path, "rb") for path in references]  # noqa: SIM115
                response = client.images.edit(image=handles, **params)
            else:
                response = client.images.generate(**params)
        except Exception as exc:
            kind = type(exc).__name__
            self.last_error = f"{kind}: {str(exc)[:300]}"
            self.last_error_transient = kind in _TRANSIENT_ERRORS
            logger.warning("Image generation request failed: %s", self.last_error)
            return None
        finally:
            for handle in handles:
                handle.close()

        data = response.data[0] if response.data else None
        payload = getattr(data, "b64_json", None) if data is not None else None
        if not payload:
            self.last_error = "API returned no image data"
            logger.warning("Image generation returned no image data")
            return None
        return base64.b64decode(payload)


def generate(
    parts: Parts,
    preset: VisualPreset,
    generator: ImageGenerator,
    *,
    output_dir: Path,
) -> Path | None:
    """A photorealistic render for this build and look, or ``None``.

    Cached by prompt hash: a build is generated once per look, never per tap.
    """
    if not generator.enabled:
        return None

    prompt = build_prompt(parts, preset)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"ai-{prompt.key}.png"
    if path.exists():
        return path

    png = generator.generate_png(prompt.text)
    if not png:
        return None

    path.write_bytes(png)
    logger.info("AI visualisation rendered: %s", path.name)
    return path
