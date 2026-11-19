"""Build images, comparison and the accessory catalogue."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.bot.handlers import accessories as acc_handler
from app.bot.handlers import compare as cmp_handler
from app.bot.views.accessories import ACCESSORY_ORDER, render_item, render_list
from app.bot.views.compare import COMPARABLE, render_comparison, spec_rows
from app.domain.components import (
    ACCESSORY_CATEGORIES,
    Component,
    ComponentCategory,
    MonitorSpec,
    PeripheralSpec,
)
from app.i18n import SUPPORTED_LANGUAGES, t
from app.services.catalog import get_catalog
from app.services.media import cache_key, image_integration_status, render_build_image

TELEGRAM_CALLBACK_LIMIT = 64
TELEGRAM_CAPTION_LIMIT = 1024


@pytest.fixture(scope="module")
def catalog():  # type: ignore[no-untyped-def]
    return get_catalog()


@pytest.fixture(scope="module")
def sample_parts(catalog):  # type: ignore[no-untyped-def]
    return {
        ComponentCategory.CPU: catalog.require("amd-ryzen-7-7800x3d"),
        ComponentCategory.GPU: catalog.require("amd-rx-9070"),
        ComponentCategory.MOTHERBOARD: catalog.require("asus-tuf-b650-plus-wifi"),
        ComponentCategory.RAM: catalog.require("kingston-fury-beast-32-ddr5-6000"),
        ComponentCategory.SSD: catalog.require("samsung-990-evo-1tb"),
        ComponentCategory.PSU: catalog.require("corsair-rm750e"),
        ComponentCategory.CASE: catalog.require("lianli-lancool-216-black"),
        ComponentCategory.COOLER: catalog.require("thermalright-peerless-assassin-120-se"),
    }


# --- build images -------------------------------------------------------------


def test_image_is_rendered(tmp_path: Path, sample_parts) -> None:  # type: ignore[no-untyped-def]
    path = render_build_image("Test Build", sample_parts, Decimal(7999), output_dir=tmp_path)
    assert path.exists()
    assert path.stat().st_size > 5000


def test_identical_input_reuses_the_file(tmp_path: Path, sample_parts) -> None:  # type: ignore[no-untyped-def]
    first = render_build_image("Test", sample_parts, Decimal(1000), output_dir=tmp_path)
    mtime = first.stat().st_mtime_ns
    second = render_build_image("Test", sample_parts, Decimal(1000), output_dir=tmp_path)
    assert first == second
    assert second.stat().st_mtime_ns == mtime


def test_different_price_produces_a_different_file(tmp_path: Path, sample_parts) -> None:  # type: ignore[no-untyped-def]
    a = render_build_image("Test", sample_parts, Decimal(1000), output_dir=tmp_path)
    b = render_build_image("Test", sample_parts, Decimal(2000), output_dir=tmp_path)
    assert a != b


def test_cache_key_is_stable_and_order_independent(sample_parts) -> None:  # type: ignore[no-untyped-def]
    shuffled = dict(reversed(list(sample_parts.items())))
    assert cache_key("X", sample_parts, Decimal(1)) == cache_key("X", shuffled, Decimal(1))


def test_image_survives_a_missing_price(tmp_path: Path, sample_parts) -> None:  # type: ignore[no-untyped-def]
    assert render_build_image("No price", sample_parts, None, output_dir=tmp_path).exists()


def test_image_handles_a_very_long_name(tmp_path: Path, sample_parts) -> None:  # type: ignore[no-untyped-def]
    path = render_build_image("A" * 300, sample_parts, Decimal(5000), output_dir=tmp_path)
    assert path.exists()


def test_no_image_source_is_claimed_to_be_connected() -> None:
    for entry in image_integration_status():
        assert entry["connected"] is False
        assert entry["route"]


# --- comparison ---------------------------------------------------------------


@pytest.mark.parametrize("category", COMPARABLE)
def test_every_comparable_category_produces_rows(catalog, category) -> None:  # type: ignore[no-untyped-def]
    parts = catalog.by_category(category)
    assert parts
    assert spec_rows(parts[0])


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_comparison_renders_in_every_language(catalog, lang: str) -> None:  # type: ignore[no-untyped-def]
    text = render_comparison(
        catalog.require("amd-ryzen-7-7800x3d"),
        catalog.require("intel-core-i5-14600kf"),
        lang,
        {"amd-ryzen-7-7800x3d": Decimal(1750), "intel-core-i5-14600kf": Decimal(1150)},
    )
    assert "7800X3D" in text and "14600KF" in text
    assert "cmp.spec" not in text  # no untranslated keys leaked
    assert len(text) <= 4096


def test_comparison_marks_indexes_as_internal(catalog) -> None:  # type: ignore[no-untyped-def]
    """The performance index must never read as a benchmark result."""
    text = render_comparison(
        catalog.require("amd-rx-9070"), catalog.require("nvidia-rtx-5070"), "ru", {}
    )
    assert "не результат бенчмарка" in text


def test_comparison_callback_data_fits(catalog) -> None:  # type: ignore[no-untyped-def]
    for category in COMPARABLE:
        for markup in (
            cmp_handler.options_keyboard(category, "", "ru"),
            cmp_handler.options_keyboard(category, "0", "ru"),
        ):
            for row in markup.inline_keyboard:
                for button in row:
                    assert len(button.callback_data.encode()) <= TELEGRAM_CALLBACK_LIMIT


def test_comparison_excludes_the_already_picked_part(catalog) -> None:  # type: ignore[no-untyped-def]
    first_pass = cmp_handler.options_keyboard(ComponentCategory.GPU, "", "ru")
    second_pass = cmp_handler.options_keyboard(ComponentCategory.GPU, "0", "ru")
    assert _count(second_pass) == _count(first_pass) - 1


def test_option_positions_are_stable() -> None:
    """Callback payloads reference positions, so the order must not drift."""
    first = [c.id for c in cmp_handler._options(ComponentCategory.CPU)]
    second = [c.id for c in cmp_handler._options(ComponentCategory.CPU)]
    assert first == second


def _count(markup) -> int:  # type: ignore[no-untyped-def]
    # The last row is navigation.
    return sum(len(row) for row in markup.inline_keyboard[:-1])


# --- accessories --------------------------------------------------------------


def test_accessory_categories_have_stock(catalog) -> None:  # type: ignore[no-untyped-def]
    stocked = [c for c in ACCESSORY_ORDER if catalog.by_category(c)]
    assert len(stocked) >= 8


def test_accessory_order_only_lists_accessories() -> None:
    assert set(ACCESSORY_ORDER) <= ACCESSORY_CATEGORIES


@pytest.mark.parametrize("category", ACCESSORY_ORDER)
def test_every_accessory_has_a_label(category: ComponentCategory) -> None:
    for lang in SUPPORTED_LANGUAGES:
        label = t(lang, f"part.{category.value}")
        assert not label.startswith("part.")


@pytest.mark.parametrize("category", ACCESSORY_ORDER)
def test_every_accessory_is_priced(catalog, category: ComponentCategory) -> None:  # type: ignore[no-untyped-def]
    prices = acc_handler._prices()
    for component in catalog.by_category(category):
        assert component.id in prices, component.id


def test_monitor_specs_are_typed(catalog) -> None:  # type: ignore[no-untyped-def]
    monitors = catalog.by_category(ComponentCategory.MONITOR)
    assert monitors
    for monitor in monitors:
        assert isinstance(monitor.spec, MonitorSpec)
        assert monitor.spec.refresh_hz >= 60


def test_peripheral_specs_are_typed(catalog) -> None:  # type: ignore[no-untyped-def]
    for category in (ComponentCategory.MOUSE, ComponentCategory.KEYBOARD):
        for component in catalog.by_category(category):
            assert isinstance(component.spec, PeripheralSpec)
            assert component.spec.summary


def test_accessory_list_renders(catalog) -> None:  # type: ignore[no-untyped-def]
    monitors = catalog.by_category(ComponentCategory.MONITOR)
    text = render_list(ComponentCategory.MONITOR, monitors, acc_handler._prices(), "ru")
    assert "Монитор" in text
    assert "PLN" in text
    assert len(text) <= 4096


def test_monitor_card_shows_the_specs(catalog) -> None:  # type: ignore[no-untyped-def]
    monitor: Component = catalog.require("gigabyte-m27q")
    text = render_item(monitor, Decimal(1250), "ru")
    assert "2560x1440" in text
    assert "170 Hz" in text
    assert "1 250 PLN" in text
    assert "ориентировочная" in text


def test_peripheral_card_shows_highlights(catalog) -> None:  # type: ignore[no-untyped-def]
    mouse = catalog.require("logitech-g-pro-x-superlight-2")
    text = render_item(mouse, Decimal(620), "ru")
    # Weights and units read the same in every language, which is why the
    # catalogue states them that way rather than in one customer's language.
    assert "60 g" in text
    assert "620 PLN" in text
    # ...while what the product *is* comes through the locale.
    assert t("ru", "acc.kind.mouse") in text


def test_accessory_cards_fit_a_caption(catalog) -> None:  # type: ignore[no-untyped-def]
    for category in ACCESSORY_ORDER:
        for component in catalog.by_category(category):
            text = render_item(component, Decimal(500), "ru")
            assert len(text) <= TELEGRAM_CAPTION_LIMIT


def test_accessory_callback_data_fits() -> None:
    for markup in (
        acc_handler.categories_keyboard("ru"),
        acc_handler.list_keyboard(ComponentCategory.MONITOR, "ru"),
        acc_handler.item_keyboard(ComponentCategory.MONITOR, "ru"),
    ):
        for row in markup.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode()) <= TELEGRAM_CALLBACK_LIMIT


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_accessory_keyboard_labels_fit_a_phone(lang: str) -> None:
    for row in acc_handler.categories_keyboard(lang).inline_keyboard:
        if len(row) > 1:
            assert all(len(button.text) <= 18 for button in row), [b.text for b in row]
