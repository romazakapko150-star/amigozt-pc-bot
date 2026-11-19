from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import (
    PICK_PREFIX,
    VALUE_AUTO,
    VALUE_BACK_TO_LIST,
    VALUE_CLEAR,
    VALUE_CUSTOM,
    VALUE_DONE,
    VALUE_GENERATE,
    VALUE_ORDER,
    VALUE_ORDER_BACK,
    VALUE_ORDER_CONFIRM,
    VALUE_SAVE,
    VALUE_SKIP,
    CfgCB,
    NavAction,
    NavCB,
)
from app.bot.flows.configurator import (
    MONITOR_OPTIONS_KEY,
    PICK_CATEGORY_KEY,
    PICK_OPTIONS_KEY,
    StepId,
)
from app.bot.keyboards.common import Row, markup, mobile_rows, nav_row
from app.domain.components import ComponentCategory
from app.domain.enums import (
    BUDGET_PRESETS_PLN,
    KNOWN_GAMES,
    PRIORITY_ORDER,
    RAM_PRESETS_GB,
    STORAGE_PRESETS_GB,
    Aesthetics,
    CpuBrand,
    GpuBrand,
    Purpose,
    Resolution,
    TargetFps,
    game_button_label,
)
from app.domain.labels import (
    CPU_BRAND_LABELS,
    GPU_BRAND_LABELS,
    format_ram,
    format_storage,
    monitor_label,
)
from app.i18n import t
from app.services.catalog import get_catalog
from app.services.recommendation.setup import PERIPHERAL_CATEGORIES

CONNECTIVITY_OPTIONS: tuple[str, ...] = ("wifi_bt", "wifi", "bt", "none")


def _btn(step: StepId, value: str, text: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=CfgCB(step=step.value, value=value).pack())


def _budget_rows(lang: str) -> list[Row]:
    buttons = [
        _btn(
            StepId.BUDGET,
            str(value),
            f"{value:,}".replace(",", " ") + ("+ PLN" if value >= 10000 else " PLN"),
        )
        for value in BUDGET_PRESETS_PLN
    ]
    rows = mobile_rows(buttons, 3)
    rows.append([_btn(StepId.BUDGET, VALUE_CUSTOM, t(lang, "nav.custom"))])
    return rows


def _games_rows(lang: str, selected: set[str]) -> list[Row]:
    buttons = [
        _btn(StepId.GAMES, key, f"{'✅ ' if key in selected else ''}{game_button_label(key)}")
        for key in KNOWN_GAMES
    ]
    rows = mobile_rows(buttons, 2)
    rows.append([_btn(StepId.GAMES, VALUE_CUSTOM, t(lang, "cfg.games.other"))])
    rows.append([_btn(StepId.GAMES, VALUE_DONE, t(lang, "nav.done"))])
    return rows


def _priority_rows(lang: str, selected: set[str]) -> list[Row]:
    """Several priorities may be ticked; "Done" closes the step."""
    buttons = [
        _btn(
            StepId.PRIORITY,
            p.value,
            f"{'☑️ ' if p.value in selected else '☐ '}{t(lang, f'priority.{p.value}')}",
        )
        for p in PRIORITY_ORDER
    ]
    rows = mobile_rows(buttons, 1)
    rows.append([_btn(StepId.PRIORITY, VALUE_DONE, t(lang, "nav.done"))])
    return rows


def _monitor_rows(answers: dict[str, Any], lang: str) -> list[Row]:
    """Offered monitors by position, never by id - callback data is 64 bytes."""
    chosen = (answers.get("setup") or {}).get(ComponentCategory.MONITOR.value)
    offered: list[str] = answers.get(MONITOR_OPTIONS_KEY) or []
    catalog = get_catalog()
    rows: list[Row] = []
    for index, component_id in enumerate(offered):
        component = catalog.get(component_id)
        if component is None:
            continue
        tick = "☑️ " if component_id == chosen else ""
        rows.append([_btn(StepId.MONITOR, str(index), f"{tick}{monitor_label(component)}")])
    if chosen:
        # Ticking a monitor must not be the end of the road: this is the only
        # button that means "yes, this one" and moves the flow on.
        rows.append([_btn(StepId.MONITOR, VALUE_DONE, t(lang, "cfg.monitor.continue"))])
    rows.append([_btn(StepId.MONITOR, VALUE_SKIP, t(lang, "cfg.monitor.skip"))])
    return rows


def _peripheral_rows(answers: dict[str, Any], lang: str) -> list[Row]:
    """The category list, or the products inside the category being browsed."""
    open_category = answers.get(PICK_CATEGORY_KEY)
    if open_category:
        return _product_rows(open_category, answers, lang)

    setup = answers.get("setup") or {}
    buttons = [
        _btn(
            StepId.PERIPHERALS,
            category.value,
            f"{'☑️ ' if category.value in setup else '☐ '}{t(lang, f'part.{category.value}')}",
        )
        for category in PERIPHERAL_CATEGORIES
    ]
    rows = mobile_rows(buttons, 2)
    rows.append([_btn(StepId.PERIPHERALS, VALUE_DONE, t(lang, "nav.done"))])
    return rows


def _product_rows(category_value: str, answers: dict[str, Any], lang: str) -> list[Row]:
    """Numbered products, then a way to drop the choice and go back."""
    chosen = (answers.get("setup") or {}).get(category_value)
    offered: list[str] = answers.get(PICK_OPTIONS_KEY) or []
    catalog = get_catalog()

    buttons: list[InlineKeyboardButton] = []
    for index, component_id in enumerate(offered):
        component = catalog.get(component_id)
        if component is None:
            continue
        tick = "☑️ " if component_id == chosen else ""
        buttons.append(_btn(StepId.PERIPHERALS, f"{PICK_PREFIX}{index}", f"{tick}{index + 1}"))

    rows = mobile_rows(buttons, 5)
    if chosen:
        rows.append([_btn(StepId.PERIPHERALS, VALUE_CLEAR, t(lang, "cfg.peripherals.clear"))])
    rows.append([_btn(StepId.PERIPHERALS, VALUE_BACK_TO_LIST, t(lang, "cfg.peripherals.back"))])
    return rows


def keyboard_for_step(step: StepId, answers: dict[str, Any], lang: str) -> InlineKeyboardMarkup:
    """Inline keyboard for a configurator step, including navigation."""
    rows: list[Row]

    match step:
        case StepId.BUDGET:
            rows = _budget_rows(lang)

        case StepId.PURPOSE:
            buttons = [_btn(step, p.value, t(lang, f"purpose.{p.value}")) for p in Purpose]
            rows = mobile_rows(buttons, 2)

        case StepId.GAMES:
            rows = _games_rows(lang, set(answers.get("games") or []))

        case StepId.RESOLUTION:
            buttons = [_btn(step, r.value, t(lang, f"resolution.{r.value}")) for r in Resolution]
            rows = mobile_rows(buttons, 1)

        case StepId.FPS:
            buttons = [_btn(step, f.value, f"{f.value} FPS") for f in TargetFps]
            rows = mobile_rows(buttons, 3)

        case StepId.PRIORITY:
            rows = _priority_rows(lang, set(answers.get("priorities") or []))

        case StepId.AESTHETICS:
            buttons = [_btn(step, a.value, t(lang, f"aesthetics.{a.value}")) for a in Aesthetics]
            rows = mobile_rows(buttons, 2)

        case StepId.CONNECTIVITY:
            buttons = [
                _btn(step, option, t(lang, f"connectivity.{option}"))
                for option in CONNECTIVITY_OPTIONS
            ]
            rows = mobile_rows(buttons, 1)

        case StepId.STORAGE:
            buttons = [_btn(step, str(gb), format_storage(gb)) for gb in STORAGE_PRESETS_GB]
            rows = mobile_rows(buttons, 2)
            rows.append([_btn(step, VALUE_AUTO, t(lang, "nav.auto"))])

        case StepId.RAM:
            buttons = [_btn(step, str(gb), format_ram(gb)) for gb in RAM_PRESETS_GB]
            rows = mobile_rows(buttons, 3)
            rows.append([_btn(step, VALUE_AUTO, t(lang, "nav.auto"))])

        case StepId.CPU:
            rows = [
                [_btn(step, CpuBrand.ANY.value, t(lang, "brand.any"))],
                [
                    _btn(step, CpuBrand.AMD.value, CPU_BRAND_LABELS[CpuBrand.AMD]),
                    _btn(step, CpuBrand.INTEL.value, CPU_BRAND_LABELS[CpuBrand.INTEL]),
                ],
            ]

        case StepId.GPU:
            rows = [
                [_btn(step, GpuBrand.ANY.value, t(lang, "brand.any"))],
                [
                    _btn(step, GpuBrand.NVIDIA.value, GPU_BRAND_LABELS[GpuBrand.NVIDIA]),
                    _btn(step, GpuBrand.AMD.value, GPU_BRAND_LABELS[GpuBrand.AMD]),
                ],
                [_btn(step, GpuBrand.INTEL.value, GPU_BRAND_LABELS[GpuBrand.INTEL])],
            ]

        case StepId.MONITOR:
            rows = _monitor_rows(answers, lang)

        case StepId.PERIPHERALS:
            rows = _peripheral_rows(answers, lang)

        case StepId.SUMMARY:
            # One action per row: the order CTA must be unmissable and
            # full-width on a phone.
            return markup(
                [_btn(step, VALUE_ORDER, t(lang, "order.button"))],
                [_btn(step, VALUE_GENERATE, t(lang, "summary.btn_generate"))],
                [
                    InlineKeyboardButton(
                        text=t(lang, "nav.back"),
                        callback_data=NavCB(action=NavAction.BACK).pack(),
                    ),
                    _btn(step, VALUE_SAVE, t(lang, "summary.btn_save")),
                ],
                [
                    InlineKeyboardButton(
                        text=t(lang, "nav.restart"),
                        callback_data=NavCB(action=NavAction.RESTART).pack(),
                    ),
                    InlineKeyboardButton(
                        text=t(lang, "nav.menu"),
                        callback_data=NavCB(action=NavAction.MENU).pack(),
                    ),
                ],
            )

        case _:  # pragma: no cover - exhaustive above
            rows = []

    rows.append(nav_row(lang))
    return markup(*rows)


def order_confirm_kb(lang: str) -> InlineKeyboardMarkup:
    """Confirmation step between the card and an actual lead."""
    step = StepId.SUMMARY
    return markup(
        [_btn(step, VALUE_ORDER_CONFIRM, t(lang, "order.confirm_yes"))],
        [
            _btn(step, VALUE_ORDER_BACK, t(lang, "order.edit")),
            _btn(step, VALUE_ORDER_BACK, t(lang, "nav.cancel")),
        ],
    )
