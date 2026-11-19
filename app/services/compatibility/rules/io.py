"""Connectivity: front panel and display outputs."""

from __future__ import annotations

from app.domain.components import (
    CaseSpec,
    ComponentCategory,
    GpuSpec,
    MonitorSpec,
    MotherboardSpec,
)
from app.services.compatibility.report import CompatibilityReport
from app.services.compatibility.rules.common import Parts, spec_of, version_number

C = ComponentCategory


def check_front_usb_c(parts: Parts, report: CompatibilityReport) -> None:
    case = spec_of(parts, C.CASE, CaseSpec)
    board = spec_of(parts, C.MOTHERBOARD, MotherboardSpec)
    if case is None or board is None:
        return
    if case.front_usb_c is None:
        report.unknown("front_usb_c", "front-panel USB-C presence not recorded for the case")
        return
    if not case.front_usb_c:
        report.passed("front_usb_c", "case has no front USB-C to wire")
        return
    if board.usb_c_header is None:
        report.unknown("front_usb_c", "board USB-C front header not recorded")
    elif not board.usb_c_header:
        report.warn(
            "front_usb_c",
            "front USB-C has no matching header on the board - it will need an adapter "
            "or stay unconnected",
        )
    else:
        report.passed("front_usb_c", "front USB-C header available on the board")


def _required_link(resolution: str, refresh_hz: int) -> tuple[float, float, str]:
    """Minimum (DisplayPort, HDMI) versions for a mode and a label for it."""
    try:
        width, height = (int(v) for v in resolution.lower().split("x"))
    except ValueError:
        return 1.2, 2.0, resolution
    pixels = width * height
    if pixels <= 1920 * 1080:
        if refresh_hz <= 240:
            return 1.2, 2.0, "1080p"
        return 1.4, 2.1, "1080p high refresh"
    if pixels <= 2560 * 1440:
        if refresh_hz <= 144:
            return 1.2, 2.0, "1440p"
        if refresh_hz <= 240:
            return 1.4, 2.1, "1440p high refresh"
        return 2.1, 2.1, "1440p 240+ Hz"
    if refresh_hz <= 60:
        return 1.2, 2.0, "4K 60 Hz"
    if refresh_hz <= 144:
        return 1.4, 2.1, "4K high refresh"
    return 2.1, 2.1, "4K 144+ Hz"


def check_monitor_gpu(parts: Parts, report: CompatibilityReport) -> None:
    monitor = spec_of(parts, C.MONITOR, MonitorSpec)
    gpu = spec_of(parts, C.GPU, GpuSpec)
    if monitor is None or gpu is None:
        return
    if gpu.outputs is None or monitor.inputs is None:
        report.unknown("monitor_output", "GPU outputs or monitor inputs not recorded")
        return

    need_dp, need_hdmi, mode = _required_link(monitor.resolution, monitor.refresh_hz)
    options: list[str] = []

    gpu_dp = version_number(gpu.outputs.displayport_version)
    mon_dp = version_number(monitor.inputs.displayport_version)
    if (
        gpu.outputs.displayport
        and monitor.inputs.displayport
        and gpu_dp is not None
        and mon_dp is not None
        and min(gpu_dp, mon_dp) >= need_dp
    ):
        options.append(f"DisplayPort {min(gpu_dp, mon_dp):.1f}")

    gpu_hdmi = version_number(gpu.outputs.hdmi_version)
    mon_hdmi = version_number(monitor.inputs.hdmi_version)
    if (
        gpu.outputs.hdmi
        and monitor.inputs.hdmi
        and gpu_hdmi is not None
        and mon_hdmi is not None
        and min(gpu_hdmi, mon_hdmi) >= need_hdmi
    ):
        options.append(f"HDMI {min(gpu_hdmi, mon_hdmi):.1f}")

    if options:
        report.passed(
            "monitor_output",
            f"{mode} at {monitor.refresh_hz} Hz over {' or '.join(options)}",
        )
    else:
        report.warn(
            "monitor_output",
            f"no shared connector carries {mode} at {monitor.refresh_hz} Hz "
            f"(needs DisplayPort {need_dp} / HDMI {need_hdmi})",
        )
