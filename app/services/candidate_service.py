"""Candidate-portal reads + small mutations.

Per-user scoping (confirmed migration fix — see the migration plan):
skill reports, insights, session history, and notifications now filter
by the requesting user's id, closing a real multi-tenancy gap the old
Mongo-era code had (it returned every row in the collection to every
caller — leftover single-demo-user behavior). `onboarding()` stays
global (a fixed wizard, not per-user data).
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.timefmt import to_wire
from app.models.candidate import AppNotification as NotificationModel
from app.models.candidate import CandidateInsight as InsightModel
from app.models.candidate import OnboardingStep as OnboardingStepModel
from app.models.candidate import PublicProfile as PublicProfileModel
from app.models.candidate import SessionHistoryRow as SessionHistoryModel
from app.models.candidate import SkillReport as SkillReportModel
from app.models.candidate import SkillReportDetail as SkillReportDetailModel
from app.models.skill import SkillLedger as SkillLedgerModel
from app.schemas.candidate import (
    AppNotification,
    CandidateInsight,
    ConstellationSkill,
    FitSignal,
    GrayArea,
    OnboardingStep,
    ProfileHighlight,
    PublicProfileData,
    ReportEvidence,
    ReportGap,
    ReportGrayItem,
    ReportParty,
    ReportPhase,
    ReportVerifier,
    RubricRow,
    SessionHistoryRow,
    SkillReport,
    SkillReportDetail,
    TimelineEntry,
    UserProfileMe,
    UserProfilePatch,
)

_FALLBACK_USER = "usr_cand_001"


def _report_to_schema(row: SkillReportModel) -> SkillReport:
    return SkillReport(
        id=row.id,
        skill=row.skill,
        verifier=row.verifier,
        score=row.score,
        date=row.date,
        status=row.status,  # type: ignore[arg-type]
        companiesViewed=row.companies_viewed,
    )


def _detail_to_schema(row: SkillReportDetailModel) -> SkillReportDetail:
    return SkillReportDetail(
        id=row.id,
        skillId=row.skill_id,
        assessmentTitle=row.assessment_title,
        candidate=ReportParty(name=row.candidate_name, id=row.candidate_ext_id),
        verifier=ReportVerifier(
            name=row.verifier_name,
            id=row.verifier_ext_id,
            title=row.verifier_title,
            rating=str(row.verifier_rating),  # verifier_rating is a real float column; wire contract is str
        ),
        date=row.date,
        duration=row.duration,
        type=row.type,  # type: ignore[arg-type]
        score=row.score,
        depth=row.depth,
        verdict=row.verdict,
        verdictLong=row.verdict_long,
        fitSignals=[FitSignal(area=f["area"], signal=f["signal"], color=f["color"]) for f in row.fit_signals],
        rubric=[RubricRow(id=r["row_id"], dim=r["dim"], score=r["score"]) for r in row.rubric],
        phases=[
            ReportPhase(num=p["num"], title=p["title"], done=p["done"], summary=p["summary"]) for p in row.phases
        ],
        summary=list(row.summary or []),
        gaps=[
            ReportGap(id=g["gap_id"], area=g["area"], evidence=g["evidence"], severity=g["severity"])
            for g in row.gaps
        ],
        gray=[ReportGrayItem(id=g["item_id"], area=g["area"], companies=g["companies"]) for g in row.gray],
        evidence=[
            ReportEvidence(
                id=e["evidence_id"], t=e["t"], type=e["type"], speaker=e["speaker"], text=e["text"],
                verdict=e["verdict"], verdictColor=e["verdict_color"],
            )
            for e in row.evidence
        ],
    )


def _insight_to_schema(row: InsightModel) -> CandidateInsight:
    return CandidateInsight(
        id=row.id, kind=row.kind, title=row.title, body=row.body, cta=row.cta,  # type: ignore[arg-type]
        companies=row.companies, acted=row.acted,
    )


def _profile_to_schema(row: PublicProfileModel) -> PublicProfileData:
    return PublicProfileData(
        shareUrl=row.share_url,
        anvId=row.anv_id,
        lastUpdated=row.last_updated,
        headline=row.headline,
        views=row.views,
        uniqueCompanies=row.unique_companies,
        inboundChats=row.inbound_chats,
        about=row.about,
        highlights=[
            ProfileHighlight(id=h["highlight_id"], skill=h["skill"], score=h["score"]) for h in row.highlights
        ],
        constellation=[
            ConstellationSkill(name=c["name"], score=c["score"], state=c["state"]) for c in row.constellation
        ],
        timeline=[
            TimelineEntry(
                id=t["entry_id"], date=t["date"], skill=t["skill"], score=t["score"], type=t["type"],
                note=t.get("note"),
            )
            for t in row.timeline
        ],
        grayAreas=[GrayArea(id=g["area_id"], name=g["name"], companies=g["companies"]) for g in row.gray_areas],
    )


def _history_to_schema(row: SessionHistoryModel) -> SessionHistoryRow:
    return SessionHistoryRow(
        id=row.id, skill=row.skill, date=row.date, duration=row.duration, verifier=row.verifier,
        score=row.score, status=row.status, note=row.note,  # type: ignore[arg-type]
    )


def _notification_to_schema(row: NotificationModel) -> AppNotification:
    return AppNotification(
        id=row.id, kind=row.kind, title=row.title, body=row.body,  # type: ignore[arg-type]
        createdAt=to_wire(row.notified_at), read=row.read, href=row.href,
    )


class CandidateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _uid(self, user_id: Optional[str]) -> str:
        return user_id or _FALLBACK_USER

    # ── Skill reports ───────────────────────────────────────────────────

    async def skill_reports(self, user_id: Optional[str]) -> list[SkillReport]:
        stmt = select(SkillReportModel).where(SkillReportModel.user_id == self._uid(user_id))
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_report_to_schema(r) for r in rows]

    async def skill_report_detail(self, user_id: Optional[str], report_id: str) -> SkillReportDetail:
        row = await self.db.get(SkillReportDetailModel, report_id)
        if row is None or row.user_id != self._uid(user_id):
            raise NotFoundError("Skill report not found")
        return _detail_to_schema(row)

    # ── Insights ────────────────────────────────────────────────────────

    async def insights(self, user_id: Optional[str]) -> list[CandidateInsight]:
        stmt = select(InsightModel).where(InsightModel.user_id == self._uid(user_id))
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_insight_to_schema(r) for r in rows]

    async def act_on_insight(self, user_id: Optional[str], insight_id: str) -> None:
        row = await self.db.get(InsightModel, insight_id)
        if row is None or row.user_id != self._uid(user_id):
            raise NotFoundError(f"Insight {insight_id} not found")
        row.acted = True
        await self.db.flush()

    # ── Onboarding / history / profile ──────────────────────────────────

    async def onboarding(self) -> list[OnboardingStep]:
        stmt = select(OnboardingStepModel).order_by(OnboardingStepModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [OnboardingStep(id=r.id, title=r.title, body=r.body, done=r.done) for r in rows]

    async def public_profile(self, user_id: Optional[str]) -> PublicProfileData:
        row = await self.db.get(PublicProfileModel, self._uid(user_id))
        if row is None:
            row = await self.db.get(PublicProfileModel, _FALLBACK_USER)
        if row is None:
            raise RuntimeError("public_profiles seed data missing")
        return _profile_to_schema(row)

    async def session_history(self, user_id: Optional[str]) -> list[SessionHistoryRow]:
        # Safety cap, not real pagination — most recent 500 sessions.
        stmt = (
            select(SessionHistoryModel)
            .where(SessionHistoryModel.user_id == self._uid(user_id))
            .order_by(SessionHistoryModel.created_at.desc())
            .limit(500)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_history_to_schema(r) for r in rows]

    # ── Notifications ───────────────────────────────────────────────────

    async def notifications(self, user_id: Optional[str]) -> list[AppNotification]:
        # Safety cap, not real pagination — most recent 500 notifications.
        stmt = (
            select(NotificationModel)
            .where(NotificationModel.user_id == self._uid(user_id))
            .order_by(NotificationModel.created_at.desc())
            .limit(500)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_notification_to_schema(r) for r in rows]

    async def mark_notification_read(self, user_id: Optional[str], notification_id: str) -> None:
        row = await self.db.get(NotificationModel, notification_id)
        if row is None or row.user_id != self._uid(user_id):
            return  # matches original best-effort (no-op-if-missing) behavior
        row.read = True
        await self.db.flush()

    # ── /api/profiles/me ────────────────────────────────────────────────

    async def profile_me(self, user_id: Optional[str]) -> UserProfileMe:
        """Derived from the user's skill ledger, mirroring the mock's
        on-the-fly construction."""
        ledger = await self.db.get(
            SkillLedgerModel, user_id or _FALLBACK_USER
        ) or await self.db.get(SkillLedgerModel, _FALLBACK_USER)
        if ledger is None:
            raise RuntimeError("skill_ledgers seed data missing")
        skills = ledger.skills
        return UserProfileMe(
            id="prof_001",
            user_id=ledger.candidate_id,
            # profile_skills (nullable) overrides the verified rows only
            # when the user has actually edited their profile skills.
            skills=(
                list(ledger.profile_skills)
                if ledger.profile_skills is not None
                else [s.name for s in skills]
            ),
            experience_years=(
                ledger.profile_experience_years
                if ledger.profile_experience_years is not None
                else 6
            ),
            current_role=ledger.profile_current_role or "Backend Engineer",
            bio=ledger.profile_bio
            or "Backend engineer focused on .NET, distributed systems, and event-driven design.",
            location=ledger.candidate_location,
            candidate_rating=4.7,
            interviews_taken=sum(s.sessions for s in skills),
            average_score=ledger.verification_score,
            shared_report_ids=[],
            created_at="2025-08-12T09:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
        )

    async def update_profile(
        self, user_id: Optional[str], patch: UserProfilePatch
    ) -> None:
        """Persist PATCH /api/profiles/me onto the caller's ledger row —
        resolved exactly like `profile_me()` resolves it (same `_uid`
        ownership convention as `mark_notification_read`), so edits land
        on the same row a subsequent GET reads back. Best-effort no-op
        if the row is missing, matching the module's other mutations.
        """
        ledger = await self.db.get(SkillLedgerModel, self._uid(user_id))
        if ledger is None:
            return
        if patch.bio is not None:
            ledger.profile_bio = patch.bio
        if patch.location is not None:
            ledger.candidate_location = patch.location
        if patch.current_role is not None:
            ledger.profile_current_role = patch.current_role
        if patch.experience_years is not None:
            ledger.profile_experience_years = patch.experience_years
        if patch.skills is not None:
            # Override list only — verified skill_ledger_rows untouched.
            ledger.profile_skills = list(patch.skills)
        await self.db.flush()
