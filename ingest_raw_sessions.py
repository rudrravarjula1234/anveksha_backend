r"""Drive the RAW ingest endpoint for 4 coherent assessment journeys.

Posts each finished session to POST /api/sessions/{id}/transcript exactly as
RAW's bot-worker (bot-worker/anveksha.py send_session_transcript) would, with
the X-Service-Key header. The session metadata carries the resolved
assessment/candidate/verifier ids so the stored transcript rows trace back by
real FK (see app/services/session_ingest_service.py).

Run (backend must be up with SERVICE_API_KEY set):
    .\.venv\Scripts\python.exe ingest_raw_sessions.py
"""

import os
import sys
import urllib.request

BASE = "http://localhost:8000"


def _service_key() -> str:
    # Read SERVICE_API_KEY straight from .env (dotenv not required here).
    with open(os.path.join(os.path.dirname(__file__), ".env"), encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("SERVICE_API_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("SERVICE_API_KEY not found in .env")


def _line(t, who, text, label):
    return {"t": t, "who": who, "text": text, "label": label}


JOURNEYS = [
    {
        "id": "iv_kafka_aarav",
        "bot_id": "BOT-001",
        "response_mode": "voice",
        "duration_ms": 58 * 60 * 1000,
        "assessment_id": "asm_01M7VSWQ0BR8P99D3HX5S3FN4V",
        "candidate_user_id": "usr_cand_001",
        "verifier_user_id": "usr_ver_001",
        "skill": "Event-Driven Backends with Kafka",
        "transcript": [
            _line("00:00", "bot", "Welcome Aarav. We'll go deep on Kafka and event-driven design. Ready?", "Bob"),
            _line("00:08", "candidate", "Ready.", "Candidate (Aarav)"),
            _line("00:14", "bot", "A producer writes to a 6-partition topic with no key. What ordering can a consumer rely on?", "Bob"),
            _line("00:32", "candidate", "Only per-partition ordering. No key means round-robin/sticky batching across partitions, so there's no total order across the topic.", "Candidate (Aarav)"),
            _line("02:10", "bot", "Four consumers, six partitions, cooperative-sticky assignor. A fifth consumer joins — what happens?", "Bob"),
            _line("02:36", "candidate", "A rebalance; cooperative-sticky revokes only the partitions that move, not the whole group, so most consumers keep processing.", "Candidate (Aarav)"),
            _line("05:00", "bot", "Give me exactly-once from one topic, through processing, to another.", "Bob"),
            _line("05:22", "candidate", "Transactional producer with idempotence, read-process-write in a transaction, consumer isolation.level=read_committed, offsets committed via sendOffsetsToTransaction.", "Candidate (Aarav)"),
            _line("09:40", "bot", "Thanks Aarav, that's the session.", "Bob"),
        ],
    },
    {
        "id": "iv_dotnet_rajesh",
        "bot_id": "bot_dotnet_architect",
        "response_mode": "text",
        "duration_ms": 60 * 60 * 1000,
        "assessment_id": "ASS-001",
        "candidate_user_id": "usr_cand_rajesh",
        "verifier_user_id": "usr_spec_001",
        "skill": ".NET Microservices & Cloud Architecture",
        "transcript": [
            _line("00:00", "bot", "We'll cover .NET microservices. Distributed transaction across two services without 2PC — how?", "Kavya"),
            _line("00:20", "candidate", "Saga — orchestration or choreography — with a compensating action per step to roll back on failure.", "Candidate (Rajesh)"),
            _line("03:10", "bot", "Propagate a correlation id across service calls in ASP.NET Core?", "Kavya"),
            _line("03:32", "candidate", "Middleware reads/creates the id, pushes it to a logging scope; an outgoing HttpClient DelegatingHandler re-attaches it. W3C traceparent via OpenTelemetry automates it.", "Candidate (Rajesh)"),
            _line("07:00", "bot", "Idempotent handling for an at-least-once broker?", "Kavya"),
            _line("07:20", "candidate", "Inbox pattern: record processed message ids transactionally with the side effect, so a replay is a no-op. Or a dedup table with a unique constraint.", "Candidate (Rajesh)"),
            _line("11:00", "bot", "Good depth. That's everything.", "Kavya"),
        ],
    },
    {
        "id": "iv_fastapi_sai",
        "bot_id": "bot_python_fastapi",
        "response_mode": "text",
        "duration_ms": 45 * 60 * 1000,
        "assessment_id": "ASS-003",
        "candidate_user_id": "usr_g_01M7TH79WNDCBB4E9REWWDK85Z",
        "verifier_user_id": "usr_verif_rajesh",
        "skill": "Python FastAPI & Async Data Systems",
        "transcript": [
            _line("00:00", "bot", "FastAPI async. What breaks if you call a blocking DB driver inside an async endpoint?", "Tara"),
            _line("00:18", "candidate", "It blocks the event loop, stalling all concurrent requests on that worker. Use an async driver or run the blocking call in a threadpool via run_in_executor / anyio.to_thread.", "Candidate (Sai)"),
            _line("03:00", "bot", "SQLAlchemy 2.0 async session per request — how do you scope it?", "Tara"),
            _line("03:24", "candidate", "A sessionmaker dependency yielding one AsyncSession per request, committed/closed in the dependency's finally. Never share a session across requests.", "Candidate (Sai)"),
            _line("06:30", "candidate", "For high concurrency I'd also bound the pool and use a pooler like PgBouncer in transaction mode with prepared statements disabled.", "Candidate (Sai)"),
            _line("09:00", "bot", "Solid. Session complete.", "Tara"),
        ],
    },
    {
        "id": "iv_sysdesign_maya",
        "bot_id": "bot_system_design",
        "response_mode": "voice",
        "duration_ms": 60 * 60 * 1000,
        "assessment_id": "ASS-002",
        "candidate_user_id": "usr_ver_001",
        "verifier_user_id": "usr_spec_001",
        "skill": "System Design - Scalable Distributed Systems",
        "transcript": [
            _line("00:00", "bot", "Design a URL shortener for 10k writes/sec, reads 100x that. Start with the write path.", "Arjun"),
            _line("00:22", "candidate", "Generate a short key (base62 of a distributed counter or hash+collision check), write to a partitioned KV store keyed by short code, async-replicate.", "Candidate (Maya)"),
            _line("03:40", "bot", "Reads are 100x writes — how do you serve them?", "Arjun"),
            _line("04:02", "candidate", "Cache hot codes in a CDN/edge + Redis; the KV store is the source of truth. Short codes are immutable so caching is trivial with long TTLs.", "Candidate (Maya)"),
            _line("07:20", "candidate", "For the counter I'd avoid a single hotspot — range-partition counter blocks per node so key generation stays local.", "Candidate (Maya)"),
            _line("10:00", "bot", "Good trade-off discussion. Done.", "Arjun"),
        ],
    },
]


def post(j: dict, key: str) -> None:
    body = {
        "room": j["id"],
        "bookingId": j["id"],
        "botId": j["bot_id"],
        "responseMode": j["response_mode"],
        "durationMs": j["duration_ms"],
        "transcript": j["transcript"],
        "participants": [
            {"identity": j["candidate_user_id"], "name": "candidate", "role": "candidate"},
            {"identity": j["bot_id"], "name": j["bot_id"], "role": "bot"},
        ],
        "metadata": {
            "assessmentId": j["assessment_id"],
            "candidateUserId": j["candidate_user_id"],
            "verifierUserId": j["verifier_user_id"],
            "skill": j["skill"],
        },
    }
    import json

    req = urllib.request.Request(
        f"{BASE}/api/sessions/{j['id']}/transcript",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Service-Key": key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(resp.status, resp.read().decode())


if __name__ == "__main__":
    key = _service_key()
    for j in JOURNEYS:
        post(j, key)
