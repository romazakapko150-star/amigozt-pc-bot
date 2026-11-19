"""Admin rendering of a compatibility snapshot.

Russian-only like the rest of the admin chrome. Reads the dict produced by
``GateResult.snapshot()`` (or ``CompatibilityReport.as_dict()``), never the
live engine, so an old lead renders exactly what was checked at order time.
"""

from __future__ import annotations

from html import escape

from app.services.compatibility.report import (
    PAIR_ORDER,
    STATUS_ICON,
    CheckStatus,
    CompatibilityReport,
)

TITLE = "<b>🧩 Совместимость сборки</b>"
MAX_DETAIL_LINES = 8


def render_compatibility(snapshot: dict) -> list[str]:
    report = CompatibilityReport.from_dict(snapshot)
    if not report.checks:
        return [TITLE, "— отчёт не сохранён"]

    lines = [TITLE]
    for pair, status in _pairs(report):
        lines.append(f"{escape(pair):<24} {STATUS_ICON[status]}")

    lines.append("")
    lines.append(f"<b>FINAL: {escape(snapshot.get('final') or report.final_label)}</b>")

    failures = [c.detail for c in report.checks if c.status is CheckStatus.FAIL]
    if failures:
        lines.append("")
        lines.append("<b>❌ Ошибки</b>")
        lines.extend(f"• {escape(d)}" for d in failures[:MAX_DETAIL_LINES])

    unknown_critical = [
        c.detail for c in report.checks if c.status is CheckStatus.UNKNOWN and c.critical
    ]
    unknown_other = [
        c.detail for c in report.checks if c.status is CheckStatus.UNKNOWN and not c.critical
    ]
    if unknown_critical or unknown_other:
        lines.append("")
        lines.append("<b>⚠️ Compatibility data missing</b>")
        lines.extend(f"• ❗ {escape(d)}" for d in unknown_critical[:MAX_DETAIL_LINES])
        lines.extend(f"• {escape(d)}" for d in unknown_other[:MAX_DETAIL_LINES])

    warnings = [c.detail for c in report.checks if c.status is CheckStatus.WARN]
    if warnings:
        lines.append("")
        lines.append("<b>⚠️ Предупреждения</b>")
        lines.extend(f"• {escape(d)}" for d in warnings[:MAX_DETAIL_LINES])

    unverified = [
        c for c in report.checks if not c.verified and c.status is not CheckStatus.UNKNOWN
    ]
    if unverified:
        lines.append("")
        lines.append(
            f"<i>Не подтверждено производителем: {len(unverified)} проверок — "
            "сверь размеры точной модели перед закупкой</i>"
        )

    power = snapshot.get("power") or {}
    if power:
        lines.append("")
        lines.append(
            f"⚡ Потребление ~{power.get('total_w', '—')} W · "
            f"рекомендовано {power.get('recommended_w', '—')} W "
            f"(запас ×{power.get('safety_factor', '—')})"
        )
        items = power.get("items") or []
        if items:
            lines.append(
                "<i>"
                + ", ".join(f"{escape(str(i.get('part')))} {i.get('watts')} W" for i in items)
                + "</i>"
            )

    missing_ids = snapshot.get("unknown_component_ids") or []
    if missing_ids:
        lines.append("")
        lines.append("❗ Компоненты не найдены в каталоге: " + escape(", ".join(missing_ids)))

    return lines


def render_compatibility_short(snapshot: dict) -> str:
    """One line for notifications: the verdict and what blocks it."""
    report = CompatibilityReport.from_dict(snapshot)
    if not report.checks:
        return "🧩 Совместимость: отчёт не сохранён"
    final = snapshot.get("final") or report.final_label
    blocking = [c.detail for c in report.checks if c.blocking]
    unknown = sum(1 for c in report.checks if c.status is CheckStatus.UNKNOWN)
    text = f"🧩 Совместимость: <b>{escape(str(final))}</b>"
    if blocking:
        text += "\n• " + "\n• ".join(escape(d) for d in blocking[:3])
    elif unknown:
        text += f" · ❔ нет данных: {unknown}"
    return text


def _pairs(report: CompatibilityReport) -> list[tuple[str, CheckStatus]]:
    present = dict(report.by_pair())
    ordered = [(pair, present[pair]) for pair in PAIR_ORDER if pair in present]
    extra = [(pair, status) for pair, status in present.items() if pair not in PAIR_ORDER]
    return ordered + extra
