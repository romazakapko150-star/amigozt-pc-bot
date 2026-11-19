"""AI visualisation: prompt building, the dormant adapter, caching, fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.components import ComponentCategory
from app.services.catalog import get_catalog
from app.services.media import PRESETS_BY_KEY
from app.services.media.ai_visual import (
    OpenAIImageGenerator,
    build_prompt,
    generate,
)

C = ComponentCategory


@pytest.fixture(scope="module")
def parts():  # type: ignore[no-untyped-def]
    catalog = get_catalog()
    return {
        C.CPU: catalog.require("amd-ryzen-7-7800x3d"),
        C.GPU: catalog.require("nvidia-rtx-5080"),
        C.MOTHERBOARD: catalog.require("asus-tuf-b650-plus-wifi"),
        C.RAM: catalog.require("corsair-vengeance-rgb-32-ddr5-6000-white"),
        C.SSD: catalog.require("wd-black-sn850x-2tb"),
        C.PSU: catalog.require("corsair-rm750e-white"),
        C.CASE: catalog.require("lianli-o11-dynamic-evo-white"),
        C.COOLER: catalog.require("arctic-liquid-freezer-iii-360-white"),
    }


class FakeGenerator:
    """Counts calls and returns a tiny valid PNG header."""

    name = "fake"

    def __init__(
        self, enabled: bool = True, payload: bytes | None = b"\x89PNG\r\n\x1a\nfake"
    ) -> None:
        self.enabled = enabled
        self.payload = payload
        self.calls: list[str] = []

    def generate_png(self, prompt: str) -> bytes | None:
        self.calls.append(prompt)
        return self.payload


# --- prompt -------------------------------------------------------------------


def test_prompt_names_the_real_parts(parts) -> None:  # type: ignore[no-untyped-def]
    prompt = build_prompt(parts, PRESETS_BY_KEY["white-purple-gaming"])
    text = prompt.text

    assert "Lian Li" in text and "O11 Dynamic EVO" in text
    assert "GeForce RTX 5080" in text
    assert "Liquid Freezer III 360" in text
    assert "360mm radiator" in text
    assert "Corsair" in text
    assert "ASUS" in text


def test_prompt_follows_the_preset(parts) -> None:  # type: ignore[no-untyped-def]
    purple = build_prompt(parts, PRESETS_BY_KEY["white-purple-gaming"]).text
    minimal_red = build_prompt(parts, PRESETS_BY_KEY["white-red-minimal"]).text

    # Facts are sentence-cased in the prompt, so compare case-insensitively.
    assert "white" in purple.lower() and "purple" in purple.lower()
    assert "red" in minimal_red.lower() and "subtle" in minimal_red.lower()
    assert purple != minimal_red


def test_prompt_uses_only_catalogue_facts(parts) -> None:  # type: ignore[no-untyped-def]
    """Every fact must trace back to a part in the build or the preset."""
    prompt = build_prompt(parts, PRESETS_BY_KEY["white-purple-gaming"])
    names = {component.brand for component in parts.values()}
    for fact in prompt.facts:
        mentions_part = any(brand in fact for brand in names)
        mentions_preset = "purple" in fact or "white" in fact.lower() or "fans" in fact
        assert mentions_part or mentions_preset, fact


def test_prompt_forbids_invented_text_and_people(parts) -> None:  # type: ignore[no-untyped-def]
    text = build_prompt(parts, PRESETS_BY_KEY["black-blue-gaming"]).text
    assert "no people" in text
    assert "no text" in text
    assert "no watermark" in text


def test_air_cooler_is_described_as_a_tower(parts) -> None:  # type: ignore[no-untyped-def]
    catalog = get_catalog()
    air = dict(parts)
    air[C.COOLER] = catalog.require("thermalright-peerless-assassin-120-white")
    text = build_prompt(air, PRESETS_BY_KEY["white-cyan-gaming"]).text
    assert "tower air cooler" in text
    assert "radiator" not in text


def test_prompt_key_is_stable(parts) -> None:  # type: ignore[no-untyped-def]
    preset = PRESETS_BY_KEY["black-red-gaming"]
    assert build_prompt(parts, preset).key == build_prompt(parts, preset).key


# --- adapter ------------------------------------------------------------------


def test_adapter_is_dormant_without_a_key() -> None:
    generator = OpenAIImageGenerator(api_key=None)
    assert generator.enabled is False
    assert generator.generate_png("anything") is None


def test_blank_key_counts_as_missing() -> None:
    assert OpenAIImageGenerator(api_key="   ").enabled is False


def test_key_enables_the_adapter() -> None:
    assert OpenAIImageGenerator(api_key="sk-test").enabled is True


# --- generate() ---------------------------------------------------------------


def test_disabled_generator_yields_nothing(tmp_path: Path, parts) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator(enabled=False)
    assert (
        generate(parts, PRESETS_BY_KEY["black-red-gaming"], generator, output_dir=tmp_path) is None
    )
    assert generator.calls == []


def test_image_is_written_and_cached(tmp_path: Path, parts) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator()
    preset = PRESETS_BY_KEY["black-red-gaming"]

    first = generate(parts, preset, generator, output_dir=tmp_path)
    second = generate(parts, preset, generator, output_dir=tmp_path)

    assert first is not None and first.exists()
    assert first == second
    # One paid call per build and look, never per tap.
    assert len(generator.calls) == 1


def test_different_looks_are_separate_renders(tmp_path: Path, parts) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator()
    red = generate(parts, PRESETS_BY_KEY["black-red-gaming"], generator, output_dir=tmp_path)
    blue = generate(parts, PRESETS_BY_KEY["black-blue-gaming"], generator, output_dir=tmp_path)
    assert red != blue
    assert len(generator.calls) == 2


def test_empty_response_falls_through(tmp_path: Path, parts) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator(payload=None)
    assert (
        generate(parts, PRESETS_BY_KEY["black-red-gaming"], generator, output_dir=tmp_path) is None
    )
    assert not list(tmp_path.glob("ai-*.png"))
