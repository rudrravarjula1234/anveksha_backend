"""Graph-RAG interview question bank: pgvector + interview_questions + question_edges.

See app/models/question_bank.py.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.db.rls import enable_rls_sql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBED_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "interview_questions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=60), nullable=True),
        sa.Column("depth", sa.String(length=30), nullable=True),
        sa.Column("probe_area", sa.String(length=200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("assesses", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("expected_signals", sa.Text(), nullable=False, server_default=""),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="seed"),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("times_asked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_signal_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_questions_skill", "interview_questions", ["skill"])
    # Cosine-distance HNSW index for vector retrieval.
    op.execute(
        "CREATE INDEX ix_interview_questions_embedding ON interview_questions "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "question_edges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("src_question_id", sa.String(), nullable=False),
        sa.Column("dst_question_id", sa.String(), nullable=False),
        sa.Column("relation", sa.String(length=20), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["src_question_id"], ["interview_questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dst_question_id"], ["interview_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("src_question_id", "dst_question_id", "relation", name="uq_question_edge"),
    )
    op.create_index("ix_question_edges_src", "question_edges", ["src_question_id"])

    op.execute(enable_rls_sql("interview_questions"))
    op.execute(enable_rls_sql("question_edges"))


def downgrade() -> None:
    op.drop_index("ix_question_edges_src", table_name="question_edges")
    op.drop_table("question_edges")
    op.execute("DROP INDEX IF EXISTS ix_interview_questions_embedding")
    op.drop_index("ix_interview_questions_skill", table_name="interview_questions")
    op.drop_table("interview_questions")
    # Leave the vector extension installed — other objects may use it.
