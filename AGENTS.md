# Anveksha Workspace Guidelines

## Product & Repo Conventions
- **Terminology**: Always use **Assessment** (not "interview") and **Verifier** (not "interviewer") in UI copy, documentation, and new domain code.
- **No Mock Auto-Seeding**: Keep `SEED_DATA=False` in `anveksha_backend`. Do not re-enable automatic mock/demo seeding on startup.
- **Active Live Stage**: Use `F:\Anveksha\RAW_App` (LiveKit + Go token server + React client + Python bot-worker) for live assessment rooms. Ignore the legacy `.NET` `F:\Anveksha\Raw` directory.

## Windows + Supabase Postgres Guardrails
- **Async Event Loop**: On Windows, `psycopg` v3 async requires `SelectorEventLoop` (it fails under `ProactorEventLoop`).
  - Always start the backend with `--loop asyncio:SelectorEventLoop`.
  - In standalone async Python scripts, call `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` before `asyncio.run()`.
- **Database URL Prefix**: `DATABASE_URL` in `.env` must use the `postgresql+psycopg://` scheme (not `postgresql://`).
- **PowerShell HTTP Calls**: Use `curl.exe` or `Invoke-RestMethod` instead of bare `curl` (which aliases `Invoke-WebRequest` and can hang on interactive prompts).
