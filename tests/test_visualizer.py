"""PC Visualizer: structured spec, fingerprint, cache, failures."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VisualizationStatus
from app.db.repositories import VisualizationRepository
from app.domain.components import ComponentCategory
from app.services.ai import (
    PROMPT_VERSION,
    Visualizer,
    build_prompt,
    describe_build,
    fingerprint,
)
from app.services.catalog import get_catalog
from app.services.media import PRESETS_BY_KEY, Accent, with_accent

C = ComponentCategory
PRESET = PRESETS_BY_KEY["black-red-gaming"]


@pytest.fixture(scope="module")
def parts():  # type: ignore[no-untyped-def]
    """The owner's example: Ryzen 7 9700X ... Fractal Pop Air - no RGB parts."""
    catalog = get_catalog()
    return {
        C.CPU: catalog.require("amd-ryzen-7-9700x"),
        C.COOLER: catalog.require("thermalright-assassin-x-120-refined-se"),
        C.MOTHERBOARD: catalog.require("msi-b650-gaming-plus-wifi"),
        C.RAM: catalog.require("kingston-fury-beast-32-ddr5-6000"),
        C.GPU: catalog.require("nvidia-rtx-5080"),
        C.SSD: catalog.require("wd-black-sn850x-2tb"),
        C.PSU: catalog.require("corsair-rm750e"),
        C.CASE: catalog.require("fractal-pop-air-black"),
    }


@pytest.fixture(scope="module")
def rgb_parts(parts):  # type: ignore[no-untyped-def]
    """Same machine in an ARGB case with RGB memory."""
    catalog = get_catalog()
    return {
        **parts,
        C.CASE: catalog.require("lianli-lancool-216-black"),
        C.RAM: catalog.require("corsair-vengeance-rgb-32-ddr5-6000"),
    }


class FakeGenerator:
    name = "fake"
    model = "fake-model"

    def __init__(
        self,
        payload: bytes | None = b"\x89PNG\r\n\x1a\nfake",
        *,
        error: str | None = None,
        transient: bool = False,
        delay: float = 0.0,
        enabled: bool = True,
    ) -> None:
        self.payload = payload
        self.calls: list[str] = []
        self.last_error = error
        self.last_error_transient = transient
        self._error = error
        self._transient = transient
        self._delay = delay
        self.enabled = enabled

    def generate_png(self, prompt: str, references=()) -> bytes | None:  # type: ignore[no-untyped-def]
        self.calls.append(prompt)
        if self._delay:
            time.sleep(self._delay)
        self.last_error = self._error
        self.last_error_transient = self._transient
        return self.payload


def _visualizer(tmp_path: Path, generator: FakeGenerator | None = None, **kw) -> Visualizer:  # type: ignore[no-untyped-def]
    return Visualizer(generator or FakeGenerator(), output_dir=tmp_path, **kw)


# --- spec and prompt ----------------------------------------------------------


def test_spec_is_built_from_catalogue_facts(parts) -> None:  # type: ignore[no-untyped-def]
    spec = describe_build(parts, PRESET)
    assert spec.components["case"] == "fractal-pop-air-black"
    assert spec.names["gpu"].startswith("NVIDIA")
    assert spec.case_colour == "black"
    assert spec.cooler_type == "air" and spec.cooler_colour == "black"
    assert spec.included_fans == 3 and spec.fan_size_mm == 120
    assert spec.ram_modules == 2 and spec.ram_rgb is False
    assert spec.board_form_factor == "ATX"


def test_a_build_without_rgb_parts_is_never_described_as_lit(parts) -> None:  # type: ignore[no-untyped-def]
    spec = describe_build(parts, PRESET)
    assert spec.lit_parts == () and spec.has_rgb is False
    assert spec.accent is Accent.WHITE  # the red choice has nothing to colour
    text = build_prompt(spec).text.lower()
    assert "no rgb lighting" in text and "glowing" not in text


def test_rgb_parts_glow_in_the_chosen_colour(rgb_parts) -> None:  # type: ignore[no-untyped-def]
    spec = describe_build(rgb_parts, PRESET)
    assert spec.lit_parts == ("fans", "memory")
    assert spec.accent is Accent.RED
    text = build_prompt(spec).text.lower()
    assert "fans and memory glowing red" in text
    assert "nothing else is lit" in text


def test_aio_radiator_position_comes_from_the_compatibility_engine(parts) -> None:  # type: ignore[no-untyped-def]
    catalog = get_catalog()
    build = dict(parts)
    build[C.COOLER] = catalog.require("arctic-liquid-freezer-iii-240")
    spec = describe_build(build, PRESET)
    assert spec.cooler_type == "aio" and spec.radiator_mm == 240
    assert spec.radiator_position == "top"  # Pop Air takes a 240 on top
    assert "mounted at the top" in build_prompt(spec).text


def test_prompt_names_every_part(parts) -> None:  # type: ignore[no-untyped-def]
    text = build_prompt(describe_build(parts, PRESET)).text
    for name in (
        "Fractal Design",
        "Pop Air",
        "GeForce RTX 5080",
        "Assassin X 120",
        "FURY Beast",
        "B650 GAMING PLUS",
    ):
        assert name in text, name
    lowered = text.lower()
    # The picture must carry no invented branding: a mangled fake logo is
    # both the ugliest failure mode and a misrepresentation of the product.
    assert "no people" in lowered
    assert "no lettering of any kind" in lowered
    assert "misspelled" in lowered
    assert "no logos" in lowered


def test_minimal_style_turns_the_lighting_down(rgb_parts) -> None:  # type: ignore[no-untyped-def]
    text = build_prompt(describe_build(rgb_parts, PRESETS_BY_KEY["black-blue-minimal"])).text
    assert "subtle blue lighting" in text.lower() and "glowing" not in text.lower()


def test_references_only_come_from_verified_photos(parts) -> None:  # type: ignore[no-untyped-def]
    spec = describe_build(parts, PRESET)
    assert spec.references == ()  # nothing verified in the catalogue yet
    case = parts[C.CASE].model_copy(
        update={"image_url": "https://example.com/pop-air.jpg", "image_verified": True}
    )
    unverified = parts[C.GPU].model_copy(update={"image_url": "https://example.com/gpu.jpg"})
    build = {**parts, C.CASE: case, C.GPU: unverified}
    spec = describe_build(build, PRESET)
    assert [r.component_id for r in spec.references] == [case.id]
    assert "reference images" in build_prompt(spec).text


# --- fingerprint --------------------------------------------------------------


def test_fingerprint_is_stable(parts) -> None:  # type: ignore[no-untyped-def]
    a = fingerprint(describe_build(parts, PRESET), model="m")
    b = fingerprint(describe_build(dict(parts), PRESET), model="m")
    assert a == b and len(a) == 24


def test_changed_gpu_changes_the_fingerprint(parts) -> None:  # type: ignore[no-untyped-def]
    other = {**parts, C.GPU: get_catalog().require("amd-rx-9070-xt")}
    assert fingerprint(describe_build(parts, PRESET), model="m") != fingerprint(
        describe_build(other, PRESET), model="m"
    )


def test_changed_case_changes_the_fingerprint(parts) -> None:  # type: ignore[no-untyped-def]
    other = {**parts, C.CASE: get_catalog().require("lianli-lancool-216-black")}
    assert fingerprint(describe_build(parts, PRESET), model="m") != fingerprint(
        describe_build(other, PRESET), model="m"
    )


def test_colour_style_model_and_prompt_version_are_part_of_the_key(rgb_parts) -> None:  # type: ignore[no-untyped-def]
    base = fingerprint(describe_build(rgb_parts, PRESET), model="m")
    blue = with_accent(PRESET, Accent.BLUE)
    assert fingerprint(describe_build(rgb_parts, blue), model="m") != base
    minimal = PRESETS_BY_KEY["black-red-minimal"]
    assert fingerprint(describe_build(rgb_parts, minimal), model="m") != base
    assert fingerprint(describe_build(rgb_parts, PRESET), model="other") != base
    assert fingerprint(describe_build(rgb_parts, PRESET), model="m", prompt_version="99") != base
    # the live prompt version is what the default key is built from, so bumping
    # it invalidates every cached render instead of silently reusing an old one
    assert (
        fingerprint(describe_build(rgb_parts, PRESET), model="m", prompt_version=PROMPT_VERSION)
        == base
    )


def test_colour_choices_share_one_render_when_nothing_is_lit(parts) -> None:  # type: ignore[no-untyped-def]
    red = fingerprint(describe_build(parts, PRESET), model="m")
    blue = fingerprint(describe_build(parts, with_accent(PRESET, Accent.BLUE)), model="m")
    assert red == blue


# --- cache ----------------------------------------------------------------------


async def test_visualizer_renders_and_records(session: AsyncSession, tmp_path: Path, parts) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator()
    visualizer = _visualizer(tmp_path, generator)
    result = await visualizer.get_or_create(session, parts, PRESET, build_id=None)
    assert result.ok and result.path is not None and result.path.is_file()
    assert result.cache_hit is False and result.api_calls == 1
    assert "Pop Air" in generator.calls[0]
    row = result.record
    assert row is not None and row.status == VisualizationStatus.READY
    assert row.fingerprint == result.fingerprint and row.prompt_version == PROMPT_VERSION
    assert row.model == "fake-model" and row.provider == "fake" and row.attempts == 1


async def test_same_build_uses_the_cache(session: AsyncSession, tmp_path: Path, parts) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator()
    visualizer = _visualizer(tmp_path, generator)
    first = await visualizer.get_or_create(session, parts, PRESET)
    second = await visualizer.get_or_create(session, dict(parts), PRESET)
    assert second.cache_hit and second.path == first.path
    assert len(generator.calls) == 1


async def test_changed_gpu_renders_again(session: AsyncSession, tmp_path: Path, parts) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator()
    visualizer = _visualizer(tmp_path, generator)
    await visualizer.get_or_create(session, parts, PRESET)
    other = {**parts, C.GPU: get_catalog().require("amd-rx-9070-xt")}
    result = await visualizer.get_or_create(session, other, PRESET)
    assert not result.cache_hit and len(generator.calls) == 2


async def test_missing_image_file_is_regenerated(
    session: AsyncSession, tmp_path: Path, parts
) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator()
    visualizer = _visualizer(tmp_path, generator)
    first = await visualizer.get_or_create(session, parts, PRESET)
    assert first.path is not None
    first.path.unlink()
    again = await visualizer.get_or_create(session, parts, PRESET)
    assert again.ok and not again.cache_hit and len(generator.calls) == 2


async def test_api_error_is_recorded_and_never_breaks(
    session: AsyncSession, tmp_path: Path, parts
) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator(payload=None, error="BadRequestError: content policy")
    visualizer = _visualizer(tmp_path, generator)
    result = await visualizer.get_or_create(session, parts, PRESET)
    assert result.status == VisualizationStatus.FAILED and result.path is None
    assert result.record is not None and "content policy" in (result.record.error or "")
    assert len(generator.calls) == 1  # a refusal is not retried
    assert not list(tmp_path.glob("ai-*.png"))


async def test_transient_error_gets_one_retry_then_gives_up(
    session: AsyncSession, tmp_path: Path, parts
) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator(payload=None, error="APITimeoutError: slow", transient=True)
    visualizer = _visualizer(tmp_path, generator, max_attempts=2)
    visualizer.MIN_INTERVAL_SECONDS = 0.0
    result = await visualizer.get_or_create(session, parts, PRESET)
    assert result.status == VisualizationStatus.FAILED
    assert len(generator.calls) == 2
    # Exhausted: the next request is free (no call) until someone forces it.
    again = await visualizer.get_or_create(session, parts, PRESET)
    assert again.status == VisualizationStatus.FAILED and len(generator.calls) == 2
    forced = await visualizer.get_or_create(session, parts, PRESET, force=True)
    assert forced.status == VisualizationStatus.FAILED and len(generator.calls) == 3


async def test_timeout_is_handled(session: AsyncSession, tmp_path: Path, parts) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator(delay=0.3)
    visualizer = _visualizer(tmp_path, generator, timeout_seconds=0.05, max_attempts=1)
    visualizer.MIN_INTERVAL_SECONDS = 0.0
    Visualizer._lock = None
    result = await asyncio.wait_for(visualizer.get_or_create(session, parts, PRESET), timeout=15)
    assert result.status in {VisualizationStatus.FAILED, VisualizationStatus.READY}


async def test_disabled_visualizer_makes_no_calls(
    session: AsyncSession, tmp_path: Path, parts
) -> None:  # type: ignore[no-untyped-def]
    generator = FakeGenerator(enabled=False)
    visualizer = _visualizer(tmp_path, generator)
    result = await visualizer.get_or_create(session, parts, PRESET)
    assert result.status == "disabled" and generator.calls == []


async def test_repository_counts_and_recent(session: AsyncSession, tmp_path: Path, parts) -> None:  # type: ignore[no-untyped-def]
    visualizer = _visualizer(tmp_path)
    await visualizer.get_or_create(session, parts, PRESET)
    repo = VisualizationRepository(session)
    counts = await repo.counts()
    assert counts[VisualizationStatus.READY] == 1
    assert len(await repo.list_recent()) == 1
