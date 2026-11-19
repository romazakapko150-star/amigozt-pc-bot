"""The desk around the PC, and what it does to the visual identity.

Two contracts are pinned here:

* the configurator can add a monitor and peripherals, and what the customer
  picked reaches the card, the price and the parts map;
* the *same* configuration always maps to the same render, and any change
  the customer can see - a different GPU, a monitor added, a mouse swapped -
  maps to a different one. That is what keeps the image library honest and
  the API bill finite.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.bot.flows.configurator import StepId, next_step
from app.bot.keyboards.configurator import keyboard_for_step
from app.domain.components import ComponentCategory as C
from app.domain.components import MonitorSpec
from app.domain.enums import Aesthetics, Priority, Purpose, Resolution
from app.domain.requirements import BuildRequirements
from app.services.ai.visualizer import describe_build, fingerprint, identity
from app.services.catalog import get_catalog
from app.services.media.presets import PRESETS_BY_KEY, Accent, default_preset, with_accent
from app.services.recommendation.setup import (
    PERIPHERAL_CATEGORIES,
    SETUP_CATEGORIES,
    SetupSelection,
    monitor_options,
    resolve,
    suggest_for,
    with_setup,
)

MODEL = "gpt-image-1"
PRESET = PRESETS_BY_KEY["black-red-gaming"]


def _parts() -> dict:
    catalog = get_catalog()
    return {
        C.CPU: catalog.require("amd-ryzen-7-9700x"),
        C.COOLER: catalog.require("thermalright-assassin-x-120-refined-se"),
        C.MOTHERBOARD: catalog.require("msi-b650-gaming-plus-wifi"),
        C.RAM: catalog.require("kingston-fury-beast-32-ddr5-6000"),
        C.GPU: catalog.require("nvidia-rtx-5080"),
        C.SSD: catalog.require("wd-black-sn850x-2tb"),
        C.PSU: catalog.require("bequiet-pure-power-12m-850"),
        C.CASE: catalog.require("fractal-pop-air-black"),
    }


def _requirements(**kwargs: object) -> BuildRequirements:
    fields: dict[str, object] = {"budget_pln": 9000, "purpose": Purpose.GAMING}
    fields.update(kwargs)
    return BuildRequirements(**fields)  # type: ignore[arg-type]


# --- the flow ------------------------------------------------------------------


def test_the_desk_is_asked_about_after_the_machine() -> None:
    answers = {"purpose": "gaming"}
    assert next_step(StepId.GPU, answers) is StepId.MONITOR
    assert next_step(StepId.MONITOR, answers) is StepId.PERIPHERALS
    assert next_step(StepId.PERIPHERALS, answers) is StepId.SUMMARY


def test_the_monitor_step_offers_a_way_out() -> None:
    markup = keyboard_for_step(StepId.MONITOR, {"_monitor_options": []}, "en")
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert any("No monitor" in label for label in labels)


def test_the_peripheral_step_offers_every_category_and_done() -> None:
    markup = keyboard_for_step(StepId.PERIPHERALS, {}, "en")
    labels = [b.text for row in markup.inline_keyboard for b in row]
    for category in PERIPHERAL_CATEGORIES:
        assert any(category.value in label.lower() or label for label in labels)
    assert len(labels) >= len(PERIPHERAL_CATEGORIES)


# --- offering a monitor ---------------------------------------------------------


def test_a_monitor_is_never_offered_below_the_chosen_resolution() -> None:
    """Selling a 1080p panel to a 4K customer is the one thing we must not do."""
    for resolution in (Resolution.FHD, Resolution.QHD, Resolution.UHD):
        offered = monitor_options(_requirements(resolution=resolution))
        assert offered, f"nothing offered for {resolution}"
        for component in offered:
            spec = component.spec
            assert isinstance(spec, MonitorSpec)
            width, _, height = spec.resolution.partition("x")
            target = {"1080p": 1920 * 1080, "1440p": 2560 * 1440, "4k": 3840 * 2160}
            expected = {
                Resolution.FHD: target["1080p"],
                Resolution.QHD: target["1440p"],
                Resolution.UHD: target["4k"],
            }[resolution]
            assert int(width) * int(height) >= expected


def test_a_high_refresh_customer_is_offered_a_high_refresh_screen_first() -> None:
    offered = monitor_options(
        _requirements(priorities=[Priority.MAX_FPS], resolution=Resolution.FHD)
    )
    top = offered[0].spec
    assert isinstance(top, MonitorSpec)
    assert top.refresh_hz >= 240


def test_a_white_build_is_suggested_white_peripherals_when_they_exist() -> None:
    catalog = get_catalog()
    white = _requirements(aesthetics=Aesthetics.WHITE)
    for category in PERIPHERAL_CATEGORIES:
        if not catalog.by_category(category):
            continue
        suggestion = suggest_for(category, white)
        assert suggestion is not None
        assert suggestion.category is category


# --- what the customer picked ---------------------------------------------------


def test_a_stored_selection_resolves_back_to_components() -> None:
    selection = resolve({"monitor": "gigabyte-m27q", "mouse": "logitech-g502-hero"})
    assert selection.monitor is not None
    assert selection.monitor.id == "gigabyte-m27q"
    assert set(selection.items) <= set(SETUP_CATEGORIES)


def test_an_unknown_or_retired_id_is_dropped_not_guessed() -> None:
    selection = resolve({"monitor": "no-such-monitor", "keyboard": ""})
    assert not selection.items


def test_a_category_that_is_not_part_of_the_desk_is_ignored() -> None:
    selection = resolve({"gpu": "nvidia-rtx-5080"})
    assert not selection.items


def test_the_setup_prices_only_what_it_can_price() -> None:
    selection = resolve(
        {"monitor": "gigabyte-m27q", "mouse": "logitech-g502-hero"},
        prices={"gigabyte-m27q": Decimal(1500)},
    )
    assert selection.total_pln == Decimal(1500)
    assert selection.has_unpriced_item


def test_the_desk_never_overwrites_a_pc_part() -> None:
    parts = _parts()
    selection = resolve({"monitor": "gigabyte-m27q"})
    merged = with_setup(parts, selection)
    assert merged[C.GPU] is parts[C.GPU]
    assert merged[C.MONITOR].id == "gigabyte-m27q"
    assert len(merged) == len(parts) + 1


# --- identity: the money-saving contract ----------------------------------------


def test_the_same_configuration_always_maps_to_the_same_render() -> None:
    a = fingerprint(describe_build(_parts(), PRESET), model=MODEL)
    b = fingerprint(describe_build(_parts(), PRESET), model=MODEL)
    assert a == b


@pytest.mark.parametrize(
    ("category", "component_id"),
    [
        (C.GPU, "amd-rx-9070-xt"),
        (C.CASE, "lianli-lancool-216-black"),
        (C.COOLER, "bequiet-dark-rock-pro-5"),
        (C.RAM, "corsair-vengeance-rgb-32-ddr5-6000"),
    ],
)
def test_swapping_a_visible_part_changes_the_identity(category: C, component_id: str) -> None:
    parts = _parts()
    base = identity(describe_build(parts, PRESET))
    swapped = {**parts, category: get_catalog().require(component_id)}
    assert identity(describe_build(swapped, PRESET)) != base


def test_adding_a_monitor_then_a_mouse_then_a_headset_keeps_making_new_identities() -> None:
    """The customer's flow from the brief: PC -> +monitor -> +mouse -> +headset."""
    catalog = get_catalog()
    parts = _parts()
    seen = [identity(describe_build(parts, PRESET))]

    parts = {**parts, C.MONITOR: catalog.require("gigabyte-m27q")}
    seen.append(identity(describe_build(parts, PRESET)))

    parts = {**parts, C.MOUSE: catalog.by_category(C.MOUSE)[0]}
    seen.append(identity(describe_build(parts, PRESET)))

    parts = {**parts, C.HEADSET: catalog.by_category(C.HEADSET)[0]}
    seen.append(identity(describe_build(parts, PRESET)))

    assert len(set(seen)) == 4, "every addition must earn its own picture"
    # ...and going back to the same setup costs nothing.
    assert identity(describe_build(parts, PRESET)) == seen[-1]


def test_swapping_one_peripheral_for_another_changes_the_identity() -> None:
    catalog = get_catalog()
    mice = catalog.by_category(C.MOUSE)
    assert len(mice) >= 2
    parts = _parts()
    first = identity(describe_build({**parts, C.MOUSE: mice[0]}, PRESET))
    second = identity(describe_build({**parts, C.MOUSE: mice[1]}, PRESET))
    assert first != second


def test_the_colour_only_matters_when_something_is_actually_lit() -> None:
    """Money rule: an unlit machine must not pay for twelve colour variants."""
    parts = _parts()  # Pop Air black, no RGB parts in this list
    red = identity(describe_build(parts, PRESET))
    blue = identity(describe_build(parts, with_accent(PRESET, Accent.BLUE)))
    assert red == blue

    lit = {**parts, C.RAM: get_catalog().require("corsair-vengeance-rgb-32-ddr5-6000")}
    assert identity(describe_build(lit, PRESET)) != identity(
        describe_build(lit, with_accent(PRESET, Accent.BLUE))
    )


def test_a_setup_selection_reaches_the_visual_identity() -> None:
    """End to end: what the configurator stored is what gets rendered."""
    parts = _parts()
    without = identity(describe_build(parts, default_preset(parts)))
    selection: SetupSelection = resolve({"monitor": "gigabyte-m27q", "keyboard": "keychron-k8"})
    merged = with_setup(parts, selection)
    assert identity(describe_build(merged, default_preset(merged))) != without


# --- the customer sees what they are buying ------------------------------------


def test_ticking_a_category_shows_the_actual_product_and_its_price() -> None:
    """A checkbox says a category was chosen; it does not say which mouse."""
    from app.bot.views.configurator import render_picked_setup

    lines = render_picked_setup(
        {"setup": {"mouse": "logitech-g502-hero", "headset": "hyperx-cloud-ii"}}, "en"
    )
    body = " | ".join(lines)
    assert "Logitech G502 HERO" in body
    assert "HyperX Cloud II" in body
    assert "PLN" in body


def test_the_monitor_step_names_the_screen_that_was_ticked() -> None:
    from app.bot.views.configurator import render_chosen_monitor

    lines = render_chosen_monitor({"setup": {"monitor": "gigabyte-m27q"}}, "en")
    assert lines and "Gigabyte M27Q" in lines[-1]
    assert render_chosen_monitor({"setup": {}}, "en") == []


def test_the_desk_block_ignores_the_monitor_it_has_its_own_step() -> None:
    from app.bot.views.configurator import render_picked_setup

    lines = render_picked_setup({"setup": {"monitor": "gigabyte-m27q"}}, "en")
    assert lines == []


def test_a_retired_product_is_dropped_from_the_picked_list() -> None:
    from app.bot.views.configurator import render_picked_setup

    lines = render_picked_setup({"setup": {"mouse": "no-such-mouse"}}, "en")
    assert not [line for line in lines if line.strip()]


@pytest.mark.parametrize("language", ["ru", "en", "pl", "uk"])
def test_the_picked_list_is_localized(language: str) -> None:
    from app.bot.views.configurator import render_picked_setup
    from app.i18n import t

    lines = render_picked_setup({"setup": {"mouse": "logitech-g502-hero"}}, language)
    assert t(language, "part.mouse") in " | ".join(lines)
