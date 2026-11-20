"""One-off: wire the Gemini (Google AI Studio) key into the backend agent stack.

- Point the active Gemini ai_models row at an available model + the Gemini
  OpenAI-compatible base_url (so autogen's OpenAIChatCompletionClient talks
  to Gemini, not api.openai.com).
- Store the API key as the `google` provider credential (encrypted at rest).

Run: .\.venv\Scripts\python.exe wire_gemini.py
"""

import asyncio
import os
import re
import selectors
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
TARGET_MODEL = "gemini-2.5-flash"  # confirmed available for this key


def _read_key() -> str:
    env_path = r"F:\Anveksha\RAW_App\.env"
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^GEMINI_API_KEY=(.+)$", line.strip())
            if m:
                return m.group(1).strip()
    raise SystemExit("GEMINI_API_KEY not found in RAW_App/.env")


async def main() -> None:
    os.environ.setdefault("PYTHONPATH", ".")
    from sqlalchemy import select

    from app.agents import credentials as credential_store
    from app.db.session import close_db, connect_to_db, get_sessionmaker
    from app.models.ai_model import AIModel

    key = _read_key()

    await connect_to_db()
    try:
        await _run(get_sessionmaker, credential_store, AIModel, key)
    finally:
        await close_db()


async def _run(get_sessionmaker, credential_store, AIModel, key) -> None:
    from sqlalchemy import select

    async with get_sessionmaker()() as db:
        rows = (await db.execute(select(AIModel))).scalars().all()
        print("Current ai_models:")
        for r in rows:
            print(f"  {r.id}  provider={r.provider!r}  model={r.model!r}  status={r.status}  endpoint={r.endpoint!r}")

        # Pick the Google/Gemini flash row (fall back to first google row).
        target = None
        for r in rows:
            if r.provider == "Google Vertex" and "flash" in r.model.lower():
                target = r
                break
        if target is None:
            for r in rows:
                if r.provider == "Google Vertex":
                    target = r
                    break
        if target is None:
            raise SystemExit("No 'Google Vertex' model row to repoint.")

        target.model = TARGET_MODEL
        target.endpoint = GEMINI_OPENAI_BASE
        target.status = "active"
        await db.flush()
        print(f"\nRepointed {target.id} -> model={target.model!r} endpoint={target.endpoint!r} status=active")

        # Credential keyed by the factory's provider string for Google Vertex
        # == 'google' (PROVIDER_MAP). upsert_credential lowercases it anyway.
        masked = await credential_store.upsert_credential(
            provider="google", api_key=key, endpoint=GEMINI_OPENAI_BASE, db=db,
        )
        await db.commit()
        print(f"Stored credential: provider=google  key={masked.get('api_key_masked') or masked.get('api_key')}  endpoint={GEMINI_OPENAI_BASE}")


if __name__ == "__main__":
    asyncio.run(main())
