"""Minimal i18n layer.

Design notes
------------
* Locales are plain ``dict[str, str]`` modules - no compilation step, no
  gettext tooling, trivial to hand to a translator.
* ``t()`` never raises: a missing key or a bad placeholder degrades to the
  default locale and finally to the key itself, so a translation mistake can
  never take the bot down mid-conversation.
* Brand names (NVIDIA GeForce, AMD Ryzen, CS2, ...) are deliberately NOT
  translated and live in ``app/domain`` instead.
"""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Any, Final

from app.i18n import en as _en
from app.i18n import pl as _pl
from app.i18n import ru as _ru
from app.i18n import uk as _uk

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE: Final = "ru"

LOCALES: Final[MappingProxyType[str, dict[str, str]]] = MappingProxyType(
    {
        "ru": _ru.TEXTS,
        "pl": _pl.TEXTS,
        "en": _en.TEXTS,
        "uk": _uk.TEXTS,
    }
)

#: Language picker: code -> native label.
LANGUAGE_LABELS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "ru": "🇷🇺 Русский",
        "pl": "🇵🇱 Polski",
        "en": "🇬🇧 English",
        "uk": "🇺🇦 Українська",
    }
)

SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = tuple(LOCALES)

#: Telegram ``language_code`` values we can map onto a supported locale.
_LANGUAGE_ALIASES: Final[dict[str, str]] = {
    "ru": "ru",
    "be": "ru",
    "uk": "uk",
    "kk": "ru",
    "pl": "pl",
    "en": "en",
}


def normalize_language(code: str | None) -> str:
    """Map a Telegram ``language_code`` onto a supported locale."""
    if not code:
        return DEFAULT_LANGUAGE
    primary = code.split("-", 1)[0].strip().lower()
    if primary in LOCALES:
        return primary
    return _LANGUAGE_ALIASES.get(primary, DEFAULT_LANGUAGE)


def t(lang: str | None, key: str, /, **kwargs: Any) -> str:
    """Translate ``key`` into ``lang``, formatting ``kwargs`` into the result."""
    language: str = lang if lang is not None and lang in LOCALES else DEFAULT_LANGUAGE
    template = LOCALES[language].get(key)

    if template is None:
        template = LOCALES[DEFAULT_LANGUAGE].get(key)
        if template is None:
            logger.warning("Missing translation key: %s", key)
            return key
        logger.warning("Missing translation key %r for language %r", key, language)

    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        logger.warning("Bad placeholders for key %r in language %r", key, language)
        return template


__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGE_LABELS",
    "LOCALES",
    "SUPPORTED_LANGUAGES",
    "normalize_language",
    "t",
]
