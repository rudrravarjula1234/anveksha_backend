"""Assessments + coupons — storage layer."""


from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

_TYPES = ("live", "bot", "bot-assisted")
_DOMAINS = ("Backend", "Frontend", "Data", "Payments", "Cloud", "Platform", "Leadership", "Behavioral")
_DEPTHS = ("Foundational", "Intermediate", "Advanced", "Expert", "Staff")
_COUPON_TYPES = ("percent", "fixed")


class Assessment(Base, TimestampMixin):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_assessments_price_nonneg"),
        CheckConstraint("duration > 0", name="ck_assessments_duration_pos"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(
        Enum(*_DOMAINS, name="assessment_domain", native_enum=False, create_constraint=True),
        nullable=False,
    )
    depth: Mapped[str] = mapped_column(
        Enum(*_DEPTHS, name="assessment_depth", native_enum=False, create_constraint=True),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(
        Enum(*_TYPES, name="assessment_type", native_enum=False, create_constraint=True), nullable=False
    )
    duration: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    popular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Flat, non-cross-referenced string lists — ARRAY, not child tables.
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    probes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    bot_links: Mapped[list["AssessmentBot"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", lazy="selectin"
    )


class AssessmentBot(Base):
    """Join table — assessments.botIds, now a real FK into bots."""

    __tablename__ = "assessment_bots"
    __table_args__ = (UniqueConstraint("assessment_id", "bot_id", name="uq_assessment_bot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # No standalone index on assessment_id: `uq_assessment_bot` leads with it.
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    # Indexed so `ON DELETE CASCADE` from bots doesn't scan this table.
    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True)

    assessment: Mapped["Assessment"] = relationship(back_populates="bot_links")


class Coupon(Base, TimestampMixin):
    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint("value > 0", name="ck_coupons_value_pos"),
        CheckConstraint("type <> 'percent' OR value <= 100", name="ck_coupons_percent_max"),
    )

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    type: Mapped[str] = mapped_column(
        Enum(*_COUPON_TYPES, name="coupon_type", native_enum=False, create_constraint=True),
        nullable=False,
    )
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    desc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
