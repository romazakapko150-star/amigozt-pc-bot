"""Accessory catalogue rendering."""

from __future__ import annotations

from decimal import Decimal
from html import escape

from app.domain.components import Component, ComponentCategory, MonitorSpec, PeripheralSpec
from app.domain.labels import format_price_pln
from app.i18n import t

#: Order the accessory shelves are offered in - screens first, then the things
#: a customer touches, then furniture.
ACCESSORY_ORDER: tuple[ComponentCategory, ...] = (
    ComponentCategory.MONITOR,
    ComponentCategory.MOUSE,
    ComponentCategory.KEYBOARD,
    ComponentCategory.HEADSET,
    ComponentCategory.MICROPHONE,
    ComponentCategory.WEBCAM,
    ComponentCategory.SPEAKERS,
    ComponentCategory.MOUSEPAD,
    ComponentCategory.CHAIR,
    ComponentCategory.DESK,
)


def render_categories(lang: str) -> str:
    return f"{t(lang, 'acc.title')}\n\n{t(lang, 'acc.pick_category')}"


def render_list(
    category: ComponentCategory,
    items: list[Component],
    prices: dict[str, Decimal],
    lang: str,
) -> str:
    if not items:
        return f"{t(lang, 'acc.title')}\n\n{t(lang, 'acc.empty')}"

    lines = [
        f"{t(lang, f'part.{category.value}')}",
        "",
        t(lang, "acc.count", count=len(items)),
        "",
    ]
    for index, component in enumerate(items, start=1):
        price = prices.get(component.id)
        price_text = f"≈{format_price_pln(price)}" if price is not None else "—"
        lines.append(f"<b>{index}.</b> {escape(component.name)}\n     {price_text}")

    lines.extend(["", t(lang, "acc.open_hint")])
    return "\n".join(lines)


def _monitor_rows(spec: MonitorSpec, lang: str) -> list[str]:
    sync = t(lang, "acc.yes") if spec.adaptive_sync else t(lang, "acc.no")
    return [
        f'• <b>{t(lang, "acc.spec.size")}:</b> {spec.size_inch:g}"',
        f"• <b>{t(lang, 'acc.spec.resolution')}:</b> {spec.resolution}",
        f"• <b>{t(lang, 'acc.spec.refresh')}:</b> {spec.refresh_hz} Hz",
        f"• <b>{t(lang, 'acc.spec.panel')}:</b> {spec.panel}",
        f"• <b>{t(lang, 'acc.spec.response')}:</b> {spec.response_ms:g} ms",
        f"• <b>{t(lang, 'acc.spec.sync')}:</b> {sync}",
    ]


def peripheral_summary(component: Component, lang: str) -> str:
    """What this product is, in the customer's language, derived from data.

    The catalogue's own ``summary`` is one language's prose and was being
    shown to everyone; this composes the same sentence from the structured
    spec instead, so it is right in all four locales and stays right for
    every product added later.
    """
    spec = component.spec
    kind = t(lang, f"acc.kind.{component.category.value}")
    traits = [
        t(lang, "acc.trait.wireless" if getattr(spec, "wireless", False) else "acc.trait.wired")
    ]
    if getattr(spec, "rgb", False):
        traits.append(t(lang, "acc.trait.rgb"))
    return f"{kind} · {' · '.join(traits)}"


def _peripheral_rows(component: Component, spec: PeripheralSpec, lang: str) -> list[str]:
    rows = [f"<i>{escape(peripheral_summary(component, lang))}</i>"]
    rows.extend(f"• {escape(item)}" for item in spec.highlights)
    if spec.wireless:
        rows.append(f"• <b>{t(lang, 'acc.spec.wireless')}:</b> {t(lang, 'acc.yes')}")
    # Lighting is a buying reason for a keyboard or a mouse, and the catalogue
    # records it per product - so it is stated, never guessed.
    if spec.rgb:
        rows.append(f"• <b>{t(lang, 'acc.spec.lighting')}:</b> {t(lang, 'acc.spec.rgb')}")
    return rows


def render_item(component: Component, price: Decimal | None, lang: str) -> str:
    lines = [
        f"{t(lang, f'part.{component.category.value}')}",
        "",
        f"<b>{escape(component.name)}</b>",
        "",
    ]

    spec = component.spec
    if isinstance(spec, MonitorSpec):
        lines.extend(_monitor_rows(spec, lang))
    elif isinstance(spec, PeripheralSpec):
        lines.extend(_peripheral_rows(component, spec, lang))

    if price is not None:
        lines.extend(
            ["", f"💰 <b>{t(lang, 'build.total')}</b>", f"<b>≈{format_price_pln(price)}</b>"]
        )
        lines.extend(["", f"<i>{t(lang, 'acc.price_note')}</i>"])

    return "\n".join(lines)
