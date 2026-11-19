"""Itemised power budget of a build.

Sustained draw is summed part by part - CPU, GPU, board, memory, drives,
fans, pump, USB devices - and a safety factor is applied on top, because
transient GPU spikes sit far above the nominal TDP and a supply sized to
the plain sum trips under load.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.components import (
    CaseSpec,
    Component,
    ComponentCategory,
    CoolerSpec,
    CoolerType,
    CpuSpec,
    FanSpec,
    GpuSpec,
    RamSpec,
    SsdSpec,
)

#: Headroom on top of the estimated sustained draw.
PSU_SAFETY_FACTOR = 1.35

#: Kept for callers of the first engine version; the itemised budget below
#: replaces this flat figure.
BASE_SYSTEM_DRAW_W = 90

MOTHERBOARD_W = 40
RAM_MODULE_W = 4
SSD_W = 6
FAN_W = 3
PUMP_W = 10
USB_DEVICES_W = 20

Parts = dict[ComponentCategory, Component]


@dataclass(frozen=True, slots=True)
class PowerBudget:
    items: tuple[tuple[str, int], ...]
    safety_factor: float = PSU_SAFETY_FACTOR

    @property
    def total_w(self) -> int:
        return sum(watts for _, watts in self.items)

    @property
    def recommended_w(self) -> int:
        """Draw plus headroom, rounded up to the next 50 W."""
        required = self.total_w * self.safety_factor
        return int(-(-required // 50) * 50)

    def as_dict(self) -> dict:
        return {
            "items": [{"part": name, "watts": watts} for name, watts in self.items],
            "total_w": self.total_w,
            "safety_factor": self.safety_factor,
            "recommended_w": self.recommended_w,
        }


def power_budget(parts: Parts) -> PowerBudget:
    items: list[tuple[str, int]] = []

    cpu = parts.get(ComponentCategory.CPU)
    if cpu is not None and isinstance(cpu.spec, CpuSpec):
        items.append(("CPU", cpu.spec.max_power_w))

    gpu = parts.get(ComponentCategory.GPU)
    if gpu is not None and isinstance(gpu.spec, GpuSpec):
        items.append(("GPU", gpu.spec.tdp_w))

    if ComponentCategory.MOTHERBOARD in parts:
        items.append(("Motherboard", MOTHERBOARD_W))

    ram = parts.get(ComponentCategory.RAM)
    if ram is not None and isinstance(ram.spec, RamSpec):
        items.append((f"RAM ({ram.spec.modules} modules)", RAM_MODULE_W * ram.spec.modules))

    ssd = parts.get(ComponentCategory.SSD)
    if ssd is not None and isinstance(ssd.spec, SsdSpec):
        items.append(("SSD", SSD_W))

    fans = 0
    case = parts.get(ComponentCategory.CASE)
    if case is not None and isinstance(case.spec, CaseSpec):
        fans += case.spec.included_fans
    cooler = parts.get(ComponentCategory.COOLER)
    if cooler is not None and isinstance(cooler.spec, CoolerSpec):
        fans += cooler.spec.fans if cooler.spec.fans is not None else 1
        if cooler.spec.cooler_type is CoolerType.AIO:
            items.append(("Pump", PUMP_W))
    extra = parts.get(ComponentCategory.FANS)
    if extra is not None and isinstance(extra.spec, FanSpec):
        fans += extra.spec.count
    if fans:
        items.append((f"Fans ({fans})", FAN_W * fans))

    items.append(("USB devices", USB_DEVICES_W))
    return PowerBudget(items=tuple(items))


def estimate_power_draw_w(parts: Parts) -> int:
    """Sustained draw of the whole system in watts."""
    return power_budget(parts).total_w


def recommended_psu_w(parts: Parts) -> int:
    """Draw plus headroom, rounded up to the next 50 W."""
    return power_budget(parts).recommended_w
