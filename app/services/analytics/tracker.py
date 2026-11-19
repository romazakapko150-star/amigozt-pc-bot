from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import AnalyticsRepository

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Anonymised product analytics.

    Only enum-like values and numbers are recorded - never message text, never
    contact details. Tracking is best-effort: a failure here must not cost the
    user their answer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = AnalyticsRepository(session)

    async def track(self, telegram_id: int, event: str, **payload: Any) -> None:
        try:
            await self._repo.track(telegram_id, event, payload)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to record analytics event %s", event)
