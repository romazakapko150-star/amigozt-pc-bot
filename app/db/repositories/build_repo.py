from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Build
from app.domain.requirements import BuildRequirements


class BuildRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_draft(self, user_id: int, requirements: BuildRequirements) -> Build:
        build = Build(
            user_id=user_id,
            requirements=requirements.model_dump(mode="json"),
            components={},
            estimated_fps={},
            budget_pln=requirements.budget_pln,
            purpose=requirements.purpose.value,
            resolution=requirements.resolution.value,
            target_fps=requirements.target_fps.value if requirements.target_fps else None,
        )
        self._session.add(build)
        await self._session.flush()
        return build

    async def get(self, build_id: int) -> Build | None:
        return await self._session.get(Build, build_id)

    async def list_for_user(self, user_id: int, limit: int = 10) -> list[Build]:
        stmt = (
            select(Build)
            .where(Build.user_id == user_id)
            .order_by(Build.created_at.desc())
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return list(result)
