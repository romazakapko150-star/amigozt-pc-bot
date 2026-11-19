from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Build, Lead, User
from app.domain.enums import LeadStatus


class LeadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        build_id: int | None,
        *,
        contact: str | None = None,
        comment: str | None = None,
        pricing_snapshot: dict | None = None,
        compatibility_snapshot: dict | None = None,
    ) -> Lead:
        lead = Lead(
            user_id=user_id,
            build_id=build_id,
            status=LeadStatus.NEW.value,
            contact=contact,
            comment=comment,
            pricing_snapshot=pricing_snapshot or {},
            compatibility_snapshot=compatibility_snapshot or {},
        )
        self._session.add(lead)
        await self._session.flush()
        return lead

    async def get(self, lead_id: int) -> Lead | None:
        return await self._session.get(Lead, lead_id)

    async def get_open_for_build(self, build_id: int) -> Lead | None:
        """Prevents a double tap on "I want to order" creating two leads."""
        open_statuses = [status.value for status in LeadStatus if status.is_open]
        stmt = (
            select(Lead)
            .where(Lead.build_id == build_id, Lead.status.in_(open_statuses))
            .order_by(Lead.id.desc())
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def list_recent(
        self, *, statuses: list[LeadStatus] | None = None, limit: int = 10
    ) -> list[tuple[Lead, User, Build | None]]:
        """Recent leads with their customer and build already loaded."""
        stmt = (
            select(Lead, User, Build)
            .join(User, User.id == Lead.user_id)
            .outerjoin(Build, Build.id == Lead.build_id)
            .order_by(Lead.created_at.desc(), Lead.id.desc())
            .limit(limit)
        )
        if statuses:
            stmt = stmt.where(Lead.status.in_([status.value for status in statuses]))

        result = await self._session.execute(stmt)
        return [(lead, user, build) for lead, user, build in result.all()]

    async def load_context(self, lead_id: int) -> tuple[Lead, User, Build | None] | None:
        stmt = (
            select(Lead, User, Build)
            .join(User, User.id == Lead.user_id)
            .outerjoin(Build, Build.id == Lead.build_id)
            .where(Lead.id == lead_id)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        lead, user, build = row
        return lead, user, build

    async def set_status(
        self, lead_id: int, status: LeadStatus, *, admin_id: int | None = None
    ) -> Lead | None:
        lead = await self.get(lead_id)
        if lead is None:
            return None
        lead.status = status.value
        if admin_id is not None:
            lead.assigned_admin_id = admin_id
        await self._session.flush()
        return lead

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(Lead.status, func.count()).group_by(Lead.status)
        result = await self._session.execute(stmt)
        return {status: count for status, count in result.all()}
