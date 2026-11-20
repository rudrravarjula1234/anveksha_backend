"""Seed the Graph-RAG question bank from existing probe data.

For each skill (an `assessments` row), ask Gemini to expand that skill's
probe areas into a small, ordered set of interview questions — easy→hard
within an area form a drill-down chain — plus a few cross-area "related"
links. Questions are embedded and stored in `interview_questions`; the
chains/links become `question_edges`.

Idempotent per skill: a skill that already has seeded questions is skipped.
Run standalone:
    .\.venv\Scripts\python.exe -m app.db.seed_question_bank
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.agents.embeddings import embed_texts
from app.agents.gemini_text import complete_json
from app.models.assessment import Assessment
from app.models.question_bank import InterviewQuestion, QuestionEdge

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert technical interview designer. You turn a skill and its "
    "probe areas into a focused question bank an AI interviewer can drill through. "
    "For each probe area, produce 2-3 questions ordered easy -> hard that form a "
    "natural drill-down chain (a strong answer to one earns the next). Also add a "
    "few 'related' links between questions in different areas that pair well.\n\n"
    "Output ONLY valid JSON, no markdown, with this exact shape:\n"
    "{\n"
    '  "questions": [\n'
    '    {"text": "...", "probe_area": "...", "assesses": ["..."],\n'
    '     "difficulty": 1-5, "expected_signals": "what a strong answer shows"}\n'
    "  ],\n"
    '  "edges": [ {"from": <question index>, "to": <question index>,\n'
    '              "relation": "drill_down" | "related"} ]\n'
    "}\n"
    "Indices are 0-based into the questions array. drill_down goes easy->hard "
    "within one probe_area. Keep questions concrete and answerable aloud."
)


async def _generate(skill: str, domain: str | None, depth: str | None, probe_areas: list[str]):
    """Gemini generation + embeddings for one skill. Holds NO DB connection
    (the LLM/embed calls are slow; the Supabase pooler drops a connection
    held across them). Returns (questions, embeddings, edges) or None."""
    user = (
        f"Skill: {skill}\nDomain: {domain or 'General'}\nDepth: {depth or 'Intermediate'}\n"
        f"Probe areas: {', '.join(probe_areas)}\n\n"
        "Generate the question bank JSON now."
    )
    data: dict[str, Any] = await complete_json(_SYSTEM, user, max_tokens=2000)
    questions = data.get("questions") or []
    edges = data.get("edges") or []
    if not questions:
        logger.warning("no questions generated for skill=%s", skill)
        return None
    embeddings = await embed_texts([q["text"] for q in questions])
    return questions, embeddings, edges


def _insert(db: AsyncSession, *, skill, domain, depth, questions, embeddings, edges) -> int:
    id_map: dict[int, str] = {}
    for i, (q, emb) in enumerate(zip(questions, embeddings)):
        qid = f"q_{str(ULID()).lower()}"
        id_map[i] = qid
        db.add(
            InterviewQuestion(
                id=qid, skill=skill, domain=domain, depth=depth,
                probe_area=str(q.get("probe_area") or "General")[:200],
                text=q["text"], assesses=list(q.get("assesses") or []),
                difficulty=int(q.get("difficulty") or 3),
                expected_signals=str(q.get("expected_signals") or ""),
                embedding=emb, source="seed",
            )
        )
    for edge in edges:
        src = id_map.get(edge.get("from"))
        dst = id_map.get(edge.get("to"))
        relation = edge.get("relation") or "drill_down"
        if src and dst and src != dst and relation in ("drill_down", "related", "follow_up", "prereq"):
            db.add(QuestionEdge(src_question_id=src, dst_question_id=dst, relation=relation, weight=1.0))
    return len(questions)


async def _main() -> None:
    import asyncio

    from app.db.session import close_db, connect_to_db, get_sessionmaker

    logging.basicConfig(level=logging.INFO)
    await connect_to_db()
    sm = get_sessionmaker()
    try:
        # 1) Read the skill list in a short transaction.
        async with sm() as db:
            assessments = (await db.execute(select(Assessment))).scalars().all()
            targets = []
            seen: set[str] = set()
            for a in assessments:
                if a.title in seen or not (a.probes or []):
                    continue
                seen.add(a.title)
                targets.append((a.title, a.domain, a.depth, list(a.probes or [])))

        total = 0
        for skill, domain, depth, probes in targets:
            # Skip already-seeded (fresh short session).
            async with sm() as db:
                existing = (
                    await db.execute(
                        select(func.count()).select_from(InterviewQuestion).where(InterviewQuestion.skill == skill)
                    )
                ).scalar_one()
            if existing:
                logger.info("skill=%s already has %d questions — skipping", skill, existing)
                continue
            # 2) Generate + embed with NO DB connection held.
            try:
                gen = await _generate(skill, domain, depth, probes)
            except Exception:
                logger.exception("generation failed for skill=%s — continuing", skill)
                continue
            if gen is None:
                continue
            questions, embeddings, edges = gen
            # 3) Short write transaction (commit per skill → partial progress safe).
            async with sm() as db:
                n = _insert(db, skill=skill, domain=domain, depth=depth,
                            questions=questions, embeddings=embeddings, edges=edges)
                await db.commit()
            total += n
            logger.info("seeded %d questions for skill=%s", n, skill)
        print(f"seeded {total} questions total")
    finally:
        await close_db()


if __name__ == "__main__":
    import asyncio
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_main())
