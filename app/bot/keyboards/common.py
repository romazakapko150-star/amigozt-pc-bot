from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import LangCB, MenuAction, MenuCB, NavAction, NavCB
from app.i18n import LANGUAGE_LABELS, t

Row = list[InlineKeyboardButton]


def chunk(buttons: Sequence[InlineKeyboardButton], per_row: int) -> list[Row]:
    return [list(buttons[i : i + per_row]) for i in range(0, len(buttons), per_row)]


#: Longest label (in characters) that still fits a column on a narrow phone.
#: Telegram shrinks the font a little and wraps to a second line, but past
#: these widths labels start being clipped with an ellipsis on ~320pt screens.
MAX_LABEL_FOR_COLUMNS: dict[int, int] = {4: 8, 3: 12, 2: 18}


def mobile_rows(buttons: Sequence[InlineKeyboardButton], preferred_columns: int) -> list[Row]:
    """Lay buttons out in the widest column count their labels actually fit.

    The layout is derived from the labels rather than hardcoded per step, so a
    long translation degrades to fewer columns instead of being clipped.
    """
    if not buttons:
        return []

    longest = max(len(button.text) for button in buttons)
    columns = preferred_columns
    while columns > 1 and longest > MAX_LABEL_FOR_COLUMNS.get(columns, 0):
        columns -= 1
    return chunk(buttons, columns)


def markup(*rows: Row) -> InlineKeyboardMarkup:
    """Build a markup from button rows, dropping empty ones.

    Pass a list of rows with ``markup(*rows)``.
    """
    return InlineKeyboardMarkup(inline_keyboard=[row for row in rows if row])


def main_menu_kb(lang: str) -> InlineKeyboardMarkup:
    def btn(key: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=t(lang, key), callback_data=MenuCB(action=action).pack())

    # Shape, not just contents: one full-width primary action, then the two
    # shortcuts into it, then browsing, then the customer's own things, then
    # the small stuff paired off at the bottom. Eight stacked full-width
    # buttons read as a wall; this reads as four groups.
    return markup(
        [btn("menu.build", MenuAction.BUILD)],
        [btn("menu.budget", MenuAction.BUDGET), btn("menu.games", MenuAction.GAMES)],
        [btn("menu.presets", MenuAction.PRESETS), btn("menu.accessories", MenuAction.ACCESSORIES)],
        [btn("menu.compare", MenuAction.COMPARE), btn("menu.mybuilds", MenuAction.MYBUILDS)],
        [
            btn("menu.about", MenuAction.ABOUT),
            btn("menu.help", MenuAction.HELP),
            btn("menu.language", MenuAction.LANGUAGE),
        ],
    )


def language_kb() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=LangCB(code=code).pack())
        for code, label in LANGUAGE_LABELS.items()
    ]
    return markup(*chunk(buttons, 1))


def back_to_menu_kb(lang: str) -> InlineKeyboardMarkup:
    return markup(
        [
            InlineKeyboardButton(
                text=t(lang, "nav.menu"), callback_data=NavCB(action=NavAction.MENU).pack()
            )
        ]
    )


def nav_row(lang: str, *, with_back: bool = True) -> Row:
    row: Row = []
    if with_back:
        row.append(
            InlineKeyboardButton(
                text=t(lang, "nav.back"), callback_data=NavCB(action=NavAction.BACK).pack()
            )
        )
    row.append(
        InlineKeyboardButton(
            text=t(lang, "nav.cancel"), callback_data=NavCB(action=NavAction.CANCEL).pack()
        )
    )
    return row
