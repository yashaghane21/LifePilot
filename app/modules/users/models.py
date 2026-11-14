import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Emails are stored lowercased; the database enforces it in case a code path forgets.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )
    # Load server-generated values (created_at) via INSERT ... RETURNING, saving a round trip.
    __mapper_args__ = {"eager_defaults": True}

    # UUIDv7: not guessable like 1, 2, 3, yet time-ordered, so the primary-key index stays compact.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    # None for accounts that only sign in through an external provider such as Google.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # Set once ownership of `email` is proven (today: by Google). An account whose email was
    # never verified may have been registered by someone else (pre-account hijacking).
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        # Never include password_hash or email: reprs end up in logs and tracebacks.
        return f"<User id={self.id}>"
