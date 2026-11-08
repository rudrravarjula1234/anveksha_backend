"""Provider credential storage — one row per provider, `provider`
(lowercase) as the natural primary key. `additional_config` is a
free-form, provider-specific blob, so it stays JSONB.
"""

from typing import Any, Optional

from sqlalchemy import Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ModelCredential(Base, TimestampMixin):
    __tablename__ = "model_credentials"

    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    additional_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
