r"""Fill the 4 journey reports' JSON detail fields with correctly-keyed,
transcript-grounded content so GET /api/candidate/skill-reports/{id} renders.

The mapper (candidate_service._detail_to_schema) expects internal keys:
  fit_signals: area, signal, color
  rubric:      row_id, dim, score
  phases:      num, title, done, summary
  gaps:        gap_id, area, evidence, severity
  gray:        item_id, area, companies
  evidence:    evidence_id, t, type, speaker, text, verdict, verdict_color

Idempotent: overwrites the JSON fields on each re-run.
"""

import asyncio
import selectors
import sys

GREEN = "var(--verdant)"
AMBER = "var(--ochre)"

DETAILS = {
    "SVR-KAFKA-10001": {
        "speaker": "AARAV",
        "fit_signals": [{"area": "Event streaming", "signal": "Strong", "color": GREEN}],
        "rubric": [
            {"row_id": "rb1", "dim": "Partitioning & ordering", "score": 9},
            {"row_id": "rb2", "dim": "Delivery guarantees", "score": 8},
            {"row_id": "rb3", "dim": "Consumer group mechanics", "score": 8},
        ],
        "phases": [
            {"num": "01", "title": "Partitioning & ordering", "done": True, "summary": "Explained per-partition ordering under keyless production."},
            {"num": "02", "title": "Rebalancing", "done": True, "summary": "Described cooperative-sticky partial revocation."},
            {"num": "03", "title": "Exactly-once", "done": True, "summary": "Transactional read-process-write with offset commit in-transaction."},
        ],
        "gaps": [{"gap_id": "gp1", "area": "Tiered storage ops", "evidence": "Not probed", "severity": "low"}],
        "gray": [{"item_id": "gr1", "area": "Cross-region replication", "companies": 3}],
        "evidence": [
            {"evidence_id": "ev1", "t": "00:32", "type": "claim", "speaker": "AARAV", "text": "Only per-partition ordering; keyless means round-robin across partitions.", "verdict": "Correct", "verdict_color": GREEN},
            {"evidence_id": "ev2", "t": "05:22", "type": "claim", "speaker": "AARAV", "text": "Transactional producer, read_committed, offsets via sendOffsetsToTransaction.", "verdict": "Correct — exactly-once path", "verdict_color": GREEN},
        ],
    },
    "SVR-DOTNET-10002": {
        "speaker": "RAJESH",
        "fit_signals": [{"area": "Distributed .NET", "signal": "Strong", "color": GREEN}],
        "rubric": [
            {"row_id": "rb1", "dim": "Saga / compensation", "score": 9},
            {"row_id": "rb2", "dim": "Observability", "score": 8},
            {"row_id": "rb3", "dim": "Idempotency", "score": 9},
        ],
        "phases": [
            {"num": "01", "title": "Distributed transactions", "done": True, "summary": "Saga with compensating actions over 2PC."},
            {"num": "02", "title": "Tracing", "done": True, "summary": "Correlation id via middleware + DelegatingHandler; W3C traceparent."},
            {"num": "03", "title": "Idempotency", "done": True, "summary": "Inbox pattern, transactional dedup."},
        ],
        "gaps": [{"gap_id": "gp1", "area": "Outbox vs inbox trade-offs", "evidence": "Mentioned briefly", "severity": "low"}],
        "gray": [{"item_id": "gr1", "area": "Service mesh policy", "companies": 2}],
        "evidence": [
            {"evidence_id": "ev1", "t": "00:20", "type": "claim", "speaker": "RAJESH", "text": "Saga — orchestration or choreography, compensating action per step.", "verdict": "Correct", "verdict_color": GREEN},
            {"evidence_id": "ev2", "t": "07:20", "type": "insight", "speaker": "RAJESH", "text": "Inbox pattern: record processed ids transactionally so replays are no-ops.", "verdict": "Strong operational judgement", "verdict_color": GREEN},
        ],
    },
    "SVR-FASTAPI-10003": {
        "speaker": "SAI",
        "fit_signals": [{"area": "Async Python", "signal": "Solid", "color": GREEN}],
        "rubric": [
            {"row_id": "rb1", "dim": "Event-loop safety", "score": 8},
            {"row_id": "rb2", "dim": "Session scoping", "score": 8},
            {"row_id": "rb3", "dim": "Concurrency at scale", "score": 7},
        ],
        "phases": [
            {"num": "01", "title": "Blocking in async", "done": True, "summary": "Identified event-loop stall; threadpool/async driver fix."},
            {"num": "02", "title": "SQLAlchemy 2.0 sessions", "done": True, "summary": "One AsyncSession per request via dependency."},
            {"num": "03", "title": "Pooling", "done": True, "summary": "PgBouncer transaction mode, prepared statements disabled."},
        ],
        "gaps": [{"gap_id": "gp1", "area": "Backpressure under burst", "evidence": "Named pooling only", "severity": "medium"}],
        "gray": [{"item_id": "gr1", "area": "ASGI server tuning", "companies": 1}],
        "evidence": [
            {"evidence_id": "ev1", "t": "00:18", "type": "claim", "speaker": "SAI", "text": "Blocking driver stalls the event loop; use async driver or run_in_executor.", "verdict": "Correct", "verdict_color": GREEN},
            {"evidence_id": "ev2", "t": "06:30", "type": "claim", "speaker": "SAI", "text": "Bound the pool; PgBouncer transaction mode with prepared statements off.", "verdict": "Correct — pooling nuance", "verdict_color": GREEN},
        ],
    },
    "SVR-SYSDES-10004": {
        "speaker": "MAYA",
        "fit_signals": [{"area": "System design", "signal": "Strong", "color": GREEN}],
        "rubric": [
            {"row_id": "rb1", "dim": "Write path", "score": 8},
            {"row_id": "rb2", "dim": "Read scaling / caching", "score": 9},
            {"row_id": "rb3", "dim": "Hotspot avoidance", "score": 8},
        ],
        "phases": [
            {"num": "01", "title": "Write path", "done": True, "summary": "Base62 key, partitioned KV, async replication."},
            {"num": "02", "title": "Read scaling", "done": True, "summary": "CDN/edge + Redis; immutable codes cache trivially."},
            {"num": "03", "title": "Hotspots", "done": True, "summary": "Range-partitioned counter blocks per node."},
        ],
        "gaps": [{"gap_id": "gp1", "area": "Analytics/click tracking", "evidence": "Not covered", "severity": "low"}],
        "gray": [{"item_id": "gr1", "area": "Global multi-region consistency", "companies": 2}],
        "evidence": [
            {"evidence_id": "ev1", "t": "00:22", "type": "claim", "speaker": "MAYA", "text": "Base62 of a distributed counter or hash+collision check, partitioned KV store.", "verdict": "Correct", "verdict_color": GREEN},
            {"evidence_id": "ev2", "t": "07:20", "type": "insight", "speaker": "MAYA", "text": "Range-partition counter blocks per node so key generation stays local.", "verdict": "Strong — avoids hotspot", "verdict_color": GREEN},
        ],
    },
}


async def _main() -> None:
    from app.db.session import connect_to_db, close_db, get_sessionmaker
    from app.models.candidate import SkillReportDetail

    await connect_to_db()
    try:
        async with get_sessionmaker()() as db:
            n = 0
            for rid, d in DETAILS.items():
                row = await db.get(SkillReportDetail, rid)
                if row is None:
                    print("missing", rid)
                    continue
                row.fit_signals = d["fit_signals"]
                row.rubric = d["rubric"]
                row.phases = d["phases"]
                row.gaps = d["gaps"]
                row.gray = d["gray"]
                row.evidence = d["evidence"]
                row.summary = [s["summary"] for s in d["phases"]]
                n += 1
            await db.commit()
            print("updated report details:", n)
    finally:
        await close_db()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_main())
