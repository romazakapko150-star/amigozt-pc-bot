"""The pre-order compatibility gate and its admin rendering."""

from __future__ import annotations

from app.bot.views.compatibility import render_compatibility, render_compatibility_short
from app.services.compatibility import LABEL_BUILDABLE, LABEL_NOT_BUILDABLE
from app.services.compatibility.gate import check_components

GOOD = {
    "cpu": "amd-ryzen-7-7800x3d",
    "motherboard": "asus-tuf-b650-plus-wifi",
    "ram": "kingston-fury-beast-32-ddr5-6000",
    "ssd": "samsung-990-evo-1tb",
    "gpu": "amd-rx-9070",
    "cooler": "thermalright-peerless-assassin-120-se",
    "case": "lianli-lancool-216-black",
    "psu": "corsair-rm750e",
}


def test_gate_passes_a_good_build() -> None:
    result = check_components(GOOD)
    assert result.compatible
    snapshot = result.snapshot()
    assert snapshot["compatible"] is True
    assert snapshot["final"] == LABEL_BUILDABLE
    assert snapshot["power"]["recommended_w"] >= snapshot["power"]["total_w"]
    assert snapshot["components"]["gpu"] == "amd-rx-9070"


def test_gate_blocks_a_board_that_does_not_fit_the_case() -> None:
    result = check_components({**GOOD, "case": "montech-air-100-argb"})  # mATX/ITX only
    assert not result.compatible
    assert "board_form_factor" in result.customer_reason_codes()
    assert result.snapshot()["final"] == LABEL_NOT_BUILDABLE


def test_gate_blocks_a_psu_that_cannot_feed_the_gpu() -> None:
    result = check_components({**GOOD, "gpu": "nvidia-rtx-5090"})
    assert not result.compatible
    codes = result.customer_reason_codes()
    assert "psu_underpowered" in codes or "psu_gpu_minimum" in codes


def test_gate_treats_an_unknown_component_id_as_blocking() -> None:
    result = check_components({**GOOD, "gpu": "no-such-gpu"})
    assert not result.compatible
    assert result.unknown_ids == ["no-such-gpu"]
    assert "generic" in result.customer_reason_codes()
    assert result.snapshot()["unknown_component_ids"] == ["no-such-gpu"]


def test_gate_blocks_an_incomplete_build() -> None:
    result = check_components({k: v for k, v in GOOD.items() if k != "psu"})
    assert not result.compatible
    assert "missing_part" in result.customer_reason_codes()


def test_admin_table_lists_pairs_and_the_verdict() -> None:
    snapshot = check_components(GOOD).snapshot()
    lines = render_compatibility(snapshot)
    text = "\n".join(lines)
    assert "CPU → Motherboard" in text
    assert "GPU → Case" in text
    assert "PSU Wattage" in text
    assert "FINAL:" in text and LABEL_BUILDABLE in text
    assert "Потребление" in text
    assert "Не подтверждено производителем" in text  # reference-model GPU length


def test_admin_table_shows_failures_first() -> None:
    snapshot = check_components({**GOOD, "case": "montech-air-100-argb"}).snapshot()
    text = "\n".join(render_compatibility(snapshot))
    assert LABEL_NOT_BUILDABLE in text
    assert "❌ Ошибки" in text
    assert "ATX board does not fit" in text


def test_short_line_for_notifications() -> None:
    good = render_compatibility_short(check_components(GOOD).snapshot())
    assert LABEL_BUILDABLE in good
    bad = render_compatibility_short(
        check_components({**GOOD, "case": "montech-air-100-argb"}).snapshot()
    )
    assert LABEL_NOT_BUILDABLE in bad and "does not fit" in bad


def test_rendering_an_empty_snapshot_is_safe() -> None:
    assert "не сохранён" in "\n".join(render_compatibility({}))
    assert "не сохранён" in render_compatibility_short({})
