from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdType


class EventName:
    """Canonical product analytics events (see roadmap section 33)."""

    START = "start"
    CONFIGURATOR_STARTED = "configurator_started"
    CONFIGURATOR_STEP = "configurator_step"
    CONFIGURATOR_COMPLETED = "configurator_completed"
    CONFIGURATOR_CANCELLED = "configurator_cancelled"
    BUILD_GENERATED = "build_generated"
    BUILD_SAVED = "build_saved"
    BUILD_SHARED = "build_shared"
    ORDER_CLICKED = "order_clicked"
    LEAD_CREATED = "lead_created"
    LEAD_STATUS_CHANGED = "lead_status_changed"
    ADMIN_OPENED = "admin_opened"
    READY_BUILDS_OPENED = "ready_builds_opened"
    READY_BUILD_VIEWED = "ready_build_viewed"
    READY_BUILD_ORDERED = "ready_build_ordered"
    COMPARE_OPENED = "compare_opened"
    COMPARE_RESULT = "compare_result"
    ACCESSORIES_OPENED = "accessories_opened"
    ACCESSORY_VIEWED = "accessory_viewed"
    VISUAL_SHOWN = "visual_shown"


class AnalyticsEvent(Base):
    """Anonymised product event. No message text is ever stored here."""

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    event: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
