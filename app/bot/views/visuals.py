"""Admin rendering of the Visual Library (Russian-only admin chrome)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape

from app.db.models import Visual, VisualizationStatus

STATUS_ICON = {
    VisualizationStatus.READY: "✅",
    VisualizationStatus.FAILED: "❌",
    VisualizationStatus.PENDING: "⏳",
}

TYPE_LABEL = {"ready_build": "полка", "build": "сборка", "component": "товар"}


def _dt(value: datetime | None) -> str:
    return value.strftime("%d.%m %H:%M") if value else "—"


def render_visual_library(
    inventory_summary: dict,
    stats: dict,
    rows: list[Visual],
    *,
    enabled: bool,
    model: str,
    cost_per_call: Decimal,
    per_category: dict[str, dict[str, int]] | None = None,
) -> str:
    s = inventory_summary
    events = stats.get("events", {})
    per_type = stats.get("per_type", {})
    lines = [
        "<b>🖼️ Visual Library</b>",
        "Движок: "
        + ("включён" if enabled else "выключен (нет ключа или AI_VISUALIZATION_ENABLED=false)")
        + f" · модель <code>{escape(model)}</code> · ≈${cost_per_call} за генерацию",
        "",
        f"TOTAL ENTITIES: <b>{s['total_entities']}</b> · builds {s['builds']} · "
        f"components {s['components']} · accessories {s['accessories']}",
        f"VISUALS EXISTING: <b>{s['visuals_existing']}</b>"
        + (f" (+{s['visuals_outdated']} старой версии промпта)" if s["visuals_outdated"] else ""),
        f"VISUALS MISSING: <b>{s['visuals_missing']}</b> · FAILED: {s['visuals_failed']}"
        + (f" · skipped {s['skipped']}" if s["skipped"] else ""),
        f"ESTIMATED NEW IMAGE CALLS: {s['estimated_calls']} · COST ≈ ${s['estimated_cost_usd']}",
        "",
        f"Запросов: {events.get('request', 0)} · cache hits: <b>{events.get('cache_hit', 0)}</b> · "
        f"API calls: <b>{events.get('api_call', 0)}</b> · "
        f"сгенерировано: {events.get('generated', 0)} · "
        f"ошибок: {events.get('failed', 0)}",
        f"Потрачено (оценка): <b>${stats.get('spend_usd', Decimal(0))}</b>",
    ]
    if per_type:
        lines.append(
            "В библиотеке: "
            + " · ".join(
                f"{TYPE_LABEL.get(kind, kind)} "
                f"{counts.get('ready', 0)}✅/{counts.get('failed', 0)}❌"
                + (f"/{counts.get('invalid', 0)}🚫" if counts.get("invalid") else "")
                for kind, counts in per_type.items()
            )
        )
    if per_category:
        lines.extend(["", "<b>Покрытие по категориям</b>"])
        for name, counts in sorted(
            per_category.items(), key=lambda item: (-item[1]["missing"], item[0])
        ):
            done = counts["existing"]
            total = counts["total"]
            bar = "🟢" if done == total else ("🟡" if done else "🔴")
            extra = []
            if counts["outdated"]:
                extra.append(f"{counts['outdated']} старой версии")
            if counts["failed"]:
                extra.append(f"{counts['failed']}❌")
            if counts["skipped"]:
                extra.append(f"{counts['skipped']} пропущено")
            tail = f" · {' · '.join(extra)}" if extra else ""
            lines.append(f"{bar} {escape(name)}: {done}/{total}{tail}")

    lines.extend(
        [
            "",
            "Команды: <code>/visual_generate &lt;category|builds&gt; &lt;N≤10&gt;</code>, "
            "<code>/visual_retry_failed [N]</code>, <code>/visual_regen &lt;id|slug&gt;</code>, "
            "<code>/visual_regen_component &lt;id&gt;</code>, "
            "<code>/visual_disable &lt;fingerprint&gt;</code>, "
            "<code>/visual_generate_all confirm</code> (явное подтверждение). "
            "Массово: <code>python -m scripts.generate_visual_library --dry-run</code>.",
        ]
    )
    if rows:
        lines.extend(["", "<b>Последние</b>"])
        for row in rows:
            icon = STATUS_ICON.get(row.status, "❔") if row.is_valid else "🚫"
            lines.append(
                f"{icon} {TYPE_LABEL.get(row.entity_type, row.entity_type)} "
                f"<code>{escape(row.entity_id)}</code> · {escape(row.category or '—')} · "
                f"<code>{escape(row.fingerprint)}</code> · {escape(row.model)} "
                f"v{escape(row.prompt_version)} · "
                f"{_dt(row.updated_at)} · попыток {row.attempts}"
                + (f" · ${row.cost_usd}" if row.cost_usd else "")
                + (" · file_id ✓" if row.telegram_file_id else "")
                + (f" · history {len(row.history)}" if row.history else "")
            )
            if row.error:
                lines.append(f"   ⚠️ {escape(row.error[:160])}")
    return "\n".join(lines)
