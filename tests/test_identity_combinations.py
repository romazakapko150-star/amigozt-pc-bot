"""Arbitrary combinations, not a hand-picked list.

The rule the whole cost model rests on:

    different resulting appearance  -> different identity -> its own render
    identical resulting appearance  -> same identity      -> reuse, no call

These tests enumerate the combination space programmatically - every subset
of the priorities a customer can tick, crossed with hardware swaps, the
monitor and the peripherals - instead of asserting on a few examples. If
someone later adds a priority, a peripheral category or a visual field, the
enumeration widens by itself and the invariants are re-checked.
"""

from __future__ import annotations

import itertools

import pytest

from app.domain.components import ComponentCategory as C
from app.domain.enums import MAX_PRIORITIES, PRIORITY_ORDER, Priority
from app.services.ai.visualizer import (
    VISUAL_PRIORITY_WORDS,
    describe_build,
    fingerprint,
    identity,
)
from app.services.catalog import get_catalog
from app.services.media.presets import PRESETS_BY_KEY

MODEL = "gpt-image-1"
PRESET = PRESETS_BY_KEY["black-red-gaming"]

#: The priorities that change a photograph, as the code defines them - not a
#: list repeated here by hand.
VISUAL = tuple(p for p in PRIORITY_ORDER if p.value in VISUAL_PRIORITY_WORDS)
COMMERCIAL = tuple(p for p in PRIORITY_ORDER if p.value not in VISUAL_PRIORITY_WORDS)


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


def _key(parts: dict, priorities: tuple[Priority, ...]) -> str:
    return identity(describe_build(parts, PRESET, priorities=[p.value for p in priorities]))


def _subsets(items: tuple[Priority, ...], max_size: int) -> list[tuple[Priority, ...]]:
    out: list[tuple[Priority, ...]] = []
    for size in range(max_size + 1):
        out.extend(itertools.combinations(items, size))
    return out


# --- the whole visual subset lattice --------------------------------------------


def test_every_subset_of_the_visual_priorities_is_its_own_picture() -> None:
    """2^4 subsets, all distinct - no combination collides with another."""
    parts = _parts()
    keys = {subset: _key(parts, subset) for subset in _subsets(VISUAL, len(VISUAL))}
    assert len(keys) == 2 ** len(VISUAL)
    assert len(set(keys.values())) == len(keys), "two different combinations share a render"


@pytest.mark.parametrize("size", [1, 2, 3, 4])
def test_combinations_of_the_same_size_differ_from_each_other(size: int) -> None:
    """Same number of ticks, different ticks: different pictures."""
    parts = _parts()
    same_size = list(itertools.combinations(VISUAL, size))
    keys = [_key(parts, subset) for subset in same_size]
    assert len(set(keys)) == len(keys)


def test_the_order_of_ticking_never_matters() -> None:
    parts = _parts()
    for subset in _subsets(VISUAL, len(VISUAL)):
        if len(subset) < 2:
            continue
        for permutation in itertools.permutations(subset):
            assert _key(parts, permutation) == _key(parts, subset)


def test_adding_or_removing_one_option_changes_the_picture_both_ways() -> None:
    parts = _parts()
    for subset in _subsets(VISUAL, len(VISUAL) - 1):
        for extra in VISUAL:
            if extra in subset:
                continue
            bigger = (*subset, extra)
            assert _key(parts, subset) != _key(parts, bigger)
            # ...and taking it away again lands exactly where we started.
            back = tuple(p for p in bigger if p is not extra)
            assert _key(parts, back) == _key(parts, subset)


def test_the_same_selection_asked_for_twice_is_always_the_same_key() -> None:
    """Determinism across the whole lattice: this is what the cache relies on."""
    parts = _parts()
    for subset in _subsets(VISUAL, len(VISUAL)):
        assert _key(parts, subset) == _key(_parts(), subset)


# --- commercial ticks ride along for free ----------------------------------------


def test_no_commercial_subset_ever_buys_another_copy() -> None:
    """Every commercial combination on top of any visual combination reuses it."""
    parts = _parts()
    for visual_subset in _subsets(VISUAL, 2):
        base = _key(parts, visual_subset)
        room = MAX_PRIORITIES - len(visual_subset)
        for commercial_subset in _subsets(COMMERCIAL, room):
            combined = (*visual_subset, *commercial_subset)
            assert _key(parts, combined) == base, f"{combined} bought a duplicate"


def test_a_selection_of_only_commercial_ticks_is_the_plain_picture() -> None:
    parts = _parts()
    plain = _key(parts, ())
    for subset in _subsets(COMMERCIAL, MAX_PRIORITIES):
        assert _key(parts, subset) == plain


# --- hardware crossed with priorities ---------------------------------------------

SWAPS: list[tuple[str, C, str]] = [
    ("gpu", C.GPU, "amd-rx-9070-xt"),
    ("case", C.CASE, "lianli-lancool-216-black"),
    ("cooler", C.COOLER, "bequiet-dark-rock-pro-5"),
    ("ram", C.RAM, "kingston-fury-beast-32-ddr5-6000"),
    ("motherboard", C.MOTHERBOARD, "asus-tuf-b650-plus-wifi"),
    ("psu", C.PSU, "seasonic-vertex-gx-1000"),
]


@pytest.mark.parametrize(("label", "category", "component_id"), SWAPS)
def test_a_hardware_swap_changes_every_combination_it_appears_in(
    label: str, category: C, component_id: str
) -> None:
    swapped = _parts(**{category: get_catalog().require(component_id)})
    base = _parts()
    for subset in _subsets(VISUAL, 2):
        assert _key(base, subset) != _key(swapped, subset), f"{label} invisible under {subset}"


def test_hardware_and_priorities_move_independently() -> None:
    """Changing both must not accidentally land on either single change."""
    other_gpu = get_catalog().require("amd-rx-9070-xt")
    a = _key(_parts(), (Priority.SILENCE,))
    b = _key(_parts(**{C.GPU: other_gpu}), (Priority.SILENCE,))
    c = _key(_parts(), (Priority.SILENCE, Priority.LOOKS))
    d = _key(_parts(**{C.GPU: other_gpu}), (Priority.SILENCE, Priority.LOOKS))
    assert len({a, b, c, d}) == 4


# --- the desk crossed with priorities ----------------------------------------------


def _desk_pieces() -> dict[C, object]:
    catalog = get_catalog()
    return {
        C.MONITOR: catalog.require("gigabyte-m27q"),
        C.KEYBOARD: catalog.by_category(C.KEYBOARD)[0],
        C.MOUSE: catalog.by_category(C.MOUSE)[0],
        C.HEADSET: catalog.by_category(C.HEADSET)[0],
    }


def test_building_the_desk_up_one_piece_at_a_time_never_repeats_a_key() -> None:
    """Add monitor, then keyboard, then mouse, then headset: four new pictures."""
    for subset in _subsets(VISUAL, 2):
        parts = _parts()
        seen = [_key(parts, subset)]
        for category, component in _desk_pieces().items():
            parts = {**parts, category: component}
            seen.append(_key(parts, subset))
        assert len(set(seen)) == len(seen), f"a desk addition was invisible under {subset}"


def test_removing_a_desk_piece_returns_to_the_earlier_key() -> None:
    """Un-ticking a peripheral must reuse the render from before it was added."""
    pieces = _desk_pieces()
    for subset in _subsets(VISUAL, 2):
        base = _parts()
        before = _key(base, subset)
        with_monitor = {**base, C.MONITOR: pieces[C.MONITOR]}
        assert _key(with_monitor, subset) != before
        without = {k: v for k, v in with_monitor.items() if k is not C.MONITOR}
        assert _key(without, subset) == before


def test_swapping_one_peripheral_for_another_is_a_different_setup() -> None:
    catalog = get_catalog()
    for category in (C.MOUSE, C.KEYBOARD, C.HEADSET):
        options = catalog.by_category(category)
        assert len(options) >= 2
        for subset in _subsets(VISUAL, 1):
            first = _key(_parts(**{category: options[0]}), subset)
            second = _key(_parts(**{category: options[1]}), subset)
            assert first != second


def test_every_desk_subset_is_its_own_setup() -> None:
    """Any combination of peripherals, not only the incremental one."""
    pieces = _desk_pieces()
    keys: set[str] = set()
    for size in range(len(pieces) + 1):
        for subset in itertools.combinations(pieces.items(), size):
            parts = _parts(**dict(subset))  # type: ignore[arg-type]
            keys.add(_key(parts, (Priority.LOOKS,)))
    assert len(keys) == 2 ** len(pieces)


# --- the fingerprint tracks the identity everywhere ---------------------------------


def test_the_render_key_follows_the_identity_across_the_lattice() -> None:
    parts = _parts()
    identities: set[str] = set()
    fingerprints: set[str] = set()
    for subset in _subsets(VISUAL, len(VISUAL)):
        spec = describe_build(parts, PRESET, priorities=[p.value for p in subset])
        identities.add(identity(spec))
        fingerprints.add(fingerprint(spec, model=MODEL))
    assert len(identities) == len(fingerprints) == 2 ** len(VISUAL)


def test_the_selection_is_capped_where_the_ui_caps_it() -> None:
    """The lattice the tests explore is the one the customer can actually reach."""
    assert MAX_PRIORITIES == 4
    assert len(VISUAL) + len(COMMERCIAL) == len(PRIORITY_ORDER) == 9
