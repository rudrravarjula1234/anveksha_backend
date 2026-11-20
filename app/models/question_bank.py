"""Graph-RAG interview question bank — storage layer.

Two tables power the "smart interviewer":

- ``interview_questions`` — one row per question the bot can ask, keyed by a
  free-text ``skill`` (matches ``booking_catalogs.skill_name`` /
  ``bots.specializations``). Each carries a Gemini embedding (768-dim) for
  vector retrieval, the probe area it covers, what it assesses, a difficulty,
  and learned quality signals that rank it over time.
- ``question_edges`` — the graph layer: directed relationships between
  questions (follow-up / drill-down / related / prereq) so the bot can
  traverse — drill deeper on a productive thread or jump to a new topic.

All new RAG state lives in the backend (it owns the DB, pgvector, and the
Gemini credential); RAW's bot-worker only calls an endpoint.
"""

from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# Gemini `gemini-embedding-001` truncated to 768 dims (requested via the
# embeddings call's `dimensions`) — small enough for a pgvector HNSW index
# (the type caps indexable dims at 2000) while keeping good retrieval.
EMBED_DIM = 768

_SOURCES = ("seed", "generated", "learned")
_RELATIONS = ("follow_up", "drill_down", "related", "prereq")


class InterviewQuestion(Base, TimestampMixin):
    __tablename__ = "interview_questions"
    __table_args__ = (Index("ix_interview_questions_skill", "skill"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Free-text skill key — retrieval filters on this. Matches
    # booking_catalogs.skill_name / an entry in bots.specializations.
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    depth: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # The probe area this question covers (coverage is tracked per area so
    # the bot knows when to switch topics). Free text, e.g. "Idempotency".
    probe_area: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    assesses: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=3)  # 1..5
    expected_signals: Mapped[str] = mapped_column(Text, nullable=False, default="")

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM), nullable=True)

    source: Mapped[str] = mapped_column(String(20), nullable=False, default="seed")
    # Learned ranking signals — updated by the post-session scorer.
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    times_asked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_signal_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class QuestionEdge(Base, TimestampMixin):
    __tablename__ = "question_edges"
    __table_args__ = (
        UniqueConstraint("src_question_id", "dst_question_id", "relation", name="uq_question_edge"),
        Index("ix_question_edges_src", "src_question_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    src_question_id: Mapped[str] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE"), nullable=False
    )
    dst_question_id: Mapped[str] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(20), nullable=False)
    # Traversal weight — bumped/decayed by the learning loop when a drill
    # chain actually elicits signal.
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
