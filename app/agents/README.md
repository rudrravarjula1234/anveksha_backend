# app/agents — Agentic Framework (ported)

Port of the legacy `backend/lib/agent_service/` AutoGen 0.7.5 wrapper into the
new FastAPI + Motor backend. The package structure (providers/, orchestrators/,
streaming/, token_usage/, mcp/, hitl/, utils/) and the orchestration logic are
preserved; only the integration seams changed.

## What changed vs the legacy version

| Legacy | Port |
| --- | --- |
| `from lib.agent_service.X import Y` | `from app.agents.X import Y` |
| `db.session.mongodb.db` | `app.db.mongo.get_database()` |
| `core.config.settings` / per-package `AgentServiceSettings` | `app.core.config.get_settings()` (new `CREDENTIAL_ENCRYPTION_KEY` setting) |
| `services/model_config_service.py` reading `model_configs` | **`model_config_adapter.py`** reading the new `ai_models` (AdminModel) collection and converting to the legacy config dict (`model` -> `model_name`, `"Azure OpenAI"` -> `azure`, `"Google Vertex"` -> `google`, `"AWS Bedrock"` -> `bedrock`, `costPer1k*` -> per-million pricing, legacy defaults for temperature/max_tokens/top_p) |
| `services/model_credential_service.py` | **`credentials.py`** — Fernet-encrypted keys in the `model_credentials` collection; key from `settings.CREDENTIAL_ENCRYPTION_KEY`, with a stable dev key derived from `JWT_SECRET` when unset in DEBUG |
| `services/token_usage_service.py` | **`token_usage/store.py`** — same contracts, rows in the `token_usage` collection (plus a new `list_recent()` for the API) |
| `schemas/interview_feedback_schemas.py`, `schemas/token_usage.py`, `lib/agent_service/schemas.py` | merged into **`schemas.py`** as Pydantic v2 models (`@validator` -> `@field_validator`, `min_items` -> `min_length`) |
| Direct `autogen_*` imports at module top-level | **`autogen_compat.py`** — single guarded import site; the whole package imports cleanly without AutoGen and sets `AUTOGEN_AVAILABLE` |
| Exceptions rooted at `Exception` | rooted at `app.core.exceptions.AppError` (same class names; global handler maps them to JSON; new `AgentFrameworkNotInstalledError` -> 503) |
| `services/interview_feedback_service.py` | **`feedback_service.py`** (same logic; see adaptations below) |

### Behavioural adaptations (intentional, small)

- **Optional AutoGen**: `startup.initialize_agent_service()` returns `None`
  (logged warning) instead of crashing when `autogen-agentchat`/`autogen-ext`
  are not installed. Constructing a provider/orchestrator/HITL agent without
  them raises `AgentFrameworkNotInstalledError` (HTTP 503).
- **Model fallback**: the legacy code hardcoded `gemini-2.0-flash`. The port
  keeps that default but falls back to the first *active* model registered in
  `ai_models` when the default is not registered (`feedback_service._resolve_model_name`).
- **`DetailedAnalysis.gap_analysis`** now defaults to `""` — the hierarchical
  coordinator prompt never emitted it (only the direct-call prompt does), so a
  required field would reject valid orchestration output.
- **`AgentConfig.human_input_mode`** accepts the legacy uppercase strings
  (`"NEVER"`) via a `mode="before"` normalizer.
- **Factory**: `custom` provider (AdminModel "Custom") routes to the
  OpenAI-compatible client with the configured endpoint; `anthropic`/`bedrock`
  raise `ModelProviderNotFoundError` exactly as in the legacy framework (it
  never implemented those providers).
- The PII sanitizer hook (`core.pii.llm_sanitizer` -> `app.core.pii.llm_sanitizer`)
  remains a lazy optional import; the new backend has no such module, so it is
  a silent no-op — identical to a legacy deployment without the PII package.

### Stubs preserved from legacy (not regressions)

- `mcp/mcp_manager.py` still *simulates* MCP connections/queries (the legacy
  MVP TODOs are kept verbatim).
- The legacy "Temporal worker activities" comment on the module-level service
  instance: the new backend has no Temporal worker; the module-level instance
  plus `startup.get_agent_service()` accessor remain for API handlers.

## API surface (`app/api/agents.py`, not mounted yet)

- `GET  /status` — `AUTOGEN_AVAILABLE`, configured providers, active model count (any authenticated user)
- `GET/POST /credentials`, `DELETE /credentials/{provider}` — admin, masked output, Fernet-encrypted at rest
- `GET  /token-usage?limit=N` — admin, recent usage rows
- `POST /feedback` — admin or interviewer; 503 until AutoGen is installed and a credential is configured

Mount it from `app.main` (the integrator wires this), e.g.:

```python
from app.api.agents import router as agents_router
app.include_router(agents_router, prefix="/api/agents")
```

## Enabling full agentic mode

1. Install the optional extras (pins match the legacy repo):

   ```bash
   pip install ".[agents]"
   # or: pip install autogen-core==0.7.5 autogen-agentchat==0.7.5 \
   #     "autogen-ext[openai,anthropic,azure,ollama,mcp]==0.7.5" "tiktoken>=0.5.0"
   ```

2. Set a real encryption key in production (`.env`):

   ```bash
   CREDENTIAL_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
   ```

   In DEBUG, an unset key falls back to a stable dev key derived from
   `JWT_SECRET` (keys encrypted with it are unreadable once a real key is set).

3. Register a model (admin UI / `POST /api/admin/models`) — e.g. provider
   `Google Vertex`, model `gemini-2.0-flash`.

4. Store the provider credential:

   ```bash
   POST /api/agents/credentials
   {"provider": "google", "api_key": "<AI-Studio key>"}
   ```

   Provider keys are the lowercase mapped names: `openai`, `azure`, `google`,
   `anthropic`, `bedrock`, `ollama` (keyless), `custom`.

5. `GET /api/agents/status` should report `"ready": true`; then
   `POST /api/agents/feedback` with `{"transcript": "...", "metadata": {...}}`.
