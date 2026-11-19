from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.build_visualization import (
    Visual,
    VisualEntityType,
    VisualEvent,
    VisualEventKind,
    VisualizationStatus,
)


class VisualizationRepository:
    """Persistence of the Visual Library."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- lookups --------------------------------------------------------------

    async def get_by_fingerprint(self, fingerprint: str) -> Visual | None:
        return await self._session.scalar(select(Visual).where(Visual.fingerprint == fingerprint))

    async def get(self, visual_id: int) -> Visual | None:
        return await self._session.get(Visual, visual_id)

    async def find_valid_by_identity(self, identity_key: str) -> Visual | None:
        """Newest usable render of this identity, whatever prompt version made it."""
        stmt = (
            select(Visual)
            .where(
                Visual.identity_key == identity_key,
                Visual.status == VisualizationStatus.READY,
                Visual.is_valid.is_(True),
            )
            .order_by(Visual.updated_at.desc(), Visual.id.desc())
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def by_fingerprints(self, fingerprints: list[str]) -> dict[str, Visual]:
        if not fingerprints:
            return {}
        stmt = select(Visual).where(Visual.fingerprint.in_(fingerprints))
        return {row.fingerprint: row for row in await self._session.scalars(stmt)}

    async def by_identities(self, identity_keys: list[str]) -> dict[str, Visual]:
        """Newest valid ready render per identity."""
        if not identity_keys:
            return {}
        stmt = (
            select(Visual)
            .where(
                Visual.identity_key.in_(identity_keys),
                Visual.status == VisualizationStatus.READY,
                Visual.is_valid.is_(True),
            )
            .order_by(Visual.updated_at.asc(), Visual.id.asc())
        )
        found: dict[str, Visual] = {}
        for row in await self._session.scalars(stmt):
            found[row.identity_key] = row  # later rows (newer) overwrite
        return found

    async def list_recent(self, limit: int = 20) -> list[Visual]:
        stmt = select(Visual).order_by(Visual.updated_at.desc(), Visual.id.desc()).limit(limit)
        return list(await self._session.scalars(stmt))

    async def list_failed(self, limit: int = 50) -> list[Visual]:
        stmt = (
            select(Visual)
            .where(Visual.status == VisualizationStatus.FAILED)
            .order_by(Visual.updated_at.desc())
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def list_for_entity(self, entity_type: str, entity_id: str) -> list[Visual]:
        stmt = (
            select(Visual)
            .where(Visual.entity_type == entity_type, Visual.entity_id == entity_id)
            .order_by(Visual.updated_at.desc())
        )
        return list(await self._session.scalars(stmt))

    # --- writes -----------------------------------------------------------------

    async def start(
        self,
        fingerprint: str,
        *,
        identity_key: str,
        entity_type: str,
        entity_id: str,
        components: dict,
        preset_key: str,
        provider: str,
        model: str,
        prompt_version: str,
        prompt_hash: str,
        prompt_text: str,
        references_used: bool,
        entity_slug: str | None = None,
        category: str | None = None,
        build_id: int | None = None,
        ready_build_id: int | None = None,
    ) -> Visual:
        """Create or reuse the row for ``fingerprint`` and mark an attempt.

        A previous successful render is moved into ``history`` by the caller
        only once the new one is saved; until then the row keeps serving it.
        """
        row = await self.get_by_fingerprint(fingerprint)
        if row is None:
            row = Visual(
                fingerprint=fingerprint,
                identity_key=identity_key,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_slug=entity_slug,
                category=category,
                components=components,
                preset_key=preset_key,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                prompt_hash=prompt_hash,
                prompt_text=prompt_text,
                references_used=references_used,
                build_id=build_id,
                ready_build_id=ready_build_id,
                attempts=0,
                history=[],
            )
            self._session.add(row)
        else:
            row.identity_key = identity_key or row.identity_key
            row.entity_type = entity_type
            row.entity_id = entity_id or row.entity_id
            row.entity_slug = entity_slug or row.entity_slug
            row.category = category or row.category
            row.prompt_hash = prompt_hash
            row.prompt_text = prompt_text
            row.prompt_version = prompt_version
            row.model = model
            row.references_used = references_used
            if row.build_id is None:
                row.build_id = build_id
            if row.ready_build_id is None:
                row.ready_build_id = ready_build_id
        row.status = VisualizationStatus.PENDING
        row.error = None
        row.attempts += 1
        await self._session.flush()
        return row

    async def mark_ready(
        self,
        row: Visual,
        image_path: str,
        *,
        seconds: float | None,
        previous: dict | None = None,
        cost_usd: Decimal | None = None,
    ) -> None:
        if previous:
            history = list(row.history or [])
            history.append(previous)
            row.history = history
        row.image_path = image_path
        row.telegram_file_id = None
        row.status = VisualizationStatus.READY
        row.is_valid = True
        row.error = None
        row.generation_seconds = round(seconds, 2) if seconds is not None else None  # type: ignore[assignment]
        row.last_used_at = datetime.now(UTC)
        if cost_usd is not None:
            row.cost_usd = (row.cost_usd or Decimal(0)) + cost_usd
        await self._session.flush()

    async def mark_failed(
        self, row: Visual, error: str, *, cost_usd: Decimal | None = None
    ) -> None:
        row.status = VisualizationStatus.FAILED
        row.error = error[:1000]
        if cost_usd is not None:
            row.cost_usd = (row.cost_usd or Decimal(0)) + cost_usd
        await self._session.flush()

    async def restore_previous(self, row: Visual, image_path: str) -> None:
        """A forced re-render failed: the earlier picture stays in service."""
        row.status = VisualizationStatus.READY
        row.image_path = image_path
        await self._session.flush()

    async def touch(self, row: Visual) -> None:
        row.last_used_at = datetime.now(UTC)
        await self._session.flush()

    async def set_file_id(self, row: Visual, file_id: str | None) -> None:
        row.telegram_file_id = file_id
        await self._session.flush()

    async def invalidate(self, row: Visual, reason: str) -> None:
        """Hide from customers; the file and the row stay."""
        row.is_valid = False
        row.error = f"invalidated: {reason}"[:1000]
        await self._session.flush()

    async def revalidate(self, row: Visual) -> None:
        row.is_valid = True
        await self._session.flush()

    # --- ledger and statistics --------------------------------------------------

    async def record_event(
        self,
        kind: str,
        entity_type: str,
        fingerprint: str | None = None,
        cost_usd: Decimal | None = None,
    ) -> None:
        self._session.add(
            VisualEvent(
                kind=kind, entity_type=entity_type, fingerprint=fingerprint, cost_usd=cost_usd
            )
        )
        await self._session.flush()

    async def counts(self) -> dict[str, int]:
        stmt = select(Visual.status, func.count()).group_by(Visual.status)
        rows = (await self._session.execute(stmt)).all()
        counts = {
            status: 0
            for status in (
                VisualizationStatus.READY,
                VisualizationStatus.FAILED,
                VisualizationStatus.PENDING,
            )
        }
        for status, count in rows:
            counts[str(status)] = int(count)
        return counts

    async def stats(self) -> dict:
        """Library totals, per entity type, and the ledger summary."""
        by_type_stmt = select(
            Visual.entity_type, Visual.status, Visual.is_valid, func.count()
        ).group_by(Visual.entity_type, Visual.status, Visual.is_valid)
        per_type: dict[str, dict[str, int]] = {}
        for entity_type, status, is_valid, count in await self._session.execute(by_type_stmt):
            bucket = per_type.setdefault(
                str(entity_type), {"ready": 0, "failed": 0, "pending": 0, "invalid": 0}
            )
            if not is_valid:
                bucket["invalid"] += int(count)
            else:
                bucket[str(status)] = bucket.get(str(status), 0) + int(count)

        events_stmt = select(
            VisualEvent.kind, func.count(), func.coalesce(func.sum(VisualEvent.cost_usd), 0)
        ).group_by(VisualEvent.kind)
        events: dict[str, int] = {
            kind: 0
            for kind in (
                VisualEventKind.REQUEST,
                VisualEventKind.CACHE_HIT,
                VisualEventKind.API_CALL,
                VisualEventKind.GENERATED,
                VisualEventKind.FAILED,
            )
        }
        spend = Decimal(0)
        for kind, count, cost in await self._session.execute(events_stmt):
            events[str(kind)] = int(count)
            spend += Decimal(str(cost or 0))

        total_cost = await self._session.scalar(select(func.coalesce(func.sum(Visual.cost_usd), 0)))
        return {
            "per_type": per_type,
            "events": events,
            "spend_usd": spend.quantize(Decimal("0.01")),
            "visual_cost_usd": Decimal(str(total_cost or 0)).quantize(Decimal("0.01")),
            "entity_types": [
                VisualEntityType.READY_BUILD,
                VisualEntityType.BUILD,
                VisualEntityType.COMPONENT,
            ],
        }
