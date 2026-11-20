"""Traceability FKs: assessment creator, transcript->assessment/candidate/
verifier, report->transcript/assessment/verifier, interview->assessment.

Makes the assessment journey fully traceable with enforced foreign keys:
  user (admin) --created--> assessment
  user (candidate) --booked--> my_interview --is--> assessment
  my_interview --produces--> assessment_transcript (candidate, verifier, assessment)
  assessment_transcript --becomes--> skill_report_detail (verifier, assessment)

All columns are nullable with ON DELETE SET NULL so existing rows are valid
and deleting a parent never cascades away a transcript/report.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence
from typing import Optional

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Optional[str] = "0003"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    # assessments.created_by_id -> users.id
    op.add_column("assessments", sa.Column("created_by_id", sa.String(), nullable=True))
    op.create_index("ix_assessments_created_by_id", "assessments", ["created_by_id"])
    op.create_foreign_key(
        "fk_assessments_created_by", "assessments", "users",
        ["created_by_id"], ["id"], ondelete="SET NULL",
    )

    # my_interviews.assessment_id -> assessments.id
    op.add_column("my_interviews", sa.Column("assessment_id", sa.String(), nullable=True))
    op.create_index("ix_my_interviews_assessment_id", "my_interviews", ["assessment_id"])
    op.create_foreign_key(
        "fk_my_interviews_assessment", "my_interviews", "assessments",
        ["assessment_id"], ["id"], ondelete="SET NULL",
    )

    # assessment_transcripts.{assessment_id, candidate_user_id, verifier_user_id}
    op.add_column("assessment_transcripts", sa.Column("assessment_id", sa.String(), nullable=True))
    op.add_column("assessment_transcripts", sa.Column("candidate_user_id", sa.String(), nullable=True))
    op.add_column("assessment_transcripts", sa.Column("verifier_user_id", sa.String(), nullable=True))
    op.create_index("ix_assessment_transcripts_assessment_id", "assessment_transcripts", ["assessment_id"])
    op.create_index("ix_assessment_transcripts_candidate_user_id", "assessment_transcripts", ["candidate_user_id"])
    op.create_index("ix_assessment_transcripts_verifier_user_id", "assessment_transcripts", ["verifier_user_id"])
    op.create_foreign_key(
        "fk_transcript_assessment", "assessment_transcripts", "assessments",
        ["assessment_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_transcript_candidate", "assessment_transcripts", "users",
        ["candidate_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_transcript_verifier", "assessment_transcripts", "users",
        ["verifier_user_id"], ["id"], ondelete="SET NULL",
    )

    # skill_report_details.{transcript_id, assessment_id, verifier_user_id}
    op.add_column("skill_report_details", sa.Column("transcript_id", sa.String(), nullable=True))
    op.add_column("skill_report_details", sa.Column("assessment_id", sa.String(), nullable=True))
    op.add_column("skill_report_details", sa.Column("verifier_user_id", sa.String(), nullable=True))
    op.create_index("ix_skill_report_details_transcript_id", "skill_report_details", ["transcript_id"])
    op.create_index("ix_skill_report_details_assessment_id", "skill_report_details", ["assessment_id"])
    op.create_index("ix_skill_report_details_verifier_user_id", "skill_report_details", ["verifier_user_id"])
    op.create_foreign_key(
        "fk_report_transcript", "skill_report_details", "assessment_transcripts",
        ["transcript_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_report_assessment", "skill_report_details", "assessments",
        ["assessment_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_report_verifier", "skill_report_details", "users",
        ["verifier_user_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_report_verifier", "skill_report_details", type_="foreignkey")
    op.drop_constraint("fk_report_assessment", "skill_report_details", type_="foreignkey")
    op.drop_constraint("fk_report_transcript", "skill_report_details", type_="foreignkey")
    op.drop_index("ix_skill_report_details_verifier_user_id", "skill_report_details")
    op.drop_index("ix_skill_report_details_assessment_id", "skill_report_details")
    op.drop_index("ix_skill_report_details_transcript_id", "skill_report_details")
    op.drop_column("skill_report_details", "verifier_user_id")
    op.drop_column("skill_report_details", "assessment_id")
    op.drop_column("skill_report_details", "transcript_id")

    op.drop_constraint("fk_transcript_verifier", "assessment_transcripts", type_="foreignkey")
    op.drop_constraint("fk_transcript_candidate", "assessment_transcripts", type_="foreignkey")
    op.drop_constraint("fk_transcript_assessment", "assessment_transcripts", type_="foreignkey")
    op.drop_index("ix_assessment_transcripts_verifier_user_id", "assessment_transcripts")
    op.drop_index("ix_assessment_transcripts_candidate_user_id", "assessment_transcripts")
    op.drop_index("ix_assessment_transcripts_assessment_id", "assessment_transcripts")
    op.drop_column("assessment_transcripts", "verifier_user_id")
    op.drop_column("assessment_transcripts", "candidate_user_id")
    op.drop_column("assessment_transcripts", "assessment_id")

    op.drop_constraint("fk_my_interviews_assessment", "my_interviews", type_="foreignkey")
    op.drop_index("ix_my_interviews_assessment_id", "my_interviews")
    op.drop_column("my_interviews", "assessment_id")

    op.drop_constraint("fk_assessments_created_by", "assessments", type_="foreignkey")
    op.drop_index("ix_assessments_created_by_id", "assessments")
    op.drop_column("assessments", "created_by_id")
