# Anveksha Backend

FastAPI service for the Anveksha skill-verification platform. Pairs with
the React frontend at `C:\Development\anveksha_ui`.

**Full coverage**: 128 API paths across auth, skills, assessments +
catalog + coupons, verifier console, candidate portal, privacy/dossier/
booking, interviewer approvals, company portal (credits, unlock,
pipeline, chat), admin ops (dashboard → pilots), the agentic framework
(ported from the legacy backend, AutoGen 0.7.5) and the agent registry.
Run the frontend against it with `pnpm dev:real` (MSW fully disabled).

Key behaviors beyond mock parity:
- **PHI protection** — interviewers see dossier ids only; candidates never
  see verifier identity at booking; companies see aliases until a
  credits-paid unlock (`POST /api/companies/candidates/{id}/unlock`).
- **Agents** — six pre-defined agents (brief, report, gap, gray, search,
  chat), admin-editable via `/api/admin/agents`. Each falls back to a
  deterministic, data-grounded response until the `[agents]` extras + a
  provider credential are configured.
- **On-demand briefs** — `POST /api/verifier/sessions/{id}/brief`
  generates at the interviewer's click, never pre-computed.

## Stack

- **Python 3.11+**, FastAPI, Pydantic v2
- **Supabase Postgres** via SQLAlchemy 2.0 async ORM + psycopg3 — see
  `app/models/`, `app/db/session.py`
- **Alembic** for schema migrations (`app/db/migrations/`)
- **Docker Compose** for one-command stack-up
- **ULID** identifiers (sortable, opaque)
- **pytest** against a real local Postgres (`docker-compose --profile
  test up postgres-test`) — no in-memory fakes

## Layout

```
anveksha-backend/
├── app/
│   ├── api/             # HTTP layer — route handlers, request/response binding
│   ├── auth/            # Bearer-token validation, dev-token support
│   ├── core/            # config, logging, IDs, exceptions (no domain code)
│   ├── db/              # Postgres session lifecycle, seeds, Alembic migrations
│   ├── middleware/      # request-id + access-log
│   ├── models/          # SQLAlchemy ORM models — one module per domain
│   ├── repositories/    # data-access layer (one class per domain, SqlRepository)
│   ├── schemas/         # Pydantic models — request/response contracts
│   └── services/        # business logic (referential checks, status flips, ...)
├── tests/               # pytest suite, runs against real local Postgres
├── docker-compose.yml   # API + Postgres test service + Temporal stack
└── docker-compose.dev.yml  # hot-reload override
```

## Quick start (Docker)

```powershell
# 1. From repo root
cp .env.example .env       # then fill in DATABASE_URL/DATABASE_MIGRATION_URL
                            # from your Supabase project's Connect panel

# 2. Apply migrations against Supabase (direct, non-pooled connection)
alembic upgrade head

# 3. Run the stack
docker compose up --build

# 4. Smoke test
curl http://localhost:8000/health
# {"status":"ok","service":"anveksha-backend","version":"0.1.0","database":"up"}
```

OpenAPI docs at <http://localhost:8000/docs> when `DEBUG=true`.

### Dev mode with hot-reload

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Mounts `./app` read-only into the container; `uvicorn --reload` picks up
changes on save.

## Quick start (no Docker)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Point DATABASE_URL/DATABASE_MIGRATION_URL at Supabase (or a local
# Postgres) in .env, then:
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Authentication

The frontend's dev-login flow issues self-describing tokens of the form
`dev_<base64(json)>` carrying `{email, role}`. When `DEBUG=true` this
backend accepts those verbatim — no user records required. Production
flips to real JWTs (placeholder hooks in `app.auth`).

```powershell
# How the dev-token is built (mirror of the frontend logic):
$payload = '{"email":"admin@anveksha.dev","role":"admin"}'
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
$token = "dev_$b64"

curl -H "Authorization: Bearer $token" http://localhost:8000/api/admin/models
```

## Endpoints (current)

### Health
| | |
|---|---|
| `GET /health` | Liveness + Postgres reachability |

### Admin Models (`require_roles("admin")`)
| | |
|---|---|
| `GET    /api/admin/models`              | list |
| `POST   /api/admin/models`              | create |
| `PATCH  /api/admin/models/{id}`         | partial update |
| `POST   /api/admin/models/{id}/toggle`  | flip active ↔ inactive |
| `DELETE /api/admin/models/{id}`         | remove |

### Admin Bots (`require_roles("admin")`)
| | |
|---|---|
| `GET    /api/admin/bots`               | list |
| `POST   /api/admin/bots`               | create — `primaryModelId` must reference a real model |
| `PATCH  /api/admin/bots/{id}`          | partial update |
| `POST   /api/admin/bots/{id}/toggle`   | cycle status |
| `DELETE /api/admin/bots/{id}`          | remove |

Both routers follow the contract in
`anveksha_ui/src/mocks/data/adminWorkflow.ts` (`AdminModel`) and
`anveksha_ui/src/mocks/data/botsFull.ts` (`BotFull`).

## Wiring the frontend

In `anveksha_ui/src/mocks/passthrough.ts`, uncomment the rows for the
endpoints you want served from this backend:

```ts
{ method: 'get',    path: '/api/admin/models' },
{ method: 'post',   path: '/api/admin/models' },
{ method: 'patch',  path: '/api/admin/models/:id' },
{ method: 'post',   path: '/api/admin/models/:id/toggle' },
{ method: 'delete', path: '/api/admin/models/:id' },
// ditto for /api/admin/bots
```

Restart `pnpm dev` (Vite — MSW handlers are built at startup, not HMR).
The admin Models / Bots pages now read/write this backend.

## Testing

```powershell
pip install -e ".[dev]"
pytest -q
```

The suite runs against a real local Postgres — `docker compose --profile
test up postgres-test` — via `tests/conftest.py`'s `pg_engine`/`pg_session`
fixtures (one connection + transaction per test, rolled back at teardown).
No in-memory fakes and no external service beyond that one container.

## Adding a module

1. New schemas in `app/schemas/` (request + response, camelCase API contract).
2. Model in `app/models/` (SQLAlchemy ORM, snake_case columns) — remember
   to import it in `app/models/__init__.py` or Alembic autogenerate won't
   see it.
3. Repository in `app/repositories/` (subclass `SqlRepository[ModelT]`).
4. Service in `app/services/` for any business logic + the schema↔model translation.
5. Router in `app/api/.../*.py`, mounted from `app/main.py`.
6. Generate + review the Alembic migration (`alembic revision --autogenerate`),
   then `alembic upgrade head`.
7. Seed data (if any) in `app/db/seed_*.py`, registered in `app/db/seed.py`.
8. Tests in `tests/` mirroring the layout.

## Production deploy checklist

- Set `DEBUG=false` (disables dev tokens, hides `/docs`)
- Replace `JWT_SECRET` with a 32+ byte secret
- Lock `CORS_ORIGINS` to the production frontend domain
- `DATABASE_URL` → Supabase's pooled Supavisor connection string
  (transaction mode, port 6543) — all runtime app traffic
- `DATABASE_MIGRATION_URL` → Supabase's direct connection string (port
  5432) — used only by `alembic upgrade head` as a pre-deploy step, never
  at app startup
- Connect as the least-privilege `anveksha_app` role, not `postgres` —
  created by `alembic upgrade head` with no password set; run
  `ALTER ROLE anveksha_app WITH PASSWORD '<secret>'` out-of-band and point
  `DATABASE_URL`/`DATABASE_MIGRATION_URL` at it
- Mount per-environment `.env` via your orchestrator (Compose / k8s / …)
- Load-test against the target Supabase compute tier before relying on it
  for sustained high-throughput traffic
