"""Skill-ledger reads.

The ledger is the composite powering the Candidate Profile page. It's
stored denormalised per candidate in `skill_ledgers` (Postgres — one row
per candidate, plus child tables for skills/authorities/external proof).

Fallback rule mirrors the mock: unknown or unauthenticated callers get
Aarav's ledger so the page always renders.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timefmt import to_wire, to_wire_opt
from app.models.skill import SkillLedger as SkillLedgerModel
from app.schemas.skill import (
    ExternalProof,
    InterviewerAuthority,
    InterviewerStats,
    InterviewerStatus,
    SkillLedger,
    SkillLedgerRow,
)

_FALLBACK_CANDIDATE_ID = "usr_cand_001"


def ledger_to_schema(row: SkillLedgerModel) -> SkillLedger:
    has_stats = any(
        v is not None
        for v in (
            row.stats_sessions,
            row.stats_rating,
            row.stats_reliability,
            row.stats_peer_score,
            row.stats_appeal_rate,
            row.stats_average_review_minutes,
            row.stats_monthly_earnings,
        )
    )
    stats = (
        InterviewerStats(
            sessions=row.stats_sessions,
            rating=row.stats_rating,
            reliability=row.stats_reliability,
            peerScore=row.stats_peer_score,
            appealRate=row.stats_appeal_rate,
            averageReviewMinutes=row.stats_average_review_minutes,
            monthlyEarnings=row.stats_monthly_earnings,
        )
        if has_stats
        else None
    )
    external_proof = (
        [ExternalProof(id=p["proof_id"], label=p["label"], url=p["url"]) for p in row.external_proofs]
        if row.external_proofs
        else None
    )
    return SkillLedger(
        candidateId=row.candidate_id,
        candidateName=row.candidate_name,
        candidateTitle=row.candidate_title,
        candidateLocation=row.candidate_location,
        candidateInitials=row.candidate_initials,
        dossierId=row.dossier_id,
        verificationScore=row.verification_score,
        verifiedCount=row.verified_count,
        partialCount=row.partial_count,
        grayCount=row.gray_count,
        topPercent=row.top_percent,
        interviewerStatus=InterviewerStatus(
            mode=row.interviewer_mode,  # type: ignore[arg-type]
            origin=row.interviewer_origin,  # type: ignore[arg-type]
            approvedBy=row.interviewer_approved_by,
            approvedAt=to_wire_opt(row.interviewer_approved_at),
            authorities=[
                InterviewerAuthority(skillId=a.skill_id, skillName=a.skill_name, approvedAt=to_wire(a.approved_at))
                for a in row.authorities
            ],
            stats=stats,
            bio=row.interviewer_bio,
            externalProof=external_proof,
        ),
        skills=[
            SkillLedgerRow(
                id=s.skill_id,
                name=s.name,
                state=s.state,  # type: ignore[arg-type]
                depth=s.depth,  # type: ignore[arg-type]
                score=s.score,
                lastVerified=s.last_verified,
                sessions=s.sessions,
                reportId=s.report_id,
                authority=s.authority,
                authoritySince=to_wire_opt(s.authority_since),
            )
            for s in row.skills
        ],
    )


class SkillService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ledger_for_user(self, user_id: Optional[str]) -> SkillLedger:
        row = None
        if user_id:
            row = await self.db.get(SkillLedgerModel, user_id)
        if row is None:
            row = await self.db.get(SkillLedgerModel, _FALLBACK_CANDIDATE_ID)
        if row is None:
            # Seeds missing — fail loudly rather than fabricate an empty page.
            raise RuntimeError("skill_ledgers seed data missing")
        return ledger_to_schema(row)
