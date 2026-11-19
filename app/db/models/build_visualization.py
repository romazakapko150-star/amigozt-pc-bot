from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdType, TimestampMixin


class VisualizationStatus:
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class VisualEntityType:
    """What a visual depicts."""

    BUILD = "build"  # a customer's configured machine (builds row or ad hoc)
    READY_BUILD = "ready_build"  # a shelf entry
    COMPONENT = "component"  # one catalogue product


class Visual(TimestampMixin, Base):
    """One saved picture of one thing the bot can show: a build, a shelf
    entry, a product. The global Visual Library.

    ``identity_key`` says *what* is depicted (parts + look, or the product);
    ``fingerprint`` adds the prompt version and the image model, so the row
    is the exact render. Lookups try the fingerprint first and then fall
    back to any valid visual of the same identity: a newer prompt version
    never makes the catalogue re-render by itself.

    Successful visuals are never deleted by code. A forced re-render keeps
    the previous file and records it under ``history``; ``is_valid=False``
    only hides a visual from customers.
    """

    __tablename__ = "visuals"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)

    entity_type: Mapped[str] = mapped_column(
        String(16), default=VisualEntityType.BUILD, index=True, nullable=False
    )
    #: Component id, ready-build id or build id as text; identity for ad hoc builds.
    entity_id: Mapped[str] = mapped_column(String(96), default="", index=True, nullable=False)
    entity_slug: Mapped[str | None] = mapped_column(String(120))
    #: Catalogue category for components, "build" for machines.
    category: Mapped[str | None] = mapped_column(String(32))

    identity_key: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    build_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("builds.id", ondelete="SET NULL"), index=True
    )
    ready_build_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("ready_builds.id", ondelete="SET NULL"), index=True
    )

    #: category -> component id for builds; the spec facts for products.
    components: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    preset_key: Mapped[str] = mapped_column(String(40), default="", nullable=False)

    image_path: Mapped[str | None] = mapped_column(String(512))
    #: Telegram's id for the uploaded image, learnt after the first send.
    telegram_file_id: Mapped[str | None] = mapped_column(String(256))

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(8), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Full prompt, so an admin can see exactly what was asked for.
    prompt_text: Mapped[str | None] = mapped_column(Text)
    references_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), default=VisualizationStatus.PENDING, index=True, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generation_seconds: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Where the picture came from: "openai-images", "manual", "schematic".
    source: Mapped[str] = mapped_column(String(32), default="openai-images", nullable=False)
    #: False hides the visual from customers without deleting anything.
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Earlier renders of this fingerprint, newest last. Files are kept.
    history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    #: Approximate spend on this visual (all attempts), in USD.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    @property
    def is_ready(self) -> bool:
        return self.status == VisualizationStatus.READY and bool(self.image_path) and self.is_valid

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Visual {self.entity_type}:{self.entity_id} {self.fingerprint} {self.status}>"


#: Name used by the first version of the visualiser.
BuildVisualization = Visual


class VisualEventKind:
    REQUEST = "request"
    CACHE_HIT = "cache_hit"
    API_CALL = "api_call"
    GENERATED = "generated"
    FAILED = "failed"


class VisualEvent(Base):
    """Append-only ledger behind the cost and cache statistics."""

    __tablename__ = "visual_events"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
