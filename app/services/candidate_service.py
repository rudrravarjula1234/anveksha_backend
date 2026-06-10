"""Candidate-portal reads + small mutations."""

from typing import Any, Optional

from app.core.exceptions import NotFoundError
from app.db.mongo import get_database
from app.schemas.candidate import (
    AppNotification,
    CandidateInsight,
    OnboardingStep,
    PublicProfileData,
    SessionHistoryRow,
    SkillReport,
    SkillReportDetail,
    UserProfileMe,
)

_FALLBACK_USER = "usr_cand_001"


def _strip(doc: dict[str, Any]) -> dict[str, Any]:
    doc.pop("_id", None)
    return doc


class CandidateService:
    def _db(self):
        return get_database()

    # ── Skill reports ───────────────────────────────────────────────────

    async def skill_reports(self) -> list[SkillReport]:
        docs = await self._db()["skill_reports"].find().to_list(length=200)
        return [SkillReport.model_validate(_strip(d)) for d in docs]

    async def skill_report_detail(self, report_id: str) -> SkillReportDetail:
        doc = await self._db()["skill_report_details"].find_one({"id": report_id})
        if doc is None:
            raise NotFoundError("Skill report not found")
        return SkillReportDetail.model_validate(_strip(doc))

    # ── Insights ────────────────────────────────────────────────────────

    async def insights(self) -> list[CandidateInsight]:
        docs = await self._db()["insights"].find().to_list(length=100)
        return [CandidateInsight.model_validate(_strip(d)) for d in docs]

    async def act_on_insight(self, insight_id: str) -> None:
        updated = await self._db()["insights"].find_one_and_update(
            {"id": insight_id}, {"$set": {"acted": True}}, return_document=True
        )
        if updated is None:
            raise NotFoundError(f"Insight {insight_id} not found")

    # ── Onboarding / history / profile ──────────────────────────────────

    async def onboarding(self) -> list[OnboardingStep]:
        docs = await self._db()["onboarding_steps"].find().to_list(length=20)
        # Preserve the wizard order (s1..s4) regardless of insertion order.
        docs.sort(key=lambda d: d.get("id", ""))
        return [OnboardingStep.model_validate(_strip(d)) for d in docs]

    async def public_profile(self, user_id: Optional[str]) -> PublicProfileData:
        doc = None
        if user_id:
            doc = await self._db()["public_profiles"].find_one({"userId": user_id})
        if doc is None:
            doc = await self._db()["public_profiles"].find_one({"userId": _FALLBACK_USER})
        if doc is None:
            raise RuntimeError("public_profiles seed data missing")
        cleaned = _strip(doc)
        cleaned.pop("userId", None)
        return PublicProfileData.model_validate(cleaned)

    async def session_history(self) -> list[SessionHistoryRow]:
        docs = await self._db()["session_history"].find().to_list(length=200)
        return [SessionHistoryRow.model_validate(_strip(d)) for d in docs]

    # ── Notifications ───────────────────────────────────────────────────

    async def notifications(self) -> list[AppNotification]:
        docs = await self._db()["notifications"].find().to_list(length=200)
        return [AppNotification.model_validate(_strip(d)) for d in docs]

    async def mark_notification_read(self, notification_id: str) -> None:
        await self._db()["notifications"].find_one_and_update(
            {"id": notification_id}, {"$set": {"read": True}}, return_document=True
        )

    # ── /api/profiles/me ────────────────────────────────────────────────

    async def profile_me(self, user_id: Optional[str]) -> UserProfileMe:
        """Derived from the user's skill ledger, mirroring the mock's
        on-the-fly construction."""
        ledger = await self._db()["skill_ledgers"].find_one(
            {"candidateId": user_id or _FALLBACK_USER}
        ) or await self._db()["skill_ledgers"].find_one({"candidateId": _FALLBACK_USER})
        if ledger is None:
            raise RuntimeError("skill_ledgers seed data missing")
        skills = ledger.get("skills", [])
        return UserProfileMe(
            id="prof_001",
            user_id=ledger["candidateId"],
            skills=[s["name"] for s in skills],
            experience_years=6,
            current_role="Backend Engineer",
            bio="Backend engineer focused on .NET, distributed systems, and event-driven design.",
            location=ledger.get("candidateLocation", ""),
            candidate_rating=4.7,
            interviews_taken=sum(s.get("sessions", 0) for s in skills),
            average_score=ledger.get("verificationScore", 0),
            shared_report_ids=[],
            created_at="2025-08-12T09:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
        )
