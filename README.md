# Anveksha Backend

FastAPI service for the Anveksha skill-verification platform. Pairs with
the React frontend at `C:\Development\anveksha_ui`.

This is a greenfield service designed to grow alongside the frontend.
First slice ships **AI Models** and **Bots** admin endpoints — the
frontend's MSW passthrough allowlist (`anveksha_ui/src/mocks/passthrough.ts`)
flips one endpoint at a time from the mock to this backend.

## Stack

- **Python 3.11+**, FastAPI, Pydantic v2
- **MongoDB** via Motor (async driver)
- **Docker Compose** for one-command stack-up
- **ULID** identifiers (sortable, opaque)
- **pytest** with an in-memory Mongo stub so tests run without containers

## Layout

```
anveksha-backend/
├── app/
│   ├── api/             # HTTP layer — route handlers, request/response binding
│   ├── auth/            # Bearer-token validation, dev-token support
│   ├── core/            # config, logging, IDs, exceptions (no domain code)
│   ├── db/              # Mongo client lifecycle + index creation
│   ├── middleware/      # request-id + access-log
│   ├── repositories/    # data-access layer (one class per Mongo collection)
│   ├── schemas/         # Pydantic models — request/response contracts
│   └── services/        # business logic (referential checks, status flips, ...)
├── tests/               # pytest suite, fully hermetic
├── docker-compose.yml   # API + Mongo stack
└── docker-compose.dev.yml  # hot-reload override
```

## Quick start (Docker)

```powershell
# 1. From repo root
cp .env.example .env       # then edit MONGO_PASSWORD etc.

# 2. Run the stack
docker compose up --build

# 3. Smoke test
curl http://localhost:8000/health
# {"status":"ok","service":"anveksha-backend","version":"0.1.0","mongo":"up"}
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

# Start a Mongo locally OR point at one via MONGO_URI in .env
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
| `GET /health` | Liveness + Mongo reachability |

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

The suite uses an in-memory `FakeCollection` (see `tests/conftest.py`)
so it runs without a Mongo container or any external service.

## Adding a module

1. New schemas in `app/schemas/` (request + response).
2. Repository in `app/repositories/` (subclass `MongoRepository`).
3. Service in `app/services/` for any business logic.
4. Router in `app/api/.../*.py`, mounted from `app/main.py`.
5. Indexes in `app/db/indexes.py`.
6. Tests in `tests/` mirroring the layout.

## Production deploy checklist

- Set `DEBUG=false` (disables dev tokens, hides `/docs`)
- Replace `JWT_SECRET` with a 32+ byte secret
- Lock `CORS_ORIGINS` to the production frontend domain
- Use a managed Mongo (Atlas) via `MONGO_URI`
- Mount per-environment `.env` via your orchestrator (Compose / k8s / …)
- Drop the `mongo` service from Compose (or use it only as a dev fallback)
