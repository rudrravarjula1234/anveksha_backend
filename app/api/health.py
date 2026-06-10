"""Public liveness probe."""

from fastapi import APIRouter

from app import __version__
from app.db.mongo import get_database

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health() -> dict[str, object]:
    """Confirms the process is up *and* Mongo is reachable."""
    try:
        await get_database().command("ping")
        mongo_ok = True
    except Exception:  # noqa: BLE001 — surfaces as degraded health, not a crash
        mongo_ok = False

    return {
        "status": "ok" if mongo_ok else "degraded",
        "service": "anveksha-backend",
        "version": __version__,
        "mongo": "up" if mongo_ok else "down",
    }
