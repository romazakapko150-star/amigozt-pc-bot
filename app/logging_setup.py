"""Logging configuration with hard guarantees against secret leakage.

Even if some third-party library tries to log a URL containing the bot token
(aiogram builds request URLs as ``https://api.telegram.org/bot<TOKEN>/...``),
``SecretRedactingFilter`` rewrites the record before it reaches any handler.
"""

from __future__ import annotations

import contextlib
import logging
import re
import sys
from collections.abc import Iterable

# No leading \b: aiogram builds request URLs as ".../bot<TOKEN>/", where the
# token is glued to a word character and \b would never match there.
TOKEN_PATTERN = re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_-]{30,}")
MASK = "***REDACTED***"


class SecretRedactingFilter(logging.Filter):
    """Removes known secrets and anything shaped like a bot token from logs."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def _scrub(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, MASK)
        return TOKEN_PATTERN.sub(MASK, text)

    def _scrub_arg(self, value: object) -> object:
        """Scrub strings only.

        Coercing every argument to ``str`` would corrupt numeric format specs:
        aiogram logs ``"Duration %d ms by bot id=%d"``, which raises TypeError
        once its integer arguments have been turned into strings.
        """
        return self._scrub(value) if isinstance(value, str) else value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._scrub(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._scrub_arg(v) for k, v in record.args.items()}
            else:
                record.args = tuple(self._scrub_arg(a) for a in record.args)
        return True


def setup_logging(level: str = "INFO", secrets: Iterable[str] = ()) -> None:
    # Windows consoles often default to a legacy codepage (cp1251/cp866); our
    # UI strings contain emoji, so logging them would raise UnicodeEncodeError.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        # Exotic stream setups (pytest capture, some IDE consoles) may refuse.
        with contextlib.suppress(ValueError, OSError):
            reconfigure(encoding="utf-8", errors="replace")

    redactor = SecretRedactingFilter(secrets)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(redactor)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.addFilter(redactor)

    # aiohttp/aiogram debug logs may contain full request URLs with the token.
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.INFO)
