from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Build, Lead, User
from app.db.repositories import BuildRepository, LeadRepository

logger = logging.getLogger(__name__)


class LeadService:
    """Creates purchase requests from a finished configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._leads = LeadRepository(session)
        self._builds = BuildRepository(session)

    async def request_order(
        self,
        user: User,
        build_id: int | None,
        *,
        comment: str | None = None,
        pricing_snapshot: dict | None = None,
        compatibility_snapshot: dict | None = None,
    ) -> tuple[Lead, Build | None, bool]:
        """Returns ``(lead, build, created)``.

        ``created`` is False when an open lead already exists for this build,
        which is what a double tap on "I want to order" produces.
        """
        build = await self._builds.get(build_id) if build_id is not None else None

        if build is not None:
            existing = await self._leads.get_open_for_build(build.id)
            if existing is not None:
                return existing, build, False

        lead = await self._leads.create(
            user.id,
            build.id if build else None,
            comment=comment,
            pricing_snapshot=pricing_snapshot,
            compatibility_snapshot=compatibility_snapshot,
        )
        if build is not None:
            build.is_saved = True

        logger.info("Lead #%s created for user_id=%s build_id=%s", lead.id, user.id, build_id)
        return lead, build, True
