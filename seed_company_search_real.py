r"""Make the real interviewed candidate Sai Rajesh discoverable in the
company portal, end-to-end traceable to his real rows.

Sai (usr_g_01M7TH79WNDCBB4E9REWWDK85Z) already has a real ingested
transcript (assessment_transcripts.iv_fastapi_sai), a published report
(skill_report_details.SVR-FASTAPI-10003) and a public profile — but he was
MISSING from `search_candidates`, so company NL search could never surface
him. This seeds, keyed by his real user id so everything downstream
resolves by that same id (search → chat transcript → report → gray demand):

  * a `search_candidates` row derived from his report + public profile, and
  * a `dossiers` row (+ one session) so "Investigate →" opens a real dossier.

The other fully-traceable candidate, Rajesh (usr_cand_rajesh / .NET,
transcript iv_dotnet_rajesh, dossier ANV-RAJESH-01), is already aligned and
left untouched.

Idempotent. Run:  .\.venv\Scripts\python.exe seed_company_search_real.py
"""

import asyncio
import selectors
import sys

UID = "usr_g_01M7TH79WNDCBB4E9REWWDK85Z"
NAME = "Sai Rajesh Rudravarjula"


async def _main() -> None:
    from sqlalchemy import select

    from app.db.session import close_db, connect_to_db, get_sessionmaker
    from app.models.company import SearchCandidate
    from app.models.portal import Dossier, DossierSession

    verified_skills = ["Python FastAPI & Async Data Systems", "Async Data Systems"]
    gray_skills = ["Event-Driven Backends with Kafka", "System Design"]

    await connect_to_db()
    try:
        async with get_sessionmaker()() as db:
            # 1) search_candidates — id == real user id, so chat/dossier/gray
            #    all resolve by this same id.
            sc = await db.get(SearchCandidate, UID)
            if sc is None:
                sc = SearchCandidate(id=UID)
                db.add(sc)
            sc.name = NAME
            sc.initials = "SR"
            sc.title = "Backend Engineer · Async Python"
            sc.years = 8
            sc.location = "Hyderabad"
            sc.verification_score = 79  # SVR-FASTAPI-10003.score
            sc.match_percent = 86
            sc.verified_skills = verified_skills
            sc.gray_skills = gray_skills
            sc.last_activity = "1d ago"

            # 2) dossiers (+ one real session) so Investigate opens real data.
            dossier = await db.get(Dossier, "ANV-SAI-01")
            if dossier is None:
                dossier = Dossier(id="ANV-SAI-01", candidate_id=UID)
                db.add(dossier)
            dossier.candidate_id = UID
            dossier.candidate_name = NAME
            dossier.candidate_initials = "SR"
            dossier.candidate_title = "Backend Engineer · Async Python"
            dossier.candidate_location = "Hyderabad"
            dossier.years = 8
            dossier.verification_score = 79
            dossier.gray_areas = gray_skills
            dossier.strengths = [
                "Async event-loop model",
                "Per-request AsyncSession scoping",
                "Connection pooling (PgBouncer)",
            ]
            dossier.is_shared = False
            await db.flush()

            have = (await db.execute(
                select(DossierSession).where(DossierSession.dossier_id == "ANV-SAI-01")
            )).scalars().all()
            if not any(s.session_id == "iv_fastapi_sai" for s in have):
                db.add(DossierSession(
                    dossier_id="ANV-SAI-01",
                    session_id="iv_fastapi_sai",  # == assessment_transcripts.id
                    date="Nov 19, 2026",
                    skill="Python FastAPI & Async Data Systems",
                    verifier="Anveksha Verifier",
                    score=79,
                    duration=45,
                    verdict="verified",
                ))

            await db.commit()
            print(f"Seeded search_candidate + dossier for {NAME} ({UID}).")
    finally:
        await close_db()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_main())
