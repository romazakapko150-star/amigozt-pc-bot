"""Electrical fit: power, connectors, headers."""

from __future__ import annotations

from app.domain.components import (
    ArgbConnector,
    CaseSpec,
    ComponentCategory,
    CoolerSpec,
    CoolerType,
    FanSpec,
    GpuSpec,
    MotherboardSpec,
    PsuSpec,
    RamSpec,
)
from app.services.compatibility.power import power_budget
from app.services.compatibility.report import CompatibilityReport
from app.services.compatibility.rules.common import Parts, spec_of, verified

C = ComponentCategory

#: A 12VHPWR / 12V-2x6 input fed through an adapter needs this many 8-pin
#: leads when the GPU does not say otherwise.
DEFAULT_8PIN_PER_12VHPWR = 2


def gpu_power_path(gpu: GpuSpec, psu: PsuSpec) -> str | None:
    """How the PSU can feed the GPU: ``"native"``, ``"adapter"`` or ``None``.

    Shared with the generator so that candidate PSUs are filtered by the
    same logic the report applies.
    """
    if gpu.pcie_12vhpwr > 0:
        if psu.pcie_12vhpwr >= gpu.pcie_12vhpwr:
            return "native"
        leads = gpu.pcie_8pin or DEFAULT_8PIN_PER_12VHPWR * gpu.pcie_12vhpwr
        return "adapter" if psu.pcie_8pin >= leads else None
    return "native" if gpu.pcie_8pin <= psu.pcie_8pin else None


def check_psu_wattage(parts: Parts, report: CompatibilityReport) -> None:
    psu = spec_of(parts, C.PSU, PsuSpec)
    if psu is None:
        return
    budget = power_budget(parts)
    needed = budget.recommended_w
    if psu.wattage < needed:
        report.fail(
            "psu_underpowered",
            f"{psu.wattage} W supply below the {needed} W recommended "
            f"(estimated draw {budget.total_w} W)",
        )
    elif psu.wattage < needed + 50:
        report.warn(
            "psu_tight",
            f"{psu.wattage} W leaves little headroom over the {needed} W recommended",
        )
    else:
        report.passed(
            "psu_underpowered",
            f"{psu.wattage} W supply covers the {needed} W recommended "
            f"(estimated draw {budget.total_w} W)",
        )

    gpu = spec_of(parts, C.GPU, GpuSpec)
    if gpu is not None and psu.wattage < gpu.recommended_psu_w:
        report.fail(
            "psu_gpu_minimum",
            f"GPU vendor asks for a {gpu.recommended_psu_w} W supply, this one is {psu.wattage} W",
        )


def check_gpu_power(parts: Parts, report: CompatibilityReport) -> None:
    psu = spec_of(parts, C.PSU, PsuSpec)
    gpu = spec_of(parts, C.GPU, GpuSpec)
    if psu is None or gpu is None:
        return
    ok = verified(parts, C.PSU)

    if gpu.pcie_12vhpwr > 0:
        if psu.pcie_12vhpwr >= gpu.pcie_12vhpwr:
            report.passed(
                "gpu_power_connector",
                "native 12VHPWR / 12V-2x6 cable on the power supply",
                verified=ok,
            )
            return
        leads = gpu.pcie_8pin or DEFAULT_8PIN_PER_12VHPWR * gpu.pcie_12vhpwr
        if psu.pcie_8pin >= leads:
            adapter = {
                True: "adapter ships with the card",
                False: "adapter is NOT in the box - buy one",
                None: "check that an adapter is in the box",
            }[gpu.adapter_included]
            report.warn(
                "gpu_power_adapter",
                f"GPU needs a 12VHPWR input; the PSU has none, so {leads}x 8-pin go through "
                f"an adapter ({adapter})",
                verified=ok,
            )
            return
        report.fail(
            "gpu_power_connector",
            f"PSU has no 12VHPWR connector and only {psu.pcie_8pin} PCIe 8-pin "
            f"(adapter needs {leads})",
            verified=ok,
        )
        return

    if gpu.pcie_8pin > psu.pcie_8pin:
        report.fail(
            "gpu_power_connector",
            f"GPU needs {gpu.pcie_8pin} PCIe 8-pin, PSU provides {psu.pcie_8pin}",
            verified=ok,
        )
    else:
        report.passed(
            "gpu_power_connector",
            f"{gpu.pcie_8pin}x PCIe 8-pin available",
            verified=ok,
        )


def check_fan_headers(parts: Parts, report: CompatibilityReport) -> None:
    board = spec_of(parts, C.MOTHERBOARD, MotherboardSpec)
    if board is None:
        return
    needed = 0
    case = spec_of(parts, C.CASE, CaseSpec)
    if case is not None:
        # Case fans on their own controller/hub take one header at most.
        if case.argb_connector is ArgbConnector.OWN_CONTROLLER and case.included_fans:
            needed += 1
        else:
            needed += case.included_fans
    cooler = spec_of(parts, C.COOLER, CoolerSpec)
    if cooler is not None:
        needed += 2 if cooler.cooler_type is CoolerType.AIO else 1
    fans = spec_of(parts, C.FANS, FanSpec)
    if fans is not None:
        needed += fans.count
    if needed == 0:
        return
    if board.fan_headers is None:
        report.unknown("fan_headers", f"{needed} fan headers needed; board headers not recorded")
    elif needed > board.fan_headers:
        report.warn(
            "fan_headers",
            f"{needed} fan connections for {board.fan_headers} headers - a fan hub or "
            "splitter is needed",
        )
    else:
        report.passed("fan_headers", f"{needed} fan connections on {board.fan_headers} headers")


def check_lighting_headers(parts: Parts, report: CompatibilityReport) -> None:
    board = spec_of(parts, C.MOTHERBOARD, MotherboardSpec)
    if board is None:
        return

    needs_5v: list[str] = []
    needs_12v: list[str] = []
    unknown: list[str] = []

    def classify(name: str, connector: ArgbConnector | None, lit: bool) -> None:
        if connector is ArgbConnector.ARGB_5V:
            needs_5v.append(name)
        elif connector is ArgbConnector.RGB_12V:
            needs_12v.append(name)
        elif connector is None and lit:
            unknown.append(name)

    case = spec_of(parts, C.CASE, CaseSpec)
    if case is not None:
        classify("case", case.argb_connector, case.rgb)
    cooler = spec_of(parts, C.COOLER, CoolerSpec)
    if cooler is not None:
        classify("cooler", cooler.argb_connector, cooler.rgb)
    ram = spec_of(parts, C.RAM, RamSpec)
    if ram is not None:
        classify("memory", ram.argb_connector, ram.rgb)
    fans = spec_of(parts, C.FANS, FanSpec)
    if fans is not None:
        classify("fans", fans.argb_connector, fans.rgb)

    if needs_5v:
        names = ", ".join(needs_5v)
        if board.argb_5v_headers is None:
            report.unknown(
                "argb_header", f"{names} need a 5V 3-pin ARGB header; board headers not recorded"
            )
        elif board.argb_5v_headers < 1:
            report.fail(
                "argb_header",
                f"{names} need a 5V 3-pin ARGB header and the board has none - "
                "add an ARGB controller or change the board",
            )
        else:
            report.passed("argb_header", f"5V 3-pin ARGB header available for {names}")

    if needs_12v:
        names = ", ".join(needs_12v)
        if board.rgb_12v_headers is None:
            report.unknown(
                "rgb_header", f"{names} need a 12V 4-pin RGB header; board headers not recorded"
            )
        elif board.rgb_12v_headers < 1:
            report.fail(
                "rgb_header",
                f"{names} need a 12V 4-pin RGB header and the board has none",
            )
        else:
            report.passed("rgb_header", f"12V 4-pin RGB header available for {names}")

    if unknown:
        report.unknown(
            "argb_unknown",
            f"lighting connector type not recorded for: {', '.join(unknown)}",
        )
