"""Catalogue integrity and the compatibility rule set."""

from __future__ import annotations

import pytest

from app.domain.components import (
    PC_CATEGORIES,
    REQUIRED_CATEGORIES,
    CaseSpec,
    Component,
    ComponentCategory,
    CoolerSpec,
    CpuSpec,
    GpuSpec,
    MotherboardSpec,
    Socket,
    parse_component,
)
from app.services.catalog import Catalog, CatalogError, get_catalog, load_components
from app.services.compatibility import Severity, estimate_power_draw_w, recommended_psu_w, validate


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return get_catalog()


# --- catalogue ----------------------------------------------------------------


def test_seed_data_loads(catalog: Catalog) -> None:
    assert len(catalog) >= 60


def test_every_pc_category_has_options(catalog: Catalog) -> None:
    for category in PC_CATEGORIES:
        assert catalog.by_category(category), f"no parts in {category}"


def test_component_ids_are_unique() -> None:
    components = load_components()
    ids = [component.id for component in components]
    assert len(ids) == len(set(ids))


def test_duplicate_ids_are_rejected() -> None:
    payload = {
        "id": "dup",
        "category": "ssd",
        "brand": "X",
        "model": "Y",
        "spec": {
            "capacity_gb": 500,
            "interface": "M.2 NVMe",
            "pcie_generation": 4,
            "read_mb_s": 1000,
            "write_mb_s": 1000,
        },
    }
    component = parse_component(payload)
    with pytest.raises(CatalogError):
        Catalog([component, component])


def test_specs_are_typed_per_category(catalog: Catalog) -> None:
    assert isinstance(catalog.by_category(ComponentCategory.CPU)[0].spec, CpuSpec)
    assert isinstance(catalog.by_category(ComponentCategory.GPU)[0].spec, GpuSpec)
    assert isinstance(catalog.by_category(ComponentCategory.CASE)[0].spec, CaseSpec)


def test_unknown_spec_field_is_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        parse_component(
            {
                "id": "bad-cpu",
                "category": "cpu",
                "brand": "X",
                "model": "Y",
                "spec": {
                    "socket": "AM5",
                    "cores": 6,
                    "threads": 12,
                    "tdp_w": 65,
                    "max_power_w": 88,
                    "memory_types": ["DDR5"],
                    "max_memory_speed_mhz": 6000,
                    "performance_index": 400,
                    "gaming_index": 400,
                    "made_up_field": 1,
                },
            }
        )


def test_every_catalogue_cpu_has_a_compatible_motherboard(catalog: Catalog) -> None:
    boards = catalog.by_category(ComponentCategory.MOTHERBOARD)
    for cpu in catalog.by_category(ComponentCategory.CPU):
        spec = cpu.spec
        assert isinstance(spec, CpuSpec)
        matching = [
            board
            for board in boards
            if isinstance(board.spec, MotherboardSpec)
            and board.spec.socket is spec.socket
            and board.spec.memory_type in spec.memory_types
        ]
        assert matching, f"{cpu.name} has no motherboard in the catalogue"


def test_every_catalogue_cpu_has_a_cooler(catalog: Catalog) -> None:
    coolers = catalog.by_category(ComponentCategory.COOLER)
    for cpu in catalog.by_category(ComponentCategory.CPU):
        spec = cpu.spec
        assert isinstance(spec, CpuSpec)
        fit = [
            cooler
            for cooler in coolers
            if isinstance(cooler.spec, CoolerSpec)
            and spec.socket in cooler.spec.sockets
            and cooler.spec.tdp_rating_w >= spec.max_power_w
        ]
        assert fit or spec.includes_cooler, f"{cpu.name} cannot be cooled"


# --- compatibility ------------------------------------------------------------


def _parts(catalog: Catalog, **ids: str) -> dict[ComponentCategory, Component]:
    return {ComponentCategory(category): catalog.require(cid) for category, cid in ids.items()}


@pytest.fixture
def good_build(catalog: Catalog) -> dict[ComponentCategory, Component]:
    return _parts(
        catalog,
        cpu="amd-ryzen-7-7800x3d",
        motherboard="asus-tuf-b650-plus-wifi",
        ram="kingston-fury-beast-32-ddr5-6000",
        ssd="samsung-990-evo-1tb",
        gpu="amd-rx-9070",
        cooler="thermalright-peerless-assassin-120-se",
        case="lianli-lancool-216-black",
        psu="corsair-rm750e",
    )


def test_a_sane_build_passes(good_build) -> None:  # type: ignore[no-untyped-def]
    report = validate(good_build)
    assert report.ok, [issue.detail for issue in report.errors]


def test_socket_mismatch_is_an_error(catalog: Catalog, good_build) -> None:  # type: ignore[no-untyped-def]
    good_build[ComponentCategory.MOTHERBOARD] = catalog.require("msi-b550-gaming-plus")
    report = validate(good_build)
    assert not report.ok
    assert any(issue.code == "socket_mismatch" for issue in report.errors)


def test_memory_type_mismatch_is_an_error(catalog: Catalog, good_build) -> None:  # type: ignore[no-untyped-def]
    good_build[ComponentCategory.RAM] = catalog.require("kingston-fury-beast-32-ddr4-3600")
    report = validate(good_build)
    assert not report.ok
    assert any(issue.code == "memory_type_mismatch" for issue in report.errors)


def test_no_catalogue_gpu_is_too_long_for_any_case(catalog: Catalog) -> None:
    """Sanity check on the seed data itself."""
    shortest_case = min(
        case.spec.max_gpu_length_mm
        for case in catalog.by_category(ComponentCategory.CASE)
        if isinstance(case.spec, CaseSpec)
    )
    longest_gpu = max(
        gpu.spec.length_mm
        for gpu in catalog.by_category(ComponentCategory.GPU)
        if isinstance(gpu.spec, GpuSpec)
    )
    assert longest_gpu <= shortest_case


def test_gpu_longer_than_the_case_is_an_error(good_build) -> None:  # type: ignore[no-untyped-def]
    """The rule itself, exercised with a deliberately tiny case."""
    good_build[ComponentCategory.CASE] = parse_component(
        {
            "id": "tiny-case",
            "category": "case",
            "brand": "Test",
            "model": "Tiny",
            "spec": {
                "form_factors": ["ATX"],
                "max_gpu_length_mm": 200,
                "max_cooler_height_mm": 200,
                "max_psu_length_mm": 200,
                "radiator_support_mm": [240, 360],
            },
        }
    )
    report = validate(good_build)
    assert any(issue.code == "gpu_too_long" for issue in report.errors)


def test_board_form_factor_must_fit_the_case(catalog: Catalog, good_build) -> None:  # type: ignore[no-untyped-def]
    good_build[ComponentCategory.CASE] = catalog.require("montech-air-100-argb")
    report = validate(good_build)
    assert any(issue.code == "board_form_factor" for issue in report.errors)


def test_cooler_below_the_cpu_draw_is_an_error(catalog: Catalog, good_build) -> None:  # type: ignore[no-untyped-def]
    # A 230 W part under a 165 W cooler.
    good_build[ComponentCategory.CPU] = catalog.require("amd-ryzen-9-9950x")
    good_build[ComponentCategory.COOLER] = catalog.require("deepcool-ak400")
    report = validate(good_build)
    assert any(issue.code == "cooler_capacity" for issue in report.errors)


def test_cooler_for_the_wrong_socket_is_an_error(good_build) -> None:  # type: ignore[no-untyped-def]
    good_build[ComponentCategory.COOLER] = parse_component(
        {
            "id": "intel-only-cooler",
            "category": "cooler",
            "brand": "Test",
            "model": "Intel Only",
            "spec": {
                "cooler_type": "air",
                "sockets": ["LGA1700"],
                "tdp_rating_w": 250,
                "height_mm": 150,
                "ram_clearance_mm": 50,
            },
        }
    )
    report = validate(good_build)
    assert any(issue.code == "cooler_socket" for issue in report.errors)


def test_underpowered_psu_is_an_error(catalog: Catalog, good_build) -> None:  # type: ignore[no-untyped-def]
    good_build[ComponentCategory.PSU] = catalog.require("bequiet-system-power-10-550")
    good_build[ComponentCategory.GPU] = catalog.require("nvidia-rtx-5090")
    report = validate(good_build)
    assert any(issue.code == "psu_underpowered" for issue in report.errors)


def test_missing_required_part_is_an_error(good_build) -> None:  # type: ignore[no-untyped-def]
    del good_build[ComponentCategory.PSU]
    report = validate(good_build)
    assert any(issue.code == "missing_part" for issue in report.errors)


def test_cpu_without_igpu_and_without_gpu_is_an_error(catalog: Catalog, good_build) -> None:  # type: ignore[no-untyped-def]
    good_build[ComponentCategory.CPU] = catalog.require("intel-core-i5-12400f")
    good_build[ComponentCategory.MOTHERBOARD] = catalog.require("asus-prime-b760-plus")
    del good_build[ComponentCategory.GPU]
    report = validate(good_build)
    assert any(issue.code == "no_display_output" for issue in report.errors)


def test_slow_memory_is_only_a_warning(catalog: Catalog, good_build) -> None:  # type: ignore[no-untyped-def]
    good_build[ComponentCategory.RAM] = catalog.require("kingston-fury-renegade-128-ddr5-5600")
    report = validate(good_build)
    assert report.ok
    assert all(issue.severity is Severity.WARNING for issue in report.issues)


def test_power_estimate_includes_cpu_gpu_and_overhead(good_build) -> None:  # type: ignore[no-untyped-def]
    draw = estimate_power_draw_w(good_build)
    # 7800X3D 162 W + RX 9070 220 W + base overhead
    assert 450 < draw < 520
    assert recommended_psu_w(good_build) >= draw
    assert recommended_psu_w(good_build) % 50 == 0


def test_required_categories_are_a_subset_of_the_card_order() -> None:
    assert set(PC_CATEGORIES) >= REQUIRED_CATEGORIES


def test_legacy_socket_constant_matches_the_catalogue(catalog: Catalog) -> None:
    from app.services.recommendation import generator

    sockets = {
        component.spec.socket
        for component in catalog.by_category(ComponentCategory.CPU)
        if isinstance(component.spec, CpuSpec)
    }
    assert sockets >= generator.LEGACY_SOCKETS
    assert Socket.AM5 not in generator.LEGACY_SOCKETS
