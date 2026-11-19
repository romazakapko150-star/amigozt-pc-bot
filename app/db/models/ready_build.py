from __future__ import annotations

from decimal import Decimal

from sqlalchemy import JSON, Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdType, TimestampMixin


class ReadyBuildStatus:
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


class ReadyBuild(TimestampMixin, Base):
    """A pre-built, compatibility-checked configuration in the catalogue.

    Two roles: something a customer can browse and order directly, and a
    template the recommendation engine can start from.

    ``reference_price_pln`` is what the build cost when it was generated - a
    snapshot, not a promise. The live price is always recomputed through the
    pricing layer, because component prices move.
    """

    __tablename__ = "ready_builds"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    #: Primary shelf this build sits on (budget, gaming, high_fps, ...).
    category: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    #: Secondary labels: resolutions, games, styles.
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    purpose: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    resolution: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    target_fps: Mapped[str | None] = mapped_column(String(16))
    tier: Mapped[str] = mapped_column(String(32), nullable=False)

    budget_min_pln: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    budget_max_pln: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    cpu_brand: Mapped[str] = mapped_column(String(16), nullable=False)
    gpu_brand: Mapped[str] = mapped_column(String(16), nullable=False)
    style: Mapped[str] = mapped_column(String(24), nullable=False)
    rgb: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wifi: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bluetooth: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    ram_gb: Mapped[int | None] = mapped_column(Integer)
    storage_gb: Mapped[int | None] = mapped_column(Integer)

    #: category -> component id, resolved against the catalogue on display.
    components: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    reference_price_pln: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    #: Admin-only snapshot of what the parts cost to acquire.
    reference_cost_pln: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    performance_score: Mapped[int | None] = mapped_column(Integer, index=True)

    # --- commercial metrics (admin only) --------------------------------
    #: All of the following describe the owner's economics, never the
    #: customer's view. Indexed where the admin panel sorts on them.
    estimated_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), index=True)
    complexity_score: Mapped[int | None] = mapped_column(Integer, index=True)
    complexity_level: Mapped[str | None] = mapped_column(String(16), index=True)
    labor_value_pln: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    component_margin_pln: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    service_reserve_pln: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    gross_profit_pln: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), index=True)
    profit_per_hour_pln: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), index=True)
    #: Full pricing breakdown as computed at seed time.
    pricing_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    @property
    def visual_priorities(self) -> list[str]:
        """What this shelf build asks a photograph to emphasise.

        A shelf row carries no priority list - the only thing it knows about
        presentation is whether it was put together to be seen. Nothing else
        is inferred, and every caller that renders a shelf visual asks here,
        so the batch and the customer's picker always agree on the key.
        """
        return ["looks"] if self.rgb else []

    status: Mapped[str] = mapped_column(
        String(16), default=ReadyBuildStatus.ACTIVE, index=True, nullable=False
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    #: Provenance. Generated builds record the engine, not a third-party shop.
    source: Mapped[str | None] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(String(512))
    image_url: Mapped[str | None] = mapped_column(String(512))

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ReadyBuild {self.slug}>"
