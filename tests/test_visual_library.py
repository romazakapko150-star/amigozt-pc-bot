"""The Visual Library contract: one identity - one render - reused forever.

Every test uses a fake generator; nothing here can reach a paid API
(conftest also forces the OpenAI key off for the whole test process).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.base import Base
from app.db.models import ReadyBuild, ReadyBuildStatus
from app.db.repositories import VisualizationRepository
from app.domain.components import ACCESSORY_CATEGORIES, ComponentCategory
from app.domain.enums import Aesthetics
from app.services.ai.visualizer import describe_build, fingerprint
from app.services.catalog import get_catalog
from app.services.media import PRESETS_BY_KEY, default_preset
from app.services.visuals import ComponentVisualizer, batch
from app.services.visuals.library import STATUS_MISSING, VisualLibrary

C = ComponentCategory
PRESET = PRESETS_BY_KEY["black-white-gaming"]
MODEL = "gpt-image-1"  # must match settings so inventory sees the same fingerprints
PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"


class FakeGenerator:
    """Deterministic stand-in for the OpenAI image generator."""

    name = "fake"
    model = MODEL

    def __init__(
        self,
        payload: bytes | None = PNG,
        *,
        error: str | None = None,
        transient: bool = False,
        delay: float = 0.0,
    ) -> None:
        self.payload = payload
        self.calls: list[str] = []
        self.enabled = True
        self.last_error = error
        self.last_error_transient = transient
        self._delay = delay

    def generate_png(self, prompt: str, references=()) -> bytes | None:  # type: ignore[no-untyped-def]
        self.calls.append(prompt)
        if self._delay:
            time.sleep(self._delay)
        return self.payload


@pytest.fixture(autouse=True)
def _quiet_library():  # type: ignore[no-untyped-def]
    """No cross-test locks and no 1-second spacing between fake API calls."""
    VisualLibrary.reset_locks()
    old = VisualLibrary.MIN_INTERVAL_SECONDS
    VisualLibrary.MIN_INTERVAL_SECONDS = 0.0
    yield
    VisualLibrary.MIN_INTERVAL_SECONDS = old
    VisualLibrary.reset_locks()


def make_visualizer(
    tmp_path: Path, generator: FakeGenerator | None = None, **kwargs
) -> tuple[ComponentVisualizer, FakeGenerator]:
    generator = generator or FakeGenerator()
    visualizer = ComponentVisualizer(
        generator,
        output_dir=tmp_path,
        model=MODEL,
        cost_per_call_usd=Decimal("0.04"),
        **kwargs,
    )
    return visualizer, generator


def a_mouse():  # type: ignore[no-untyped-def]
    return next(c for c in get_catalog() if c.category is C.MOUSE)


def two_mice():  # type: ignore[no-untyped-def]
    mice = [c for c in get_catalog() if c.category is C.MOUSE]
    assert len(mice) >= 2
    return mice[0], mice[1]


# --- cache: one identity, one render, reused forever ---------------------------


async def test_hundred_requests_for_one_product_cost_one_api_call(
    session: AsyncSession, tmp_path: Path
) -> None:
    visualizer, generator = make_visualizer(tmp_path)
    mouse = a_mouse()

    first = await visualizer.get_or_create(session, mouse, allow_generation=True)
    assert first.ok and not first.cache_hit and first.api_calls == 1

    for _ in range(99):
        again = await visualizer.get_or_create(session, mouse, allow_generation=True)
        assert again.ok and again.cache_hit and again.api_calls == 0

    assert len(generator.calls) == 1
    stats = await VisualizationRepository(session).stats()
    assert stats["events"]["api_call"] == 1
    assert stats["events"]["cache_hit"] == 99
    assert stats["spend_usd"] == Decimal("0.04")


async def test_two_products_have_two_fingerprints(tmp_path: Path) -> None:
    visualizer, _ = make_visualizer(tmp_path)
    mouse_a, mouse_b = two_mice()
    assert visualizer.fingerprint_for(mouse_a) != visualizer.fingerprint_for(mouse_b)


async def test_admin_metadata_never_changes_the_fingerprint(tmp_path: Path) -> None:
    """Spec provenance (price-keeping and audit fields) is not visual identity."""
    visualizer, _ = make_visualizer(tmp_path)
    mouse = a_mouse()
    edited = mouse.model_copy(
        update={"spec_source": "audit", "spec_notes": "checked twice", "spec_verified": True}
    )
    assert visualizer.fingerprint_for(mouse) == visualizer.fingerprint_for(edited)


async def test_restart_reuses_the_saved_render(session: AsyncSession, tmp_path: Path) -> None:
    visualizer, generator = make_visualizer(tmp_path)
    mouse = a_mouse()
    await visualizer.get_or_create(session, mouse, allow_generation=True)

    reborn, fresh = make_visualizer(tmp_path)  # new process: new objects, same DB
    found = await reborn.status_for(session, mouse)
    assert found is not None and found.is_ready
    result = await reborn.get_or_create(session, mouse, allow_generation=True)
    assert result.cache_hit and len(fresh.calls) == 0 and len(generator.calls) == 1


async def test_prompt_version_bump_reuses_the_older_render(
    session: AsyncSession, tmp_path: Path
) -> None:
    visualizer, generator = make_visualizer(tmp_path)
    mouse = a_mouse()
    await visualizer.get_or_create(session, mouse, allow_generation=True)

    request = visualizer.request_for(mouse)
    bumped = replace(request, fingerprint="a-new-prompt-version-fp", prompt_version="99")
    result = await visualizer.library(session).get_or_generate(bumped, allow_generation=True)
    assert result.ok and result.cache_hit
    assert result.extra.get("version") == "outdated"
    assert len(generator.calls) == 1  # the bump alone never re-renders


# --- concurrency: parallel identical requests share one render -----------------


async def test_parallel_requests_render_once(tmp_path: Path) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    generator = FakeGenerator(delay=0.15)
    visualizer, _ = make_visualizer(tmp_path, generator)
    mouse = a_mouse()

    async def one_customer():  # type: ignore[no-untyped-def]
        async with factory() as session:
            result = await visualizer.get_or_create(session, mouse, allow_generation=True)
            await session.commit()
            return result

    first, second = await asyncio.gather(one_customer(), one_customer())
    assert first.ok and second.ok
    assert len(generator.calls) == 1, "a double tap must never pay twice"
    assert {first.cache_hit, second.cache_hit} == {False, True}
    await engine.dispose()


# --- retry safety ---------------------------------------------------------------


async def test_timeout_is_terminal_and_never_retried(session: AsyncSession, tmp_path: Path) -> None:
    # timeout_seconds is negative so the library's wait (timeout + 10s) fires
    # in 0.1s while the fake API is still "working": the ambiguous-billing case.
    generator = FakeGenerator(delay=0.6)
    visualizer, _ = make_visualizer(tmp_path, generator, timeout_seconds=-9.9)
    mouse = a_mouse()

    result = await visualizer.get_or_create(session, mouse, allow_generation=True)
    assert not result.ok and result.api_calls == 1
    assert "not retried" in (result.error or "")
    assert len(generator.calls) == 1, "a timeout may already be billed: no blind retry"


async def test_transient_error_gets_exactly_one_retry(
    session: AsyncSession, tmp_path: Path
) -> None:
    generator = FakeGenerator(payload=None, error="RateLimitError: slow down", transient=True)
    visualizer, _ = make_visualizer(tmp_path, generator, max_attempts=2)
    mouse = a_mouse()

    result = await visualizer.get_or_create(session, mouse, allow_generation=True)
    assert not result.ok
    assert len(generator.calls) == 2  # capped by max_attempts, never unbounded
    stats = await VisualizationRepository(session).stats()
    assert stats["events"]["api_call"] == 2 and stats["events"]["failed"] == 1


# --- history and failed regeneration -------------------------------------------


async def test_forced_regeneration_keeps_the_old_file_in_history(
    session: AsyncSession, tmp_path: Path
) -> None:
    visualizer, _ = make_visualizer(tmp_path)
    mouse = a_mouse()
    first = await visualizer.get_or_create(session, mouse, allow_generation=True)
    old_path = first.path
    assert old_path is not None and old_path.is_file()

    second = await visualizer.get_or_create(session, mouse, force=True, allow_generation=True)
    assert second.ok and second.path != old_path
    assert old_path.is_file(), "successful visuals are never deleted"
    record = second.record
    assert record is not None and len(record.history) == 1
    assert record.history[0]["image_path"] == str(old_path)


async def test_failed_regeneration_keeps_the_old_picture_active(
    session: AsyncSession, tmp_path: Path
) -> None:
    visualizer, _ = make_visualizer(tmp_path)
    mouse = a_mouse()
    first = await visualizer.get_or_create(session, mouse, allow_generation=True)
    assert first.ok and first.path is not None

    broken = FakeGenerator(payload=None, error="boom")
    failing, _ = make_visualizer(tmp_path, broken)
    result = await failing.get_or_create(session, mouse, force=True, allow_generation=True)
    assert not result.ok and result.extra.get("kept_previous") is True

    still = await visualizer.status_for(session, mouse)
    assert still is not None and still.is_ready
    assert still.image_path == str(first.path) and Path(still.image_path).is_file()


async def test_invalidate_hides_but_never_deletes(session: AsyncSession, tmp_path: Path) -> None:
    visualizer, _ = make_visualizer(tmp_path)
    mouse = a_mouse()
    first = await visualizer.get_or_create(session, mouse, allow_generation=True)
    record = first.record
    assert record is not None and first.path is not None

    await visualizer.library(session).invalidate(record, "wrong shroud")
    assert await visualizer.status_for(session, mouse) is None
    assert first.path.is_file(), "the file stays on disk"
    blocked = await visualizer.get_or_create(session, mouse, allow_generation=False)
    assert blocked.status == STATUS_MISSING


# --- build fingerprints: the setup is part of the identity ----------------------


def _core_parts():  # type: ignore[no-untyped-def]
    catalog = get_catalog()
    return {
        C.CPU: catalog.require("amd-ryzen-7-9700x"),
        C.COOLER: catalog.require("thermalright-assassin-x-120-refined-se"),
        C.MOTHERBOARD: catalog.require("msi-b650-gaming-plus-wifi"),
        C.RAM: catalog.require("kingston-fury-beast-32-ddr5-6000"),
        C.GPU: catalog.require("nvidia-rtx-5080"),
        C.SSD: catalog.require("wd-black-sn850x-2tb"),
        # the RTX 5080 asks for 850 W - a smaller unit makes the build
        # NOT BUILDABLE and the inventory would rightly skip it
        C.PSU: catalog.require("bequiet-pure-power-12m-850"),
        C.CASE: catalog.require("fractal-pop-air-black"),
    }


def test_adding_or_swapping_a_mouse_changes_the_build_fingerprint() -> None:
    parts = _core_parts()
    mouse_a, mouse_b = two_mice()
    base = fingerprint(describe_build(parts, PRESET), model=MODEL)
    with_a = fingerprint(describe_build({**parts, C.MOUSE: mouse_a}, PRESET), model=MODEL)
    with_b = fingerprint(describe_build({**parts, C.MOUSE: mouse_b}, PRESET), model=MODEL)
    assert len({base, with_a, with_b}) == 3
    again = fingerprint(describe_build({**parts, C.MOUSE: mouse_a}, PRESET), model=MODEL)
    assert again == with_a  # the same setup always maps to the same visual


def test_swapping_the_case_changes_the_build_fingerprint() -> None:
    parts = _core_parts()
    other = get_catalog().require("lianli-lancool-216-black")
    base = fingerprint(describe_build(parts, PRESET), model=MODEL)
    swapped = fingerprint(describe_build({**parts, C.CASE: other}, PRESET), model=MODEL)
    assert base != swapped


def test_peripherals_show_up_in_the_prompt() -> None:
    from app.services.ai.visualizer import build_prompt

    parts = _core_parts()
    mouse = a_mouse()
    monitor = next(c for c in get_catalog() if c.category is C.MONITOR)
    text = build_prompt(describe_build({**parts, C.MOUSE: mouse, C.MONITOR: monitor}, PRESET)).text
    assert mouse.name in text and monitor.name in text
    assert "switched on" in text  # the monitor is presented alive, not a black slab


# --- inventory, batch selection and the free legacy rekey ----------------------


async def test_inventory_counts_and_select_limit(session: AsyncSession, tmp_path: Path) -> None:
    settings = get_settings()
    inv = await batch.inventory(session, settings=settings, include_builds=False)
    s = inv.summary()
    # Derived from the catalogue, not hardcoded: adding stock must not force
    # a test edit, but a component that stops being planned must fail.
    catalogue_size = len([c for c in get_catalog() if not c.discontinued])
    accessory_count = len(
        [c for c in get_catalog() if c.category in ACCESSORY_CATEGORIES and not c.discontinued]
    )
    assert s["components"] + s["accessories"] == s["total_entities"] == catalogue_size
    assert s["accessories"] == accessory_count
    assert s["visuals_existing"] == 0 and s["visuals_missing"] == catalogue_size
    assert len(inv.select(limit=5)) == 5
    assert len(inv.select()) == catalogue_size

    visualizer, _ = make_visualizer(tmp_path)
    await visualizer.get_or_create(session, a_mouse(), allow_generation=True)
    inv = await batch.inventory(session, settings=settings, include_builds=False)
    s = inv.summary()
    assert s["visuals_existing"] == 1 and s["visuals_missing"] == catalogue_size - 1
    assert len(inv.select()) == catalogue_size - 1, (
        "missing-only never re-selects an existing visual"
    )


async def test_rekey_attaches_a_legacy_render_for_free(
    session: AsyncSession, tmp_path: Path
) -> None:
    parts = _core_parts()
    ready = ReadyBuild(
        slug="rekey-test",
        name="Rekey Test",
        category="gaming",
        tags=[],
        purpose="gaming",
        resolution="1440p",
        tier="mid",
        budget_min_pln=5000,
        budget_max_pln=9000,
        cpu_brand="amd",
        gpu_brand="nvidia",
        style="black",
        rgb=False,
        wifi=True,
        bluetooth=True,
        components={category.value: component.id for category, component in parts.items()},
        pricing_snapshot={},
        status=ReadyBuildStatus.ACTIVE,
    )
    session.add(ready)
    await session.flush()

    preset = default_preset(parts, Aesthetics("black"))
    legacy_file = tmp_path / "legacy.png"
    legacy_file.write_bytes(PNG)
    repo = VisualizationRepository(session)
    row = await repo.start(
        "legacy-old-fingerprint",
        identity_key="",
        entity_type="ready_build",
        entity_id=str(ready.id),
        components={category.value: component.id for category, component in parts.items()},
        preset_key=preset.key,
        provider="openai-images",
        model=MODEL,
        prompt_version="2",
        prompt_hash="x",
        prompt_text="legacy",
        references_used=False,
        ready_build_id=ready.id,
    )
    await repo.mark_ready(row, str(legacy_file), seconds=1.0)

    settings = get_settings()
    inv = await batch.inventory(session, settings=settings, include_components=False)
    assert [p.state for p in inv.plans] == [batch.STATE_MISSING]

    moved = await batch.rekey_legacy(session, inv)
    assert moved == 1
    inv = await batch.inventory(session, settings=settings, include_components=False)
    assert [p.state for p in inv.plans] == [batch.STATE_EXISTING]
    assert row.fingerprint == inv.plans[0].fingerprint, "no paid re-render needed"
