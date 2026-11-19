"""The bot must at least assemble: routers, middlewares, command list."""

from __future__ import annotations

import pytest

from app.bot.dispatcher import _strip_emoji
from app.bot.handlers import build_router
from app.i18n import SUPPORTED_LANGUAGES, t


def test_router_tree_is_assembled() -> None:
    root = build_router()
    names = [child.name for child in root.sub_routers]

    assert names == [
        "errors",
        "common",
        "configurator",
        "builds",
        "ready_builds",
        "compare",
        "accessories",
        "visual",
        "admin",
        "fallback",
    ]
    # A catch-all registered before the real handlers would swallow everything.
    assert names[-1] == "fallback"


def test_dispatcher_is_fully_wired(dispatcher) -> None:
    """One assembled dispatcher per process - aiogram allows no more."""
    registered = [type(m).__name__ for m in dispatcher.update.outer_middleware]
    assert "ThrottlingMiddleware" in registered
    assert "DbSessionMiddleware" in registered
    assert "UserMiddleware" in registered
    # Throttling must come first, before any database work is done.
    assert registered.index("ThrottlingMiddleware") < registered.index("DbSessionMiddleware")

    used = dispatcher.resolve_used_update_types()
    assert "message" in used
    assert "callback_query" in used


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_command_descriptions_are_telegram_safe(lang: str) -> None:
    """Telegram rejects command descriptions with emoji or empty text."""
    for key in ("menu.build", "menu.budget", "menu.mybuilds", "menu.help"):
        description = _strip_emoji(t(lang, key))
        assert description
        assert 1 <= len(description) <= 256
        assert all(ord(char) < 0x2190 for char in description)
