from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsEvent


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def track(self, telegram_id: int, event: str, payload: dict | None = None) -> None:
        self._session.add(
            AnalyticsEvent(telegram_id=telegram_id, event=event, payload=payload or {})
        )
