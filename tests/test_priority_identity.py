"""Ticked priorities are part of what the picture shows - and what it costs.

The audit found that "quiet", "RGB" and "quiet + RGB" all mapped to one
render: the priorities never reached the visual spec. They do now, with one
deliberate limit. A priority earns a place in the identity only if it
changes what a photograph would show; a purely commercial tick (best
price/performance, room to upgrade, low power draw, versatility) steers
which parts get bought - and the parts are already in the identity - so it
must not buy a second copy of an identical picture.
"""

from __future__ import annotations

import pytest

from app.domain.components import ComponentCategory as C
from app.domain.enums import Priority
from app.services.ai.visualizer import (
    VISUAL_PRIORITY_WORDS,
    build_prompt,
    describe_build,
    fingerprint,
    identity,
    visual_priorities_of,
)
from app.services.catalog import get_catalog
from app.services.media.presets import PRESETS_BY_KEY

MODEL = "gpt-image-1"
PRESET = PRESETS_BY_KEY["black-red-gaming"]


def _parts(**overrides: object) -> dict:
    catalog = get_catalog()
    parts = {
        C.CPU: catalog.require("amd-ryzen-7-9700x"),
        C.COOLER: catalog.require("thermalright-assassin-x-120-refined-se"),
        C.MOTHERBOARD: catalog.require("msi-b650-gaming-plus-wifi"),
        C.RAM: catalog.require("corsair-vengeance-rgb-32-ddr5-6000"),
        C.GPU: catalog.require("nvidia-rtx-5080"),
        C.SSD: catalog.require("wd-black-sn850x-2tb"),
        C.PSU: catalog.require("bequiet-pure-power-12m-850"),
        C.CASE: catalog.require("fractal-pop-air-black"),
    }
    parts.update(overrides)  # type: ignore[arg-type]
    return parts


def _identity(parts: dict, *priorities: Priority) -> str:
    return identity(describe_build(parts, PRESET, priorities=[p.value for p in priorities]))


# --- the filter ----------------------------------------------------------------


def test_only_visually_meaningful_priorities_join_the_signature() -> None:
    assert set(VISUAL_PRIORITY_WORDS) == {"looks", "silence", "cooling", "compact"}
    assert visual_priorities_of(["looks", "price_performance", "max_fps"]) == ("looks",)


def test_the_signature_is_order_independent_and_deduplicated() -> None:
    """The same wishes must always produce the same key, however they were ticked."""
    a = visual_priorities_of(["looks", "silence"])
    b = visual_priorities_of(["silence", "looks", "silence"])
    assert a == b == ("looks", "silence")


def test_no_priorities_means_no_signature() -> None:
    assert visual_priorities_of(None) == ()
    assert visual_priorities_of([]) == ()


# --- the brief's own combinations ------------------------------------------------


def test_quiet_rgb_and_quiet_plus_rgb_are_three_different_pictures() -> None:
    parts = _parts()
    quiet = _identity(parts, Priority.SILENCE)
    rgb = _identity(parts, Priority.LOOKS)
    both = _identity(parts, Priority.SILENCE, Priority.LOOKS)
    assert len({quiet, rgb, both}) == 3


def test_adding_a_monitor_to_a_combination_changes_it_again() -> None:
    monitor = get_catalog().require("gigabyte-m27q")
    without = _identity(_parts(), Priority.SILENCE, Priority.LOOKS)
    with_screen = _identity(_parts(**{C.MONITOR: monitor}), Priority.SILENCE, Priority.LOOKS)
    assert without != with_screen


def test_changing_the_gpu_under_the_same_priorities_changes_it_again() -> None:
    other = get_catalog().require("amd-rx-9070-xt")
    base = _identity(_parts(), Priority.SILENCE, Priority.LOOKS)
    swapped = _identity(_parts(**{C.GPU: other}), Priority.SILENCE, Priority.LOOKS)
    assert base != swapped


def test_the_same_combination_asked_for_twice_is_the_same_picture() -> None:
    """The cache contract: identical configuration, zero further API calls."""
    first = _identity(_parts(), Priority.LOOKS, Priority.SILENCE)
    second = _identity(_parts(), Priority.SILENCE, Priority.LOOKS)
    assert first == second


def test_a_commercial_tick_does_not_buy_another_copy_of_the_same_photo() -> None:
    """Max FPS changes which parts are chosen, not how the machine looks.

    With the parts held identical, adding it must reuse the render - the
    parts it would have changed are in the identity in their own right.
    """
    parts = _parts()
    without = _identity(parts, Priority.SILENCE, Priority.LOOKS)
    with_commercial = _identity(parts, Priority.SILENCE, Priority.LOOKS, Priority.MAX_FPS)
    assert without == with_commercial


@pytest.mark.parametrize(
    "priority",
    [
        Priority.PRICE_PERFORMANCE,
        Priority.EFFICIENCY,
        Priority.UPGRADEABILITY,
        Priority.VERSATILITY,
    ],
)
def test_every_commercial_priority_is_visually_free(priority: Priority) -> None:
    parts = _parts()
    assert _identity(parts) == _identity(parts, priority)


@pytest.mark.parametrize(
    "priority", [Priority.LOOKS, Priority.SILENCE, Priority.COOLING, Priority.COMPACT]
)
def test_every_visual_priority_earns_its_own_picture(priority: Priority) -> None:
    parts = _parts()
    assert _identity(parts) != _identity(parts, priority)


# --- the fingerprint follows the identity ----------------------------------------


def test_the_render_key_moves_with_the_identity() -> None:
    parts = _parts()
    quiet = fingerprint(
        describe_build(parts, PRESET, priorities=[Priority.SILENCE.value]), model=MODEL
    )
    lit = fingerprint(describe_build(parts, PRESET, priorities=[Priority.LOOKS.value]), model=MODEL)
    assert quiet != lit


# --- the prompt actually says it --------------------------------------------------


def test_the_prompt_describes_what_the_customer_asked_for() -> None:
    parts = _parts()
    quiet = build_prompt(describe_build(parts, PRESET, priorities=["silence"])).text.lower()
    lit = build_prompt(describe_build(parts, PRESET, priorities=["looks"])).text.lower()
    assert "quiet machine" in quiet and "show piece" not in quiet
    assert "show piece" in lit


def test_the_prompt_still_names_the_real_parts_and_forbids_fake_branding() -> None:
    text = build_prompt(
        describe_build(_parts(), PRESET, priorities=["looks", "cooling"])
    ).text.lower()
    assert "rtx 5080" in text
    assert "no lettering of any kind" in text


def test_a_commercial_priority_adds_nothing_to_the_prompt() -> None:
    parts = _parts()
    plain = build_prompt(describe_build(parts, PRESET)).text
    commercial = build_prompt(
        describe_build(parts, PRESET, priorities=["price_performance", "upgradeability"])
    ).text
    assert plain == commercial


# --- the batch and the customer must use the same key ----------------------------


def test_a_shelf_row_answers_its_own_visual_priorities() -> None:
    """One definition, so the batch cannot pay for a render the picker misses."""
    from app.db.models import ReadyBuild

    lit = ReadyBuild(slug="x", name="x", category="gaming", rgb=True)
    plain = ReadyBuild(slug="y", name="y", category="gaming", rgb=False)
    assert lit.visual_priorities == ["looks"]
    assert plain.visual_priorities == []


def test_the_shelf_key_is_the_same_from_either_side() -> None:
    from app.db.models import ReadyBuild
    from app.services.ai.visualizer import Visualizer

    class _Off:
        name = "fake"
        model = "fake-model"
        enabled = False

        def generate_png(self, prompt, references=()):  # type: ignore[no-untyped-def]
            raise AssertionError("no generation in this test")

    visualizer = Visualizer(_Off(), enabled=False, model="fake-model")
    parts = _parts()
    ready = ReadyBuild(slug="lit", name="Lit", category="gaming", rgb=True)

    # What the batch would store...
    batch_key = visualizer.identity_for(parts, PRESET, ready.visual_priorities)
    # ...and what the customer's picker would look up.
    picker_key = identity(describe_build(parts, PRESET, priorities=ready.visual_priorities))
    assert batch_key == picker_key
