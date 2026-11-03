from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SsoLoginTicket(TimestampMixin, Base):
    """JTI of an accepted, short-lived CRM login ticket; primary key prevents replay."""

    __tablename__ = "sso_login_tickets"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
