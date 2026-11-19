"""Platform fit: CPU, board, memory, storage."""

from __future__ import annotations

from app.domain.components import (
    REQUIRED_CATEGORIES,
    ComponentCategory,
    CoolerSpec,
    CpuSpec,
    CpuSupport,
    MemoryType,
    MotherboardSpec,
    RamSpec,
    SsdSpec,
)
from app.services.compatibility.report import CompatibilityReport
from app.services.compatibility.rules.common import Parts, spec_of

C = ComponentCategory

STANDARD_M2 = "2280"


def check_completeness(parts: Parts, report: CompatibilityReport) -> None:
    for category in sorted(REQUIRED_CATEGORIES):
        if category not in parts:
            report.fail("missing_part", f"no {category.value} selected")

    cpu = spec_of(parts, C.CPU, CpuSpec)
    if cpu is not None and C.GPU not in parts and not cpu.integrated_graphics:
        report.fail(
            "no_display_output",
            "CPU has no integrated graphics and no discrete GPU is present",
        )


def check_cpu_motherboard(parts: Parts, report: CompatibilityReport) -> None:
    cpu = spec_of(parts, C.CPU, CpuSpec)
    board = spec_of(parts, C.MOTHERBOARD, MotherboardSpec)
    if cpu is None or board is None:
        return

    if cpu.socket is not board.socket:
        report.fail(
            "socket_mismatch",
            f"CPU socket {cpu.socket} does not fit motherboard socket {board.socket}",
        )
        return
    report.passed("socket_mismatch", f"socket {cpu.socket} matches")

    if board.memory_type not in cpu.memory_types:
        report.fail(
            "cpu_memory_type",
            f"CPU does not support {board.memory_type} used by the motherboard",
        )

    if cpu.family is None or board.cpu_support is None:
        report.unknown("bios_update", "CPU support list for this board not recorded")
        return
    support = board.cpu_support.get(cpu.family)
    if support is None:
        report.unknown("bios_update", f"board support for the {cpu.family} family not recorded")
    elif support is CpuSupport.NATIVE:
        report.passed("bios_update", f"{cpu.family} supported out of the box")
    elif support is CpuSupport.BIOS_UPDATE:
        report.warn("bios_update", "BIOS update may be required for this CPU")
    else:
        report.fail("cpu_unsupported", f"board does not support the {cpu.family} family")


def check_cooler_cpu(parts: Parts, report: CompatibilityReport) -> None:
    cooler = spec_of(parts, C.COOLER, CoolerSpec)
    cpu = spec_of(parts, C.CPU, CpuSpec)
    if cpu is None:
        return
    if cooler is None:
        if not cpu.includes_cooler:
            report.fail("no_cooler", "CPU does not include a cooler and none was chosen")
        return

    if cpu.socket not in cooler.sockets:
        report.fail("cooler_socket", f"cooler does not support socket {cpu.socket}")
    else:
        report.passed("cooler_socket", f"cooler mounts on {cpu.socket}")

    if cooler.tdp_rating_w < cpu.max_power_w:
        report.fail(
            "cooler_capacity",
            f"cooler rated {cooler.tdp_rating_w} W cannot handle {cpu.max_power_w} W",
        )
    else:
        report.passed(
            "cooler_capacity",
            f"cooler rated {cooler.tdp_rating_w} W for a {cpu.max_power_w} W CPU",
        )


def check_memory(parts: Parts, report: CompatibilityReport) -> None:
    ram = spec_of(parts, C.RAM, RamSpec)
    board = spec_of(parts, C.MOTHERBOARD, MotherboardSpec)
    cpu = spec_of(parts, C.CPU, CpuSpec)
    if ram is None or board is None:
        return

    if ram.memory_type is not board.memory_type:
        report.fail(
            "memory_type_mismatch",
            f"{ram.memory_type} memory does not fit a {board.memory_type} motherboard",
        )
        return
    report.passed(
        "memory_type_mismatch", f"{ram.memory_type} memory on a {board.memory_type} board"
    )

    if ram.modules > board.memory_slots:
        report.fail(
            "memory_slots",
            f"{ram.modules} modules need more than the {board.memory_slots} available slots",
        )

    if ram.total_capacity_gb > board.max_memory_gb:
        report.fail(
            "memory_capacity",
            f"{ram.total_capacity_gb} GB exceeds the motherboard limit of {board.max_memory_gb} GB",
        )

    supported = board.max_memory_speed_mhz
    if cpu is not None:
        supported = min(supported, cpu.max_memory_speed_mhz)
    if ram.speed_mhz > supported:
        report.warn(
            "memory_speed",
            f"memory rated {ram.speed_mhz} MHz will run at {supported} MHz",
        )

    if ram.modules >= 4 and ram.memory_type is MemoryType.DDR5:
        report.warn(
            "memory_four_modules",
            "four DDR5 modules often run below the rated speed; two larger modules are "
            "the more stable choice",
        )

    if ram.profiles is None or board.memory_profiles is None:
        report.unknown("memory_profile", "EXPO/XMP profile support not recorded")
    elif not set(ram.profiles) & set(board.memory_profiles):
        report.warn(
            "memory_profile",
            f"memory ships with {'/'.join(p.value for p in ram.profiles)} profiles, the board "
            f"lists {'/'.join(p.value for p in board.memory_profiles)} - rated speed may need "
            "manual settings",
        )
    else:
        report.passed("memory_profile", "memory profile supported by the board")


def check_storage(parts: Parts, report: CompatibilityReport) -> None:
    ssd = spec_of(parts, C.SSD, SsdSpec)
    board = spec_of(parts, C.MOTHERBOARD, MotherboardSpec)
    if ssd is None or board is None:
        return

    form = (ssd.form_factor or "").lower()
    is_sata_drive = bool(form) and not form.startswith("m.2")

    if is_sata_drive:
        if board.sata_ports is None:
            report.unknown("sata_ports", "SATA port count not recorded for the board")
        elif board.sata_ports < 1:
            report.fail("sata_ports", "board has no SATA port for the drive")
        else:
            report.passed("sata_ports", "SATA port available")
        return

    if board.m2_slots < 1:
        report.fail("no_m2_slot", "motherboard has no M.2 slot for the SSD")
        return
    report.passed("no_m2_slot", f"{board.m2_slots} M.2 slot(s) on the board")

    size = form.replace("m.2", "").strip() if form else None
    if size:
        if board.m2_slot_sizes is not None:
            if size in board.m2_slot_sizes:
                report.passed("m2_size", f"M.2 {size} slot available")
            else:
                report.fail(
                    "m2_size",
                    f"M.2 {size} drive does not fit the board's "
                    f"{'/'.join(board.m2_slot_sizes)} slots",
                )
        elif size == STANDARD_M2:
            report.passed(
                "m2_size",
                "M.2 2280 is the standard desktop size; slot lengths not listed by the vendor",
                verified=False,
            )
        else:
            report.unknown(
                "m2_size", f"board M.2 slot lengths not recorded for a {size} drive", critical=True
            )
    elif ssd.interface.lower().startswith("m.2"):
        report.unknown("m2_size", "SSD form factor not recorded")

    board_gen = max(board.m2_slot_gens) if board.m2_slot_gens else board.pcie_version
    if ssd.pcie_generation > board_gen:
        report.warn(
            "ssd_pcie_generation",
            f"PCIe {ssd.pcie_generation} SSD will run at PCIe {board_gen} speed",
        )

    if board.lane_sharing_notes:
        report.warn("lane_sharing", "; ".join(board.lane_sharing_notes))
