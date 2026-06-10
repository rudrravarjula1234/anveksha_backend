"""Interviewer approval workflows.

Approving a request has real cross-collection effects (this is where the
backend goes beyond the mock):

1. The approval row flips to `approved` with reviewer + timestamp.
2. The candidate appears on (or extends) the active-interviewers list.
3. If the candidate has a skill ledger, the matching skill row gains
   `authority: true` and the ledger's `interviewerStatus` is promoted to
   freelance with the new authority appended — so the candidate's own
   profile reflects the grant immediately.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from ulid import ULID

from app.core.exceptions import NotFoundError, ValidationError
from app.db.mongo import get_database
from app.schemas.approvals import (
    ActiveInterviewer,
    ApprovalsOverview,
    InterviewerApproval,
    SelfRequestBody,
    SpecialistInvite,
    SpecialistInviteBody,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip(doc: dict[str, Any]) -> dict[str, Any]:
    doc.pop("_id", None)
    return doc


class ApprovalsService:
    def _db(self):
        return get_database()

    # ── Reads ───────────────────────────────────────────────────────────

    async def overview(self) -> ApprovalsOverview:
        approvals = await self._db()["interviewer_approvals"].find().to_list(length=500)
        invites = await self._db()["specialist_invites"].find().to_list(length=500)
        active = await self._db()["active_interviewers"].find().to_list(length=500)
        return ApprovalsOverview(
            approvals=[InterviewerApproval.model_validate(_strip(d)) for d in approvals],
            invites=[SpecialistInvite.model_validate(_strip(d)) for d in invites],
            active=[ActiveInterviewer.model_validate(_strip(d)) for d in active],
        )

    # ── Decisions ───────────────────────────────────────────────────────

    async def _decide(
        self, approval_id: str, status: str, reviewer_id: str, note: Optional[str]
    ) -> dict[str, Any]:
        updated = await self._db()["interviewer_approvals"].find_one_and_update(
            {"id": approval_id},
            {"$set": {
                "status": status,
                "reviewedBy": reviewer_id,
                "reviewedAt": _now_iso(),
                "decisionNote": note,
            }},
            return_document=True,
        )
        if updated is None:
            raise NotFoundError(f"Approval {approval_id} not found")
        return _strip(updated)

    async def approve(
        self, approval_id: str, reviewer_id: str, note: Optional[str] = None
    ) -> InterviewerApproval:
        doc = await self._decide(approval_id, "approved", reviewer_id, note)
        await self._grant_authority(doc)
        return InterviewerApproval.model_validate(doc)

    async def reject(
        self, approval_id: str, reviewer_id: str, note: Optional[str] = None
    ) -> InterviewerApproval:
        doc = await self._decide(approval_id, "rejected", reviewer_id, note)
        return InterviewerApproval.model_validate(doc)

    async def _grant_authority(self, approval: dict[str, Any]) -> None:
        candidate_id = approval["candidateId"]
        skill_name = approval["requestedSkill"]
        now = approval.get("reviewedAt") or _now_iso()

        # 1. Active-interviewers list
        active = self._db()["active_interviewers"]
        existing = await active.find_one({"candidateId": candidate_id})
        if existing:
            if skill_name not in existing.get("authorities", []):
                await active.find_one_and_update(
                    {"candidateId": candidate_id},
                    {"$set": {"authorities": [*existing.get("authorities", []), skill_name]}},
                    return_document=True,
                )
        else:
            await active.insert_one({
                "candidateId": candidate_id,
                "candidateName": approval["candidateName"],
                "candidateInitials": approval["candidateInitials"],
                "mode": "freelance",
                "authorities": [skill_name],
                "sessions": 0,
                "joinedAt": now,
            })

        # 2. Skill ledger — authority flag + interviewerStatus promotion
        ledgers = self._db()["skill_ledgers"]
        ledger = await ledgers.find_one({"candidateId": candidate_id})
        if ledger is None:
            return  # candidate has no ledger yet (external persona)

        skills = ledger.get("skills", [])
        matched_skill_id = None
        for row in skills:
            if row.get("name") == skill_name:
                row["authority"] = True
                row["authoritySince"] = now
                matched_skill_id = row.get("id")
                break

        status = ledger.get("interviewerStatus") or {"mode": "none", "authorities": []}
        if status.get("mode") in (None, "none", "pending"):
            status["mode"] = "freelance"
            status.setdefault("origin", approval.get("origin"))
            status["approvedBy"] = approval.get("reviewedBy")
            status["approvedAt"] = now
        authorities = status.get("authorities", [])
        if not any(a.get("skillName") == skill_name for a in authorities):
            authorities.append({
                "skillId": matched_skill_id or skill_name.lower().replace(" ", "_"),
                "skillName": skill_name,
                "approvedAt": now,
            })
        status["authorities"] = authorities

        await ledgers.find_one_and_update(
            {"candidateId": candidate_id},
            {"$set": {"skills": skills, "interviewerStatus": status}},
            return_document=True,
        )

    # ── Candidate self-request ──────────────────────────────────────────

    async def self_request(
        self, body: SelfRequestBody, user_doc: Optional[dict[str, Any]]
    ) -> InterviewerApproval:
        if not user_doc:
            raise ValidationError("user record required for a self-request")
        # Block duplicate pending requests for the same skill.
        dup = await self._db()["interviewer_approvals"].find_one({
            "candidateId": user_doc["id"],
            "requestedSkill": body.skillName,
            "status": "pending",
        })
        if dup:
            raise ValidationError(
                f"A pending request for {body.skillName} already exists",
                status_code=409,
            )
        initials = (user_doc.get("first_name") or "?")[:1].upper()
        fresh = {
            "id": f"apr_{str(ULID()).lower()}",
            "candidateId": user_doc["id"],
            "candidateName": f"{user_doc.get('first_name', '')} {user_doc.get('last_name', '')}".strip(),
            "candidateInitials": initials,
            "dossierId": "ANV-" + user_doc["id"][-4:].upper(),
            "requestedSkill": body.skillName,
            "origin": "self-requested",
            "submittedAt": _now_iso(),
            "status": "pending",
            "candidateScore": body.skillScore,
            "candidateSessions": body.sessions,
        }
        await self._db()["interviewer_approvals"].insert_one(dict(fresh))
        return InterviewerApproval.model_validate(fresh)

    # ── Specialist invites ──────────────────────────────────────────────

    async def invite_specialist(
        self, body: SpecialistInviteBody, reviewer_id: str
    ) -> SpecialistInvite:
        fresh = {
            "id": f"inv_{str(ULID()).lower()}",
            "email": body.email,
            "firstName": body.firstName,
            "lastName": body.lastName,
            "skillName": body.skillName,
            "bio": body.bio,
            "externalProof": [p.model_dump() for p in body.externalProof],
            "status": "sent",
            "invitedAt": _now_iso(),
            "invitedBy": reviewer_id,
        }
        await self._db()["specialist_invites"].insert_one(dict(fresh))
        return SpecialistInvite.model_validate(fresh)
