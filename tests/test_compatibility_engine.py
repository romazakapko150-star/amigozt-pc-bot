"""Compatibility engine v2: physical, electrical, platform and I/O rules.

The ten cases the owner asked for come first, then the UNKNOWN policy,
the itemised power budget and the report contract.
"""

from __future__ import annotations

import pytest

from app.domain.components import (
    Component,
    ComponentCategory,
    parse_component,
)
from app.services.catalog import Catalog, get_catalog
from app.services.compatibility import (
    LABEL_BUILDABLE,
    LABEL_DATA_MISSING,
    LABEL_NOT_BUILDABLE,
    CheckStatus,
    CompatibilityReport,
    power_budget,
    validate,
    validate_build,
)
from app.services.compatibility.rules.common import radiator_fits, version_number
from app.services.compatibility.rules.electrical import gpu_power_path

C = ComponentCategory


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return get_catalog()


def _parts(catalog: Catalog, **ids: str) -> dict[ComponentCategory, Component]:
    return {ComponentCategory(category): catalog.require(cid) for category, cid in ids.items()}


@pytest.fixture
def build(catalog: Catalog) -> dict[ComponentCategory, Component]:
    """A known-good AM5 build on verified catalogue parts."""
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


def _case(**overrides) -> Component:  # type: ignore[no-untyped-def]
    spec = {
        "form_factors": ["ATX", "mATX", "ITX"],
        "max_gpu_length_mm": 400,
        "max_cooler_height_mm": 180,
        "max_psu_length_mm": 200,
        "radiator_support_mm": [240, 280, 360],
        "psu_form_factors": ["ATX"],
        "max_gpu_slots": 4,
        "radiator_positions": {"top": [240, 360], "front": [240, 280, 360]},
        "front_usb_c": False,
    }
    spec.update(overrides)
    return parse_component(
        {
            "id": "test-case",
            "category": "case",
            "brand": "Test",
            "model": "Case",
            "spec": spec,
            "spec_verified": True,
        }
    )


def _codes(report: CompatibilityReport, status: CheckStatus) -> set[str]:
    return {check.code for check in report.checks if check.status is status}


# --- the owner's ten cases ----------------------------------------------------


def test_case_1_atx_board_in_atx_case_passes(build) -> None:  # type: ignore[no-untyped-def]
    report = validate_build(build)
    assert report.compatible, report.as_dict()["errors"]
    assert "board_form_factor" in _codes(report, CheckStatus.PASS)
    assert report.final_label == LABEL_BUILDABLE


def test_case_2_atx_board_in_itx_only_case_fails(build) -> None:  # type: ignore[no-untyped-def]
    build[C.CASE] = _case(form_factors=["ITX"])
    report = validate_build(build)
    assert not report.compatible
    assert "board_form_factor" in _codes(report, CheckStatus.FAIL)
    assert report.final_label == LABEL_NOT_BUILDABLE


def test_case_3_gpu_too_long_fails(build) -> None:  # type: ignore[no-untyped-def]
    build[C.CASE] = _case(max_gpu_length_mm=250)
    report = validate_build(build)
    assert not report.compatible
    assert "gpu_too_long" in _codes(report, CheckStatus.FAIL)
    assert any("290 mm" in e for e in report.as_dict()["errors"])


def test_case_4_cooler_too_tall_fails(build) -> None:  # type: ignore[no-untyped-def]
    build[C.CASE] = _case(max_cooler_height_mm=150)
    report = validate_build(build)
    assert "cooler_too_tall" in _codes(report, CheckStatus.FAIL)
    assert not report.compatible


def test_case_5_psu_too_long_fails(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.PSU] = catalog.require("seasonic-vertex-px-1200")  # 160 mm
    build[C.CASE] = _case(max_psu_length_mm=150)
    report = validate_build(build)
    assert "psu_too_long" in _codes(report, CheckStatus.FAIL)
    assert not report.compatible


def test_case_6_ddr4_memory_on_ddr5_board_fails(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.RAM] = catalog.require("kingston-fury-beast-32-ddr4-3600")
    report = validate_build(build)
    assert "memory_type_mismatch" in _codes(report, CheckStatus.FAIL)
    assert not report.compatible


def test_case_7_am5_cpu_on_am5_board_passes(build) -> None:  # type: ignore[no-untyped-def]
    report = validate_build(build)
    assert "socket_mismatch" in _codes(report, CheckStatus.PASS)
    assert report.compatible


def test_case_7b_am5_cpu_on_lga1700_board_fails(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.MOTHERBOARD] = catalog.require("msi-b760-gaming-plus-wifi")
    report = validate_build(build)
    assert "socket_mismatch" in _codes(report, CheckStatus.FAIL)


def test_case_8_insufficient_psu_wattage_fails(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.GPU] = catalog.require("nvidia-rtx-5090")
    build[C.PSU] = catalog.require("corsair-rm750e")
    report = validate_build(build)
    failed = _codes(report, CheckStatus.FAIL)
    assert "psu_underpowered" in failed
    assert "psu_gpu_minimum" in failed
    assert not report.compatible


def test_case_9a_argb_part_without_header_fails(build) -> None:  # type: ignore[no-untyped-def]
    """ARGB fans, a board with no 5V header and no controller in the box."""
    build[C.CASE] = _case(rgb=True, argb_connector="5v_3pin")
    build[C.MOTHERBOARD] = parse_component(
        {
            "id": "no-argb-board",
            "category": "motherboard",
            "brand": "Test",
            "model": "Plain B650",
            "spec": {
                "socket": "AM5",
                "chipset": "B650",
                "form_factor": "ATX",
                "memory_type": "DDR5",
                "memory_slots": 4,
                "max_memory_gb": 128,
                "max_memory_speed_mhz": 6400,
                "m2_slots": 2,
                "pcie_version": 4,
                "argb_5v_headers": 0,
                "rgb_12v_headers": 0,
            },
        }
    )
    report = validate_build(build)
    assert "argb_header" in _codes(report, CheckStatus.FAIL)
    assert not report.compatible


def test_case_9b_argb_part_with_own_controller_passes(build) -> None:  # type: ignore[no-untyped-def]
    build[C.CASE] = _case(rgb=True, argb_connector="own_controller")
    report = validate_build(build)
    assert "argb_header" not in _codes(report, CheckStatus.FAIL)
    assert report.compatible


def test_case_9c_argb_header_count_unknown_is_a_warning_not_a_block(build) -> None:  # type: ignore[no-untyped-def]
    build[C.CASE] = _case(rgb=True, argb_connector="5v_3pin")
    build[C.MOTHERBOARD] = parse_component(
        {
            "id": "unknown-headers-board",
            "category": "motherboard",
            "brand": "Test",
            "model": "Unknown headers",
            "spec": {
                "socket": "AM5",
                "chipset": "B650",
                "form_factor": "ATX",
                "memory_type": "DDR5",
                "memory_slots": 4,
                "max_memory_gb": 128,
                "max_memory_speed_mhz": 6400,
                "m2_slots": 2,
                "pcie_version": 4,
            },
        }
    )
    report = validate_build(build)
    assert "argb_header" in _codes(report, CheckStatus.UNKNOWN)
    assert report.compatible  # non-critical unknown
    assert any("argb" in w.lower() for w in report.as_dict()["warnings"])


def test_case_10_m2_drive_that_does_not_fit_the_slots_fails(build) -> None:  # type: ignore[no-untyped-def]
    build[C.SSD] = parse_component(
        {
            "id": "long-m2",
            "category": "ssd",
            "brand": "Test",
            "model": "22110 NVMe",
            "spec": {
                "capacity_gb": 2000,
                "interface": "M.2 NVMe",
                "pcie_generation": 4,
                "read_mb_s": 7000,
                "write_mb_s": 6000,
                "form_factor": "M.2 22110",
            },
        }
    )
    build[C.MOTHERBOARD] = parse_component(
        {
            "id": "short-slots-board",
            "category": "motherboard",
            "brand": "Test",
            "model": "2280 only",
            "spec": {
                "socket": "AM5",
                "chipset": "B650",
                "form_factor": "ATX",
                "memory_type": "DDR5",
                "memory_slots": 4,
                "max_memory_gb": 128,
                "max_memory_speed_mhz": 6400,
                "m2_slots": 2,
                "pcie_version": 4,
                "m2_slot_sizes": ["2280", "2280"],
            },
        }
    )
    report = validate_build(build)
    assert "m2_size" in _codes(report, CheckStatus.FAIL)
    assert not report.compatible


def test_case_10b_board_without_m2_fails(build) -> None:  # type: ignore[no-untyped-def]
    build[C.MOTHERBOARD] = parse_component(
        {
            "id": "no-m2-board",
            "category": "motherboard",
            "brand": "Test",
            "model": "No M.2",
            "spec": {
                "socket": "AM5",
                "chipset": "A620",
                "form_factor": "mATX",
                "memory_type": "DDR5",
                "memory_slots": 2,
                "max_memory_gb": 64,
                "max_memory_speed_mhz": 5600,
                "m2_slots": 0,
                "pcie_version": 4,
            },
        }
    )
    report = validate_build(build)
    assert "no_m2_slot" in _codes(report, CheckStatus.FAIL)


# --- UNKNOWN policy -----------------------------------------------------------


def test_unknown_psu_form_factor_blocks_the_build(build) -> None:  # type: ignore[no-untyped-def]
    """A critical number missing is never treated as compatible."""
    build[C.CASE] = _case(psu_form_factors=None)
    report = validate_build(build)
    assert "psu_form_factor" in _codes(report, CheckStatus.UNKNOWN)
    assert not report.compatible
    assert report.final_label == LABEL_DATA_MISSING
    assert any("data missing" in e for e in report.as_dict()["errors"])


def test_sfx_psu_in_atx_only_case_fails(build) -> None:  # type: ignore[no-untyped-def]
    build[C.PSU] = parse_component(
        {
            "id": "sfx-psu",
            "category": "psu",
            "brand": "Test",
            "model": "SFX 750",
            "spec": {
                "wattage": 750,
                "efficiency": "80+ Gold",
                "modular": "full",
                "atx_version": "ATX 3.1",
                "pcie_8pin": 3,
                "pcie_12vhpwr": 1,
                "eps_8pin": 2,
                "length_mm": 125,
                "form_factor": "SFX",
            },
        }
    )
    report = validate_build(build)
    assert "psu_form_factor" in _codes(report, CheckStatus.FAIL)


def test_unknown_slot_clearance_is_reported_but_does_not_block(build) -> None:  # type: ignore[no-untyped-def]
    build[C.CASE] = _case(max_gpu_slots=None)
    report = validate_build(build)
    assert "gpu_slots" in _codes(report, CheckStatus.UNKNOWN)
    assert report.compatible
    assert report.data_missing


def test_front_radiator_without_published_clearance_is_never_assumed_safe(
    build, catalog: Catalog
) -> None:  # type: ignore[no-untyped-def]
    """GPU 340 mm, case 350 mm, 360 mm radiator only fits in the front."""
    build[C.COOLER] = catalog.require("arctic-liquid-freezer-iii-360")
    build[C.GPU] = parse_component(
        {
            "id": "long-gpu",
            "category": "gpu",
            "brand": "Test",
            "model": "340 mm card",
            "spec": {
                "vram_gb": 16,
                "tdp_w": 220,
                "recommended_psu_w": 650,
                "length_mm": 340,
                "slots": 2.5,
                "pcie_8pin": 2,
                "performance_index": 500,
            },
        }
    )
    build[C.CASE] = _case(
        max_gpu_length_mm=350,
        radiator_positions={"front": [360], "top": [240]},
        radiator_support_mm=[240, 360],
    )
    report = validate_build(build)
    assert "gpu_too_long" in _codes(report, CheckStatus.PASS)
    assert "gpu_front_radiator" in _codes(report, CheckStatus.UNKNOWN)
    assert not report.compatible


def test_front_radiator_with_published_clearance_decides(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.COOLER] = catalog.require("arctic-liquid-freezer-iii-360")
    build[C.CASE] = _case(
        max_gpu_length_mm=350,
        max_gpu_length_with_front_radiator_mm=280,
        radiator_positions={"front": [360], "top": [240]},
    )
    report = validate_build(build)  # RX 9070 is 290 mm
    assert "gpu_front_radiator" in _codes(report, CheckStatus.FAIL)


def test_top_mount_keeps_the_gpu_bay_free(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.COOLER] = catalog.require("arctic-liquid-freezer-iii-360")
    report = validate_build(build)  # Lancool 216 takes 360 on top
    assert "gpu_front_radiator" not in {c.code for c in report.checks}
    assert any("top" in c.detail for c in report.checks if c.code == "radiator_position")
    assert report.compatible


def test_radiator_smaller_than_the_listed_rail_fits() -> None:
    assert radiator_fits(240, [360]) == (True, True)
    assert radiator_fits(280, [360]) == (False, False)
    assert radiator_fits(240, [240]) == (True, False)
    assert radiator_fits(420, [280]) == (False, False)


# --- electrical ---------------------------------------------------------------


def test_12vhpwr_card_on_native_cable_passes(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.GPU] = catalog.require("nvidia-rtx-5070")
    report = validate_build(build)
    assert "gpu_power_connector" in _codes(report, CheckStatus.PASS)
    assert "gpu_power_adapter" not in {c.code for c in report.checks}


def test_12vhpwr_card_through_adapter_is_a_warning(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.GPU] = catalog.require("nvidia-rtx-5070")
    build[C.PSU] = parse_component(
        {
            "id": "old-psu",
            "category": "psu",
            "brand": "Test",
            "model": "Old 750",
            "spec": {
                "wattage": 750,
                "efficiency": "80+ Gold",
                "modular": "full",
                "atx_version": "ATX 2.52",
                "pcie_8pin": 4,
                "pcie_12vhpwr": 0,
                "length_mm": 150,
                "form_factor": "ATX",
            },
        }
    )
    report = validate_build(build)
    assert "gpu_power_adapter" in _codes(report, CheckStatus.WARN)
    assert report.compatible


def test_12vhpwr_card_with_too_few_8pin_fails(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.GPU] = catalog.require("nvidia-rtx-5090")  # 4x 8-pin via adapter
    build[C.PSU] = parse_component(
        {
            "id": "weak-psu",
            "category": "psu",
            "brand": "Test",
            "model": "Old 1200",
            "spec": {
                "wattage": 1200,
                "efficiency": "80+ Gold",
                "modular": "full",
                "atx_version": "ATX 2.52",
                "pcie_8pin": 2,
                "pcie_12vhpwr": 0,
                "length_mm": 150,
                "form_factor": "ATX",
            },
        }
    )
    report = validate_build(build)
    assert "gpu_power_connector" in _codes(report, CheckStatus.FAIL)


def test_gpu_power_path_helper(catalog: Catalog) -> None:
    gpu = catalog.require("nvidia-rtx-5090").spec
    assert gpu_power_path(gpu, catalog.require("seasonic-vertex-px-1200").spec) == "native"
    assert gpu_power_path(gpu, catalog.require("bequiet-system-power-10-550").spec) is None


def test_power_budget_is_itemised(build) -> None:  # type: ignore[no-untyped-def]
    budget = power_budget(build)
    names = [name for name, _ in budget.items]
    assert names[0] == "CPU" and names[1] == "GPU"
    assert any(name.startswith("Fans") for name in names)
    assert "USB devices" in names
    assert budget.total_w == sum(w for _, w in budget.items)
    assert budget.recommended_w % 50 == 0
    assert budget.recommended_w >= budget.total_w * 1.35


def test_fan_pack_that_does_not_fit_the_mounts_fails(build) -> None:  # type: ignore[no-untyped-def]
    build[C.CASE] = _case(
        fan_mounts={
            "front": {"count": 3, "sizes_mm": [120]},
            "rear": {"count": 1, "sizes_mm": [120]},
        },
        included_fans=2,
    )
    build[C.FANS] = parse_component(
        {
            "id": "fans-140",
            "category": "fans",
            "brand": "Test",
            "model": "3x140",
            "spec": {"size_mm": 140, "count": 3},
        }
    )
    report = validate_build(build)
    assert "fan_size" in _codes(report, CheckStatus.FAIL)

    build[C.FANS] = parse_component(
        {
            "id": "fans-120",
            "category": "fans",
            "brand": "Test",
            "model": "3x120",
            "spec": {"size_mm": 120, "count": 3},
        }
    )
    report = validate_build(build)
    assert "fan_mounts" in _codes(report, CheckStatus.FAIL)  # only 2 free mounts


# --- platform -----------------------------------------------------------------


def test_bios_update_is_a_customer_visible_warning(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.CPU] = catalog.require("amd-ryzen-7-9800x3d")
    report = validate_build(build)
    assert "bios_update" in _codes(report, CheckStatus.WARN)
    assert report.compatible


def test_four_ddr5_modules_carry_a_note(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.RAM] = catalog.require("kingston-fury-renegade-128-ddr5-5600")
    report = validate_build(build)
    assert "memory_four_modules" in _codes(report, CheckStatus.WARN)


def test_front_usb_c_without_header_is_a_warning(build) -> None:  # type: ignore[no-untyped-def]
    build[C.CASE] = _case(front_usb_c=True)
    build[C.MOTHERBOARD] = parse_component(
        {
            "id": "no-usbc-board",
            "category": "motherboard",
            "brand": "Test",
            "model": "No USB-C header",
            "spec": {
                "socket": "AM5",
                "chipset": "B650",
                "form_factor": "ATX",
                "memory_type": "DDR5",
                "memory_slots": 4,
                "max_memory_gb": 128,
                "max_memory_speed_mhz": 6400,
                "m2_slots": 2,
                "pcie_version": 4,
                "usb_c_header": False,
            },
        }
    )
    report = validate_build(build)
    assert "front_usb_c" in _codes(report, CheckStatus.WARN)
    assert report.compatible


# --- monitor ------------------------------------------------------------------


def _monitor(resolution: str, hz: int, inputs: dict) -> Component:
    return parse_component(
        {
            "id": "mon",
            "category": "monitor",
            "brand": "Test",
            "model": "Monitor",
            "spec": {
                "size_inch": 27,
                "resolution": resolution,
                "refresh_hz": hz,
                "panel": "IPS",
                "response_ms": 1,
                "inputs": inputs,
            },
        }
    )


def test_1440p_240hz_needs_displayport_1_4(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.GPU] = catalog.require("nvidia-rtx-5070")  # DP 2.1b / HDMI 2.1b
    build[C.MONITOR] = _monitor(
        "2560x1440",
        240,
        {"displayport": 1, "displayport_version": "1.4", "hdmi": 2, "hdmi_version": "2.0"},
    )
    report = validate_build(build)
    assert "monitor_output" in _codes(report, CheckStatus.PASS)
    assert any("DisplayPort 1.4" in c.detail for c in report.checks if c.code == "monitor_output")

    build[C.MONITOR] = _monitor("2560x1440", 240, {"hdmi": 1, "hdmi_version": "2.0"})
    report = validate_build(build)
    assert "monitor_output" in _codes(report, CheckStatus.WARN)


def test_monitor_check_is_unknown_without_output_data(build, catalog: Catalog) -> None:  # type: ignore[no-untyped-def]
    build[C.MONITOR] = _monitor("1920x1080", 165, {"displayport": 1, "displayport_version": "1.4"})
    report = validate_build(build)  # RX 9070 outputs not verified
    assert "monitor_output" in _codes(report, CheckStatus.UNKNOWN)
    assert report.compatible


def test_version_number_parsing() -> None:
    assert version_number("2.1b") == 2.1
    assert version_number("1.4a") == 1.4
    assert version_number(None) is None


# --- report contract ----------------------------------------------------------


def test_report_contract_has_the_agreed_shape(build) -> None:  # type: ignore[no-untyped-def]
    raw = validate_build(build).as_dict()
    assert set(raw) == {"compatible", "final", "errors", "warnings", "unknown", "checks"}
    assert raw["compatible"] is True
    assert raw["checks"] and {"code", "pair", "status", "detail", "critical", "verified"} <= set(
        raw["checks"][0]
    )
    restored = CompatibilityReport.from_dict(raw)
    assert restored.compatible and restored.final_label == raw["final"]


def test_admin_table_groups_checks_by_pair(build) -> None:  # type: ignore[no-untyped-def]
    report = validate_build(build)
    pairs = dict(report.by_pair())
    assert pairs["CPU → Motherboard"] is CheckStatus.PASS
    assert pairs["GPU → Case"] in {CheckStatus.PASS, CheckStatus.UNKNOWN}
    assert pairs["PSU Wattage"] is CheckStatus.PASS


def test_unverified_gpu_length_is_flagged_for_the_admin(build) -> None:  # type: ignore[no-untyped-def]
    """Reference-model GPUs carry typical lengths - the check passes but is marked."""
    report = validate_build(build)
    gpu_check = next(c for c in report.checks if c.code == "gpu_too_long")
    assert gpu_check.status is CheckStatus.PASS
    assert gpu_check.verified is False
    assert gpu_check in report.unverified


def test_legacy_api_still_works(build) -> None:  # type: ignore[no-untyped-def]
    report = validate(build)
    assert report.ok
    assert report.errors == []
    assert all(hasattr(issue, "severity") for issue in report.warnings)
