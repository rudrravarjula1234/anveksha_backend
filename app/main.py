"""FastAPI application factory + lifespan.

The app is built by `create_app()` rather than at module import time so
tests can construct a fresh instance with overridden dependencies.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import auth, candidate, catalog, health, portal, skills, verifier
from app.api.admin import assessments as admin_assessments
from app.api.admin import bots as admin_bots
from app.api.admin import coupons as admin_coupons
from app.api.admin import models as admin_models
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.db.indexes import ensure_indexes
from app.db.mongo import close_mongo, connect_to_mongo
from app.db.seed import run_seeds
from app.middleware.access_log import AccessLogMiddleware
from app.middleware.request_id import RequestIDMiddleware

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    log.info("Starting %s v%s (DEBUG=%s)", settings.PROJECT_NAME, __version__, settings.DEBUG)
    await connect_to_mongo()
    await ensure_indexes()
    await run_seeds()
    try:
        yield
    finally:
        await close_mongo()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Anveksha Backend",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # ── Middleware (innermost → outermost order) ─────────────────────────
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # ── Exception handlers ───────────────────────────────────────────────
    @app.exception_handler(AppError)
    async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.error_code, **exc.extra},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed", "code": "validation_error", "errors": exc.errors()},
        )

    # ── Routes ───────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(skills.router, prefix="/api/skills")
    app.include_router(catalog.router, prefix="/api/catalog")
    app.include_router(verifier.router, prefix="/api/verifier")
    # Candidate router spans /api/candidate, /api/notifications and
    # /api/profiles — paths are fully qualified inside, so mount at /api.
    app.include_router(candidate.router, prefix="/api")
    # Portal router spans /api/privacy, /api/dossier and /api/interviews.
    app.include_router(portal.router, prefix="/api")
    app.include_router(admin_models.router, prefix="/api/admin/models")
    app.include_router(admin_bots.router, prefix="/api/admin/bots")
    app.include_router(admin_assessments.router_full, prefix="/api/admin/assessments-full")
    app.include_router(admin_assessments.router_slim, prefix="/api/admin/assessments")
    app.include_router(admin_coupons.router, prefix="/api/admin/coupons")

    return app


app = create_app()
