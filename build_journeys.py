r"""Wire 4 end-to-end, fully-traceable assessment journeys on top of the
RAW-ingested transcripts (see ingest_raw_sessions.py).

For each journey it creates / links, all by real FK:
  assessments.created_by_id        -> admin who created every assessment
  my_interviews (assessment_id)    -> candidate booked this assessment
  assessment_transcripts           -> status 'reported' + dossier summary
  skill_report_details             -> report FKs transcript + assessment + verifier
  skill_reports / session_history  -> candidate-portal rows FK the report
  admin_dossiers                   -> admin Dossiers page row FKs the report

Idempotent: every row is keyed by id and skipped if already present.
Also drops the two earlier report-less demo transcripts that have no FKs.

Run:  .\.venv\Scripts\python.exe build_journeys.py
"""

import asyncio
import selectors
import sys

ADMIN = "usr_adm_001"

# verifier_user_id -> display fields
VERIFIERS = {
    "usr_ver_001": {"name": "Maya Iyer", "ext": "v_maya", "title": "Senior Backend Engineer", "rating": 4.8},
    "usr_spec_001": {"name": "Dr. Suresh Mehra", "ext": "v_002", "title": "Principal Architect", "rating": 4.9},
    "usr_verif_rajesh": {"name": "Sai Rajesh", "ext": "v_rajesh", "title": "Staff Engineer", "rating": 4.7},
}
# candidate_user_id -> display fields
CANDIDATES = {
    "usr_cand_001": {"name": "Aarav Rao", "ext": "c_001"},
    "usr_cand_rajesh": {"name": "Rajesh Rudravarjula", "ext": "c_rajesh"},
    "usr_g_01M7TH79WNDCBB4E9REWWDK85Z": {"name": "Sai Rajesh Rudravarjula", "ext": "c_rajesh_g"},
    "usr_ver_001": {"name": "Maya Iyer", "ext": "c_maya"},
}

JOURNEYS = [
    {
        "iv": "iv_kafka_aarav", "report": "SVR-KAFKA-10001",
        "assessment_id": "asm_01M7VSWQ0BR8P99D3HX5S3FN4V",
        "assessment_title": "Event-Driven Backends with Kafka",
        "skill_id": "skl_kafka", "type": "live", "depth": "Expert",
        "candidate": "usr_cand_001", "verifier": "usr_ver_001",
        "score": 84, "date": "Nov 18, 2026", "duration": "58 min",
        "verdict": "Verified — strong event-streaming fundamentals.",
    },
    {
        "iv": "iv_dotnet_rajesh", "report": "SVR-DOTNET-10002",
        "assessment_id": "ASS-001",
        "assessment_title": ".NET Microservices & Cloud Architecture",
        "skill_id": "skl_dotnet", "type": "live", "depth": "Advanced",
        "candidate": "usr_cand_rajesh", "verifier": "usr_spec_001",
        "score": 88, "date": "Nov 19, 2026", "duration": "60 min",
        "verdict": "Verified — confident distributed-systems reasoning.",
    },
    {
        "iv": "iv_fastapi_sai", "report": "SVR-FASTAPI-10003",
        "assessment_id": "ASS-003",
        "assessment_title": "Python FastAPI & Async Data Systems",
        "skill_id": "skl_fastapi", "type": "bot-assisted", "depth": "Intermediate",
        "candidate": "usr_g_01M7TH79WNDCBB4E9REWWDK85Z", "verifier": "usr_verif_rajesh",
        "score": 79, "date": "Nov 19, 2026", "duration": "45 min",
        "verdict": "Verified — solid async model understanding.",
    },
    {
        "iv": "iv_sysdesign_maya", "report": "SVR-SYSDES-10004",
        "assessment_id": "ASS-002",
        "assessment_title": "System Design - Scalable Distributed Systems",
        "skill_id": "skl_sysdesign", "type": "bot-assisted", "depth": "Staff",
        "candidate": "usr_ver_001", "verifier": "usr_spec_001",
        "score": 82, "date": "Nov 20, 2026", "duration": "60 min",
        "verdict": "Verified — pragmatic scaling trade-offs.",
    },
]


async def _main() -> None:
    from sqlalchemy import text
    from app.db.session import connect_to_db, close_db, get_sessionmaker
    from app.models.assessment import Assessment
    from app.models.candidate import SkillReport, SkillReportDetail, SessionHistoryRow
    from app.models.admin_ops import AdminDossier
    from app.models.session_ingest import AssessmentTranscript
    from app.models.portal import MyInterview
    from app.core.timefmt import parse_wire

    await connect_to_db()
    try:
        async with get_sessionmaker()() as db:
            # 0) Every assessment gets a creator (the admin). Traceable "who made this".
            await db.execute(
                text("UPDATE assessments SET created_by_id=:a WHERE created_by_id IS NULL"),
                {"a": ADMIN},
            )

            # Drop the two earlier FK-less demo transcripts (superseded by journeys).
            await db.execute(
                text("DELETE FROM assessment_transcripts WHERE id IN ('KAF-98001','DOT-98002')")
            )

            created = {"interviews": 0, "reports": 0, "details": 0, "history": 0, "admin_dossiers": 0}

            for j in JOURNEYS:
                cand = CANDIDATES[j["candidate"]]
                ver = VERIFIERS[j["verifier"]]
                sched = parse_wire("2026-11-18T10:00:00.000Z")

                # 1) Booking: candidate booked this assessment.
                if not await db.get(MyInterview, j["iv"]):
                    db.add(MyInterview(
                        id=j["iv"], user_id=j["candidate"],
                        catalog_id=j["assessment_id"], assessment_id=j["assessment_id"],
                        title=j["assessment_title"], status="completed", scheduled_date=sched,
                    ))
                    created["interviews"] += 1

                # 2) Transcript -> reported + dossier summary (FKs already set at ingest).
                tr = await db.get(AssessmentTranscript, j["iv"])
                if tr is not None:
                    tr.status = "reported"
                    tr.dossier = {
                        "reportId": j["report"], "score": j["score"],
                        "verdict": j["verdict"], "verifier": ver["name"],
                    }

                # 3) The report — FKs transcript + assessment + verifier.
                if not await db.get(SkillReportDetail, j["report"]):
                    db.add(SkillReportDetail(
                        id=j["report"], user_id=j["candidate"],
                        transcript_id=j["iv"], assessment_id=j["assessment_id"],
                        verifier_user_id=j["verifier"],
                        skill_id=j["skill_id"], assessment_title=j["assessment_title"],
                        candidate_name=cand["name"], candidate_ext_id=cand["ext"],
                        verifier_name=ver["name"], verifier_ext_id=ver["ext"],
                        verifier_title=ver["title"], verifier_rating=ver["rating"],
                        date=j["date"], duration=j["duration"], type=j["type"],
                        score=j["score"], depth=j["depth"],
                        verdict=j["verdict"], verdict_long=j["verdict"],
                        summary=[j["verdict"]],
                        fit_signals=[], rubric=[], phases=[], gaps=[], gray=[],
                        evidence=[{"source": "transcript", "ref": j["iv"]}],
                    ))
                    created["details"] += 1

                # 4) Candidate-portal skill_reports row -> the report.
                if not await db.get(SkillReport, j["report"]):
                    db.add(SkillReport(
                        id=j["report"], user_id=j["candidate"], report_id=j["report"],
                        skill=j["assessment_title"], verifier=ver["name"],
                        score=j["score"], date=j["date"], status="published",
                        companies_viewed=0,
                    ))
                    created["reports"] += 1

                # 5) Session history row -> the report.
                sh_id = "sh_" + j["iv"]
                if not await db.get(SessionHistoryRow, sh_id):
                    db.add(SessionHistoryRow(
                        id=sh_id, user_id=j["candidate"], report_id=j["report"],
                        skill=j["assessment_title"], date=j["date"], duration=j["duration"],
                        verifier=ver["name"], score=j["score"], status="published",
                        note=None,
                    ))
                    created["history"] += 1

                # 6) Admin Dossiers page row -> the report.
                ad_id = "ad_" + j["iv"]
                if not await db.get(AdminDossier, ad_id):
                    db.add(AdminDossier(
                        id=ad_id, report_id=j["report"], candidate=cand["name"],
                        skill=j["assessment_title"], verifier=ver["name"],
                        date=j["date"], score=j["score"], status="published",
                    ))
                    created["admin_dossiers"] += 1

            await db.commit()
            print("Journeys wired:", created)
    finally:
        await close_db()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_main())
