"""Shared helpers for the benchmark harness (Phase A/C measurement).

Everything here is import-safe without a database. `run_bench` and
`compare` both build on these primitives so that a baseline run and an
optimized run are measured and normalized by identical code.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import uuid as _uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

# ── Normalization ──────────────────────────────────────────────────────────
# Volatile values that legitimately differ between two identical runs:
#   * ISO datetimes (created_at/updated_at/last_login/"now" stamps)
#   * ULIDs generated at runtime (26-char Crockford base32)
#   * dev bearer tokens (embed an iat timestamp)
#   * encrypted credential blobs (Fernet random IV)
# Everything else must match byte-for-byte between runs.

_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?([+-]\d{2}:\d{2}|Z)?")
# ULIDs appear bare (`01J...`), prefixed (`mdl_01J...`, `tok_01J...`), and
# in lowercase (`svr_01j...`) — `\b` doesn't fire after `_`, and some
# services lowercase ids, so match all-caps or all-lower variants explicitly.
_ULID_RE = re.compile(
    r"(?<![0-9A-Za-z])(?:[0-9A-HJKMNP-TV-Z]{26}|[0-9a-hjkmnp-tv-z]{26})(?![0-9A-Za-z])"
)
_TOKEN_RE = re.compile(r"dev_[A-Za-z0-9+/=_.-]+")
_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}(?![0-9A-Fa-f])")

VOLATILE_KEYS = {"api_key_encrypted"}


def normalize(value: Any, key: Optional[str] = None) -> Any:
    """Recursively replace volatile values with stable placeholders."""
    if isinstance(value, dict):
        return {k: normalize(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v, key) for v in value]
    if isinstance(value, (_dt.datetime, _dt.date)):
        return "<TS>"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (_uuid.UUID, memoryview)):
        return str(value)
    if isinstance(value, str):
        if key in VOLATILE_KEYS:
            return "<ENC>"
        s = _TS_RE.sub("<TS>", value)
        s = _TOKEN_RE.sub("<TOKEN>", s)
        s = _ULID_RE.sub("<ULID>", s)
        s = _HEX_RE.sub("<HEX>", s)
        return s
    return value


def dumps_norm(obj: Any) -> str:
    """Canonical JSON for normalized structures (sorted keys, no spaces)."""
    return json.dumps(normalize(obj), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ── Statistics ─────────────────────────────────────────────────────────────

def percentile(values: list[float], p: float) -> float:
    """Linear-interpolation percentile (same convention as numpy default)."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def summarize(latencies_ms: list[float]) -> dict[str, float]:
    return {
        "p50": round(percentile(latencies_ms, 50), 3),
        "p95": round(percentile(latencies_ms, 95), 3),
        "p99": round(percentile(latencies_ms, 99), 3),
        "max": round(max(latencies_ms), 3) if latencies_ms else 0.0,
        "mean": round(sum(latencies_ms) / len(latencies_ms), 3) if latencies_ms else 0.0,
    }


# ── Route introspection ────────────────────────────────────────────────────
# Starlette >=0.48 wraps include_router in a lazy `_IncludedRouter`; the
# prefix and router-level deps live on its `include_context`.

def _classify_call(call: Any) -> Optional[tuple[str, list[str]]]:
    from app.auth.deps import get_current_principal

    if call is get_current_principal:
        return ("principal", [])
    if getattr(call, "__qualname__", "") == "require_roles.<locals>._enforce":
        allowed: tuple = ()
        for cell in call.__closure__ or ():
            v = cell.cell_contents
            if isinstance(v, tuple) and all(isinstance(x, str) for x in v):
                allowed = v
        return ("roles", list(allowed))
    return None


def _walk_deps(deps: Any) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    stack = list(deps)
    while stack:
        d = stack.pop()
        if hasattr(d, "dependencies"):
            stack.extend(d.dependencies)
            call = getattr(d, "call", None)
        else:
            call = getattr(d, "callable", None)
        hit = _classify_call(call) if call else None
        if hit:
            out.append(hit)
    return out


def enumerate_routes(app: Any) -> list[dict[str, Any]]:
    """Every APIRoute: full path template, methods, auth kind + roles."""
    from fastapi.routing import APIRoute

    routes: list[dict[str, Any]] = []

    def _add(route: APIRoute, prefix: str, router_deps: Any) -> None:
        kinds = _walk_deps(route.dependant.dependencies)
        if router_deps:
            kinds += _walk_deps(router_deps)
        kind, roles = "none", []
        for k, r in kinds:
            if k == "roles":
                kind, roles = "roles", r
                break
        else:
            if kinds:
                kind = "principal"
        path = prefix + route.path
        params = [p for p in (prefix + route.path_format).split("/") if p.startswith("{")]
        for m in sorted(route.methods - {"HEAD", "OPTIONS"}):
            routes.append(
                {
                    "key": f"{m} {path}",
                    "method": m,
                    "path": path,
                    "auth": kind,
                    "roles": roles,
                    "params": params,
                    "name": route.name,
                }
            )

    for r in app.routes:
        if type(r).__name__ == "_IncludedRouter":
            prefix = r.include_context.prefix or ""
            deps = r.include_context.dependencies
            for sub in r.original_router.routes:
                if isinstance(sub, APIRoute):
                    _add(sub, prefix, deps)
        elif isinstance(r, APIRoute):
            _add(r, "", None)

    routes.sort(key=lambda x: x["key"])
    return routes


# ── Persona tokens ─────────────────────────────────────────────────────────

PERSONAS = {
    "adm": ("usr_adm_001", "admin"),
    "ver": ("usr_ver_001", "interviewer"),
    "co": ("usr_co_001", "company"),
    "hr": ("usr_hr_001", "hr"),
    "cand": ("usr_cand_001", "candidate"),
}


def build_tokens() -> dict[str, str]:
    from app.auth.dev_tokens import make_dev_token

    return {p: make_dev_token(sub, role) for p, (sub, role) in PERSONAS.items()}


def auth_headers(persona: Optional[str], tokens: dict[str, str]) -> dict[str, str]:
    if persona is None:
        return {}
    return {"Authorization": f"Bearer {tokens[persona]}"}


def persona_for(route: dict[str, Any]) -> Optional[str]:
    """Pick the persona that satisfies the route's auth requirements."""
    if route["auth"] == "none":
        return None
    roles = set(route["roles"])
    if "admin" in roles:
        return "adm"
    if "interviewer" in roles:
        return "ver"
    if "company" in roles or "hr" in roles:
        return "co"
    if "candidate" in roles:
        return "cand"
    # principal-only: default by surface
    p = route["path"]
    if p.startswith("/api/admin"):
        return "adm"
    if p.startswith("/api/verifier"):
        return "ver"
    if p.startswith("/api/compan") or p.startswith("/api/ai-search"):
        return "co"
    if p.startswith("/api/workflows"):
        return "cand"
    return "cand"


# ── Scratch DB lifecycle ───────────────────────────────────────────────────

SCRATCH_DB = "anveksha_bench"


def alembic_cfg():
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    return cfg


async def reset_scratch_db(scratch_url: Any) -> None:
    """DROP + CREATE the scratch database and build schema at head."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from alembic import command

    admin_url = scratch_url.set(database="postgres")
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin.begin() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_url.database}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{scratch_url.database}"'))
    await admin.dispose()

    eng = create_async_engine(scratch_url)
    cfg = alembic_cfg()

    def _up(sc):
        cfg.attributes["connection"] = sc
        command.upgrade(cfg, "head")

    async with eng.begin() as conn:
        await conn.run_sync(_up)
    await eng.dispose()


# ── State dump ─────────────────────────────────────────────────────────────

async def dump_state(engine: Any) -> dict[str, list[dict[str, Any]]]:
    """Full normalized dump of every table, ordered by primary key."""
    from sqlalchemy import select, text

    import app.models  # noqa: F401 — registers tables
    from app.models.base import Base

    out: dict[str, list[dict[str, Any]]] = {}
    async with engine.connect() as conn:
        for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
            order_cols = [c.name for c in table.columns if c.primary_key] or [table.columns[0].name]
            order = ", ".join(order_cols)
            res = await conn.execute(text(f'SELECT * FROM "{table.name}" ORDER BY {order}'))
            rows = []
            for r in res.mappings():
                rows.append({k: normalize(v, k) for k, v in dict(r).items()})
            out[table.name] = rows
    return out
