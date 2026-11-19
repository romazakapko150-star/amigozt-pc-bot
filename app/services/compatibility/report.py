"""Result model of the compatibility engine.

Every rule records a ``Check`` with one of four statuses:

* ``PASS``    - confirmed compatible from the data we hold;
* ``WARN``    - works, but the customer or the builder should know something
                (BIOS update, adapter cable, memory below rated speed);
* ``FAIL``    - the parts will not fit, will not boot, or are unsafe;
* ``UNKNOWN`` - the catalogue lacks the number needed to decide.

UNKNOWN is never silently treated as PASS. For *critical* checks - the ones
that decide whether the machine can physically be assembled and powered -
an UNKNOWN blocks the build exactly like a FAIL until someone fills in the
data. For the rest it is reported to the admin as missing data.

The older ``Issue``/``Severity`` view (``errors``, ``warnings``, ``ok``) is
kept so the generator, the ready-build scripts and the customer card keep
working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"


#: Human-readable pair per check code, in the order the admin table lists them.
PAIR_BY_CODE: dict[str, str] = {
    "missing_part": "Build",
    "no_display_output": "Build",
    "socket_mismatch": "CPU → Motherboard",
    "cpu_memory_type": "CPU → Motherboard",
    "bios_update": "CPU → Motherboard",
    "cpu_unsupported": "CPU → Motherboard",
    "memory_type_mismatch": "Motherboard → RAM",
    "memory_slots": "Motherboard → RAM",
    "memory_capacity": "Motherboard → RAM",
    "memory_speed": "Motherboard → RAM",
    "memory_profile": "Motherboard → RAM",
    "memory_four_modules": "Motherboard → RAM",
    "no_cooler": "CPU → Cooler",
    "cooler_socket": "CPU → Cooler",
    "cooler_capacity": "CPU → Cooler",
    "gpu_too_long": "GPU → Case",
    "gpu_front_radiator": "GPU → Case",
    "gpu_slots": "GPU → Case",
    "cooler_too_tall": "Cooler → Case",
    "radiator_unsupported": "Cooler → Case",
    "radiator_position": "Cooler → Case",
    "ram_clearance": "Cooler → RAM",
    "board_form_factor": "Motherboard → Case",
    "psu_too_long": "PSU → Case",
    "psu_form_factor": "PSU → Case",
    "psu_underpowered": "PSU Wattage",
    "psu_tight": "PSU Wattage",
    "psu_gpu_minimum": "PSU Wattage",
    "gpu_power_connector": "GPU Power",
    "gpu_power_adapter": "GPU Power",
    "no_m2_slot": "SSD → Motherboard",
    "m2_size": "SSD → Motherboard",
    "ssd_pcie_generation": "SSD → Motherboard",
    "sata_ports": "SSD → Motherboard",
    "lane_sharing": "SSD → Motherboard",
    "drive_bays": "Drives → Case",
    "fan_size": "Fans → Case",
    "fan_mounts": "Fans → Case",
    "fan_headers": "Fans → Motherboard",
    "argb_header": "ARGB → Motherboard",
    "rgb_header": "ARGB → Motherboard",
    "argb_unknown": "ARGB → Motherboard",
    "front_usb_c": "Front panel → Motherboard",
    "monitor_output": "Monitor → GPU",
}

#: Pairs in display order for the admin report.
PAIR_ORDER: tuple[str, ...] = (
    "Build",
    "CPU → Motherboard",
    "Motherboard → RAM",
    "CPU → Cooler",
    "GPU → Case",
    "Cooler → Case",
    "Cooler → RAM",
    "Motherboard → Case",
    "PSU → Case",
    "PSU Wattage",
    "GPU Power",
    "SSD → Motherboard",
    "Drives → Case",
    "Fans → Case",
    "Fans → Motherboard",
    "ARGB → Motherboard",
    "Front panel → Motherboard",
    "Monitor → GPU",
)

STATUS_ICON: dict[CheckStatus, str] = {
    CheckStatus.PASS: "✅",
    CheckStatus.WARN: "⚠️",
    CheckStatus.FAIL: "❌",
    CheckStatus.UNKNOWN: "❔",
}

LABEL_BUILDABLE = "🟢 BUILDABLE"
LABEL_NOT_BUILDABLE = "🔴 NOT BUILDABLE"
LABEL_DATA_MISSING = "🟡 DATA MISSING"


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    severity: Severity
    detail: str

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR


@dataclass(frozen=True, slots=True)
class Check:
    code: str
    status: CheckStatus
    detail: str
    #: A critical UNKNOWN blocks the build; a non-critical one is reported.
    critical: bool = False
    #: False when a number this check relied on is not manufacturer-verified.
    verified: bool = True

    @property
    def pair(self) -> str:
        return PAIR_BY_CODE.get(self.code, "Other")

    @property
    def blocking(self) -> bool:
        return self.status is CheckStatus.FAIL or (
            self.status is CheckStatus.UNKNOWN and self.critical
        )

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "pair": self.pair,
            "status": self.status.value,
            "detail": self.detail,
            "critical": self.critical,
            "verified": self.verified,
        }


@dataclass(slots=True)
class CompatibilityReport:
    checks: list[Check] = field(default_factory=list)

    # --- recording ------------------------------------------------------

    def add(self, code: str, severity: Severity, detail: str) -> None:
        """Legacy entry point: ERROR → FAIL, WARNING → WARN."""
        status = CheckStatus.FAIL if severity is Severity.ERROR else CheckStatus.WARN
        self.checks.append(Check(code=code, status=status, detail=detail, critical=True))

    def record(
        self,
        code: str,
        status: CheckStatus,
        detail: str,
        *,
        critical: bool = False,
        verified: bool = True,
    ) -> None:
        self.checks.append(
            Check(code=code, status=status, detail=detail, critical=critical, verified=verified)
        )

    def passed(self, code: str, detail: str, *, verified: bool = True) -> None:
        self.record(code, CheckStatus.PASS, detail, verified=verified)

    def warn(self, code: str, detail: str, *, verified: bool = True) -> None:
        self.record(code, CheckStatus.WARN, detail, verified=verified)

    def fail(self, code: str, detail: str, *, verified: bool = True) -> None:
        self.record(code, CheckStatus.FAIL, detail, critical=True, verified=verified)

    def unknown(self, code: str, detail: str, *, critical: bool = False) -> None:
        self.record(code, CheckStatus.UNKNOWN, detail, critical=critical)

    # --- legacy view ----------------------------------------------------

    @property
    def issues(self) -> list[Issue]:
        return self.errors + self.warnings

    @property
    def errors(self) -> list[Issue]:
        out: list[Issue] = []
        for check in self.checks:
            if check.status is CheckStatus.FAIL:
                out.append(Issue(check.code, Severity.ERROR, check.detail))
            elif check.status is CheckStatus.UNKNOWN and check.critical:
                out.append(Issue(check.code, Severity.ERROR, f"{check.detail} (data missing)"))
        return out

    @property
    def warnings(self) -> list[Issue]:
        out: list[Issue] = []
        for check in self.checks:
            if check.status is CheckStatus.WARN:
                out.append(Issue(check.code, Severity.WARNING, check.detail))
            elif check.status is CheckStatus.UNKNOWN and not check.critical:
                out.append(Issue(check.code, Severity.WARNING, f"{check.detail} (data missing)"))
        return out

    @property
    def ok(self) -> bool:
        """No failure and no critical unknown - the build may be offered."""
        return not any(check.blocking for check in self.checks)

    #: Spelled-out alias for the order gate and the admin report.
    @property
    def compatible(self) -> bool:
        return self.ok

    # --- new view -------------------------------------------------------

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status is CheckStatus.FAIL]

    @property
    def unknowns(self) -> list[Check]:
        return [c for c in self.checks if c.status is CheckStatus.UNKNOWN]

    @property
    def unverified(self) -> list[Check]:
        return [c for c in self.checks if not c.verified]

    @property
    def data_missing(self) -> bool:
        return bool(self.unknowns)

    @property
    def final_label(self) -> str:
        if self.failures:
            return LABEL_NOT_BUILDABLE
        if any(c.status is CheckStatus.UNKNOWN and c.critical for c in self.checks):
            return LABEL_DATA_MISSING
        return LABEL_BUILDABLE

    def by_pair(self) -> list[tuple[str, CheckStatus]]:
        """Worst status per pair, in display order. Pairs with no check are omitted."""
        rank = {
            CheckStatus.FAIL: 3,
            CheckStatus.UNKNOWN: 2,
            CheckStatus.WARN: 1,
            CheckStatus.PASS: 0,
        }
        worst: dict[str, CheckStatus] = {}
        for check in self.checks:
            current = worst.get(check.pair)
            if current is None or rank[check.status] > rank[current]:
                worst[check.pair] = check.status
        ordered = [(pair, worst[pair]) for pair in PAIR_ORDER if pair in worst]
        extra = [(pair, status) for pair, status in worst.items() if pair not in PAIR_ORDER]
        return ordered + extra

    def as_dict(self) -> dict:
        """The contract the order gate freezes into ``leads.compatibility_snapshot``."""
        return {
            "compatible": self.compatible,
            "final": self.final_label,
            "errors": [issue.detail for issue in self.errors],
            "warnings": [issue.detail for issue in self.warnings],
            "unknown": [check.detail for check in self.unknowns],
            "checks": [check.as_dict() for check in self.checks],
        }

    @classmethod
    def from_dict(cls, raw: dict) -> CompatibilityReport:
        checks = []
        for item in raw.get("checks", []):
            try:
                checks.append(
                    Check(
                        code=str(item["code"]),
                        status=CheckStatus(item["status"]),
                        detail=str(item.get("detail", "")),
                        critical=bool(item.get("critical", False)),
                        verified=bool(item.get("verified", True)),
                    )
                )
            except (KeyError, ValueError):
                continue
        return cls(checks=checks)
