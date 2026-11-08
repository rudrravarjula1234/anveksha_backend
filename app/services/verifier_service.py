"""Verifier console business logic.

Singletons read the fixed `id = "default"` row of `verifier_console_state`
(merged from the four former per-section singleton tables); multi-verifier
support later swaps the id for the caller's user id without touching the
API layer. `publish_report()` flips status, drops the pending-queue row,
and — when `session_reports.published_report_id` links to a candidate-
facing report — syncs that report's score/verdict too, atomic for free
under the app's one-transaction-per-request model.
"""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.core.exceptions import NotFoundError
from app.core.privacy import candidate_anon_id, mask_initials
from app.core.timefmt import to_wire
from app.models.candidate import SessionHistoryRow as SessionHistoryModel
from app.models.candidate import SkillReport as SkillReportModel
from app.models.candidate import SkillReportDetail as SkillReportDetailModel
from app.models.verifier import PendingReport as PendingReportModel
from app.models.verifier import SessionReport as SessionReportModel
from app.models.verifier import SuggestedGap as SuggestedGapModel
from app.models.verifier import VerifierConsoleState as VerifierConsoleStateModel
from app.models.verifier import VerifierSession as VerifierSessionModel
from app.models.verifier import VerifierSlot as VerifierSlotModel
from app.schemas.verifier import (
    EarningMonth as EarningMonthSchema,
)
from app.schemas.verifier import (
    GovernanceData,
    NextSessionBrief,
    PendingReportListItem,
    ReportEnvelope,
    ReportSection,
    SessionReport,
    SuggestedGap,
    VerifierEarnings,
    VerifierProfile,
    VerifierProfileUpdate,
    VerifierQueue,
    VerifierSession,
    VerifierSlot,
    VerifierSlotCreate,
    VerifierStats,
)
from app.schemas.verifier import (
    GovernanceRecentReport as GovernanceRecentReportSchema,
)
from app.schemas.verifier import (
    GovernanceSignal as GovernanceSignalSchema,
)
from app.schemas.verifier import (
    QualityMetric as QualityMetricSchema,
)
from app.schemas.verifier import (
    RateCardRow as RateCardRowSchema,
)

_FALLBACK_REPORT_ID = "rpt_001"


def _to_session_schema(row: VerifierSessionModel, *, anonymize: bool = True) -> VerifierSession:
    candidate = candidate_anon_id(row.candidate) if anonymize else row.candidate
    initials = mask_initials() if anonymize else row.candidate_initials
    return VerifierSession(
        id=row.id, rawId=row.raw_id, time=row.time, date=row.date, candidate=candidate,
        candidateInitials=initials, skill=row.skill, duration=row.duration, status=row.status,  # type: ignore[arg-type]
        tags=list(row.tags or []), depth=row.depth,
    )


def _to_report_schema(row: SessionReportModel, *, anonymize: bool = True) -> SessionReport:
    return SessionReport(
        id=row.id, sessionId=row.session_id,
        candidateName=candidate_anon_id(row.candidate_name) if anonymize else row.candidate_name,
        skill=row.skill, verdict=row.verdict, overallScore=row.overall_score,  # type: ignore[arg-type]
        sections=[
            ReportSection(
                id=s["section_id"], title=s["title"], aiScore=s["ai_score"], verifierScore=s.get("verifier_score"),
                notes=s["notes"], evidence=list(s.get("evidence") or []),
            )
            for s in row.sections
        ],
        grayAreas=list(row.gray_areas or []), strengths=list(row.strengths or []), status=row.status,  # type: ignore[arg-type]
        createdAt=to_wire(row.report_created_at),
    )


class VerifierService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Reads ───────────────────────────────────────────────────────────

    async def queue(self) -> VerifierQueue:
        # No dedicated stats table — rating/sessions, reliability, and
        # earnings each have one real owner (the matching column set of
        # the console-state row); assembled here rather than stored a
        # fourth time.
        row = await self.db.get(VerifierConsoleStateModel, "default")
        if row is None:
            raise RuntimeError("verifier console state seed data missing")
        lanes: dict[str, list[VerifierSession]] = {"live": [], "upcoming": [], "completed": []}
        # Safety cap, not real pagination or per-verifier scoping (see module docstring).
        stmt = select(VerifierSessionModel).order_by(VerifierSessionModel.id).limit(2000)
        rows = (await self.db.execute(stmt)).scalars().all()
        for row_ in rows:
            lanes[row_.lane].append(_to_session_schema(row_))
        return VerifierQueue(
            stats=VerifierStats(
                rating=row.rating, sessionCount=row.sessions, reliability=row.reliability,
                earnings=row.current_amount,
            ),
            live=lanes["live"], upcoming=lanes["upcoming"], completed=lanes["completed"],
        )

    async def next_brief(self) -> NextSessionBrief:
        row = await self.db.get(VerifierConsoleStateModel, "default")
        if row is None:
            raise RuntimeError("verifier console state seed data missing")
        return NextSessionBrief(
            sessionId=row.session_id, candidate=candidate_anon_id(row.candidate), skill=row.skill,
            summary=row.summary, prioritizedProbes=list(row.prioritized_probes or []),
            grayRequested=list(row.gray_requested or []),
        )

    async def governance(self) -> GovernanceData:
        row = await self.db.get(VerifierConsoleStateModel, "default")
        if row is None:
            raise RuntimeError("verifier console state seed data missing")
        return GovernanceData(
            reliability=row.reliability, scoreVariance=row.score_variance, candidateRating=row.candidate_rating,
            appealRate=row.appeal_rate, averageReviewTimeMin=row.average_review_time_min,
            monthlyEarnings=row.current_amount,
            signals=[
                GovernanceSignalSchema(id=s["signal_id"], name=s["name"], value=s["value"], target=s["target"])
                for s in row.signals
            ],
            recentReports=[
                GovernanceRecentReportSchema(
                    id=r["report_id"], candidate=r["candidate"], skill=r["skill"], date=r["date"],
                    verdict=r["verdict"], score=r["score"],
                )
                for r in row.recent_reports
            ],
        )

    async def earnings(self) -> VerifierEarnings:
        row = await self.db.get(VerifierConsoleStateModel, "default")
        if row is None:
            raise RuntimeError("verifier console state seed data missing")
        return VerifierEarnings(
            currentMonth=row.current_month, currentAmount=row.current_amount,
            currentSessions=row.current_sessions, ytdAmount=row.ytd_amount, ytdSessions=row.ytd_sessions,
            rateStandard=row.rate_standard, rateAdvanced=row.rate_advanced, pending=row.pending,
            months=[
                EarningMonthSchema(id=m["month_id"], month=m["month"], sessions=m["sessions"], hours=m["hours"],
                                    amount=m["amount"], status=m["status"])
                for m in row.months
            ],
            rateCard=[RateCardRowSchema(id=r["row_id"], label=r["label"], value=r["value"]) for r in row.rate_card],
        )

    async def profile(self) -> VerifierProfile:
        row = await self.db.get(VerifierConsoleStateModel, "default")
        if row is None:
            raise RuntimeError("verifier console state seed data missing")
        return VerifierProfile(
            name=row.name, title=row.title, yearsExperience=row.years_experience, rating=row.rating,
            sessions=row.sessions, bio=row.bio, linkedin=row.linkedin, language=row.language,
            specializations=list(row.specializations or []), pendingReports=row.pending_reports,
            quality=[QualityMetricSchema(id=q["metric_id"], metric=q["metric"], value=q["value"]) for q in row.quality],
        )

    async def update_profile(self, patch: VerifierProfileUpdate) -> VerifierProfile:
        diff = patch.model_dump(exclude_unset=True)
        if diff:
            row = await self.db.get(VerifierConsoleStateModel, "default")
            if row is not None:
                field_map = {
                    "name": "name", "title": "title", "yearsExperience": "years_experience", "bio": "bio",
                    "linkedin": "linkedin", "language": "language", "specializations": "specializations",
                }
                for k, v in diff.items():
                    if k in field_map:
                        setattr(row, field_map[k], v)
                await self.db.flush()
        return await self.profile()

    # ── Pending reports + report editing ───────────────────────────────

    async def pending_reports(self) -> list[PendingReportListItem]:
        # Safety cap, not real pagination.
        stmt = select(PendingReportModel).order_by(PendingReportModel.id).limit(2000)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            PendingReportListItem(
                id=r.id, sessionId=r.session_id, candidate=candidate_anon_id(r.candidate),
                initials=mask_initials(), skill=r.skill, date=r.date, aiScore=r.ai_score,
            )
            for r in rows
        ]

    async def _suggested_gaps(self) -> list[SuggestedGap]:
        stmt = select(SuggestedGapModel).order_by(SuggestedGapModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [SuggestedGap(id=g.id, text=g.text, sub=g.sub, accepted=g.accepted, note=g.note) for g in rows]

    async def _find_report(self, report_id: str) -> Optional[SessionReportModel]:
        row = await self.db.get(SessionReportModel, report_id)
        if row is None:
            # Mock parity: unknown ids fall back to the first seeded report
            # so the editor pane always has content.
            row = await self.db.get(SessionReportModel, _FALLBACK_REPORT_ID)
        return row

    async def get_report(self, report_id: str) -> ReportEnvelope:
        row = await self._find_report(report_id)
        if row is None:
            raise NotFoundError(f"Report {report_id} not found")
        return ReportEnvelope(report=_to_report_schema(row), suggestedGaps=await self._suggested_gaps())

    async def patch_report(self, report_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Free-form per-section save. The mock echoes {ok, patched, report}."""
        row = await self._find_report(report_id)
        if row is None:
            raise NotFoundError(f"Report {report_id} not found")
        # Whitelist the fields the editor actually patches; ignore the rest.
        allowed = {"verdict", "overallScore", "grayAreas", "strengths", "status"}
        field_map = {
            "verdict": "verdict", "overallScore": "overall_score", "grayAreas": "gray_areas",
            "strengths": "strengths", "status": "status",
        }
        diff = {k: v for k, v in patch.items() if k in allowed}
        for k, v in diff.items():
            setattr(row, field_map[k], v)
        if "sections" in patch:
            row.sections = [
                {
                    "section_id": s["id"], "title": s["title"], "ai_score": s["aiScore"],
                    "verifier_score": s.get("verifierScore"), "notes": s.get("notes", ""),
                    "evidence": s.get("evidence", []),
                }
                for s in patch["sections"]
            ]
        await self.db.flush()
        return {"ok": True, "patched": patch, "report": _to_report_schema(row).model_dump()}

    async def publish_report(self, report_id: str) -> dict[str, Any]:
        row = await self.db.get(SessionReportModel, report_id)
        if row is not None:
            row.status = "published"
            # Published reports leave the pending queue — same session,
            # same request/transaction as the status flip above.
            pending = await self.db.get(PendingReportModel, report_id)
            if pending is not None:
                await self.db.delete(pending)
            if row.published_report_id:
                await self._sync_published_report(row.published_report_id, row.overall_score)
            await self.db.flush()
        return {"ok": True, "status": "published"}

    async def _sync_published_report(self, detail_id: str, score: float) -> None:
        """Keep the candidate-facing report views' score in sync with a
        just-published score — the one live write path connecting the
        verifier's working copy to the report(s) that link to it via
        `report_id`/`published_report_id`. Only `score` syncs: `verdict`
        here is a short verified/partial/gray tag, but the linked
        `skill_report_details.verdict` is a written prose summary sentence
        — a different kind of content, not a reformatted copy of the same
        fact, so it's left to the verifier to edit directly."""
        detail = await self.db.get(SkillReportDetailModel, detail_id)
        if detail is not None:
            detail.score = round(score)
        for model in (SkillReportModel, SessionHistoryModel):
            stmt = select(model).where(model.report_id == detail_id)
            for linked in (await self.db.execute(stmt)).scalars().all():
                linked.score = round(score)

    # ── Slots ───────────────────────────────────────────────────────────

    async def slots(self) -> list[VerifierSlot]:
        stmt = select(VerifierSlotModel).order_by(VerifierSlotModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            VerifierSlot(id=r.id, day=r.day, time=r.time, duration=r.duration, skill=r.skill,  # type: ignore[arg-type]
                          booked=r.booked, candidate=r.candidate)
            for r in rows
        ]

    async def create_slot(self, payload: VerifierSlotCreate) -> VerifierSlot:
        row = VerifierSlotModel(
            id=f"vs_{str(ULID()).lower()}",
            day=payload.day or "Mon",
            time=payload.time or "09:00",
            duration=payload.duration or 60,
            skill=payload.skill or "Any",
            booked=False,
        )
        self.db.add(row)
        await self.db.flush()
        return VerifierSlot(id=row.id, day=row.day, time=row.time, duration=row.duration,  # type: ignore[arg-type]
                             skill=row.skill, booked=row.booked, candidate=row.candidate)

    async def delete_slot(self, slot_id: str) -> None:
        row = await self.db.get(VerifierSlotModel, slot_id)
        if row is None:
            raise NotFoundError(f"Slot {slot_id} not found")
        await self.db.delete(row)
        await self.db.flush()
