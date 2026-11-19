from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import ReadyBuild, ReadyBuildStatus

#: Business rankings the admin can ask for: key -> ORDER BY clause.
RANKINGS: dict[str, ColumnElement] = {
    "profit": ReadyBuild.gross_profit_pln.desc(),
    "hour_best": ReadyBuild.profit_per_hour_pln.desc(),
    "hour_worst": ReadyBuild.profit_per_hour_pln.asc(),
    "complex": ReadyBuild.complexity_score.desc(),
    "longest": ReadyBuild.estimated_hours.desc(),
    "revenue": ReadyBuild.reference_price_pln.desc(),
    "margin_low": (ReadyBuild.gross_profit_pln / ReadyBuild.reference_price_pln).asc(),
}


class ReadyBuildRepository:
    """Read access to the ready-build shelf."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base(self):  # type: ignore[no-untyped-def]
        return select(ReadyBuild).where(ReadyBuild.status == ReadyBuildStatus.ACTIVE)

    async def get(self, build_id: int) -> ReadyBuild | None:
        return await self._session.get(ReadyBuild, build_id)

    async def get_by_slug(self, slug: str) -> ReadyBuild | None:
        return await self._session.scalar(select(ReadyBuild).where(ReadyBuild.slug == slug))

    async def list_active(self) -> list[ReadyBuild]:
        stmt = (
            select(ReadyBuild)
            .where(ReadyBuild.status == ReadyBuildStatus.ACTIVE)
            .order_by(ReadyBuild.id)
        )
        return list(await self._session.scalars(stmt))

    async def count(self, *, category: str | None = None, max_price_pln: int | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(ReadyBuild)
            .where(ReadyBuild.status == ReadyBuildStatus.ACTIVE)
        )
        stmt = self._apply(stmt, category, max_price_pln)
        return int(await self._session.scalar(stmt) or 0)

    async def fetch(
        self,
        *,
        category: str | None = None,
        max_price_pln: int | None = None,
        limit: int = 5,
        offset: int = 0,
    ) -> list[ReadyBuild]:
        stmt = self._apply(self._base(), category, max_price_pln)
        stmt = stmt.order_by(ReadyBuild.reference_price_pln.asc()).limit(limit).offset(offset)
        return list(await self._session.scalars(stmt))

    async def ranked(self, sort: str, limit: int = 10) -> list[ReadyBuild]:
        """Shelf entries ordered by a business metric. Admin only."""
        order = RANKINGS.get(sort)
        if order is None:
            return []
        stmt = self._base().where(ReadyBuild.profit_per_hour_pln.is_not(None))
        return list(await self._session.scalars(stmt.order_by(order).limit(limit)))

    async def categories(self) -> list[tuple[str, int]]:
        """Categories that actually have builds, with their counts."""
        stmt = (
            select(ReadyBuild.category, func.count())
            .where(ReadyBuild.status == ReadyBuildStatus.ACTIVE)
            .group_by(ReadyBuild.category)
            .order_by(func.count().desc())
        )
        result = await self._session.execute(stmt)
        return [(category, count) for category, count in result.all()]

    @staticmethod
    def _apply(stmt, category: str | None, max_price_pln: int | None):  # type: ignore[no-untyped-def]
        if category:
            stmt = stmt.where(ReadyBuild.category == category)
        if max_price_pln is not None:
            stmt = stmt.where(ReadyBuild.reference_price_pln <= max_price_pln)
        return stmt
