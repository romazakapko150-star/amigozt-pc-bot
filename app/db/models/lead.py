from __future__ import annotations

from sqlalchemy import JSON, BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdType, TimestampMixin
from app.domain.enums import LeadStatus


class Lead(TimestampMixin, Base):
    """Purchase request. Deliberately stores the minimum of personal data.

    Everything needed to contact the customer is already in ``users`` (their
    Telegram id and username), so no phone numbers or emails are collected
    unless the customer volunteers them in ``contact``.
    """

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        IdType, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    build_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("builds.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(
        String(32), default=LeadStatus.NEW.value, index=True, nullable=False
    )
    #: Telegram id of the admin who took the lead, if any.
    assigned_admin_id: Mapped[int | None] = mapped_column(BigInteger)

    contact: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)

    #: Pricing frozen at the moment the order was placed. Component prices move;
    #: what this order was *supposed* to earn must not move with them.
    pricing_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    #: Compatibility report frozen at the moment the order was placed
    #: (``CompatibilityReport.as_dict()`` plus the power budget). Catalogue
    #: data changes later; what was checked for *this* order must not.
    compatibility_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    @property
    def status_enum(self) -> LeadStatus:
        try:
            return LeadStatus(self.status)
        except ValueError:  # pragma: no cover - legacy rows
            return LeadStatus.NEW
