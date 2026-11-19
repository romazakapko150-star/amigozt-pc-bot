"""Rendering for the ready-build shelf."""

from __future__ import annotations

import re
from decimal import Decimal
from html import escape

from app.bot.views.build import render_lighting
from app.bot.views.chrome import note
from app.db.models import ReadyBuild
from app.domain.components import PC_CATEGORIES, Component, ComponentCategory
from app.domain.labels import format_price_pln
from app.domain.lighting import plan_lighting
from app.i18n import t
from app.services.catalog import Catalog

#: ``starter-4600`` -> ``starter``: a shelf slug is "<recipe>-<budget>".
_RECIPE_KEY = re.compile(r"-\d+$")


def shelf_description(build: ReadyBuild, lang: str) -> str:
    """The recipe's pitch in the customer's language.

    The database row keeps the seeded text; the locale is asked first so an
    English customer never reads the Russian original. A recipe with no
    translation yet falls back to the stored line rather than leaving the
    card blank.
    """
    key = f"shelf.desc.{_RECIPE_KEY.sub('', build.slug or '')}"
    translated = t(lang, key)
    return (build.description or "") if translated == key else translated


def render_filters(total: int, lang: str) -> str:
    return (
        f"{t(lang, 'ready.title')}\n\n"
        f"{t(lang, 'ready.count', count=total)}\n\n"
        f"{t(lang, 'ready.pick_filter')}"
    )


def render_row(index: int, build: ReadyBuild) -> str:
    """One line per build: number, name, price, and a lighting badge.

    The badge is one character on purpose - a shelf row has to stay
    scannable on a phone - and it appears only for builds whose parts really
    glow, so it means something when it is there.
    """
    price = (
        format_price_pln(build.reference_price_pln)
        if build.reference_price_pln is not None
        else "—"
    )
    badge = " 🌈" if build.rgb else ""
    return f"<b>{index}.</b> {escape(build.name)}{badge}\n     {price}"


def render_list(builds: list[ReadyBuild], total: int, page: int, pages: int, lang: str) -> str:
    if not builds:
        return f"{t(lang, 'ready.title')}\n\n{t(lang, 'ready.empty')}"

    lines = [
        t(lang, "ready.title"),
        "",
        t(lang, "ready.count", count=total),
        "",
    ]
    start = (page - 1) * len(builds)
    lines.extend(render_row(start + offset, build) for offset, build in enumerate(builds, start=1))

    if pages > 1:
        lines.extend(["", f"<i>{t(lang, 'ready.page', page=page, total=pages)}</i>"])
    lines.extend(["", t(lang, "ready.open_hint")])
    return "\n".join(lines)


def render_build_page(build: ReadyBuild, catalog: Catalog, lang: str) -> str:
    """Full card for one shelf entry, in the same mobile layout as a fresh build."""
    lines = [f"<b>{escape(build.name)}</b>"]
    description = shelf_description(build, lang)
    if description:
        lines.append(note(escape(description)))
    lines.append("")

    for category in PC_CATEGORIES:
        component_id = build.components.get(category.value)
        if component_id is None:
            continue
        component = catalog.get(component_id)
        if component is None:
            continue
        lines.append(t(lang, f"part.{category.value}"))
        lines.append(escape(component.name))
        lines.append("")

    # Same source of truth as the configurator card and the picture: what
    # the parts can light up, and whether this shelf build shows it off.
    lighting = render_lighting(
        plan_lighting(parts_from(build, catalog), requested=bool(build.visual_priorities)),
        lang,
    )
    if lighting:
        lines.extend([*lighting, ""])

    if build.reference_price_pln is not None:
        lines.append(f"💰 <b>{t(lang, 'build.total')}</b>")
        lines.append(f"<b>{format_price_pln(Decimal(build.reference_price_pln))}</b>")
        # Same rule as a generated build: no benchmark data, no frame numbers.
        lines.extend(
            ["", note(f"{t(lang, 'build.approx')}\n🎯 {t(lang, 'build.fps_unavailable')}")]
        )
    return "\n".join(lines)


def parts_from(build: ReadyBuild, catalog: Catalog) -> dict[ComponentCategory, Component]:
    """Resolve stored component ids back into catalogue entries."""
    resolved: dict[ComponentCategory, Component] = {}
    for raw_category, component_id in build.components.items():
        try:
            category = ComponentCategory(raw_category)
        except ValueError:
            continue
        component = catalog.get(component_id)
        if component is not None:
            resolved[category] = component
    return resolved
