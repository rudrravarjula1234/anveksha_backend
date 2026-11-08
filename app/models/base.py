"""Declarative base + shared mixins for all ORM models.

Kept separate from `app/db/session.py` (engine/session lifecycle) so
`app/models/*` never has to import the engine module — avoids a circular
import between models and connection wiring.
"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for every ORM model in `app/models/`."""


class TimestampMixin:
    """`created_at` / `updated_at`, stamped server-side (Postgres `now()`).

    `onupdate=func.now()` covers writes made through this app's ORM.
    A DB-level trigger (see the `updated_at_trigger` migration) backstops
    writes from outside it — raw SQL, the Supabase SQL editor, future
    bulk scripts — so `updated_at` stays authoritative either way.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
