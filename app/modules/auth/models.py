import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OAuthIdentity(Base):
    """Links a LifePilot user to an account at an external identity provider."""

    __tablename__ = "oauth_identities"
    __table_args__ = (
        # One provider account can belong to only one LifePilot user.
        UniqueConstraint("provider", "subject", name="uq_oauth_identities_provider_subject"),
    )
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    # The provider's permanent user id (Google `sub`). Emails can change; this cannot.
    subject: Mapped[str] = mapped_column(String(255))
    # The email the provider reported at link time, for display and auditing only.
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<OAuthIdentity provider={self.provider} user_id={self.user_id}>"


class RefreshSession(Base):
    """One refresh token. Each refresh marks the row used and inserts its successor in the
    same family; a used token presented again means theft, and the whole family is revoked."""

    __tablename__ = "refresh_sessions"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Every token descended from one login shares a family_id.
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    # SHA-256 of the token; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<RefreshSession id={self.id} family={self.family_id}>"
