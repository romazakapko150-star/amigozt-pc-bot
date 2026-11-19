"""Display labels that are intentionally NOT translated.

Brand and product names must read identically in every locale - translating
"NVIDIA GeForce" or "Red Dead Redemption 2" would be wrong, not helpful.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.domain.enums import CpuBrand, GpuBrand

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from app.domain.components import Component

CPU_BRAND_LABELS: dict[CpuBrand, str] = {
    CpuBrand.AMD: "AMD Ryzen",
    CpuBrand.INTEL: "Intel Core",
}

GPU_BRAND_LABELS: dict[GpuBrand, str] = {
    GpuBrand.NVIDIA: "NVIDIA GeForce",
    GpuBrand.AMD: "AMD Radeon",
    GpuBrand.INTEL: "Intel Arc",
}


def monitor_label(component: Component) -> str:
    """``27" 1440p 165 Hz - Gigabyte M27Q``: the numbers that decide, first."""
    spec = component.spec
    size = getattr(spec, "size_inch", None)
    resolution = getattr(spec, "resolution", None)
    refresh = getattr(spec, "refresh_hz", None)
    head = " ".join(
        part
        for part in (
            f'{size:g}"' if size else "",
            SHORT_RESOLUTIONS.get(str(resolution).replace(" ", ""), str(resolution or "")),
            f"{refresh} Hz" if refresh else "",
        )
        if part
    )
    return f"{head} · {component.name}" if head else component.name


#: Marketing shorthand the customer already knows.
SHORT_RESOLUTIONS: dict[str, str] = {
    "1920x1080": "1080p",
    "2560x1440": "1440p",
    "3440x1440": "UWQHD",
    "3840x2160": "4K",
}


def format_storage(gb: int) -> str:
    """500 -> ``500 GB``; 1000 -> ``1 TB``; 1500 -> ``1.5 TB``."""
    if gb < 1000:
        return f"{gb} GB"
    tb = gb / 1000
    return f"{tb:g} TB"


def format_ram(gb: int) -> str:
    return f"{gb} GB"


def format_price_pln(value: float | int | Decimal) -> str:
    """Poland-friendly formatting: ``5 500 PLN``.

    Rounds to whole złoty: a build card quoting groszy reads like a bill,
    and the underlying prices are estimates anyway.
    """
    return f"{round(value):,}".replace(",", " ") + " PLN"
