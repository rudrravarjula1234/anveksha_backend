---
name: anveksha-local-stack
description: >-
  Start, verify, and troubleshoot the full Anveksha local stack (anveksha_backend,
  anveksha_ui in real mode, and RAW_App LiveKit/Docker services) on Windows.
  Use when bringing up the stack, checking service health, or resolving port/DB issues.
---

# Anveksha Local Stack Runbook

## Service & Port Map
| Service | Directory | Port | Mode / Notes |
| :--- | :--- | :--- | :--- |
| `anveksha_backend` | `F:\Anveksha\anveksha_backend` | `8000` | FastAPI + Supabase Postgres (`SEED_DATA=False`) |
| `anveksha_ui` | `F:\Anveksha\anveksha_ui` | `5173` | Vite `--mode real` (MSW disabled) |
| `RAW_App` Web | `F:\Anveksha\RAW_App\web` | `5174` | Mapped `5174:5173` in Docker to avoid colliding with `anveksha_ui` |
| `RAW_App` Token Server | `F:\Anveksha\RAW_App\server` | `8080` | Go server (`/healthz`, `/api/token`, `/api/bots/*`) |
| `RAW_App` LiveKit | Docker (`livekit`) | `7880` | WebRTC signaling (`ws://localhost:7880`) |
| `RAW_App` Temporal UI | Docker (`temporal-ui`) | `8088` | Temporal gRPC on `7233` |

## Startup Commands (Windows PowerShell)

1. **Backend (`anveksha_backend`)**:
   ```powershell
   $env:PYTHONPATH="."; .\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --loop asyncio:SelectorEventLoop --reload
   ```
2. **Frontend (`anveksha_ui`)**:
   ```powershell
   cd F:\Anveksha\anveksha_ui; pnpm run dev:real --port 5173
   ```
3. **RAW WebRTC Stack (`RAW_App`)**:
   ```powershell
   cd F:\Anveksha\RAW_App; docker compose up -d
   ```

## Health & Smoke Checks
- Backend + Supabase DB: `curl.exe -s http://localhost:8000/health`
- RAW Token Server: `curl.exe -s http://localhost:8080/healthz`
- UI & RAW Web: `http://localhost:5173/` and `http://localhost:5174/`
- Docker containers: `docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"`
