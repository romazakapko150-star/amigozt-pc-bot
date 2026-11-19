"""Rendering of configurator messages (HTML parse mode).

Every value that can originate from user input goes through ``html.escape``:
a game title like ``<b>lol`` must never break the message or inject markup.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from functools import lru_cache
from html import escape
from typing import Any

from app.bot.flows.configurator import (
    PICK_CATEGORY_KEY,
    PICK_OPTIONS_KEY,
    StepId,
    progress,
)
from app.bot.views.chrome import note
from app.domain.components import ComponentCategory
from app.domain.enums import (
    MAX_BUDGET_PLN,
    MAX_PRIORITIES,
    MIN_BUDGET_PLN,
    Aesthetics,
    CpuBrand,
    GpuBrand,
    Priority,
    Purpose,
    Resolution,
)
from app.domain.labels import (
    CPU_BRAND_LABELS,
    GPU_BRAND_LABELS,
    format_price_pln,
    format_ram,
    format_storage,
)
from app.domain.requirements import BuildRequirements
from app.i18n import t
from app.services.catalog import get_catalog
from app.services.pricing import EstimatePriceProvider
from app.services.recommendation import BuildOption


@lru_cache(maxsize=1)
def estimate_prices() -> dict[str, Decimal]:
    """Indicative price per component id. Cached: the catalogue is static."""
    catalog = get_catalog()
    offers = EstimatePriceProvider().get_offers([c.id for c in catalog])
    return {cid: found[0].price_pln for cid, found in offers.items() if found}


#: Steps that get an extra explanatory line under the question.
_HINTS: dict[StepId, str] = {
    StepId.BUDGET: "cfg.budget.hint",
    StepId.RAM: "cfg.ram.hint",
    StepId.PRIORITY: "cfg.priority.hint",
    StepId.MONITOR: "cfg.monitor.hint",
    StepId.PERIPHERALS: "cfg.peripherals.hint",
}


def _selected_count(step: StepId, answers: dict[str, Any]) -> int:
    """How many boxes are ticked on a multi-select step."""
    if step is StepId.PRIORITY:
        return len(answers.get("priorities") or [])
    if step is StepId.PERIPHERALS:
        setup = answers.get("setup") or {}
        return len([c for c in setup if c != ComponentCategory.MONITOR.value])
    return 0


def render_picked_setup(answers: dict[str, Any], lang: str) -> list[str]:
    """The desk items chosen so far: what they are and what they cost.

    A ticked box says a category was chosen; it does not say *which* mouse.
    The model is picked automatically to suit the build, so the customer has
    to be shown it at the moment it is chosen, not two steps later.
    """
    setup = answers.get("setup") or {}
    picks = {c: cid for c, cid in setup.items() if c != ComponentCategory.MONITOR.value}
    if not picks:
        return []

    catalog = get_catalog()
    prices = estimate_prices()
    lines: list[str] = [""]
    for category_value, component_id in picks.items():
        component = catalog.get(component_id)
        if component is None:
            continue
        price = prices.get(component_id)
        priced = f" · ≈{format_price_pln(price)}" if price is not None else ""
        label = t(lang, f"part.{category_value}")
        lines.append(f"☑️ <b>{label}</b>: {escape(component.name)}{priced}")
    return lines


def render_chosen_monitor(answers: dict[str, Any], lang: str) -> list[str]:
    """The screen the customer ticked, named and priced."""
    setup = answers.get("setup") or {}
    component_id = setup.get(ComponentCategory.MONITOR.value)
    if not component_id:
        return []
    component = get_catalog().get(component_id)
    if component is None:
        return []
    price = estimate_prices().get(component_id)
    priced = f" · ≈{format_price_pln(price)}" if price is not None else ""
    return ["", f"☑️ <b>{escape(component.name)}</b>{priced}"]


def render_offer(answers: dict[str, Any], lang: str) -> list[str]:
    """The numbered products on the shelf the customer opened.

    The numbers match the buttons and the tiles in the photo above, so the
    three ways of reading the same list cannot disagree.
    """
    offered = answers.get(PICK_OPTIONS_KEY) or []
    chosen = (answers.get("setup") or {}).get(answers.get(PICK_CATEGORY_KEY) or "")
    catalog = get_catalog()
    prices = estimate_prices()
    lines: list[str] = [""]
    for index, component_id in enumerate(offered, start=1):
        component = catalog.get(component_id)
        if component is None:
            continue
        price = prices.get(component_id)
        priced = f" · ≈{format_price_pln(price)}" if price is not None else ""
        tick = "☑️ " if component_id == chosen else ""
        lines.append(f"{tick}<b>{index}.</b> {escape(component.name)}{priced}")
    return lines


def render_question(step: StepId, answers: dict[str, Any], lang: str) -> str:
    current, total = progress(step, answers)
    header = f"<i>{t(lang, 'common.progress', current=current, total=total)}</i>"
    body = t(lang, f"cfg.{step.value}.q")

    lines = [header, "", body]

    if step is StepId.GAMES:
        selected = len(answers.get("games") or [])
        lines.append("")
        lines.append(note(t(lang, "cfg.games.hint", count=selected)))
    elif (hint_key := _HINTS.get(step)) is not None:
        lines.append("")
        # Counters make it obvious that a step takes several answers; the
        # other hints simply ignore the extra placeholders.
        lines.append(
            note(t(lang, hint_key, count=_selected_count(step, answers), max=MAX_PRIORITIES))
        )
        if step is StepId.PERIPHERALS:
            if answers.get(PICK_CATEGORY_KEY):
                lines.append("")
                lines.append(note(t(lang, "cfg.peripherals.pick")))
                lines.extend(render_offer(answers, lang))
            else:
                lines.extend(render_picked_setup(answers, lang))
        elif step is StepId.MONITOR:
            lines.extend(render_chosen_monitor(answers, lang))

    return "\n".join(lines)


def render_budget_error(lang: str) -> str:
    return t(lang, "cfg.budget.invalid", min=MIN_BUDGET_PLN, max=MAX_BUDGET_PLN)


def _connectivity_key(requirements: BuildRequirements) -> str:
    if requirements.wifi and requirements.bluetooth:
        return "wifi_bt"
    if requirements.wifi:
        return "wifi"
    if requirements.bluetooth:
        return "bt"
    return "none"


#: Emoji shown next to each summary field so the card scans quickly on a phone
#: without relying on column alignment.
_FIELD_EMOJI: dict[str, str] = {
    "summary.purpose": "🎯",
    "summary.resolution": "🖥",
    "summary.fps": "⚡",
    "summary.priority": "🧭",
    "summary.aesthetics": "🎨",
    "summary.connectivity": "📶",
    "summary.storage": "💾",
    "summary.ram": "🧠",
    "summary.cpu": "🧩",
    "summary.gpu": "🖼",
}


def render_summary(
    requirements: BuildRequirements,
    lang: str,
    answers: dict[str, Any] | None = None,
    options: Sequence[BuildOption] | None = None,
) -> str:
    """Mobile-first card: short lines, long values on a line of their own.

    The price never shares a line with a label, because a wrapped or clipped
    price is the one thing a customer must not misread on a narrow screen.
    Game titles get their own block for the same reason.
    """
    auto = t(lang, "summary.auto")

    def row(label_key: str, value: str) -> str:
        return f"{_FIELD_EMOJI[label_key]} <b>{t(lang, label_key)}:</b> {value}"

    lines: list[str] = [
        t(lang, "summary.ready"),
        "",
        f"💰 <b>{t(lang, 'summary.budget')}</b>",
        f"<b>{format_price_pln(requirements.budget_pln)}</b>",
        "",
        row("summary.purpose", t(lang, f"purpose.{Purpose(requirements.purpose).value}")),
    ]

    lines.append(
        row(
            "summary.resolution",
            t(lang, f"resolution.{Resolution(requirements.resolution).value}"),
        )
    )
    if requirements.target_fps is not None:
        lines.append(row("summary.fps", f"{requirements.target_fps.value} FPS"))

    lines.append(
        row(
            "summary.priority",
            ", ".join(t(lang, f"priority.{Priority(p).value}") for p in requirements.priorities),
        )
    )
    lines.append(
        row(
            "summary.aesthetics",
            t(lang, f"aesthetics.{Aesthetics(requirements.aesthetics).value}"),
        )
    )
    lines.append(
        row("summary.connectivity", t(lang, f"connectivity.{_connectivity_key(requirements)}"))
    )
    lines.append(
        row(
            "summary.storage",
            format_storage(requirements.storage_gb) if requirements.storage_gb else auto,
        )
    )
    lines.append(
        row("summary.ram", format_ram(requirements.ram_gb) if requirements.ram_gb else auto)
    )

    cpu = CpuBrand(requirements.cpu_brand)
    gpu = GpuBrand(requirements.gpu_brand)
    lines.append(row("summary.cpu", CPU_BRAND_LABELS.get(cpu) or t(lang, "brand.any")))
    lines.append(row("summary.gpu", GPU_BRAND_LABELS.get(gpu) or t(lang, "brand.any")))

    if requirements.games:
        lines.extend(["", f"🎮 <b>{t(lang, 'summary.games')}</b>"])
        lines.extend(f"• {escape(title)}" for title in requirements.game_titles)

    # What these answers actually buy, before the customer commits to them.
    if options:
        lines.extend(["", f"🖥 <b>{t(lang, 'summary.variants')}</b>"])
        for index, option in enumerate(options, start=1):
            tier = t(lang, f"build.tier.{option.tier.value}")
            lines.append(
                f"<b>{index}.</b> {tier} — <b>{format_price_pln(option.client_price_pln)}</b>"
            )
            headline = ", ".join(
                escape(option.parts[category].name)
                for category in (ComponentCategory.CPU, ComponentCategory.GPU)
                if category in option.parts
            )
            if headline:
                lines.append(f"     {headline}")

    # The desk the customer just chose belongs on the card that summarises
    # the order: without it they confirm a monitor and a mouse they never see.
    desk = render_desk_summary(answers or {}, lang)
    if desk:
        lines.extend(["", f"🖥 <b>{t(lang, 'summary.setup')}</b>", *desk])

    lines.extend(["", t(lang, "summary.hint_next")])
    return "\n".join(lines)


def render_desk_summary(answers: dict[str, Any], lang: str) -> list[str]:
    """Every setup item the customer picked, monitor included, with prices."""
    setup = answers.get("setup") or {}
    if not setup:
        return []
    catalog = get_catalog()
    prices = estimate_prices()
    lines: list[str] = []
    for category_value, component_id in setup.items():
        component = catalog.get(component_id)
        if component is None:
            continue
        price = prices.get(component_id)
        priced = f" · ≈{format_price_pln(price)}" if price is not None else ""
        lines.append(
            f"• <b>{t(lang, f'part.{category_value}')}</b>: {escape(component.name)}{priced}"
        )
    return lines


def render_order_confirmation(requirements: BuildRequirements, lang: str) -> str:
    """Short confirmation shown before a lead is created.

    Deliberately brief: the full card is still on screen above it, and a second
    wall of text would push the confirm button off a phone screen.
    """
    purpose = t(lang, f"purpose.{Purpose(requirements.purpose).value}")
    return (
        f"🛒 <b>{t(lang, 'order.confirm_q')}</b>\n\n"
        f"💰 <b>{t(lang, 'summary.budget')}</b>\n"
        f"<b>{format_price_pln(requirements.budget_pln)}</b>\n\n"
        f"{_FIELD_EMOJI['summary.purpose']} {purpose}"
    )
