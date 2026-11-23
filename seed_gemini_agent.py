"""One-off: wire Gemini as the agent-registry LLM.

Inserts/updates an active `ai_models` row (Google/Gemini) + an encrypted
`model_credentials` row (provider key 'google', the key autogen's Gemini
client + runner.run_single_agent look up). After this, report_generator /
gap_analyzer (modelId=None) resolve to Gemini and run for real instead of
falling back. Idempotent. Reads the Gemini key from GEMINI_API_KEY env or
the first arg.
"""
import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.agents.credentials import get_encryption
from app.core.config import get_settings
from app.models.ai_model import AIModel
from app.models.credentials import ModelCredential

GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODEL_ID = "mdl_gemini_flash"
MODEL_NAME = "gemini-2.0-flash"


async def main() -> None:
    key = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("Provide the Gemini API key via arg or GEMINI_API_KEY env.")

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    enc = get_encryption().encrypt(key.encode()).decode()

    async with maker() as db:  # type: AsyncSession
        # ── credential (PK = legacy provider key 'google') ──
        cred = await db.get(ModelCredential, "google")
        if cred is None:
            cred = ModelCredential(provider="google")
            db.add(cred)
        cred.api_key_encrypted = enc
        cred.endpoint = GEMINI_OPENAI_BASE
        cred.is_active = True

        # ── model (provider display 'Google Vertex' -> 'google') ──
        model = await db.get(AIModel, MODEL_ID)
        if model is None:
            model = AIModel(id=MODEL_ID)
            db.add(model)
        model.name = "Gemini 2.0 Flash"
        model.provider = "Google Vertex"
        model.model = MODEL_NAME
        model.endpoint = GEMINI_OPENAI_BASE
        model.status = "active"
        model.context_window = 1000000

        await db.commit()

        # verify what the registry will resolve
        rows = (await db.execute(select(AIModel).where(AIModel.status == "active"))).scalars().all()
        print("active models:", [(r.id, r.provider, r.model) for r in rows])
        print("credential google set:", bool(cred.api_key_encrypted))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
