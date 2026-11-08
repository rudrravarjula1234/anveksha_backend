"""Privacy, dossier and booking flows."""

from collections import defaultdict
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.core.demo import DEMO_CANDIDATE_ID
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.privacy import MASKED_VERIFIER
from app.core.timefmt import to_wire, utc_now
from app.models.portal import BookingCatalog as BookingCatalogModel
from app.models.portal import Dossier as DossierModel
from app.models.portal import LiveSessionSnapshot as LiveSessionModel
from app.models.portal import MyInterview as MyInterviewModel
from app.models.portal import PrivacySettings as PrivacySettingsModel
from app.models.skill import SkillLedger as SkillLedgerModel
from app.schemas.booking import (
    AssessmentSignal,
    BookingCatalog,
    BookingDay,
    BookingSlot,
    Dossier,
    DossierSession,
    LiveSessionSnapshot,
    MyInterview,
    ScheduleRequest,
    ScheduleResponse,
    SessionParty,
    SessionPhase,
    TranscriptLine,
    UnverifiedClaim,
)
from app.schemas.privacy import PrivacyPatch, PrivacySettings, SharedReport
from app.services.skill_service import ledger_to_schema

_FALLBACK_CATALOG_ID = "KAF-204"
_FALLBACK_SESSION_ID = "KAF-88421"


def _privacy_to_schema(row: PrivacySettingsModel) -> PrivacySettings:
    return PrivacySettings(
        shareProfile=row.share_profile, shareDossiers=row.share_dossiers,
        shareTranscripts=row.share_transcripts, allowGrayFollowups=row.allow_gray_followups,
        hideFromCompanies=list(row.hide_from_companies or []), discoverability=row.discoverability,  # type: ignore[arg-type]
        shareScore=row.share_score, shareGap=row.share_gap, shareGray=row.share_gray,
        shareTranscript=row.share_transcript, allowFollowup=row.allow_followup,
        anonymousMode=row.anonymous_mode, shareVerifierPanel=row.share_verifier_panel,
        sharedReports=[
            SharedReport(id=r["id"], reportId=r["report_id"], sharedWith=r["shared_with"],
                         sharedAt=r["shared_at"], expiresAt=r["expires_at"], status=r["status"])
            for r in row.shared_reports
        ],
    )


class PrivacyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _row_for(self, user_id: Optional[str]) -> PrivacySettingsModel:
        # Only the caller's own row: never another user's as a stand-in.
        row = await self.db.get(PrivacySettingsModel, user_id) if user_id else None
        if row is None:
            raise NotFoundError("No privacy settings for this user")
        return row

    async def get(self, user_id: Optional[str]) -> PrivacySettings:
        return _privacy_to_schema(await self._row_for(user_id))

    async def patch(self, user_id: Optional[str], patch: PrivacyPatch) -> PrivacySettings:
        row = await self._row_for(user_id)
        diff = patch.model_dump(exclude_unset=True)
        field_map = {
            "shareProfile": "share_profile", "shareDossiers": "share_dossiers",
            "shareTranscripts": "share_transcripts", "allowGrayFollowups": "allow_gray_followups",
            "hideFromCompanies": "hide_from_companies", "discoverability": "discoverability",
            "shareScore": "share_score", "shareGap": "share_gap", "shareGray": "share_gray",
            "shareTranscript": "share_transcript", "allowFollowup": "allow_followup",
            "anonymousMode": "anonymous_mode", "shareVerifierPanel": "share_verifier_panel",
        }
        for k, v in diff.items():
            if k in field_map:
                setattr(row, field_map[k], v)
        if diff:
            await self.db.flush()
        return _privacy_to_schema(row)

    async def revoke_shared_report(self, user_id: Optional[str], shared_id: str) -> None:
        row = await self._row_for(user_id)
        # Reassign the whole list (not an in-place mutation) so
        # SQLAlchemy's JSONB change tracking picks it up.
        row.shared_reports = [r for r in row.shared_reports if r["id"] != shared_id]
        await self.db.flush()


class DossierService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _to_schema(self, row: DossierModel, ledger: SkillLedgerModel) -> Dossier:
        return Dossier(
            id=row.id, candidateId=row.candidate_id, candidateName=row.candidate_name,
            candidateInitials=row.candidate_initials, candidateTitle=row.candidate_title,
            candidateLocation=row.candidate_location, years=row.years,
            verificationScore=row.verification_score, ledger=ledger_to_schema(ledger),
            sessions=[
                DossierSession(id=s.session_id, date=s.date, skill=s.skill, verifier=s.verifier,
                                score=s.score, duration=s.duration, verdict=s.verdict)
                for s in row.sessions
            ],
            grayAreas=list(row.gray_areas or []), strengths=list(row.strengths or []), isShared=row.is_shared,
        )

    async def _load(self, row: DossierModel) -> Dossier:
        ledger = await self.db.get(SkillLedgerModel, row.candidate_id)
        if ledger is None:
            raise RuntimeError(f"skill_ledgers missing for dossier candidate {row.candidate_id}")
        return self._to_schema(row, ledger)

    async def _row_of(self, candidate_id: str) -> Optional[DossierModel]:
        stmt = select(DossierModel).where(DossierModel.candidate_id == candidate_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_mine(self, user_id: Optional[str]) -> Dossier:
        # Only the caller's own dossier: never another user's as a stand-in.
        row = await self._row_of(user_id) if user_id else None
        if row is None:
            raise NotFoundError("No dossier for this user")
        return await self._load(row)

    async def get_by_id(self, dossier_id: str) -> Dossier:
        row = await self.db.get(DossierModel, dossier_id)
        if row is None:
            # Mock parity: any id resolves to the seeded demo dossier (the
            # company dossier page is routed by candidate id, not dossier id).
            row = await self._row_of(DEMO_CANDIDATE_ID)
        if row is None:
            raise NotFoundError(f"Dossier {dossier_id} not found")
        return await self._load(row)

    async def share(self, dossier_id: str, user_id: Optional[str]) -> dict[str, Any]:
        # Only the owner may share, and only a dossier that really exists.
        row = await self.db.get(DossierModel, dossier_id)
        if row is None or row.candidate_id != user_id:
            raise NotFoundError(f"Dossier {dossier_id} not found")
        row.is_shared = True
        await self.db.flush()
        return {"ok": True, "shareUrl": f"https://anveksha.app/d/{row.id}"}


class BookingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _catalog_row(self, catalog_id: Optional[str]) -> BookingCatalogModel:
        row = None
        if catalog_id:
            row = await self.db.get(BookingCatalogModel, catalog_id)
        if row is None:
            row = await self.db.get(BookingCatalogModel, _FALLBACK_CATALOG_ID)
        if row is None:
            raise RuntimeError("booking_catalogs seed data missing")
        return row

    def _to_schema(self, row: BookingCatalogModel) -> BookingCatalog:
        slots_by_day: dict[str, list[BookingSlot]] = defaultdict(list)
        for slot in row.slots:
            # PHI rule: candidates never learn WHICH verifier they're
            # paired with at booking time. Ratings stay visible (quality
            # signal); identity does not.
            slots_by_day[slot["day_key"]].append(
                BookingSlot(id=slot["slot_key"], time=slot["time"], verifier=MASKED_VERIFIER,
                            rating=slot["rating"], duration=slot["duration"])
            )
        return BookingCatalog(
            catalogId=row.catalog_id, skillName=row.skill_name, description=row.description,
            depth=row.depth, duration=row.duration, style=row.style, format=row.format,
            evidence=row.evidence, probes=row.probes, weekRange=row.week_range,
            days=[
                BookingDay(id=d["day_key"], day=d["day"], date=d["date"], status=d["status"],
                           slotCount=d["slot_count"])
                for d in row.days
            ],
            slotsByDay=dict(slots_by_day),
        )

    async def catalog(self, catalog_id: Optional[str] = None) -> BookingCatalog:
        return self._to_schema(await self._catalog_row(catalog_id))

    async def schedule(self, payload: ScheduleRequest, user_id: Optional[str]) -> ScheduleResponse:
        if not user_id:
            # Bookings belong to a users row (FK); never file one under someone else.
            raise ForbiddenError("A user record is required to book an interview")
        catalog = await self.catalog()
        booking_id = f"int_{str(ULID()).lower()}"
        # Whole seconds, matching the booking API's historical precision.
        scheduled_at = utc_now().replace(microsecond=0)
        self.db.add(
            MyInterviewModel(
                id=booking_id, user_id=user_id, catalog_id=catalog.catalogId,
                title=catalog.skillName, status="scheduled", scheduled_date=scheduled_at,
            )
        )
        await self.db.flush()
        return ScheduleResponse(
            id=booking_id, status="scheduled", scheduled_date=to_wire(scheduled_at),
            dayId=payload.dayId, slotId=payload.slotId, catalog=catalog,
        )

    async def live_session(self, session_id: str) -> LiveSessionSnapshot:
        row = await self.db.get(LiveSessionModel, session_id)
        if row is None:
            row = await self.db.get(LiveSessionModel, _FALLBACK_SESSION_ID)
        if row is None:
            raise NotFoundError(f"Session {session_id} not found")
        claim = (
            UnverifiedClaim(text=row.unverified_claim_text, at=row.unverified_claim_at or "")
            if row.unverified_claim_text
            else None
        )
        return LiveSessionSnapshot(
            id=row.id, catalogId=row.catalog_id, skill=row.skill, status=row.status,  # type: ignore[arg-type]
            elapsedSeconds=row.elapsed_seconds,
            candidate=SessionParty(name=row.candidate_name, initials=row.candidate_initials,
                                    color=row.candidate_color),
            verifier=SessionParty(name=row.verifier_name, initials=row.verifier_initials,
                                   color=row.verifier_color),
            transcript=[TranscriptLine(t=t["t"], who=t["who"], text=t["text"]) for t in row.transcript],
            phases=[
                SessionPhase(num=p["num"], title=p["title"], done=p["done"], active=p["active"])
                for p in row.phases
            ],
            currentProbe=row.current_probe,
            assessment=[
                AssessmentSignal(label=a["label"], value=a["value"], tag=a["tag"]) for a in row.assessment
            ],
            suggestedProbes=list(row.suggested_probes or []),
            unverifiedClaim=claim,
        )

    async def my_interviews(self, user_id: Optional[str]) -> list[MyInterview]:
        if not user_id:
            return []
        stmt = (
            select(MyInterviewModel)
            .where(MyInterviewModel.user_id == user_id)
            .order_by(MyInterviewModel.id)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            MyInterview(id=r.id, catalog_id=r.catalog_id, title=r.title, status=r.status,
                        scheduled_date=to_wire(r.scheduled_date))
            for r in rows
        ]
