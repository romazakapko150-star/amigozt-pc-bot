from __future__ import annotations

from decimal import Decimal

from sqlalchemy import JSON, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdType, TimestampMixin


class Build(TimestampMixin, Base):
    """A configuration produced by the configurator.

    ``requirements`` always holds the normalised ``BuildRequirements`` payload.
    ``components`` / ``estimated_fps`` are filled in by the recommendation
    engine (Phase 2-3) and stay empty for drafts.
    """

    __tablename__ = "builds"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    tier: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(128))

    requirements: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    components: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    estimated_fps: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Denormalised for cheap analytics queries / admin dashboard filters.
    budget_pln: Mapped[int | None] = mapped_column(Integer)
    purpose: Mapped[str | None] = mapped_column(String(32), index=True)
    resolution: Mapped[str | None] = mapped_column(String(16))
    target_fps: Mapped[str | None] = mapped_column(String(16))
    total_price_pln: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    is_saved: Mapped[bool] = mapped_column(default=False, nullable=False)
