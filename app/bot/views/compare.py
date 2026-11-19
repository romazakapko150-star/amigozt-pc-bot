"""Side-by-side component comparison.

Rendered as one short line per spec (``label: A / B``) rather than a table:
Telegram has no table support and a fixed-width layout wraps badly on a phone.
"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from app.domain.components import (
    Component,
    ComponentCategory,
    CpuSpec,
    GpuSpec,
    RamSpec,
    SsdSpec,
)
from app.domain.labels import format_price_pln, format_storage
from app.i18n import t

#: Categories worth comparing. Cases and coolers differ mostly by dimensions
#: the configurator already checks, so they are left out for now.
COMPARABLE: tuple[ComponentCategory, ...] = (
    ComponentCategory.CPU,
    ComponentCategory.GPU,
    ComponentCategory.RAM,
    ComponentCategory.SSD,
)

Row = tuple[str, str]


def _cpu_rows(spec: CpuSpec) -> list[Row]:
    return [
        ("cores", str(spec.cores)),
        ("threads", str(spec.threads)),
        ("socket", spec.socket.value),
        ("tdp", f"{spec.max_power_w} W"),
        ("memory_support", "/".join(m.value for m in spec.memory_types)),
        ("gaming_index", str(spec.gaming_index)),
        ("perf_index", str(spec.performance_index)),
    ]


def _gpu_rows(spec: GpuSpec) -> list[Row]:
    return [
        ("vram", f"{spec.vram_gb} GB"),
        ("perf_index", str(spec.performance_index)),
        ("tdp", f"{spec.tdp_w} W"),
        ("psu_rec", f"{spec.recommended_psu_w} W"),
        ("length", f"{spec.length_mm} mm"),
        ("upscaling", ", ".join(spec.upscaling) or "—"),
    ]


def _ram_rows(spec: RamSpec) -> list[Row]:
    return [
        ("memory_type", spec.memory_type.value),
        ("capacity", f"{spec.total_capacity_gb} GB"),
        ("speed", f"{spec.speed_mhz} MHz"),
        ("latency", f"CL{spec.cas_latency}"),
    ]


def _ssd_rows(spec: SsdSpec) -> list[Row]:
    return [
        ("capacity", format_storage(spec.capacity_gb)),
        ("read", f"{spec.read_mb_s} MB/s"),
        ("write", f"{spec.write_mb_s} MB/s"),
        ("pcie", f"Gen {spec.pcie_generation}"),
    ]


def spec_rows(component: Component) -> list[Row]:
    spec = component.spec
    if isinstance(spec, CpuSpec):
        return _cpu_rows(spec)
    if isinstance(spec, GpuSpec):
        return _gpu_rows(spec)
    if isinstance(spec, RamSpec):
        return _ram_rows(spec)
    if isinstance(spec, SsdSpec):
        return _ssd_rows(spec)
    return []


def render_comparison(
    left: Component,
    right: Component,
    lang: str,
    prices: dict[str, Decimal] | None = None,
) -> str:
    """Compare two parts of the same category."""
    lines = [
        t(lang, "cmp.title"),
        "",
        f"🅰 <b>{escape(left.name)}</b>",
        f"🅱 <b>{escape(right.name)}</b>",
        "",
    ]

    left_rows = dict(spec_rows(left))
    right_rows = dict(spec_rows(right))

    for key in dict.fromkeys([*left_rows, *right_rows]):
        left_value = left_rows.get(key, "—")
        right_value = right_rows.get(key, "—")
        lines.append(f"<b>{t(lang, f'cmp.spec.{key}')}</b>\n🅰 {left_value}  ·  🅱 {right_value}")

    if prices:
        left_price = prices.get(left.id)
        right_price = prices.get(right.id)
        if left_price is not None or right_price is not None:
            lines.append(
                f"<b>{t(lang, 'cmp.spec.price')}</b>\n"
                f"🅰 ≈{format_price_pln(left_price) if left_price else '—'}  ·  "
                f"🅱 ≈{format_price_pln(right_price) if right_price else '—'}"
            )

    notes = [t(lang, "cmp.index_note")]
    if prices:
        notes.append(t(lang, "cmp.price_note"))
    lines.extend(["", f"<i>{' '.join(notes)}</i>"])

    return "\n".join(lines)
