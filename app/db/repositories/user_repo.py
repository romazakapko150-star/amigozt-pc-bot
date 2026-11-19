from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        return await self._session.scalar(stmt)

    async def get_or_create(
        self,
        telegram_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        language: str = "ru",
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                language=language,
            )
            self._session.add(user)
            await self._session.flush()
            return user

        # Keep the profile fresh - users rename themselves often.
        if username != user.username:
            user.username = username
        if first_name and first_name != user.first_name:
            user.first_name = first_name
        return user
