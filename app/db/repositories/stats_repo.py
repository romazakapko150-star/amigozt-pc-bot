from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsEvent, Build, EventName, Lead, User


@dataclass(slots=True)
class AdminStats:
    users_total: int = 0
    users_last_7d: int = 0
    builds_total: int = 0
    leads_total: int = 0
    leads_by_status: dict[str, int] = field(default_factory=dict)
    configurators_started: int = 0
    configurators_completed: int = 0
    top_budgets: list[tuple[int, int]] = field(default_factory=list)
    top_purposes: list[tuple[str, int]] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        """Share of started configurators that reached the summary."""
        if not self.configurators_started:
            return 0.0
        return self.configurators_completed / self.configurators_started


class StatsRepository:
    """Read-only aggregates for the admin interface."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _count(self, model: type, *conditions: object) -> int:
        stmt = select(func.count()).select_from(model)
        for condition in conditions:
            stmt = stmt.where(condition)  # type: ignore[arg-type]
        return int(await self._session.scalar(stmt) or 0)

    async def _event_count(self, event: str) -> int:
        return await self._count(AnalyticsEvent, AnalyticsEvent.event == event)

    async def collect(self) -> AdminStats:
        week_ago = datetime.now(UTC) - timedelta(days=7)

        stats = AdminStats(
            users_total=await self._count(User),
            users_last_7d=await self._count(User, User.created_at >= week_ago),
            builds_total=await self._count(Build),
            leads_total=await self._count(Lead),
            configurators_started=await self._event_count(EventName.CONFIGURATOR_STARTED),
            configurators_completed=await self._event_count(EventName.CONFIGURATOR_COMPLETED),
        )

        by_status = await self._session.execute(
            select(Lead.status, func.count()).group_by(Lead.status)
        )
        stats.leads_by_status = {status: count for status, count in by_status.all()}

        budgets = await self._session.execute(
            select(Build.budget_pln, func.count().label("n"))
            .where(Build.budget_pln.is_not(None))
            .group_by(Build.budget_pln)
            .order_by(func.count().desc())
            .limit(5)
        )
        stats.top_budgets = [(int(budget), count) for budget, count in budgets.all()]

        purposes = await self._session.execute(
            select(Build.purpose, func.count().label("n"))
            .where(Build.purpose.is_not(None))
            .group_by(Build.purpose)
            .order_by(func.count().desc())
            .limit(5)
        )
        stats.top_purposes = [(str(purpose), count) for purpose, count in purposes.all()]

        return stats
