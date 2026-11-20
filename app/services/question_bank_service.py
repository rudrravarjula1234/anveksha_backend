"""Graph-RAG retrieval + traversal for the interview question bank.

Three capabilities the smart interviewer needs:
- `retrieve`  — vector search the bank for a skill, re-ranked by learned quality.
- `neighbors` — graph expansion (follow-up / drill-down links) of asked questions.
- `plan_next` — the decision policy: drill the current thread, switch topic, or
  generate a brand-new question when the bank has no good fit (and store it,
  so the bank grows). Returns a structured next-probe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.agents.embeddings import embed_text
from app.agents.gemini_text import complete_json
from app.models.question_bank import InterviewQuestion, QuestionEdge

logger = logging.getLogger(__name__)

# Below this cosine similarity, the best bank hit isn't relevant enough —
# generate a fresh question instead.
_RELEVANCE_FLOOR = 0.45
# An area is "covered enough" after this many questions; prefer switching.
_AREA_SATURATION = 3
# Under this many seconds left, favor breadth (switch to uncovered areas).
_TIME_LOW_SECONDS = 150


@dataclass
class NextProbe:
    question_id: Optional[str]
    question: str
    probe_area: str
    assesses: list[str]
    difficulty: int
    rationale: str
    action: str  # "drill" | "switch" | "new"

    def as_dict(self) -> dict[str, Any]:
        return {
            "questionId": self.question_id,
            "question": self.question,
            "probeArea": self.probe_area,
            "assesses": self.assesses,
            "difficulty": self.difficulty,
            "rationale": self.rationale,
            "action": self.action,
        }


async def resolve_bank_skill(db: AsyncSession, raw_skill: str) -> str:
    """Map a free-text skill (e.g. booking_catalogs.skill_name ".NET
    Microservices") to the bank's skill key (e.g. assessments.title ".NET
    Microservices & Cloud Architecture"), which rarely match exactly. Exact
    first, then case-insensitive containment either direction (shortest bank
    skill wins), else the raw string."""
    from sqlalchemy import func as _func
    from sqlalchemy import literal

    exact = (
        await db.execute(
            select(InterviewQuestion.skill).where(InterviewQuestion.skill == raw_skill).limit(1)
        )
    ).scalar_one_or_none()
    if exact:
        return exact
    row = (
        await db.execute(
            select(InterviewQuestion.skill)
            .where(
                InterviewQuestion.skill.ilike(f"%{raw_skill}%")
                | literal(raw_skill).ilike(_func.concat("%", InterviewQuestion.skill, "%"))
            )
            .order_by(_func.length(InterviewQuestion.skill))
            .limit(1)
        )
    ).scalar_one_or_none()
    return row or raw_skill


def _score(distance: float, quality: float) -> float:
    """Combine vector closeness (1-distance) with learned quality, so good
    questions surface more without ignoring relevance."""
    similarity = 1.0 - float(distance)
    return similarity * (0.5 + float(quality))


class QuestionBankService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def retrieve(
        self, *, skill: str, query_text: str, exclude_ids: Optional[list[str]] = None, k: int = 8
    ) -> list[tuple[InterviewQuestion, float]]:
        """Top-k questions for `skill` nearest to `query_text`, re-ranked by
        quality. Returns (question, similarity) pairs, best first."""
        qv = await embed_text(query_text)
        exclude = set(exclude_ids or [])
        dist = InterviewQuestion.embedding.cosine_distance(qv)
        stmt = (
            select(InterviewQuestion, dist.label("distance"))
            .where(InterviewQuestion.skill == skill)
            .order_by(dist)
            .limit(k * 3)
        )
        rows = (await self.db.execute(stmt)).all()
        scored = [
            (q, 1.0 - float(d), _score(d, q.quality_score))
            for (q, d) in rows
            if q.id not in exclude
        ]
        scored.sort(key=lambda t: t[2], reverse=True)
        return [(q, sim) for (q, sim, _s) in scored[:k]]

    async def neighbors(
        self, *, question_id: str, relations: tuple[str, ...], exclude_ids: Optional[list[str]] = None
    ) -> list[tuple[InterviewQuestion, QuestionEdge]]:
        """Graph neighbors of a question along the given relations, highest
        edge weight first."""
        exclude = set(exclude_ids or [])
        stmt = (
            select(InterviewQuestion, QuestionEdge)
            .join(QuestionEdge, QuestionEdge.dst_question_id == InterviewQuestion.id)
            .where(QuestionEdge.src_question_id == question_id)
            .where(QuestionEdge.relation.in_(relations))
            .order_by(QuestionEdge.weight.desc())
        )
        rows = (await self.db.execute(stmt)).all()
        return [(q, e) for (q, e) in rows if q.id not in exclude]

    async def _area_counts(self, asked_ids: list[str]) -> dict[str, int]:
        if not asked_ids:
            return {}
        rows = (
            await self.db.execute(
                select(InterviewQuestion.probe_area, func.count())
                .where(InterviewQuestion.id.in_(asked_ids))
                .group_by(InterviewQuestion.probe_area)
            )
        ).all()
        return {area: int(n) for area, n in rows}

    async def _generate_new(
        self, *, skill: str, context: str, covered_areas: list[str]
    ) -> NextProbe:
        system = (
            "You are an expert technical interviewer. Produce ONE next question that "
            "advances the interview. Output ONLY JSON: "
            '{"text":"...","probe_area":"...","assesses":["..."],"difficulty":1-5,'
            '"expected_signals":"...","rationale":"why ask this now"}'
        )
        user = (
            f"Skill: {skill}\nAlready covered areas: {', '.join(covered_areas) or 'none'}\n"
            f"Recent conversation:\n{context[:1500]}\n\n"
            "The question bank had no strongly relevant question. Generate a fresh, "
            "on-topic question (prefer an uncovered area). JSON now."
        )
        data = await complete_json(system, user, max_tokens=500)
        qid = f"q_{str(ULID()).lower()}"
        emb = await embed_text(data["text"])
        row = InterviewQuestion(
            id=qid,
            skill=skill,
            probe_area=str(data.get("probe_area") or "General")[:200],
            text=data["text"],
            assesses=list(data.get("assesses") or []),
            difficulty=int(data.get("difficulty") or 3),
            expected_signals=str(data.get("expected_signals") or ""),
            embedding=emb,
            source="generated",
        )
        self.db.add(row)
        await self.db.flush()
        return NextProbe(
            question_id=qid,
            question=row.text,
            probe_area=row.probe_area,
            assesses=row.assesses,
            difficulty=row.difficulty,
            rationale=str(data.get("rationale") or "No bank question fit — generated a fresh one."),
            action="new",
        )

    async def plan_next(
        self,
        *,
        skill: str,
        last_answer: str,
        asked_ids: Optional[list[str]] = None,
        covered_areas: Optional[list[str]] = None,
        seconds_remaining: Optional[int] = None,
    ) -> NextProbe:
        asked_ids = asked_ids or []
        covered_areas = covered_areas or []
        context = last_answer or f"Start of a {skill} interview."

        area_counts = await self._area_counts(asked_ids)
        time_low = seconds_remaining is not None and seconds_remaining < _TIME_LOW_SECONDS

        # 1) Try to DRILL: follow-up/drill-down neighbor of the last asked
        #    question, as long as its area isn't saturated and time isn't low.
        if asked_ids and not time_low:
            last_id = asked_ids[-1]
            drill = await self.neighbors(
                question_id=last_id, relations=("follow_up", "drill_down"), exclude_ids=asked_ids
            )
            if drill:
                q, edge = drill[0]
                if area_counts.get(q.probe_area, 0) < _AREA_SATURATION:
                    return NextProbe(
                        question_id=q.id, question=q.text, probe_area=q.probe_area,
                        assesses=q.assesses, difficulty=q.difficulty,
                        rationale="Drilling deeper on this thread — their answer earned a harder follow-up.",
                        action="drill",
                    )

        # 2) SWITCH / breadth: retrieve relevant questions, prefer an
        #    uncovered (or least-covered, when time is low) probe area.
        hits = await self.retrieve(skill=skill, query_text=context, exclude_ids=asked_ids, k=8)
        if hits:
            def area_load(q: InterviewQuestion) -> int:
                return area_counts.get(q.probe_area, 0)

            uncovered = [(q, sim) for (q, sim) in hits if area_load(q) == 0]
            pick_from = uncovered or hits
            # When time is tight, maximize breadth (least-covered area);
            # otherwise take the most relevant hit.
            if time_low:
                pick_from = sorted(pick_from, key=lambda t: (area_load(t[0]), -t[1]))
            q, sim = pick_from[0]
            if sim >= _RELEVANCE_FLOOR:
                action = "switch" if (not asked_ids or area_load(q) == 0) else "drill"
                reason = (
                    "Time is limited — moving to an uncovered area for breadth."
                    if time_low
                    else "Best-matching bank question for the current thread."
                )
                return NextProbe(
                    question_id=q.id, question=q.text, probe_area=q.probe_area,
                    assesses=q.assesses, difficulty=q.difficulty, rationale=reason, action=action,
                )

        # 3) GENERATE-NEW: nothing in the bank fit well enough.
        return await self._generate_new(skill=skill, context=context, covered_areas=covered_areas)
