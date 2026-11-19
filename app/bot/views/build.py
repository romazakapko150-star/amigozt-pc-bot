"""Build card rendering.

Mobile-first: one part per block, the label on its own line and the part name
below it, so a long model name wraps naturally instead of colliding with a
price. Money gets its own block: parts, assembly, total.

Nothing here may read the quote's admin side (market cost, profit, hours).
The customer sees two numbers and their sum - that is the whole deal.
"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from app.bot.views.chrome import note
from app.domain.components import PC_CATEGORIES, ComponentCategory
from app.domain.enums import BuildTier
from app.domain.labels import format_price_pln
from app.domain.lighting import LightingPlan
from app.i18n import t
from app.services.recommendation import BuildOption
from app.services.recommendation.setup import SetupSelection

#: The compatibility warnings worth surfacing to a customer. Anything else is
#: an internal detail the shop deals with.
_CUSTOMER_WARNINGS = {
    "memory_speed",
    "psu_tight",
    "ssd_pcie_generation",
    "bios_update",
    "gpu_power_adapter",
    "front_usb_c",
    "memory_four_modules",
    "memory_profile",
    "monitor_output",
}


def render_order_blocked(reason_codes: list[str], lang: str) -> str:
    """The pre-order check failed: say what, in the customer's words."""
    lines = [t(lang, "order.blocked"), "", t(lang, "order.blocked_hint"), ""]
    lines.extend(f"• {t(lang, f'compat.block.{code}')}" for code in reason_codes)
    return "\n".join(lines)


def render_setup_block(selection: SetupSelection, lang: str) -> list[str]:
    """The desk, its prices, and the grand total - or nothing at all.

    Kept separate from the machine on purpose: the customer must be able to
    see what the PC costs without the extras folded into it.
    """
    if not selection:
        return []
    lines = ["", f"🖥 <b>{t(lang, 'setup.title')}</b>"]
    for category, component in selection.items.items():
        price = selection.prices.get(component.id)
        priced = f" — {format_price_pln(price)}" if price is not None else ""
        lines.append(f"{t(lang, f'part.{category.value}')}: {escape(component.name)}{priced}")
    lines.append(f"🧾 <b>{t(lang, 'setup.total')}</b> {format_price_pln(selection.total_pln)}")
    return lines


def render_lighting(plan: LightingPlan, lang: str) -> list[str]:
    """What this machine does about lighting, in one honest line.

    Read from :mod:`app.domain.lighting`, which reads the catalogue - the
    same object the picture is drawn from, so the card and the photograph
    cannot contradict each other. A build whose parts have no LEDs is never
    described as lit, however firmly the customer ticked RGB.
    """
    if plan.promised_but_missing:
        return [f"💡 {t(lang, 'build.lighting.unavailable')}"]
    if not plan.show_lighting:
        return []
    parts = ", ".join(t(lang, f"part.{name}") for name in plan.lit_parts)
    key = "build.lighting.featured" if plan.emphasise else "build.lighting.available"
    line = f"💡 {t(lang, key, parts=parts)}"
    if plan.capabilities.any_addressable:
        line += f" · {t(lang, 'build.lighting.addressable')}"
    return [line]


def render_build_card(option: BuildOption, lang: str, setup: SetupSelection | None = None) -> str:
    tier_label = t(lang, f"build.tier.{BuildTier(option.tier).value}")
    quote = option.quote

    lines = [
        t(lang, "build.ready"),
        f"<b>{tier_label}</b>",
        "",
    ]

    for category in PC_CATEGORIES:
        component = option.parts.get(category)
        if component is None:
            continue
        lines.append(t(lang, f"part.{category.value}"))
        lines.append(escape(component.name))
        lines.append("")

    # Parts and assembly are separate lines on purpose: the customer should
    # see what the hardware costs and what the work costs.
    lines.append(f"🧾 <b>{t(lang, 'build.components_line')}</b>")
    lines.append(format_price_pln(quote.components_price_pln))
    lines.append(f"🛠️ <b>{t(lang, 'build.assembly_line', tier=escape(quote.service_tier_name))}</b>")
    lines.append(format_price_pln(quote.service_fee_pln))
    lines.append("")
    lines.append(f"💰 <b>{t(lang, 'build.total')}</b>")
    lines.append(f"<b>{format_price_pln(option.client_price_pln)}</b>")

    if setup:
        lines.extend(render_setup_block(setup, lang))
        lines.append("")
        lines.append(
            f"🧮 <b>{t(lang, 'setup.grand_total')}</b> "
            f"<b>{format_price_pln(option.client_price_pln + setup.total_pln)}</b>"
        )

    lighting = render_lighting(option.lighting, lang)
    if lighting:
        lines.extend(["", *lighting])

    key = "build.approx" if option.is_approximate else "build.verified_note"
    lines.extend(["", note(f"{t(lang, key)}\n{t(lang, 'build.assembly_hint')}")])

    if "legacy_platform" in option.notes:
        lines.extend(["", t(lang, "build.legacy_note")])

    surfaced = [issue for issue in option.report.warnings if issue.code in _CUSTOMER_WARNINGS]
    if surfaced:
        lines.extend(["", f"<b>{t(lang, 'build.warnings')}</b>"])
        lines.extend(f"• {t(lang, f'compat.{issue.code}')}" for issue in surfaced)

    # Frame rates come from recorded benchmarks only. There are none yet, so
    # the card says so rather than inventing numbers.
    lines.extend(["", f"🎯 <i>{t(lang, 'build.fps_unavailable')}</i>"])

    return "\n".join(lines)


def render_no_build(minimum_price_pln: Decimal | None, lang: str) -> str:
    if minimum_price_pln is None:
        return t(lang, "build.none_generic")
    return t(lang, "build.none", minimum=format_price_pln(minimum_price_pln))


def components_payload(option: BuildOption) -> dict[str, str]:
    """Component ids per category, for the ``builds.components`` JSON column."""
    return {category.value: component.id for category, component in option.parts.items()}


def component_names(option: BuildOption) -> dict[str, str]:
    return {
        ComponentCategory(category).value: component.name
        for category, component in option.parts.items()
    }
