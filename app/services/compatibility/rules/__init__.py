"""Rule set of the compatibility engine, grouped by what can go wrong.

Order matters only for readability of the report: physical fit first,
because a part that does not fit makes every other question moot.
"""

from __future__ import annotations

from collections.abc import Callable

from app.services.compatibility.report import CompatibilityReport
from app.services.compatibility.rules import electrical, io, physical, platform
from app.services.compatibility.rules.common import Parts

Rule = Callable[[Parts, CompatibilityReport], None]

ALL_RULES: tuple[Rule, ...] = (
    platform.check_completeness,
    physical.check_board_in_case,
    physical.check_gpu_in_case,
    physical.check_cooler_in_case,
    physical.check_cooler_ram_clearance,
    physical.check_psu_in_case,
    physical.check_fans_in_case,
    physical.check_drives_in_case,
    electrical.check_psu_wattage,
    electrical.check_gpu_power,
    electrical.check_fan_headers,
    electrical.check_lighting_headers,
    platform.check_cpu_motherboard,
    platform.check_cooler_cpu,
    platform.check_memory,
    platform.check_storage,
    io.check_front_usb_c,
    io.check_monitor_gpu,
)

__all__ = ["ALL_RULES", "Rule"]
