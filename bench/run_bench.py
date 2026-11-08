"""Benchmark harness — measures every HTTP endpoint of the Anveksha backend.

Run from `anveksha_backend/`:

    .\\.venv\\Scripts\\python.exe -m bench.run_bench --label baseline
    .\\.venv\\Scripts\\python.exe -m bench.run_bench --label optimized

Methodology
-----------
* A scratch Postgres database (`anveksha_bench`) is dropped/recreated and
  built at `alembic upgrade head` on every invocation, then seeded by the
  app's own lifespan — every run starts from an identical data state.
* The app runs in-process (ASGI transport + real lifespan + real engine).
  The network stack is excluded, which is intentional: before/after
  comparisons isolate application + DB work, and SQL statement counts are
  exact either way.
* SQL statements per request are counted with a SQLAlchemy
  `before_cursor_execute` hook on the pooled sync engine.
* Read pass: every GET route — warmup + N timed iterations, p50/p95/p99,
  response snapshot (normalized).
* Write pass: every non-GET route, in a deterministic scripted order with
  real payloads (see WRITE_SPEC), each response + latency + SQL recorded.
* Finally a full normalized DB dump is taken for state comparison.

Artifacts land in `bench/artifacts/<label>/`:
    results.json   reads + boot/seed metrics
    writes.json    write-pass records
    snapshots/     normalized response snapshots (reads + writes)
    state.json     normalized full-DB dump after the write pass
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

# ── Environment MUST be set before any app import (settings are cached). ──
os.environ["DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "error"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ.setdefault("DATABASE_ECHO", "false")
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

from bench.common import (  # noqa: E402
    ARTIFACTS_DIR,
    SCRATCH_DB,
    auth_headers,
    build_tokens,
    dump_state,
    enumerate_routes,
    normalize,
    persona_for,
    reset_scratch_db,
    summarize,
)

# Point the app (and Alembic, via env) at the scratch DB BEFORE any app
# import — settings are cached on first access, so the override must win up
# front. Every run rebuilds this database from migrations + seeds.
_ENV_DB_URL = os.environ.get("DATABASE_URL") or ""
if not _ENV_DB_URL:
    raise SystemExit("DATABASE_URL is not set — check anveksha_backend/.env")
SCRATCH_URL = make_url(_ENV_DB_URL).set(database=SCRATCH_DB)
# str(url) masks the password (hide_password=True) — use render_as_string.
os.environ["DATABASE_URL"] = SCRATCH_URL.render_as_string(hide_password=False)
os.environ["DATABASE_MIGRATION_URL"] = SCRATCH_URL.render_as_string(hide_password=False)

_ITERATIONS = 12
_WARMUP = 3

# ── Path-parameter resolution ──────────────────────────────────────────────
# Default: one seeded row per entity, resolved straight from the DB.
# Ambiguous spaces (same param name, different tables) get per-route
# overrides in _PARAM_OVERRIDES.

_SQL = {
    "agent": "SELECT id FROM agent_registry ORDER BY id LIMIT 1",
    "approval": "SELECT id FROM interviewer_approvals ORDER BY id LIMIT 1",
    "approval2": "SELECT id FROM interviewer_approvals ORDER BY id OFFSET 1 LIMIT 1",
    "bot": "SELECT id FROM bots ORDER BY id LIMIT 1",
    "candidate": "SELECT candidate_id FROM pipeline_cards ORDER BY candidate_id LIMIT 1",
    "catalog": "SELECT catalog_id FROM booking_catalogs ORDER BY catalog_id LIMIT 1",
    "coupon": "SELECT code FROM coupons ORDER BY code LIMIT 1",
    "company": "SELECT id FROM companies ORDER BY id LIMIT 1",
    "custom": "SELECT id FROM rbac_custom_roles ORDER BY id LIMIT 1",
    "dossier": "SELECT id FROM dossiers ORDER BY id LIMIT 1",
    "flag": "SELECT id FROM integrity_flags ORDER BY id LIMIT 1",
    "followup": "SELECT id FROM gray_followups ORDER BY id LIMIT 1",
    "group": "SELECT name FROM flag_groups ORDER BY id LIMIT 1",
    "insight": "SELECT id FROM insights ORDER BY id LIMIT 1",
    "interviewer": "SELECT id FROM anonymous_interviewers ORDER BY id LIMIT 1",
    "item": "SELECT id FROM assessments ORDER BY id LIMIT 1",
    "key": "SELECT key FROM admin_feature_flags ORDER BY key LIMIT 1",
    "member": "SELECT id FROM team_members ORDER BY id LIMIT 1",
    "model": "SELECT id FROM ai_models ORDER BY id LIMIT 1",
    "notification": "SELECT id FROM notifications WHERE user_id = 'usr_cand_001' ORDER BY id LIMIT 1",
    "perm": "SELECT permissions[1] FROM admin_role_permissions ORDER BY role LIMIT 1",
    "report_skill": "SELECT id FROM skill_report_details ORDER BY id LIMIT 1",
    "report_session": "SELECT id FROM session_reports ORDER BY id LIMIT 1",
    "role": "SELECT id FROM rbac_roles ORDER BY id LIMIT 1",
    "live_session": "SELECT id FROM live_sessions ORDER BY id LIMIT 1",
    "ver_session": "SELECT id FROM verifier_sessions ORDER BY id LIMIT 1",
    "vslot": "SELECT id FROM verifier_slots ORDER BY id LIMIT 1",
    "aslot": "SELECT id FROM admin_slots ORDER BY id LIMIT 1",
    "verifier": "SELECT id FROM admin_verifiers ORDER BY id LIMIT 1",
}

_PARAM_DEFAULTS: dict[str, Any] = {
    "agent_id": _SQL["agent"],
    "approval_id": _SQL["approval"],
    "bot_id": _SQL["bot"],
    "candidate_id": _SQL["candidate"],
    "catalog_id": _SQL["catalog"],
    "code": _SQL["coupon"],
    "company_id": _SQL["company"],
    "custom_id": _SQL["custom"],
    "dossier_id": _SQL["dossier"],
    "flag_id": _SQL["flag"],
    "followup_id": _SQL["followup"],
    "group": _SQL["group"],
    "insight_id": _SQL["insight"],
    "interviewer_id": _SQL["interviewer"],
    "item_id": _SQL["item"],
    "key": _SQL["key"],
    "member_id": _SQL["member"],
    "model_id": _SQL["model"],
    "notification_id": _SQL["notification"],
    "perm": _SQL["perm"],
    "provider": "openai",
    "report_id": _SQL["report_skill"],
    "role": _SQL["role"],
    "session_id": _SQL["live_session"],
    "shared_id": "shr_bench_missing",
    "slot_id": _SQL["vslot"],
    "user_id": "usr_cand_rajesh",
    "verifier_id": _SQL["verifier"],
    "workflow_id": "wf_bench_missing",
}

_PARAM_OVERRIDES: dict[str, dict[str, Any]] = {
    "GET /api/verifier/reports/{report_id}": {"report_id": _SQL["report_session"]},
    "PATCH /api/verifier/reports/{report_id}": {"report_id": _SQL["report_session"]},
    "POST /api/verifier/reports/{report_id}/generate": {"report_id": _SQL["report_session"]},
    "POST /api/verifier/reports/{report_id}/publish": {"report_id": _SQL["report_session"]},
    "POST /api/verifier/sessions/{session_id}/brief": {"session_id": _SQL["ver_session"]},
    # impersonate reads the admin roster table, not the portal `companies` one
    "POST /api/admin/companies/{company_id}/impersonate": {
        "company_id": "SELECT id FROM admin_companies ORDER BY id LIMIT 1"
    },
}


# ── The scripted write pass ────────────────────────────────────────────────
# Ordered deliberately: creates before updates before deletes; destructive
# ops on seeded personas last; `DELETE /api/admin/models` after the full-bot
# create (FK into ai_models). `$name` tokens resolve at execution time from
# captures (ctx) or the seeded-ids map.

def _op(
    key: str,
    persona: Optional[str],
    body: Any = None,
    *,
    params: Optional[dict[str, str]] = None,
    repeat: int = 1,
    capture: Optional[tuple[str, str]] = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "persona": persona,
        "body": body,
        "params": params or {},
        "repeat": repeat,
        "capture": capture,
    }


def write_spec() -> list[dict[str, Any]]:
    return [
        # ── Auth (public) ────────────────────────────────────────────────
        _op("POST /api/auth/dev-login", None,
            {"email": "bench@example.dev", "role": "admin", "userId": "usr_adm_001"}),
        _op("POST /api/auth/google-register", None,
            {"google_token": "bench-google-token", "role": "candidate"}),
        _op("POST /api/auth/refresh", None, {"refresh_token": "@refresh_cand"}),
        _op("POST /api/auth/logout", "cand"),
        # ── AI search + agents (deterministic fallbacks, no external calls)
        _op("POST /api/ai-search", "co", {"query": "python"}),
        _op("POST /api/agents/candidate-search", "cand", {"query": "python"}),
        _op("POST /api/agents/gray-analysis", "cand", {"sessionId": "$ver_session"}),
        _op("POST /api/agents/gap-analysis", "cand", {"sessionId": "$ver_session"}),
        _op("POST /api/agents/feedback", "adm",
            {"transcript": "Interviewer: Explain how you would implement a rate limiter.\n\n"
                           "Candidate: I would use a token bucket algorithm refilled at a fixed rate."}),
        _op("POST /api/agents/credentials", "adm",
            {"provider": "openai", "api_key": "sk-bench-dummy-key"}),
        _op("DELETE /api/agents/credentials/{provider}", "adm", None,
            params={"provider": "openai"}),
        # ── Admin: models (created first — full-bot create FKs ai_models) ─
        _op("POST /api/admin/models", "adm",
            {"name": "Bench Model", "provider": "OpenAI", "model": "bench-model-1",
             "contextWindow": 8192},
            capture=("model_id", "id")),
        _op("PATCH /api/admin/models/{model_id}", "adm", {"notes": "bench patch"},
            params={"model_id": "$model_id"}),
        _op("POST /api/admin/models/{model_id}/toggle", "adm", None,
            params={"model_id": "$model_id"}, repeat=2),
        # ── Admin: full bots ─────────────────────────────────────────────
        _op("POST /api/admin/bots", "adm",
            {"name": "BenchBot", "specializations": ["Python"],
             "primaryModelId": "$model_id", "persona": "bench", "systemPrompt": "bench"},
            capture=("fbot_id", "id")),
        _op("PATCH /api/admin/bots/{bot_id}", "adm",
            {"persona": "bench persona v2", "systemPrompt": "bench prompt v2"},
            params={"bot_id": "$fbot_id"}),
        _op("POST /api/admin/bots/{bot_id}/toggle", "adm", None,
            params={"bot_id": "$fbot_id"}, repeat=2),
        _op("DELETE /api/admin/bots/{bot_id}", "adm", None, params={"bot_id": "$fbot_id"}),
        _op("POST /api/bots", "adm",
            {"name": "Bench Simple Bot", "description": "bench", "type": "interviewer",
             "model": "bench-model-1"}),
        # ── Admin: coupons ───────────────────────────────────────────────
        _op("POST /api/admin/coupons", "adm",
            {"code": "BENCHCPN", "type": "percent", "value": 10, "desc": "bench"},
            capture=("coupon_code", "code")),
        _op("POST /api/admin/coupons/{code}/toggle", "adm", None,
            params={"code": "$coupon_code"}),
        _op("DELETE /api/admin/coupons/{code}", "adm", None, params={"code": "$coupon_code"}),
        # ── Admin: assessments ───────────────────────────────────────────
        _op("POST /api/admin/assessments", "adm",
            {"title": "Bench Assessment Alpha", "domain": "Backend", "depth": "Intermediate",
             "type": "live", "duration": 45, "price": 0},
            capture=("asmt_id", "id")),
        _op("POST /api/admin/assessments-full", "adm",
            {"title": "Bench Assessment Full Beta", "domain": "Data", "depth": "Advanced",
             "type": "bot", "duration": 60, "price": 50},
            capture=("fasmt_id", "id")),
        _op("POST /api/admin/assessments/{item_id}/toggle-publish", "adm", None,
            params={"item_id": "$asmt_id"}, repeat=2),
        _op("PATCH /api/admin/assessments-full/{item_id}", "adm", {"price": 111},
            params={"item_id": "$asmt_id"}),
        _op("POST /api/admin/assessments-full/{item_id}/toggle-publish", "adm", None,
            params={"item_id": "$asmt_id"}),
        _op("DELETE /api/admin/assessments-full/{item_id}", "adm", None,
            params={"item_id": "$asmt_id"}),
        _op("DELETE /api/admin/assessments-full/{item_id}", "adm", None,
            params={"item_id": "$fasmt_id"}),
        _op("DELETE /api/admin/assessments/{item_id}", "adm"),
        # ── Admin: dossiers ──────────────────────────────────────────────
        _op("POST /api/admin/dossiers", "adm",
            {"candidate": "Bench Candidate", "skill": "Python", "verifier": "Bench Verifier",
             "date": "2026-01-05", "score": 77},
            capture=("ados_id", "id")),
        _op("PATCH /api/admin/dossiers/{dossier_id}", "adm", {"score": 80},
            params={"dossier_id": "$ados_id"}),
        _op("POST /api/admin/dossiers/{dossier_id}/publish", "adm", None,
            params={"dossier_id": "$ados_id"}),
        _op("DELETE /api/admin/dossiers/{dossier_id}", "adm", None,
            params={"dossier_id": "$ados_id"}),
        # ── Admin: slots ─────────────────────────────────────────────────
        _op("POST /api/admin/slots", "adm",
            {"verifier": "Bench Verifier", "day": "Mon", "time": "11:00", "duration": 30,
             "skill": "Python"},
            capture=("aslot_id", "id")),
        _op("POST /api/admin/slots/{slot_id}/block", "adm", None,
            params={"slot_id": "$aslot_id"}),
        # ── Admin: agent registry ────────────────────────────────────────
        _op("PATCH /api/admin/agents/{agent_id}", "adm", {"temperature": 0.7}),
        _op("POST /api/admin/agents/{agent_id}/reset", "adm"),
        # ── Admin: feature flags + flags ─────────────────────────────────
        _op("PUT /api/admin/feature-flags/{key}", "adm", {"enabled": True}),
        _op("PUT /api/admin/feature-flags/{key}", "adm", {"enabled": False}),
        _op("PUT /api/admin/flags", "adm", {"bench": True}),
        _op("POST /api/admin/flags/group/{group}", "adm", {"value": True}),
        _op("POST /api/admin/flags/group/{group}", "adm", {"value": False}),
        _op("POST /api/admin/flags/reset", "adm"),
        # ── Admin: integrity, approvals, verifiers, specialists ──────────
        _op("POST /api/admin/integrity/{flag_id}/resolve", "adm"),
        _op("POST /api/admin/interviewer-approvals/{approval_id}/approve", "adm",
            {"note": "bench approve"}, params={"approval_id": "$approval"}),
        _op("POST /api/admin/interviewer-approvals/{approval_id}/reject", "adm",
            {"note": "bench reject"}, params={"approval_id": "$approval2"}),
        _op("POST /api/admin/verifiers/invite", "adm",
            {"email": "bench.verifier@example.dev", "specialization": "Python"}),
        _op("POST /api/admin/verifiers/{verifier_id}/approve", "adm"),
        _op("POST /api/admin/verifiers/{verifier_id}/suspend", "adm"),
        _op("POST /api/admin/specialists/invite", "adm",
            {"email": "bench.specialist@example.dev", "firstName": "Bench",
             "lastName": "Specialist", "skillName": "Python", "bio": "bench"}),
        _op("POST /api/candidate/interviewer-request", "cand",
            {"skillName": "Python", "skillScore": 78.5, "sessions": 12}),
        # ── Admin: RBAC ──────────────────────────────────────────────────
        _op("POST /api/admin/rbac/custom", "adm",
            {"name": "Bench Role", "baseRole": "candidate", "desc": "bench custom role"},
            capture=("cust_id", "id")),
        _op("PUT /api/admin/rbac/{role}/{perm}", "adm", {"on": True}),
        _op("DELETE /api/admin/rbac/custom/{custom_id}", "adm", None,
            params={"custom_id": "$cust_id"}),
        # ── Admin: pilots ────────────────────────────────────────────────
        _op("POST /api/admin/pilots-full", "adm",
            {"name": "Bench Pilot", "college": "Bench College", "dept": "CSE",
             "batch": "2026", "coordinator": "Bench Coordinator",
             "startDate": "2026-01-05", "endDate": "2026-03-05"}),
        _op("POST /api/admin/pilot-students", "adm",
            {"name": "Bench Student", "email": "bench.student@example.dev",
             "program": "Bench Program"}),
        _op("POST /api/admin/pilot-students/import", "adm",
            {"rows": [{"name": "Bench Import", "email": "bench.import@example.dev",
                       "program": "Bench Program"}]}),
        # ── Admin: credit rate ───────────────────────────────────────────
        _op("PATCH /api/admin/credit-rate", "adm", {"rupeesPerCredit": 42.5}),
        # ── Admin: users + impersonation (destructive on non-persona rows)
        _op("PUT /api/admin/users/{user_id}/roles", "adm", {"roles": ["candidate"]},
            params={"user_id": "usr_cand_rajesh"}),
        _op("POST /api/admin/users/{user_id}/deactivate", "adm", None,
            params={"user_id": "usr_cand_rajesh"}),
        _op("POST /api/admin/companies/{company_id}/impersonate", "adm"),
        # ── Company surface ──────────────────────────────────────────────
        _op("POST /api/companies/me/credits/earn", "co",
            {"amount": 25, "reason": "bench earn"}, repeat=5),
        _op("POST /api/companies/me/credits/spend", "co",
            {"amount": 5, "reason": "bench spend"}, repeat=5),
        _op("POST /api/companies/me/interviewers", "co",
            {"displayName": "Bench Interviewer", "title": "Senior Engineer",
             "email": "bench.iv@northstack.co", "specialties": ["Python"]},
            capture=("iv_id", "id")),
        _op("POST /api/companies/me/interviewers/{interviewer_id}/verify-email", "co", None,
            params={"interviewer_id": "$iv_id"}),
        _op("DELETE /api/companies/me/interviewers/{interviewer_id}", "co", None,
            params={"interviewer_id": "$iv_id"}),
        _op("POST /api/companies/candidates/{candidate_id}/unlock", "co"),
        _op("POST /api/companies/pipeline/{candidate_id}/move", "co", {"stage": "shortlist"}),
        _op("POST /api/companies/pipeline/{candidate_id}/move", "co", {"stage": "investigating"}),
        _op("POST /api/companies/followup", "co",
            {"candidateId": "$candidate", "skills": ["Python"], "message": "bench followup"}),
        _op("POST /api/companies/chat", "co",
            {"candidateId": "$candidate", "prompt": "What is this candidate's strongest skill?"}),
        _op("POST /api/company/team", "co", {"email": "bench.team@example.dev", "role": "Recruiter"},
            capture=("team_id", "id")),
        _op("DELETE /api/company/team/{member_id}", "co", None, params={"member_id": "$team_id"}),
        _op("POST /api/company/gray-followups/{followup_id}/remind", "co"),
        _op("DELETE /api/company/gray-followups/{followup_id}", "co"),
        # ── Candidate surface ────────────────────────────────────────────
        _op("POST /api/dossier/{dossier_id}/share", "cand"),
        _op("POST /api/interviews/schedule", "cand",
            {"dayId": "$day_id", "slotId": "$slot_id_book"}),
        _op("POST /api/notifications/{notification_id}/read", "cand", None, repeat=3),
        _op("PATCH /api/privacy/settings", "cand", {"shareScore": True, "shareGap": False}),
        _op("DELETE /api/privacy/shared-reports/{shared_id}", "cand", None),
        _op("PATCH /api/profiles/me", "cand",
            {"bio": "Bench bio", "location": "Bench City", "current_role": "Engineer",
             "experience_years": 5, "skills": ["Python", "SQL"]}),
        _op("POST /api/candidate/insights/{insight_id}/act", "cand"),
        # ── Verifier surface ─────────────────────────────────────────────
        _op("POST /api/verifier/my-slots", "ver",
            {"day": "Mon", "time": "11:30", "duration": 30, "skill": "Python"},
            capture=("vslot_id", "id")),
        _op("DELETE /api/verifier/my-slots/{slot_id}", "ver", None,
            params={"slot_id": "$vslot_id"}),
        _op("PATCH /api/verifier/my-profile", "ver",
            {"bio": "Bench verifier bio", "linkedin": "https://linkedin.com/in/bench",
             "language": "English"}),
        _op("PATCH /api/verifier/reports/{report_id}", "ver", {"overallScore": 8.1}),
        _op("POST /api/verifier/reports/{report_id}/generate", "ver"),
        _op("POST /api/verifier/reports/{report_id}/publish", "ver"),
        _op("POST /api/verifier/sessions/{session_id}/brief", "ver",
            {"sessionId": "$ver_session"}),
        # ── Workflows (Temporal absent → deterministic 503) ──────────────
        _op("POST /api/workflows/agent", "cand", {"agentId": "$agent", "context": {}}),
        _op("POST /api/workflows/{workflow_id}/cancel", "adm", None),
        # ── Admin: models delete LAST (FK from bots above already deleted)
        _op("DELETE /api/admin/models/{model_id}", "adm", None,
            params={"model_id": "$model_id"}),
    ]


# ── Harness machinery ──────────────────────────────────────────────────────

class Harness:
    def __init__(self, app: Any, engine: Any, counter: dict[str, int],
                 tokens: dict[str, str], routes: list[dict[str, Any]],
                 iterations: int, warmup: int) -> None:
        import httpx

        self.app = app
        self.engine = engine
        self.counter = counter
        self.tokens = tokens
        self.routes = routes
        self.iterations = iterations
        self.warmup = warmup
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://localhost",
            timeout=60.0,
        )
        self.ids: dict[str, str] = {}
        self.ctx: dict[str, str] = {}
        self._sql_cache: dict[str, Optional[str]] = {}

    # ── request plumbing ─────────────────────────────────────────────
    async def hit(self, method: str, path: str, persona: Optional[str], body: Any) -> tuple[Any, float, int]:
        before = self.counter["n"]
        t0 = time.perf_counter()
        kwargs: dict[str, Any] = {}
        if body is not None:
            kwargs["json"] = body
        r = await self.client.request(method, path, headers=auth_headers(persona, self.tokens), **kwargs)
        ms = (time.perf_counter() - t0) * 1000.0
        return r, ms, self.counter["n"] - before

    @staticmethod
    def body_json(r: Any) -> Any:
        try:
            return r.json()
        except Exception:
            return {"_text": r.text[:2000]}

    # ── id / param resolution ────────────────────────────────────────
    async def resolve_sql(self, sql: str) -> Optional[str]:
        if sql not in self._sql_cache:
            from sqlalchemy import text

            try:
                async with self.engine.connect() as conn:
                    row = (await conn.execute(text(sql))).first()
                val = str(row[0]) if row and row[0] is not None else None
            except Exception as e:  # bad resolver must not kill the run
                print(f"  [bench] resolver SQL failed ({e.__class__.__name__}): {sql}")
                val = None
            self._sql_cache[sql] = val
        return self._sql_cache[sql]

    async def param_value(self, route_key: str, param: str, opd: Optional[dict] = None) -> str:
        if opd and param in opd["params"]:
            v = opd["params"][param]
            if v.startswith("$"):
                name = v[1:]
                if name in self.ctx:
                    return str(self.ctx[name])
                if name in self.ids:
                    return str(self.ids[name])
                print(f"  [bench] unresolved token {v} for {route_key}")
                return f"missing_{name}"
            return v
        spec = _PARAM_OVERRIDES.get(route_key, {})
        source = spec.get(param, _PARAM_DEFAULTS.get(param))
        if source is None:
            return f"missing_{param}"
        if not isinstance(source, str) or not source.startswith("SELECT"):
            return str(source)
        val = await self.resolve_sql(source)
        return val if val else f"missing_{param}"

    async def build_path(self, route_key: str, opd: Optional[dict] = None) -> str:
        path = route_key.split(" ", 1)[1]
        for name, val in self.ctx.items():
            path = path.replace(f"${name}", str(val))
        for param in re.findall(r"\{(\w+)\}", path):
            value = await self.param_value(route_key, param, opd)
            path = path.replace("{" + param + "}", value)
        return path

    async def subst_body(self, body: Any) -> Any:
        if isinstance(body, str) and (body.startswith("@") or body.startswith("$")):
            name = body[1:]
            if name in self.ctx:
                return self.ctx[name]
            if name in self.ids:
                return self.ids[name]
            if name == "refresh_cand":
                return self.tokens["cand"] + ".refresh"
            print(f"  [bench] unresolved body token {body}")
            return f"missing_{name}"
        if isinstance(body, dict):
            return {k: await self.subst_body(v) for k, v in body.items()}
        if isinstance(body, list):
            return [await self.subst_body(v) for v in body]
        return body

    # ── setup: seed ids + catalog ctx ────────────────────────────────
    async def setup(self) -> None:
        for name, sql in _SQL.items():
            self.ids[name] = await self.resolve_sql(sql) or f"missing_{name}"
        # booking catalog day/slot ids for the schedule write
        r, _, _ = await self.hit("GET", "/api/interviews/catalog", "cand", None)
        data = self.body_json(r)
        days = (data or {}).get("days") or []
        slots = (data or {}).get("slotsByDay") or {}
        if days:
            self.ids["day_id"] = days[0]["id"]
            day_slots = slots.get(days[0]["id"]) or []
            self.ids["slot_id_book"] = day_slots[0]["id"] if day_slots else "missing_slot"
        else:
            self.ids["day_id"] = "missing_day"
            self.ids["slot_id_book"] = "missing_slot"

    # ── read pass ────────────────────────────────────────────────────
    async def read_pass(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        gets = [r for r in self.routes if r["method"] == "GET"]
        snap_dir = ARTIFACTS_DIR / self.label / "snapshots"
        for route in gets:
            key = route["key"]
            persona = persona_for(route)
            path = await self.build_path(key)
            statuses: dict[str, int] = {}
            lats: list[float] = []
            sqls: list[int] = []
            first_body: Any = None
            first_len = 0
            for i in range(self.warmup + self.iterations):
                r, ms, nq = await self.hit("GET", path, persona, None)
                statuses[str(r.status_code)] = statuses.get(str(r.status_code), 0) + 1
                if i >= self.warmup:
                    lats.append(ms)
                    sqls.append(nq)
                    if first_body is None:
                        first_body = normalize(self.body_json(r))
                        first_len = len(r.content)
            fname = re.sub(r"[^A-Za-z0-9]+", "_", key)[:110] + ".json"
            (snap_dir / fname).write_text(
                json.dumps(first_body, indent=1, ensure_ascii=False), encoding="utf-8"
            )
            out[key] = {
                "persona": persona,
                "resolved_path": path,
                "statuses": statuses,
                "latency_ms": summarize(lats),
                "sql": sqls,
                "sql_min": min(sqls) if sqls else 0,
                "sql_max": max(sqls) if sqls else 0,
                "bytes": first_len,
                "snapshot": f"snapshots/{fname}",
            }
            if set(statuses) - {"200"}:
                print(f"  [read] {key} -> {statuses}")
            if sqls and min(sqls) != max(sqls):
                print(f"  [read] {key} SQL count varies: {sorted(set(sqls))}")
        return out

    # ── write pass ───────────────────────────────────────────────────
    async def write_pass(self, label: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        snap_dir = ARTIFACTS_DIR / label / "snapshots" / "writes"
        covered: set[str] = set()

        # W1: scripted spec
        for i, opd in enumerate(write_spec()):
            key = opd["key"]
            if key not in {r["key"] for r in self.routes}:
                print(f"  [write] SPEC KEY NOT A ROUTE: {key}")
                continue
            covered.add(key)
            path = await self.build_path(key, opd)
            body = await self.subst_body(opd["body"])
            rec = await self._run_op(i, key, path, opd["persona"], body, opd, snap_dir)
            records.append(rec)

        # W2: every remaining write route, best-effort empty body
        remaining = [
            r for r in self.routes
            if r["method"] != "GET" and r["key"] not in covered
        ]
        for j, route in enumerate(remaining):
            key = route["key"]
            persona = route.get("auto_persona") or persona_for(route)
            path = await self.build_path(key)
            body = {} if route["method"] in {"POST", "PATCH", "PUT"} else None
            rec = await self._run_op(1000 + j, key, path, persona, body, None, snap_dir)
            records.append(rec)
        return records

    async def _run_op(self, idx: int, key: str, path: str, persona: Optional[str],
                      body: Any, opd: Optional[dict], snap_dir: Path) -> dict[str, Any]:
        method = key.split(" ", 1)[0]
        repeat = opd["repeat"] if opd else 1
        statuses: dict[str, int] = {}
        lats: list[float] = []
        sqls: list[int] = []
        first_body: Any = None
        for _ in range(repeat):
            r, ms, nq = await self.hit(method, path, persona, body)
            statuses[str(r.status_code)] = statuses.get(str(r.status_code), 0) + 1
            lats.append(ms)
            sqls.append(nq)
            if first_body is None:
                first_body = normalize(self.body_json(r))
        if opd and opd.get("capture") and r.status_code < 400:
            cap_key, field = opd["capture"]
            data = self.body_json(r)
            if isinstance(data, dict) and field in data:
                self.ctx[cap_key] = str(data[field])
            else:
                print(f"  [write] capture failed for {key}: no field '{field}'")
        fname = f"{idx:04d}_" + re.sub(r"[^A-Za-z0-9]+", "_", key)[:100] + ".json"
        (snap_dir / fname).write_text(
            json.dumps(first_body, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        if set(statuses) - {"200", "201", "204"}:
            print(f"  [write] {key} -> {statuses}")
        if sqls and min(sqls) != max(sqls):
            print(f"  [write] {key} SQL count varies: {sorted(set(sqls))}")
        return {
            "key": key,
            "resolved_path": path,
            "persona": persona,
            "statuses": statuses,
            "latency_ms": summarize(lats),
            "sql": sqls,
            "sql_min": min(sqls) if sqls else 0,
            "sql_max": max(sqls) if sqls else 0,
            "repeat": repeat,
            "snapshot": f"snapshots/writes/{fname}",
        }

    label = "bench"

    async def close(self) -> None:
        await self.client.aclose()


async def run(label: str, iterations: int, warmup: int) -> None:
    from sqlalchemy import event

    import app.db.session as dbs
    from app.main import create_app

    print(f"[bench] resetting scratch DB {SCRATCH_DB} ...")
    await reset_scratch_db(SCRATCH_URL)

    app = create_app()
    await dbs.connect_to_db()
    engine = dbs._state.engine
    assert engine is not None

    counter = {"n": 0}

    def _count(*_a: Any) -> None:
        counter["n"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _count)

    out_dir = ARTIFACTS_DIR / label
    if out_dir.exists():
        import shutil

        shutil.rmtree(out_dir)
    (out_dir / "snapshots" / "writes").mkdir(parents=True)

    tokens = build_tokens()
    routes = enumerate_routes(app)
    h = Harness(app, engine, counter, tokens, routes, iterations, warmup)
    h.label = label

    t0 = time.perf_counter()
    seed_q0 = counter["n"]
    lc = app.router.lifespan_context(app)
    await lc.__aenter__()
    boot_ms = (time.perf_counter() - t0) * 1000.0
    seed_queries = counter["n"] - seed_q0
    print(f"[bench] lifespan seed phase: {boot_ms:.0f} ms, {seed_queries} SQL statements")

    entered = True
    try:
        await h.setup()
        print(f"[bench] read pass ({len([r for r in routes if r['method'] == 'GET'])} GET routes, "
              f"warmup={warmup}, n={iterations}) ...")
        reads = await h.read_pass()
        print(f"[bench] write pass ...")
        writes = await h.write_pass(label)
        print(f"[bench] state dump ...")
        state = await dump_state(engine)

        # ── warm-restart probe (H1): shut the app down and boot it again on
        # the SAME already-seeded database. The seed phase should fast-path
        # (a single marker query) instead of replaying every seeder.
        await h.close()
        await lc.__aexit__(None, None, None)
        entered = False
        counter["n"] = 0
        await dbs.connect_to_db()  # fresh engine; pre-created so its queries count
        engine2 = dbs._state.engine
        assert engine2 is not None
        event.listen(engine2.sync_engine, "before_cursor_execute", _count)
        t1 = time.perf_counter()
        lc2 = app.router.lifespan_context(app)
        try:
            await lc2.__aenter__()
        finally:
            warm_ms = (time.perf_counter() - t1) * 1000.0
            warm_queries = counter["n"]
            await lc2.__aexit__(None, None, None)
        print(f"[bench] warm restart: {warm_ms:.0f} ms, {warm_queries} SQL statements")

        results = {
            "meta": {
                "label": label,
                "iterations": iterations,
                "warmup": warmup,
                "when": dt.datetime.now(dt.timezone.utc).isoformat(),
                "transport": "in-process ASGI (no network stack); SQL counted via engine hook",
                "routes_total": len(routes),
                "routes_get": len([r for r in routes if r["method"] == "GET"]),
                "routes_write": len([r for r in routes if r["method"] != "GET"]),
            },
            "boot": {
                "seed_phase_ms": round(boot_ms, 1),
                "seed_phase_queries": seed_queries,
                "warm_reboot_ms": round(warm_ms, 1),
                "warm_reboot_queries": warm_queries,
            },
            "reads": reads,
        }
        (out_dir / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
        (out_dir / "writes.json").write_text(json.dumps(writes, indent=1), encoding="utf-8")
        (out_dir / "state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
        n_reads_ok = sum(1 for v in reads.values() if list(v["statuses"]) == ["200"])
        print(f"[bench] done: {len(reads)} reads ({n_reads_ok} all-200), {len(writes)} writes, "
              f"{len(state)} tables. Artifacts: {out_dir}")
    finally:
        if entered:
            await h.close()
            await lc.__aexit__(None, None, None)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--label", default="baseline")
    p.add_argument("--iterations", type=int, default=_ITERATIONS)
    p.add_argument("--warmup", type=int, default=_WARMUP)
    args = p.parse_args()
    asyncio.run(run(args.label, args.iterations, args.warmup))


if __name__ == "__main__":
    main()
