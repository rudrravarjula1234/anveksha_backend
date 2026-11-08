"""Public liveness probe."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.db.session import get_session

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """Confirms the process is up *and* Postgres is reachable."""
    try:
        await db.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # noqa: BLE001 — surfaces as degraded health, not a crash
        database_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "service": "anveksha-backend",
        "version": __version__,
        "database": "up" if database_ok else "down",
    }
