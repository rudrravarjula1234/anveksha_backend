"""Interviewer approval workflows.

Approving a request has real cross-table effects (this is where the
backend goes beyond the mock):

1. The approval row flips to `approved` with reviewer + timestamp.
2. The candidate appears on (or extends) the active-interviewers list.
3. If the candidate has a skill ledger, the matching skill row gains
   `authority: true` and the ledger's `interviewerStatus` is promoted to
   freelance with the new authority appended — so the candidate's own
   profile reflects the grant immediately.

All three tables are written in the same session; the app's
one-transaction-per-request model (see app/db/session.py) makes this
atomic without any explicit `session.begin()` here.
"""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.timefmt import to_wire, to_wire_opt, utc_now
from app.models.approvals import (
    ActiveInterviewer as ActiveInterviewerModel,
)
from app.models.approvals import (
    InterviewerApproval as InterviewerApprovalModel,
)
from app.models.approvals import (
    SpecialistInvite as SpecialistInviteModel,
)
from app.models.skill import InterviewerAuthority as InterviewerAuthorityModel
from app.models.skill import SkillLedger as SkillLedgerModel
from app.schemas.approvals import (
    ActiveInterviewer,
    ApprovalsOverview,
    InterviewerApproval,
    SelfRequestBody,
    SpecialistInvite,
    SpecialistInviteBody,
)
from app.schemas.skill import ExternalProof


def _approval_to_schema(row: InterviewerApprovalModel) -> InterviewerApproval:
    return InterviewerApproval(
        id=row.id,
        candidateId=row.candidate_id,
        candidateName=row.candidate_name,
        candidateInitials=row.candidate_initials,
        dossierId=row.dossier_id,
        requestedSkill=row.requested_skill,
        origin=row.origin,  # type: ignore[arg-type]
        submittedAt=to_wire(row.submitted_at),
        status=row.status,  # type: ignore[arg-type]
        candidateScore=row.candidate_score,
        candidateSessions=row.candidate_sessions,
        botReasoning=row.bot_reasoning,
        reviewedBy=row.reviewed_by,
        reviewedAt=to_wire_opt(row.reviewed_at),
        decisionNote=row.decision_note,
    )


def _invite_to_schema(row: SpecialistInviteModel) -> SpecialistInvite:
    return SpecialistInvite(
        id=row.id,
        email=row.email,
        firstName=row.first_name,
        lastName=row.last_name,
        skillName=row.skill_name,
        bio=row.bio,
        externalProof=[ExternalProof(id=p["proof_id"], label=p["label"], url=p["url"]) for p in row.external_proofs],
        status=row.status,  # type: ignore[arg-type]
        invitedAt=to_wire(row.invited_at),
        invitedBy=row.invited_by,
        acceptedAt=to_wire_opt(row.accepted_at),
    )


def _active_to_schema(row: ActiveInterviewerModel) -> ActiveInterviewer:
    return ActiveInterviewer(
        candidateId=row.candidate_id,
        candidateName=row.candidate_name,
        candidateInitials=row.candidate_initials,
        mode=row.mode,  # type: ignore[arg-type]
        authorities=[a["skill_name"] for a in row.authorities],
        sessions=row.sessions,
        rating=row.rating,
        reliability=row.reliability,
        joinedAt=to_wire(row.joined_at),
    )


class ApprovalsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Reads ───────────────────────────────────────────────────────────

    # Decided requests are history: the console shows them as "recent
    # decisions", so only the newest are read (ix_interviewer_approvals_decided).
    # Every pending request is always returned; the review queue must be whole.
    RECENT_DECISIONS = 200

    async def overview(self) -> ApprovalsOverview:
        pending_stmt = (
            select(InterviewerApprovalModel)
            .where(InterviewerApprovalModel.status == "pending")
            .order_by(InterviewerApprovalModel.submitted_at, InterviewerApprovalModel.id)
        )
        decided_stmt = (
            select(InterviewerApprovalModel)
            .where(InterviewerApprovalModel.status != "pending")
            .order_by(InterviewerApprovalModel.reviewed_at.desc(), InterviewerApprovalModel.id.desc())
            .limit(self.RECENT_DECISIONS)
        )
        approvals = [
            *(await self.db.execute(pending_stmt)).scalars().all(),
            *(await self.db.execute(decided_stmt)).scalars().all(),
        ]
        invites = (await self.db.execute(select(SpecialistInviteModel))).scalars().all()
        active = (await self.db.execute(select(ActiveInterviewerModel))).scalars().all()
        return ApprovalsOverview(
            approvals=[_approval_to_schema(a) for a in approvals],
            invites=[_invite_to_schema(i) for i in invites],
            active=[_active_to_schema(a) for a in active],
        )

    # ── Decisions ───────────────────────────────────────────────────────

    async def _decide(
        self, approval_id: str, status: str, reviewer_id: str, note: Optional[str]
    ) -> InterviewerApprovalModel:
        # Row-locked so two reviewers deciding at once can't both pass the check.
        row = await self.db.get(InterviewerApprovalModel, approval_id, with_for_update=True)
        if row is None:
            raise NotFoundError(f"Approval {approval_id} not found")
        if row.status != "pending":
            # A decision is final: re-approving a rejection would grant the
            # authority, and rejecting an approval wouldn't take it back.
            raise ConflictError(f"Approval {approval_id} was already {row.status}")
        row.status = status
        row.reviewed_by = reviewer_id
        row.reviewed_at = utc_now()
        row.decision_note = note
        await self.db.flush()
        return row

    async def approve(
        self, approval_id: str, reviewer_id: str, note: Optional[str] = None
    ) -> InterviewerApproval:
        row = await self._decide(approval_id, "approved", reviewer_id, note)
        await self._grant_authority(row)
        return _approval_to_schema(row)

    async def reject(
        self, approval_id: str, reviewer_id: str, note: Optional[str] = None
    ) -> InterviewerApproval:
        row = await self._decide(approval_id, "rejected", reviewer_id, note)
        return _approval_to_schema(row)

    async def _grant_authority(self, approval: InterviewerApprovalModel) -> None:
        candidate_id = approval.candidate_id
        skill_name = approval.requested_skill
        now = approval.reviewed_at or utc_now()

        # 1. Active-interviewers list
        active = await self.db.get(ActiveInterviewerModel, candidate_id)
        if active is None:
            active = ActiveInterviewerModel(
                candidate_id=candidate_id,
                candidate_name=approval.candidate_name,
                candidate_initials=approval.candidate_initials,
                mode="freelance",
                sessions=0,
                joined_at=now,
            )
            self.db.add(active)
            await self.db.flush()
        existing_skills = {a["skill_name"] for a in active.authorities}
        if skill_name not in existing_skills:
            # Reassign the whole list (not an in-place append) so
            # SQLAlchemy's JSONB change tracking picks it up.
            active.authorities = active.authorities + [{"skill_name": skill_name}]

        # 2. Skill ledger — authority flag + interviewerStatus promotion
        ledger = await self.db.get(SkillLedgerModel, candidate_id)
        if ledger is None:
            await self.db.flush()
            return  # candidate has no ledger yet (external persona)

        matched_skill_id = None
        for skill_row in ledger.skills:
            if skill_row.name == skill_name:
                skill_row.authority = True
                skill_row.authority_since = now
                matched_skill_id = skill_row.skill_id
                break

        if ledger.interviewer_mode in (None, "none", "pending"):
            ledger.interviewer_mode = "freelance"
            if ledger.interviewer_origin is None:
                ledger.interviewer_origin = approval.origin
            ledger.interviewer_approved_by = approval.reviewed_by
            ledger.interviewer_approved_at = now

        existing_authorities = {a.skill_name for a in ledger.authorities}
        if skill_name not in existing_authorities:
            self.db.add(
                InterviewerAuthorityModel(
                    ledger_candidate_id=candidate_id,
                    skill_id=matched_skill_id or skill_name.lower().replace(" ", "_"),
                    skill_name=skill_name,
                    approved_at=now,
                )
            )
        await self.db.flush()

    # ── Candidate self-request ──────────────────────────────────────────

    async def self_request(
        self, body: SelfRequestBody, user_doc: Optional[dict[str, Any]]
    ) -> InterviewerApproval:
        if not user_doc:
            raise ValidationError("user record required for a self-request")
        # Block duplicate pending requests for the same skill. This check
        # gives the common case a clean 409; the partial unique index
        # `uq_interviewer_approvals_pending_skill` catches the concurrent one.
        stmt = select(InterviewerApprovalModel).where(
            InterviewerApprovalModel.candidate_id == user_doc["id"],
            InterviewerApprovalModel.requested_skill == body.skillName,
            InterviewerApprovalModel.status == "pending",
        )
        dup = (await self.db.execute(stmt)).scalar_one_or_none()
        if dup:
            raise ValidationError(
                f"A pending request for {body.skillName} already exists",
                status_code=409,
            )
        initials = (user_doc.get("first_name") or "?")[:1].upper()
        row = InterviewerApprovalModel(
            id=f"apr_{str(ULID()).lower()}",
            candidate_id=user_doc["id"],
            candidate_name=f"{user_doc.get('first_name', '')} {user_doc.get('last_name', '')}".strip(),
            candidate_initials=initials,
            dossier_id="ANV-" + user_doc["id"][-4:].upper(),
            requested_skill=body.skillName,
            origin="self-requested",
            submitted_at=utc_now(),
            status="pending",
            candidate_score=body.skillScore,
            candidate_sessions=body.sessions,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(row)
        except IntegrityError as exc:
            raise ValidationError(
                f"A pending request for {body.skillName} already exists",
                status_code=409,
            ) from exc
        return _approval_to_schema(row)

    # ── Specialist invites ──────────────────────────────────────────────

    async def invite_specialist(
        self, body: SpecialistInviteBody, reviewer_id: str
    ) -> SpecialistInvite:
        row = SpecialistInviteModel(
            id=f"inv_{str(ULID()).lower()}",
            email=body.email,
            first_name=body.firstName,
            last_name=body.lastName,
            skill_name=body.skillName,
            bio=body.bio,
            status="sent",
            invited_at=utc_now(),
            invited_by=reviewer_id,
        )
        row.external_proofs = [
            {"proof_id": p.id, "label": p.label, "url": p.url} for p in body.externalProof
        ]
        self.db.add(row)
        await self.db.flush()
        return _invite_to_schema(row)
