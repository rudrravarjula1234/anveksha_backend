"""assessment_transcripts — ingested RAW session transcripts.

Stores the full transcript + metadata + optional dossier the RAW bot-worker
POSTs when an assessment session ends. See app/models/session_ingest.py.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assessment_transcripts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("room", sa.String(), nullable=False),
        sa.Column("booking_id", sa.String(), nullable=True),
        sa.Column("bot_id", sa.String(), nullable=True),
        sa.Column("response_mode", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ended"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transcript", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("participants", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("dossier", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assessment_transcripts_room", "assessment_transcripts", ["room"])
    op.create_index("ix_assessment_transcripts_booking_id", "assessment_transcripts", ["booking_id"])


def downgrade() -> None:
    op.drop_index("ix_assessment_transcripts_booking_id", table_name="assessment_transcripts")
    op.drop_index("ix_assessment_transcripts_room", table_name="assessment_transcripts")
    op.drop_table("assessment_transcripts")
