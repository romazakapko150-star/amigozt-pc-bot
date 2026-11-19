"""Shared visual language for the bot's messages.

Telegram gives a free bot a small palette: bold, italic, code, links,
spoilers and - the one most bots never use - block quotes, which draw an
indented bar down the side of a passage. Used consistently these are enough
to give a message structure a customer can skim: a title, the facts, and
the asides visibly set apart from both.

The rules here are deliberately few, so every screen looks like the same
product:

* a **title** is bold, on its own line;
* a **note** the customer may skip - a hint, a disclaimer, a price caveat -
  is a quote, never italic body text;
* a long block they rarely need is an *expandable* quote, collapsed by
  default so the card stays short on a phone;
* a **divider** separates blocks that are about different things.

Nothing here formats numbers or translates: it arranges text that has
already been translated.
"""

from __future__ import annotations

#: A thin rule. Telegram has no horizontal line, and a row of box-drawing
#: characters is the only thing that renders identically on every client.
DIVIDER = "━━━━━━━━━━━━━━━"


def title(text: str) -> str:
    """The one line that says what this screen is."""
    return f"<b>{text}</b>"


def note(text: str) -> str:
    """An aside: quoted, so the eye can skip it and come back."""
    return f"<blockquote>{text}</blockquote>"


def collapsed(text: str) -> str:
    """A long aside, collapsed until the customer taps it open.

    Telegram shows the first lines and an expand arrow, which keeps a card
    with a lot of small print short without hiding anything.
    """
    return f"<blockquote expandable>{text}</blockquote>"


def divider() -> str:
    return DIVIDER


def field(label: str, value: str, emoji: str = "") -> str:
    """``🎯 Purpose: Gaming`` - a label and its value on one line."""
    prefix = f"{emoji} " if emoji else ""
    return f"{prefix}<b>{label}:</b> {value}"


def block(heading: str, lines: list[str], emoji: str = "") -> list[str]:
    """A titled group of lines, with the blank line that separates it."""
    if not lines:
        return []
    prefix = f"{emoji} " if emoji else ""
    return ["", f"{prefix}<b>{heading}</b>", *lines]
