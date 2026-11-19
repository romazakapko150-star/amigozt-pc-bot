"""Lighting is a fact about hardware; RGB is a wish. They must not be confused.

The rule these tests defend: a machine is never described, keyed or
photographed as lit unless a part in it actually emits light, and a customer
who asks for RGB the parts cannot produce is told so rather than sold a
render of LEDs that do not exist.
"""

from __future__ import annotations

import pytest

from app.bot.views.build import render_lighting
from app.domain.components import ComponentCategory as C
from app.domain.enums import Priority
from app.domain.lighting import (
    LightingState,
    describe_lighting,
    plan_lighting,
)
from app.i18n import SUPPORTED_LANGUAGES, t
from app.services.ai.visualizer import build_prompt, describe_build, identity
from app.services.catalog import get_catalog
from app.services.media.presets import PRESETS_BY_KEY

PRESET = PRESETS_BY_KEY["black-red-gaming"]

#: The build from the customer's screenshot: nothing in it emits light.
DARK_IDS = {
    C.CPU: "intel-core-i5-13600kf",
    C.COOLER: "deepcool-ak400",
    C.MOTHERBOARD: "msi-b760-gaming-plus-wifi",
    C.RAM: "kingston-fury-beast-32-ddr5-6000",
    C.GPU: "amd-rx-7700-xt",
    C.SSD: "kingston-nv3-1tb",
    C.PSU: "corsair-rm750e",
    C.CASE: "fractal-pop-air-black",
}


def _parts(**overrides: str) -> dict:
    catalog = get_catalog()
    ids = {**DARK_IDS, **{C(k): v for k, v in overrides.items()}}
    return {category: catalog.require(cid) for category, cid in ids.items()}


def _lit_parts() -> dict:
    """The same machine with an ARGB case and RGB memory fitted."""
    return _parts(case="lianli-lancool-216-black", ram="corsair-vengeance-rgb-32-ddr5-6000")


# --- capability comes from the catalogue, never from a guess --------------------


def test_the_screenshot_build_really_has_no_lighting() -> None:
    """Verified against catalogue data, not against the picture."""
    capabilities = describe_lighting(_parts())
    assert capabilities.lit == ()
    assert not capabilities.any_lit
    # The board could drive lighting - that is not the same as having any.
    assert capabilities.header_capable
    assert capabilities.expandable


def test_lit_parts_are_reported_with_their_categories() -> None:
    capabilities = describe_lighting(_lit_parts())
    assert set(capabilities.lit) == {"case", "ram"}
    assert "case" in capabilities.addressable


def test_a_part_with_no_lighting_field_is_unknown_not_dark() -> None:
    """A graphics card carries no such field; we neither claim nor deny."""
    capabilities = describe_lighting(_parts())
    assert "gpu" in capabilities.unknown
    assert "gpu" not in capabilities.lit


def test_lit_peripherals_are_counted_apart_from_the_tower() -> None:
    catalog = get_catalog()
    parts = {**_parts(), C.KEYBOARD: catalog.require("razer-huntsman-mini")}
    capabilities = describe_lighting(parts)
    assert "keyboard" in capabilities.lit_peripherals
    assert "keyboard" not in capabilities.lit


# --- the four states -------------------------------------------------------------


@pytest.mark.parametrize(
    ("lit", "requested", "expected"),
    [
        (False, False, LightingState.NONE),
        (False, True, LightingState.UNAVAILABLE),
        (True, False, LightingState.AVAILABLE),
        (True, True, LightingState.REQUESTED),
    ],
)
def test_capability_and_intent_combine_into_one_state(
    lit: bool, requested: bool, expected: LightingState
) -> None:
    parts = _lit_parts() if lit else _parts()
    assert plan_lighting(parts, requested=requested).state is expected


def test_asking_for_rgb_never_invents_it() -> None:
    """Case C from the brief: the wish must not create hardware."""
    plan = plan_lighting(_parts(), requested=True)
    assert plan.promised_but_missing
    assert not plan.show_lighting
    assert plan.lit_parts == ()


def test_lighting_present_but_not_asked_for_is_still_lighting() -> None:
    plan = plan_lighting(_lit_parts(), requested=False)
    assert plan.show_lighting and not plan.emphasise


# --- the description says what the data says ------------------------------------


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_a_dark_build_is_never_described_as_lit(language: str) -> None:
    lines = render_lighting(plan_lighting(_parts(), requested=False), language)
    assert lines == []


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_an_impossible_request_is_answered_honestly(language: str) -> None:
    lines = render_lighting(plan_lighting(_parts(), requested=True), language)
    assert len(lines) == 1
    assert t(language, "build.lighting.unavailable") in lines[0]


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_a_requested_lit_build_names_rgb_and_its_parts(language: str) -> None:
    lines = render_lighting(plan_lighting(_lit_parts(), requested=True), language)
    assert len(lines) == 1
    assert t(language, "part.case") in lines[0]
    assert t(language, "part.ram") in lines[0]
    assert t(language, "build.lighting.addressable") in lines[0]


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_available_and_featured_read_differently(language: str) -> None:
    available = render_lighting(plan_lighting(_lit_parts(), requested=False), language)[0]
    featured = render_lighting(plan_lighting(_lit_parts(), requested=True), language)[0]
    assert available != featured


# --- description, spec and prompt agree -------------------------------------------


def test_the_prompt_asks_for_lighting_only_when_the_parts_have_it() -> None:
    dark = build_prompt(describe_build(_parts(), PRESET, priorities=["looks"])).text.lower()
    assert "no rgb lighting anywhere" in dark
    assert "brightly lit" not in dark


def test_a_requested_lit_build_gets_an_emphatic_prompt() -> None:
    spec = describe_build(_lit_parts(), PRESET, priorities=["looks"])
    text = build_prompt(spec).text.lower()
    assert spec.lighting.emphasise
    assert "clearly and brightly lit" in text
    assert "individually addressable" in text


def test_a_lit_build_nobody_asked_about_is_lit_but_not_a_light_show() -> None:
    spec = describe_build(_lit_parts(), PRESET, priorities=[])
    text = build_prompt(spec).text.lower()
    assert spec.lit_parts
    assert "clearly and brightly lit" not in text


def test_the_prompt_still_forbids_invented_branding_everywhere() -> None:
    for priorities in ([], ["looks"]):
        text = build_prompt(describe_build(_lit_parts(), PRESET, priorities=priorities)).text
        assert text.lower().count("no lettering of any kind") >= 1
        # Stated before the parts, where the model still pays attention.
        assert text.index("no lettering of any kind") < text.index("Professional")


# --- and none of it explodes the bill ---------------------------------------------


def test_an_ungrantable_wish_reuses_the_dark_render() -> None:
    """Nothing glows either way, so both must be the same paid picture."""
    without = identity(describe_build(_parts(), PRESET, priorities=[]))
    with_wish = identity(describe_build(_parts(), PRESET, priorities=["looks"]))
    assert without == with_wish


def test_lighting_that_shows_earns_its_own_render() -> None:
    parts = _lit_parts()
    available = identity(describe_build(parts, PRESET, priorities=[]))
    featured = identity(describe_build(parts, PRESET, priorities=["looks"]))
    assert available != featured


def test_quiet_and_rgb_together_keep_both_intents() -> None:
    parts = _lit_parts()
    spec = describe_build(parts, PRESET, priorities=["silence", "looks"])
    text = build_prompt(spec).text.lower()
    assert spec.lighting.emphasise
    assert "quiet machine" in text
    assert "brightly lit" in text
    quiet_only = identity(describe_build(parts, PRESET, priorities=["silence"]))
    assert identity(spec) != quiet_only


def test_the_signature_has_exactly_three_visual_outcomes() -> None:
    """off / present / featured - anything more would buy duplicate pictures."""
    seen = {
        describe_build(parts, PRESET, priorities=priorities).lighting_signature
        for parts in (_parts(), _lit_parts())
        for priorities in ([], ["looks"], ["silence"], ["silence", "looks"])
    }
    assert seen == {"off", "present", "featured"}


def test_swapping_in_lit_memory_changes_the_picture() -> None:
    base = identity(describe_build(_parts(), PRESET, priorities=["looks"]))
    lit_ram = identity(
        describe_build(
            _parts(ram="corsair-vengeance-rgb-32-ddr5-6000"), PRESET, priorities=["looks"]
        )
    )
    assert base != lit_ram


def test_the_priority_enum_still_carries_rgb() -> None:
    """Guards the wiring: "looks" is the tick that asks for lighting."""
    assert Priority.LOOKS.value == "looks"
