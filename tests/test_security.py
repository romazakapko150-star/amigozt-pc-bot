"""Guards for the rules in the project brief: no secret leaks, no floods."""

from __future__ import annotations

import logging

import pytest

from app.bot.handlers.configurator import parse_budget
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.config import Settings
from app.domain.enums import MAX_BUDGET_PLN, MIN_BUDGET_PLN
from app.logging_setup import MASK, SecretRedactingFilter, setup_logging

FAKE_TOKEN = "1234567890:AAF_FAKE_TOKEN_FOR_TESTS_ONLY_0123456789"


# --- secrets ------------------------------------------------------------------


def test_settings_never_expose_the_token_in_repr() -> None:
    settings = Settings(telegram_bot_token=FAKE_TOKEN)  # type: ignore[call-arg]
    assert FAKE_TOKEN not in repr(settings)
    assert FAKE_TOKEN not in str(settings)
    # It is still readable where it is actually needed.
    assert settings.bot_token == FAKE_TOKEN


def test_log_filter_redacts_a_known_secret() -> None:
    log_filter = SecretRedactingFilter([FAKE_TOKEN])
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "calling %s",
        (f"https://api.telegram.org/bot{FAKE_TOKEN}/getMe",),
        None,
    )
    log_filter.filter(record)
    assert FAKE_TOKEN not in str(record.args)
    assert MASK in str(record.args)


def test_log_filter_redacts_anything_shaped_like_a_token() -> None:
    """Even a token we were never told about must not reach the log."""
    log_filter = SecretRedactingFilter([])
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        f"url=https://api.telegram.org/bot{FAKE_TOKEN}/x",
        None,
        None,
    )
    log_filter.filter(record)
    assert FAKE_TOKEN not in record.msg
    assert MASK in record.msg


def test_setup_logging_installs_the_filter(caplog: pytest.LogCaptureFixture) -> None:
    setup_logging("INFO", secrets=[FAKE_TOKEN])
    logger = logging.getLogger("amigozt.test")
    with caplog.at_level(logging.INFO):
        logger.info("token is %s", FAKE_TOKEN)
    assert FAKE_TOKEN not in caplog.text


def test_admin_ids_are_parsed_from_a_plain_env_string() -> None:
    settings = Settings(  # type: ignore[call-arg]
        telegram_bot_token=FAKE_TOKEN, admin_telegram_ids="111, 222;333, oops,"
    )
    assert settings.admin_ids == frozenset({111, 222, 333})


def test_admin_ids_default_to_empty() -> None:
    settings = Settings(telegram_bot_token=FAKE_TOKEN)  # type: ignore[call-arg]
    assert settings.admin_ids == frozenset()


# --- input validation ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5500", 5500),
        ("5 500", 5500),
        ("5.500 PLN", 5500),
        ("  6000zl ", 6000),
        (str(MIN_BUDGET_PLN), MIN_BUDGET_PLN),
        (str(MAX_BUDGET_PLN), MAX_BUDGET_PLN),
    ],
)
def test_parse_budget_accepts_realistic_input(text: str, expected: int) -> None:
    assert parse_budget(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "abc",
        "0",
        str(MIN_BUDGET_PLN - 1),
        str(MAX_BUDGET_PLN + 1),
        "99999999999999",
        "'; DROP TABLE users;--",
        "<script>alert(1)</script>",
    ],
)
def test_parse_budget_rejects_junk(text: str) -> None:
    assert parse_budget(text) is None


# --- rate limiting ------------------------------------------------------------


def test_throttler_allows_a_short_burst_then_blocks() -> None:
    throttler = ThrottlingMiddleware(rate=1.0, burst=3)
    now = 1000.0

    assert [throttler._allow(1, now) for _ in range(3)] == [True, True, True]
    assert throttler._allow(1, now) is False


def test_throttler_refills_over_time() -> None:
    throttler = ThrottlingMiddleware(rate=1.0, burst=1)
    assert throttler._allow(1, 1000.0) is True
    assert throttler._allow(1, 1000.1) is False
    assert throttler._allow(1, 1002.0) is True


def test_throttler_is_per_user() -> None:
    throttler = ThrottlingMiddleware(rate=1.0, burst=1)
    assert throttler._allow(1, 1000.0) is True
    assert throttler._allow(2, 1000.0) is True


def test_log_filter_preserves_non_string_arguments() -> None:
    """Coercing args to str breaks %d specs used by aiogram's own loggers."""
    log_filter = SecretRedactingFilter([FAKE_TOKEN])
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "Update id=%s handled in %d ms by bot id=%d",
        ("691162484", 291, 1234567890),
        None,
    )
    log_filter.filter(record)

    # Would raise TypeError if the integers had been stringified.
    assert record.getMessage() == "Update id=691162484 handled in 291 ms by bot id=1234567890"


def test_log_filter_still_scrubs_string_arguments_among_numbers() -> None:
    log_filter = SecretRedactingFilter([FAKE_TOKEN])
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "%s took %d ms", (FAKE_TOKEN, 12), None
    )
    log_filter.filter(record)
    assert FAKE_TOKEN not in record.getMessage()
    assert record.getMessage().endswith("took 12 ms")
