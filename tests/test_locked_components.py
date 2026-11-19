"""LOCKED / PREFERRED / FLEXIBLE components and smart replacement."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.components import ComponentCategory
from app.domain.enums import Aesthetics, CpuBrand, Purpose, Resolution
from app.domain.requirements import BuildRequirements, ComponentStatus
from app.services.catalog import get_catalog
from app.services.compatibility import validate_build
from app.services.recommendation import BuildService
from app.services.recommendation.replacement import resolve_conflict, suggest_replacements

C = ComponentCategory


@pytest.fixture(scope="module")
def service() -> BuildService:
    return BuildService()


def _requirements(**overrides) -> BuildRequirements:  # type: ignore[no-untyped-def]
    base = dict(budget_pln=9000, purpose=Purpose.GAMING, resolution=Resolution.QHD)
    base.update(overrides)
    return BuildRequirements(**base)


def _parts(**ids: str):  # type: ignore[no-untyped-def]
    catalog = get_catalog()
    return {C(cat): catalog.require(cid) for cat, cid in ids.items()}


GOOD = dict(
    cpu="amd-ryzen-7-7800x3d",
    motherboard="asus-tuf-b650-plus-wifi",
    ram="kingston-fury-beast-32-ddr5-6000",
    ssd="samsung-990-evo-1tb",
    gpu="amd-rx-9070",
    cooler="thermalright-peerless-assassin-120-se",
    case="lianli-lancool-216-black",
    psu="corsair-rm750e",
)


# --- statuses -----------------------------------------------------------------


def test_status_defaults_to_flexible() -> None:
    req = _requirements(locked={"case": "fractal-pop-air-black"}, preferred={"gpu": "amd-rx-9070"})
    assert req.status_of(C.CASE) is ComponentStatus.LOCKED
    assert req.status_of(C.GPU) is ComponentStatus.PREFERRED
    assert req.status_of(C.RAM) is ComponentStatus.FLEXIBLE
    assert req.locked_categories == {C.CASE}


def test_unknown_category_in_locked_is_rejected() -> None:
    with pytest.raises(ValueError):
        _requirements(locked={"toaster": "x"})


# --- generator honours locks --------------------------------------------------


def test_locked_case_is_kept_in_every_option(service: BuildService) -> None:
    """The board and cooler are picked to fit the fixed (mATX-only) case."""
    req = _requirements(locked={"case": "montech-air-100-argb"})
    options = service.build_options(req)
    assert options, "no build around the locked case"
    for option in options:
        assert option.parts[C.CASE].id == "montech-air-100-argb"
        board = option.parts[C.MOTHERBOARD]
        assert board.spec.form_factor.value in {"mATX", "ITX"}  # type: ignore[union-attr]
        assert option.report.compatible


def test_locked_gpu_gets_a_case_and_psu_that_fit(service: BuildService) -> None:
    req = _requirements(budget_pln=16000, locked={"gpu": "nvidia-rtx-5080"})
    options = service.build_options(req)
    assert options, "no build around the locked GPU"
    for option in options:
        assert option.parts[C.GPU].id == "nvidia-rtx-5080"
        psu = option.parts[C.PSU].spec
        assert psu.wattage >= 850  # type: ignore[union-attr]
        assert option.parts[C.CASE].spec.max_gpu_length_mm >= 310  # type: ignore[union-attr]


def test_locked_parts_that_cannot_coexist_yield_nothing(service: BuildService) -> None:
    """The engine never quietly swaps a locked part to make a build work."""
    req = _requirements(
        budget_pln=16000,
        locked={"gpu": "nvidia-rtx-5090", "psu": "bequiet-system-power-10-550"},
    )
    assert service.build_options(req) == []


def test_locked_overrides_the_brand_filter(service: BuildService) -> None:
    req = _requirements(cpu_brand=CpuBrand.INTEL, locked={"cpu": "amd-ryzen-5-7600"})
    options = service.build_options(req)
    assert options and all(o.parts[C.CPU].id == "amd-ryzen-5-7600" for o in options)


def test_preferred_part_is_used_when_it_fits(service: BuildService) -> None:
    req = _requirements(budget_pln=12000, preferred={"case": "fractal-north-white"})
    options = service.build_options(req)
    assert options
    assert any(o.parts[C.CASE].id == "fractal-north-white" for o in options)


def test_preferred_part_is_dropped_when_it_cannot_fit(service: BuildService) -> None:
    """A preferred part the budget cannot carry must not block generation."""
    req = _requirements(budget_pln=5000, preferred={"gpu": "nvidia-rtx-5090"})
    options = service.build_options(req)
    assert options, "preference must not block generation"
    assert all(o.parts[C.GPU].id != "nvidia-rtx-5090" for o in options)


# --- replacement ----------------------------------------------------------------


def test_replacement_keeps_the_locked_case_and_swaps_the_board(service: BuildService) -> None:
    """An ATX board in a locked mATX case: the board goes, the case stays."""
    parts = _parts(**{**GOOD, "case": "montech-air-100-argb"})
    report = validate_build(parts)
    assert not report.compatible

    req = _requirements(budget_pln=12000, locked={"case": "montech-air-100-argb"})
    resolution = resolve_conflict(parts, report, req, service.catalog, service.price_book())
    assert resolution is not None
    assert resolution.kept == [C.CASE]
    assert resolution.category is C.MOTHERBOARD
    assert resolution.status is ComponentStatus.FLEXIBLE
    assert resolution.resolved, "no replacement found"
    for option in resolution.replacements:
        assert option.compatible
        assert option.component.category is C.MOTHERBOARD
        assert option.component.spec.form_factor.value in {"mATX", "ITX"}  # type: ignore[union-attr]


def test_replacements_are_compatible_with_the_whole_build(service: BuildService) -> None:
    parts = _parts(**GOOD)
    req = _requirements(budget_pln=12000)
    options = suggest_replacements(parts, C.GPU, req, service.catalog, service.price_book())
    assert options
    for option in options:
        assert option.compatible
        assert option.performance_delta >= -0.15
        trial = dict(parts)
        trial[C.GPU] = option.component
        assert validate_build(trial).compatible


def test_flexible_parts_are_changed_before_preferred_ones(service: BuildService) -> None:
    parts = _parts(**{**GOOD, "gpu": "nvidia-rtx-5090"})  # RM750e is far too weak
    report = validate_build(parts)
    assert not report.compatible
    # GPU preferred, PSU flexible: the PSU is what gets replaced.
    req = _requirements(budget_pln=20000, preferred={"gpu": "nvidia-rtx-5090"})
    resolution = resolve_conflict(parts, report, req, service.catalog, service.price_book())
    assert resolution is not None and resolution.category is C.PSU
    assert resolution.status is ComponentStatus.FLEXIBLE
    assert resolution.resolved
    assert all(r.component.spec.wattage >= 1000 for r in resolution.replacements)  # type: ignore[union-attr]


def test_all_involved_parts_locked_means_no_resolution(service: BuildService) -> None:
    parts = _parts(**{**GOOD, "gpu": "nvidia-rtx-5090"})
    report = validate_build(parts)
    req = _requirements(
        budget_pln=20000, locked={"gpu": "nvidia-rtx-5090", "psu": "corsair-rm750e"}
    )
    resolution = resolve_conflict(parts, report, req, service.catalog, service.price_book())
    assert resolution is not None
    assert not resolution.resolved
    assert set(resolution.kept) >= {C.GPU, C.PSU}


def test_no_conflict_means_no_resolution(service: BuildService) -> None:
    parts = _parts(**GOOD)
    report = validate_build(parts)
    assert (
        resolve_conflict(parts, report, _requirements(), service.catalog, service.price_book())
        is None
    )


def test_replacements_respect_the_budget(service: BuildService) -> None:
    parts = _parts(**GOOD)
    prices = service.price_book()
    others = sum(prices[p.id] for c, p in parts.items() if c is not C.GPU)
    cap = others + prices["amd-rx-9070"] + Decimal(100)
    options = suggest_replacements(
        parts,
        C.GPU,
        _requirements(aesthetics=Aesthetics.BLACK),
        service.catalog,
        prices,
        acquisition_budget_pln=cap,
        limit=10,
    )
    for option in options:
        assert others + prices[option.component.id] <= cap
