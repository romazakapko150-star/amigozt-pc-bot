from __future__ import annotations

import re

import pytest

from app.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGE_LABELS,
    LOCALES,
    SUPPORTED_LANGUAGES,
    normalize_language,
    t,
)

PLACEHOLDER = re.compile(r"{(\w+)}")


def test_all_locales_expose_the_same_keys() -> None:
    """A missing translation must fail the build, not surface in production."""
    reference = set(LOCALES[DEFAULT_LANGUAGE])
    for language, texts in LOCALES.items():
        assert set(texts) == reference, f"key mismatch in locale {language!r}"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_placeholders_match_the_reference_locale(language: str) -> None:
    """A translator must not drop or rename a {placeholder}."""
    for key, reference_text in LOCALES[DEFAULT_LANGUAGE].items():
        expected = set(PLACEHOLDER.findall(reference_text))
        actual = set(PLACEHOLDER.findall(LOCALES[language][key]))
        assert actual == expected, f"{language}:{key} placeholders differ"


def test_every_locale_has_a_picker_label() -> None:
    assert set(LANGUAGE_LABELS) == set(LOCALES)


def test_no_empty_translations() -> None:
    for language, texts in LOCALES.items():
        for key, value in texts.items():
            assert value.strip(), f"{language}:{key} is empty"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("pl", "pl"),
        ("pl-PL", "pl"),
        ("en-GB", "en"),
        ("ru", "ru"),
        ("uk", "uk"),
        ("uk-UA", "uk"),
        ("de-DE", DEFAULT_LANGUAGE),
        (None, DEFAULT_LANGUAGE),
        ("", DEFAULT_LANGUAGE),
    ],
)
def test_normalize_language(code: str | None, expected: str) -> None:
    assert normalize_language(code) == expected


def test_t_formats_placeholders() -> None:
    assert t("en", "common.progress", current=3, total=12) == "Step 3 of 12"
    assert "3" in t("pl", "common.progress", current=3, total=12)


def test_t_falls_back_instead_of_raising() -> None:
    assert t("en", "does.not.exist") == "does.not.exist"
    # Unknown language -> default locale, never a KeyError.
    assert t("de", "common.error") == LOCALES[DEFAULT_LANGUAGE]["common.error"]
    # Missing placeholder -> raw template, never a crash mid-conversation.
    assert t("en", "common.progress") == LOCALES["en"]["common.progress"]
