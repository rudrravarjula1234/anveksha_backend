"""Users — storage layer, one canonical `users` table.

`roles` is order-sensitive (see `auth_service.py`'s role-resolution
logic), so it's a `user_roles` join table with an explicit `position`
column rather than a plain unordered join table.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# Kept in sync with app.schemas.user.UserRole.
_ROLES = ("candidate", "company", "interviewer", "hr", "admin")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_created_at", "created_at"),
        # Auth lower-cases emails before lookup (auth_service.py); this keeps
        # every write path honest so the case-sensitive unique index on
        # `email` really is unique per mailbox.
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    user_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    picture: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # `lazy="selectin"` + `order_by` on the FK side keeps `user.roles`
    # always loaded (no N+1 across the many places that read a user's full
    # role list) and always in original assignment order.
    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="UserRole.position",
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_roles_user_id_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # No standalone index: `uq_user_roles_user_id_role` leads with user_id.
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum(*_ROLES, name="user_role_value", native_enum=False, create_constraint=True),
        nullable=False,
        index=True,
    )
    # Preserves the original ordered-list semantics from Mongo — several
    # call sites key off roles[0] (primary role) / roles[-1] (most-recently
    # granted), e.g. auth_service.py's role-resolution logic.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(back_populates="roles")
