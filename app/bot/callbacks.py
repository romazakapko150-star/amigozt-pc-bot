"""Typed callback-data contracts.

Using aiogram's ``CallbackData`` factories instead of raw strings keeps the
64-byte Telegram limit in check and makes handler filters explicit.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="m"):
    """Main-menu navigation."""

    action: str


class CfgCB(CallbackData, prefix="c"):
    """An answer to a configurator step: ``step`` + selected ``value``."""

    step: str
    value: str


class NavCB(CallbackData, prefix="n"):
    """Cross-cutting navigation inside the configurator."""

    action: str  # back | cancel | restart | menu


class LangCB(CallbackData, prefix="l"):
    """Interface language selection."""

    code: str


class ReadyCB(CallbackData, prefix="rb"):
    """Ready-build shelf navigation."""

    action: str  # f=filters l=list b=budget o=open r=order
    value: str
    page: int


class CompareCB(CallbackData, prefix="cm"):
    """Component comparison. ``pick`` holds list positions, not ids: two
    component ids would blow past Telegram's 64-byte callback_data limit."""

    action: str  # c=categories 1=first 2=second r=result
    category: str
    pick: str


class AccessoryCB(CallbackData, prefix="ac"):
    """Accessory catalogue. ``pick`` is a list position, not a component id."""

    action: str  # c=categories l=list i=item
    category: str
    pick: str


class VisualCB(CallbackData, prefix="v"):
    """Re-render a build image in another visual preset.

    ``kind`` is b (a customer build row) or r (a ready build); ``preset`` is a
    VisualPreset key, or empty for the default look.
    """

    kind: str
    id: int
    preset: str


class AdminCB(CallbackData, prefix="a"):
    """Admin panel navigation."""

    action: str  # home | leads | builds | stats


class RankCB(CallbackData, prefix="rk"):
    """Ready-build profitability rankings (admin only)."""

    sort: str


class LeadCB(CallbackData, prefix="ld"):
    """An admin action on one lead."""

    lead_id: int
    action: str  # take | contact | reject | complete


class AdminAction:
    HOME = "home"
    LEADS = "leads"
    BUILDS = "builds"
    STATS = "stats"
    RANKINGS = "rank"


class LeadAction:
    TAKE = "take"
    CONTACT = "contact"
    REJECT = "reject"
    COMPLETE = "complete"


class MenuAction:
    BUILD = "build"
    BUDGET = "budget"
    GAMES = "games"
    PRESETS = "presets"
    COMPARE = "compare"
    MYBUILDS = "mybuilds"
    ABOUT = "about"
    HELP = "help"
    LANGUAGE = "language"
    ACCESSORIES = "acc"


class NavAction:
    BACK = "back"
    CANCEL = "cancel"
    RESTART = "restart"
    MENU = "menu"


#: Sentinel values shared by several steps.
VALUE_AUTO = "auto"
VALUE_CUSTOM = "custom"
VALUE_DONE = "done"
VALUE_ORDER = "order"
VALUE_ORDER_CONFIRM = "ordyes"
VALUE_ORDER_BACK = "ordno"
VALUE_GENERATE = "generate"
VALUE_SAVE = "save"
VALUE_SKIP = "skip"
#: Peripherals step: clear this category, or leave the product list.
VALUE_CLEAR = "clr"
VALUE_BACK_TO_LIST = "cats"
#: Prefix for "the product at this position", kept to three bytes so the
#: whole callback stays far inside Telegram's 64-byte limit.
PICK_PREFIX = "p"
