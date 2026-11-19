"""Physical fit: will the parts go into the case at all."""

from __future__ import annotations

from app.domain.components import (
    CaseSpec,
    ComponentCategory,
    CoolerSpec,
    CoolerType,
    FanSpec,
    GpuSpec,
    MotherboardSpec,
    PsuSpec,
    RamSpec,
    SsdSpec,
)
from app.services.compatibility.report import CompatibilityReport
from app.services.compatibility.rules.common import (
    Parts,
    choose_radiator_position,
    radiator_fits,
    spec_of,
    verified,
)

C = ComponentCategory

#: Radiator plus one row of fans, used when a case does not publish the GPU
#: clearance it keeps with a front-mounted radiator.
DEFAULT_RADIATOR_STACK_MM = 38 + 25


def check_board_in_case(parts: Parts, report: CompatibilityReport) -> None:
    case = spec_of(parts, C.CASE, CaseSpec)
    board = spec_of(parts, C.MOTHERBOARD, MotherboardSpec)
    if case is None or board is None:
        return
    ok = verified(parts, C.CASE)
    if board.form_factor not in case.form_factors:
        report.fail(
            "board_form_factor",
            f"{board.form_factor} board does not fit this case "
            f"(takes {', '.join(ff.value for ff in case.form_factors)})",
            verified=ok,
        )
    else:
        report.passed("board_form_factor", f"{board.form_factor} board fits the case", verified=ok)


def check_gpu_in_case(parts: Parts, report: CompatibilityReport) -> None:
    gpu = spec_of(parts, C.GPU, GpuSpec)
    case = spec_of(parts, C.CASE, CaseSpec)
    if gpu is None or case is None:
        return
    ok = verified(parts, C.GPU, C.CASE)

    if gpu.length_mm > case.max_gpu_length_mm:
        report.fail(
            "gpu_too_long",
            f"GPU is {gpu.length_mm} mm, the case fits {case.max_gpu_length_mm} mm",
            verified=ok,
        )
    else:
        report.passed(
            "gpu_too_long",
            f"GPU {gpu.length_mm} mm within the {case.max_gpu_length_mm} mm clearance",
            verified=ok,
        )

    _check_gpu_front_radiator(parts, gpu, case, report, ok)

    if case.max_gpu_slots is None:
        report.unknown("gpu_slots", "case slot clearance for the GPU not published")
    elif gpu.slots > case.max_gpu_slots:
        report.fail(
            "gpu_slots",
            f"GPU occupies {gpu.slots} slots, the case offers {case.max_gpu_slots}",
            verified=ok,
        )
    else:
        report.passed("gpu_slots", f"{gpu.slots}-slot GPU fits", verified=ok)


def _check_gpu_front_radiator(
    parts: Parts, gpu: GpuSpec, case: CaseSpec, report: CompatibilityReport, ok: bool
) -> None:
    cooler = spec_of(parts, C.COOLER, CoolerSpec)
    if cooler is None or cooler.cooler_type is not CoolerType.AIO or not cooler.radiator_mm:
        return
    position = _radiator_position(case, cooler.radiator_mm)
    if position != "front":
        return

    if case.max_gpu_length_with_front_radiator_mm is not None:
        limit = case.max_gpu_length_with_front_radiator_mm
        if gpu.length_mm > limit:
            report.fail(
                "gpu_front_radiator",
                f"with the {cooler.radiator_mm} mm radiator in the front the GPU clearance "
                f"drops to {limit} mm; GPU is {gpu.length_mm} mm",
                verified=ok,
            )
        else:
            report.passed(
                "gpu_front_radiator",
                f"GPU {gpu.length_mm} mm fits the {limit} mm clearance with a front radiator",
                verified=ok,
            )
        return

    stack = DEFAULT_RADIATOR_STACK_MM
    if cooler.radiator_thickness_mm is not None and cooler.fan_thickness_mm is not None:
        stack = cooler.radiator_thickness_mm + cooler.fan_thickness_mm
    estimated = case.max_gpu_length_mm - stack
    if gpu.length_mm <= estimated:
        report.passed(
            "gpu_front_radiator",
            f"front radiator stack {stack} mm leaves ~{estimated} mm for the "
            f"{gpu.length_mm} mm GPU (estimated, case does not publish this clearance)",
            verified=False,
        )
    else:
        report.unknown(
            "gpu_front_radiator",
            f"cannot confirm the {gpu.length_mm} mm GPU next to a front-mounted "
            f"{cooler.radiator_mm} mm radiator (~{estimated} mm estimated clearance) - "
            "mount the radiator elsewhere or choose a shorter card",
            critical=True,
        )


def _radiator_position(case: CaseSpec, size_mm: int) -> str | None:
    if case.radiator_positions:
        position, _ = choose_radiator_position(case.radiator_positions, size_mm)
        return position.value if position is not None else None
    return None


def check_cooler_in_case(parts: Parts, report: CompatibilityReport) -> None:
    cooler = spec_of(parts, C.COOLER, CoolerSpec)
    case = spec_of(parts, C.CASE, CaseSpec)
    if cooler is None or case is None:
        return
    ok = verified(parts, C.COOLER, C.CASE)

    if cooler.cooler_type is CoolerType.AIR:
        if cooler.height_mm > case.max_cooler_height_mm:
            report.fail(
                "cooler_too_tall",
                f"cooler is {cooler.height_mm} mm, the case fits {case.max_cooler_height_mm} mm",
                verified=ok,
            )
        else:
            report.passed(
                "cooler_too_tall",
                f"cooler {cooler.height_mm} mm under the {case.max_cooler_height_mm} mm limit",
                verified=ok,
            )
        return

    if not cooler.radiator_mm:
        report.unknown("radiator_unsupported", "AIO radiator size not recorded", critical=True)
        return

    if case.radiator_positions:
        position, derived = choose_radiator_position(case.radiator_positions, cooler.radiator_mm)
        if position is None:
            report.fail(
                "radiator_unsupported",
                f"case has no mount for a {cooler.radiator_mm} mm radiator",
                verified=ok,
            )
            return
        note = " (smaller than the listed rail, same fan width)" if derived else ""
        report.passed(
            "radiator_position",
            f"{cooler.radiator_mm} mm radiator mounts at the {position.value}{note}",
            verified=ok,
        )
        return

    fits, derived = radiator_fits(cooler.radiator_mm, case.radiator_support_mm)
    if not fits:
        report.fail(
            "radiator_unsupported",
            f"case does not take a {cooler.radiator_mm} mm radiator",
            verified=ok,
        )
        return
    report.passed(
        "radiator_unsupported",
        f"case takes a {cooler.radiator_mm} mm radiator",
        verified=ok,
    )
    report.unknown("radiator_position", "radiator mounting positions not recorded for the case")


def check_cooler_ram_clearance(parts: Parts, report: CompatibilityReport) -> None:
    cooler = spec_of(parts, C.COOLER, CoolerSpec)
    ram = spec_of(parts, C.RAM, RamSpec)
    if cooler is None or ram is None or cooler.cooler_type is not CoolerType.AIR:
        return
    if not cooler.ram_clearance_mm:
        report.unknown("ram_clearance", "cooler memory-height limit not published")
        return
    if ram.height_mm > cooler.ram_clearance_mm:
        report.fail(
            "ram_clearance",
            f"{ram.height_mm} mm memory does not clear the cooler ({cooler.ram_clearance_mm} mm)",
            verified=verified(parts, C.COOLER, C.RAM),
        )
    else:
        report.passed(
            "ram_clearance",
            f"{ram.height_mm} mm memory under the {cooler.ram_clearance_mm} mm cooler limit",
            verified=verified(parts, C.COOLER, C.RAM),
        )


def check_psu_in_case(parts: Parts, report: CompatibilityReport) -> None:
    psu = spec_of(parts, C.PSU, PsuSpec)
    case = spec_of(parts, C.CASE, CaseSpec)
    if psu is None or case is None:
        return
    ok = verified(parts, C.PSU, C.CASE)

    if psu.length_mm > case.max_psu_length_mm:
        report.fail(
            "psu_too_long",
            f"PSU is {psu.length_mm} mm, the case fits {case.max_psu_length_mm} mm",
            verified=ok,
        )
    else:
        report.passed(
            "psu_too_long",
            f"PSU {psu.length_mm} mm within the {case.max_psu_length_mm} mm bay",
            verified=ok,
        )

    if psu.form_factor is None or case.psu_form_factors is None:
        missing = "PSU" if psu.form_factor is None else "case"
        report.unknown(
            "psu_form_factor", f"{missing} power-supply form factor not recorded", critical=True
        )
    elif psu.form_factor not in case.psu_form_factors:
        report.fail(
            "psu_form_factor",
            f"{psu.form_factor} power supply does not fit a case made for "
            f"{', '.join(ff.value for ff in case.psu_form_factors)}",
            verified=ok,
        )
    else:
        report.passed("psu_form_factor", f"{psu.form_factor} power supply fits", verified=ok)


def check_fans_in_case(parts: Parts, report: CompatibilityReport) -> None:
    fans = spec_of(parts, C.FANS, FanSpec)
    case = spec_of(parts, C.CASE, CaseSpec)
    if fans is None or case is None:
        return
    if not case.fan_mounts:
        report.unknown("fan_mounts", "case fan mounts not recorded")
        return

    sizes = {size for mount in case.fan_mounts.values() for size in mount.sizes_mm}
    if fans.size_mm not in sizes:
        report.fail(
            "fan_size",
            f"{fans.size_mm} mm fans do not fit; the case takes "
            f"{', '.join(str(s) for s in sorted(sizes))} mm",
            verified=verified(parts, C.CASE),
        )
        return
    report.passed(
        "fan_size", f"{fans.size_mm} mm fans fit the case", verified=verified(parts, C.CASE)
    )

    capacity = sum(
        mount.count for mount in case.fan_mounts.values() if fans.size_mm in mount.sizes_mm
    )
    free = capacity - case.included_fans
    if fans.count > free:
        report.fail(
            "fan_mounts",
            f"{fans.count} extra fans need more than the {max(free, 0)} free "
            f"{fans.size_mm} mm mounts",
            verified=verified(parts, C.CASE),
        )
    else:
        report.passed(
            "fan_mounts",
            f"{fans.count} extra fans fit the {free} free mounts",
            verified=verified(parts, C.CASE),
        )


def check_drives_in_case(parts: Parts, report: CompatibilityReport) -> None:
    ssd = spec_of(parts, C.SSD, SsdSpec)
    case = spec_of(parts, C.CASE, CaseSpec)
    if ssd is None or case is None or ssd.form_factor is None:
        return
    form = ssd.form_factor.lower()
    if form.startswith("m.2"):
        return
    if "3.5" in form:
        bays = case.drive_bays_35
        label = '3.5"'
    else:
        bays = case.drive_bays_25
        label = '2.5"'
    if bays is None:
        report.unknown("drive_bays", f"case {label} drive bays not recorded", critical=True)
    elif bays < 1:
        report.fail(
            "drive_bays", f"case has no {label} drive bay", verified=verified(parts, C.CASE)
        )
    else:
        report.passed(
            "drive_bays", f"{label} drive bay available", verified=verified(parts, C.CASE)
        )
