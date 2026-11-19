"""The customer never sees a language they did not choose.

``test_i18n`` proves the four locales carry the same keys. These tests prove
the harder half: that the code actually *asks* for a translation instead of
carrying Russian copy inside a handler, a view or a picture, and that every
key the code asks for exists.

Admin surfaces are exempt on purpose - the admin panel is Russian-only
internal tooling (see the module docstrings there).
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from app.domain.enums import Priority
from app.i18n import DEFAULT_LANGUAGE, LOCALES, SUPPORTED_LANGUAGES
from app.services.media.presets import Accent, CaseFinish, Style
from app.services.ready_builds.catalogue import RECIPES

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
CYRILLIC = re.compile(r"[Ѐ-ӿ]")

#: Russian here is intentional and documented in the modules themselves.
ADMIN_ONLY = (
    "/i18n/",
    "/views/admin.py",
    "/views/visuals.py",
    "/views/compatibility.py",
    "/handlers/admin.py",
    "/keyboards/admin.py",
    # Labour and complexity line items are admin metrics; the customer is
    # never shown them (there is a separate test guarding that).
    "/services/pricing/complexity.py",
    "/services/pricing/labor.py",
    # Seed data for the shelf: the row keeps the original text, the card
    # renders `shelf.desc.<recipe>` from the locale instead.
    "/services/ready_builds/catalogue.py",
)


def _customer_facing() -> list[pathlib.Path]:
    return [
        path
        for path in sorted(APP.rglob("*.py"))
        if not any(part in path.as_posix() for part in ADMIN_ONLY)
    ]


def _docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                lines.add(body[0].value.lineno)
    return lines


def test_no_customer_facing_module_carries_russian_copy() -> None:
    """A hardcoded phrase reaches every customer, whatever language they picked."""
    offenders: list[str] = []
    for path in _customer_facing():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        skip = _docstring_lines(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and CYRILLIC.search(node.value)
                and node.lineno not in skip
            ):
                offenders.append(f"{path.name}:{node.lineno}: {node.value[:60]}")
    assert not offenders, "hardcoded Russian in customer-facing code:\n" + "\n".join(offenders)


def _requested_keys() -> dict[str, set[str]]:
    """Every literal key passed to ``t(lang, "...")``, by module."""
    found: dict[str, set[str]] = {}
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "t"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                found.setdefault(path.name, set()).add(node.args[1].value)
    return found


def test_every_key_the_code_asks_for_exists_in_every_locale() -> None:
    reference = set(LOCALES[DEFAULT_LANGUAGE])
    missing: list[str] = []
    for module, keys in _requested_keys().items():
        for key in sorted(keys):
            if key not in reference:
                missing.append(f"{module}: {key}")
    assert not missing, "keys used in code but absent from the locales:\n" + "\n".join(missing)


def test_the_code_really_does_ask_for_translations() -> None:
    """Guards the test above from silently passing on an empty scan."""
    assert sum(len(keys) for keys in _requested_keys().values()) > 100


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_enum_the_customer_sees_is_translated(language: str) -> None:
    texts = LOCALES[language]
    for priority in Priority:
        assert f"priority.{priority.value}" in texts
    for accent in Accent:
        assert f"accent.{accent.value}" in texts
    for finish in CaseFinish:
        assert f"finish.{finish.value}" in texts
    for style in Style:
        assert f"visual.style_{style.value}" in texts


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_shelf_recipe_has_a_translated_pitch(language: str) -> None:
    for recipe in RECIPES:
        key = f"shelf.desc.{recipe.key}"
        assert key in LOCALES[language], f"{language} is missing {key}"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_the_picture_footer_is_translated(language: str) -> None:
    assert "visual.image_footer" in LOCALES[language]


# --- what the customer is actually handed ---------------------------------------

#: Letters that exist in Russian but not in Ukrainian: a Russian string that
#: leaked into the Ukrainian locale gives itself away with one of these.
RUSSIAN_ONLY = re.compile(r"[ыэъЫЭЪ]")


def _rendered_surfaces(language: str) -> list[tuple[str, str]]:
    """Every string a customer can be shown, actually rendered."""
    from decimal import Decimal

    from app.bot.flows.configurator import STEPS, StepId
    from app.bot.keyboards.common import main_menu_kb
    from app.bot.keyboards.configurator import keyboard_for_step, order_confirm_kb
    from app.bot.views.build import render_no_build, render_order_blocked
    from app.bot.views.configurator import render_budget_error, render_question
    from app.domain.components import ComponentCategory
    from app.i18n import t
    from app.services.catalog import get_catalog
    from app.services.media.presets import PRESETS_BY_KEY, Accent, accent_label, preset_title

    answers = {
        "budget_pln": 8000,
        "purpose": "gaming",
        "games": ["cs2"],
        "resolution": "1440p",
        "target_fps": "144",
        "priorities": ["silence", "looks"],
        "priority": "silence",
        "aesthetics": "black_rgb",
        "storage_gb": 1000,
        "ram_gb": 32,
        "_monitor_options": [
            c.id for c in get_catalog().by_category(ComponentCategory.MONITOR)[:4]
        ],
        "setup": {"monitor": "gigabyte-m27q", "mouse": "logitech-g502-hero"},
    }

    out: list[tuple[str, str]] = []
    for button in (b for row in main_menu_kb(language).inline_keyboard for b in row):
        out.append(("menu button", button.text))
    for step in STEPS:
        if step.id is StepId.SUMMARY:
            continue
        out.append((f"question {step.id.value}", render_question(step.id, answers, language)))
        markup = keyboard_for_step(step.id, answers, language)
        for button in (b for row in markup.inline_keyboard for b in row):
            out.append((f"button {step.id.value}", button.text))
    for button in (b for row in order_confirm_kb(language).inline_keyboard for b in row):
        out.append(("order confirm", button.text))
    out.append(("budget error", render_budget_error(language)))
    out.append(("no build", render_no_build(Decimal(4500), language)))
    out.append(("order blocked", render_order_blocked(["psu_gpu_minimum"], language)))
    for accent in Accent:
        out.append(("accent label", accent_label(accent, language)))
    out.append(("preset title", preset_title(PRESETS_BY_KEY["black-red-gaming"], language)))
    for key in (
        "visual.image_footer",
        "visual.generating",
        "visual.unavailable",
        "visual.ai_title",
        "setup.title",
        "setup.grand_total",
        "cfg.peripherals.none",
        "common.error",
        "order.expired",
        "build.none_generic",
    ):
        out.append((f"key {key}", t(language, key)))
    for recipe in RECIPES:
        out.append((f"shelf {recipe.key}", t(language, f"shelf.desc.{recipe.key}")))
    return out


@pytest.mark.parametrize("language", ["en", "pl"])
def test_a_latin_flow_never_shows_a_cyrillic_character(language: str) -> None:
    """The end-to-end version: render the flow and read what comes out."""
    strays = [
        f"{where}: {text[:60]}"
        for where, text in _rendered_surfaces(language)
        if CYRILLIC.search(text)
    ]
    assert not strays, f"Cyrillic in the {language} flow: " + "; ".join(strays)


def test_the_ukrainian_flow_is_not_quietly_russian() -> None:
    strays = [
        f"{where}: {text[:60]}"
        for where, text in _rendered_surfaces("uk")
        if RUSSIAN_ONLY.search(text)
    ]
    assert not strays, "Russian-only letters in the Ukrainian flow: " + "; ".join(strays)


def test_the_sweep_actually_covers_the_flow() -> None:
    """Guards the two tests above from passing on an empty list."""
    assert len(_rendered_surfaces("en")) > 150


# --- the catalogue is data, and data must not carry one language ----------------


def test_no_catalogue_text_shown_to_a_customer_is_in_one_language() -> None:
    """The gap the .py-only scan missed: product text lives in JSON.

    Highlights are printed verbatim on an accessory card, so they have to be
    unit-neutral ("121 g", "8000 Hz polling") rather than written in any one
    language. The summary line is derived from the spec through the locale
    and is checked separately.
    """
    import json

    data = pathlib.Path(__file__).resolve().parents[1] / "app" / "data" / "components"
    offenders: list[str] = []
    for path in sorted(data.glob("*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            for highlight in item.get("spec", {}).get("highlights") or []:
                if CYRILLIC.search(highlight):
                    offenders.append(f"{item['id']}: {highlight}")
    assert not offenders, "language-specific product text: " + "; ".join(offenders)


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_accessory_describes_itself_in_the_chosen_language(language: str) -> None:
    from app.bot.views.accessories import peripheral_summary
    from app.domain.components import ACCESSORY_CATEGORIES, PeripheralSpec
    from app.services.catalog import get_catalog

    checked = 0
    for component in get_catalog():
        if component.category not in ACCESSORY_CATEGORIES:
            continue
        if not isinstance(component.spec, PeripheralSpec):
            continue
        summary = peripheral_summary(component, language)
        assert summary and "acc." not in summary, f"{component.id}: {summary}"
        if language in {"en", "pl"}:
            assert not CYRILLIC.search(summary), f"{component.id}: {summary}"
        checked += 1
    assert checked > 20
