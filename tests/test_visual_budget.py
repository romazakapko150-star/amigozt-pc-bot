"""The spend ceiling: the one test that stands between a bug and a bill.

The batch renders one plan at a time and every render costs real money, so
the ceiling is checked *before* each call rather than after: a run may reach
the limit, never cross it. These tests use a fake generator - no API is
touched - but they pin exactly the arithmetic that decides when to stop.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.models import Base
from app.domain.components import ComponentCategory
from app.services.visuals import batch
from app.services.visuals.components import ComponentVisualizer
from tests.fake_telegram import FAKE_TOKEN

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


class CountingGenerator:
    """Stands in for the image API and counts what a run would have cost."""

    name = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.enabled = True
        self.last_error: str | None = None
        self.last_error_transient = False

    def generate_png(self, prompt: str, references=()) -> bytes | None:  # type: ignore[no-untyped-def]
        self.calls.append(prompt)
        return PNG


@pytest.fixture
def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        telegram_bot_token=FAKE_TOKEN,
        ai_image_cost_usd=Decimal("0.04"),
    )


@pytest.fixture
def session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory


async def _prepare(engine) -> None:  # type: ignore[no-untyped-def]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _component_plans(count: int) -> list[batch.EntityPlan]:
    """Real catalogue components, planned as missing visuals."""
    from app.services.catalog import get_catalog

    visualizer = ComponentVisualizer(CountingGenerator())
    plans: list[batch.EntityPlan] = []
    for component in list(get_catalog())[:count]:
        request = visualizer.request_for(component)
        plans.append(
            batch.EntityPlan(
                entity_type="component",
                entity_id=component.id,
                label=component.name,
                category=component.category.value,
                identity_key=request.identity_key,
                fingerprint=request.fingerprint,
                state=batch.STATE_MISSING,
                component=component,
            )
        )
    return plans


async def _run(
    session_factory,  # type: ignore[no-untyped-def]
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    plans: list[batch.EntityPlan],
    ceiling: Decimal | None,
) -> tuple[batch.BatchSummary, CountingGenerator]:
    engine, factory = session_factory
    await _prepare(engine)
    generator = CountingGenerator()

    def fake_from_settings(cfg=None):  # type: ignore[no-untyped-def]
        return ComponentVisualizer(generator, output_dir=tmp_path, max_attempts=1)

    monkeypatch.setattr(ComponentVisualizer, "from_settings", staticmethod(fake_from_settings))
    summary = await batch.generate(factory, plans, settings=settings, max_spend_usd=ceiling)
    await engine.dispose()
    return summary, generator


async def test_a_ceiling_stops_the_run_before_it_is_crossed(
    session_factory, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """$0.10 at $0.04 a call buys two renders, not three."""
    summary, generator = await _run(
        session_factory, settings, tmp_path, monkeypatch, _component_plans(5), Decimal("0.10")
    )
    assert len(generator.calls) == 2
    assert summary.api_calls == 2
    assert summary.cost_usd == Decimal("0.08")
    assert summary.cost_usd <= Decimal("0.10")
    assert summary.hit_the_ceiling
    assert summary.stopped_on_budget == 3


async def test_an_exact_ceiling_is_reached_and_not_exceeded(
    session_factory, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    summary, generator = await _run(
        session_factory, settings, tmp_path, monkeypatch, _component_plans(5), Decimal("0.12")
    )
    assert len(generator.calls) == 3
    assert summary.cost_usd == Decimal("0.12")
    assert not summary.hit_the_ceiling or summary.stopped_on_budget == 2


async def test_a_zero_ceiling_spends_nothing(
    session_factory, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    summary, generator = await _run(
        session_factory, settings, tmp_path, monkeypatch, _component_plans(3), Decimal(0)
    )
    assert generator.calls == []
    assert summary.cost_usd == Decimal(0)
    assert summary.stopped_on_budget == 3


async def test_without_a_ceiling_every_plan_is_rendered(
    session_factory, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    summary, generator = await _run(
        session_factory, settings, tmp_path, monkeypatch, _component_plans(4), None
    )
    assert len(generator.calls) == 4
    assert not summary.hit_the_ceiling


# --- the inventory's own arithmetic --------------------------------------------


def test_the_estimate_matches_what_a_run_would_actually_cost() -> None:
    """The number shown to the owner before they say yes must be the real one."""
    inventory = batch.Inventory(
        plans=[
            batch.EntityPlan(
                entity_type="component",
                entity_id=f"x{index}",
                label=f"x{index}",
                category=ComponentCategory.GPU.value,
                identity_key=f"i{index}",
                fingerprint=f"f{index}",
                state=batch.STATE_MISSING,
            )
            for index in range(10)
        ],
        cost_per_call_usd=Decimal("0.04"),
    )
    summary = inventory.summary()
    assert summary["estimated_calls"] == 10
    assert summary["estimated_cost_usd"] == Decimal("0.40")
    assert len(inventory.select()) == 10


def test_an_existing_visual_is_never_selected_and_never_costs_anything() -> None:
    plans = [
        batch.EntityPlan(
            entity_type="component",
            entity_id="a",
            label="a",
            category="gpu",
            identity_key="ia",
            fingerprint="fa",
            state=batch.STATE_EXISTING,
        ),
        batch.EntityPlan(
            entity_type="component",
            entity_id="b",
            label="b",
            category="gpu",
            identity_key="ib",
            fingerprint="fb",
            state=batch.STATE_MISSING,
        ),
    ]
    inventory = batch.Inventory(plans=plans, cost_per_call_usd=Decimal("0.04"))
    chosen = inventory.select()
    assert [p.entity_id for p in chosen] == ["b"]
    assert inventory.summary()["estimated_cost_usd"] == Decimal("0.04")
