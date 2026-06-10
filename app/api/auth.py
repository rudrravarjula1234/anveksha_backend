"""HTTP layer for `/api/auth`.

Contract mirror of `anveksha_ui/src/mocks/handlers/auth.ts`:

    POST /api/auth/google-register  — {google_token, role?} → AuthResponse
    POST /api/auth/dev-login        — {email, role, userId?} → AuthResponse
    POST /api/auth/refresh          — {refresh_token} → AuthResponse
    GET  /api/auth/me               — bearer → User
    POST /api/auth/logout           — → {ok: true}

dev-login and the google-register stub are DEBUG-only (404 in prod so
they don't advertise their existence).
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import Principal, get_current_principal
from app.core.config import get_settings
from app.schemas.user import (
    AuthResponse,
    DevLoginRequest,
    GoogleRegisterRequest,
    RefreshRequest,
    User,
)
from app.services.auth_service import AuthService

router = APIRouter(tags=["Auth"])


def _service() -> AuthService:
    return AuthService()


def _debug_only() -> None:
    if not get_settings().DEBUG:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.post("/dev-login", response_model=AuthResponse)
async def dev_login(
    body: DevLoginRequest,
    service: AuthService = Depends(_service),
) -> AuthResponse:
    _debug_only()
    return await service.dev_login(body.role, body.userId)


@router.post("/google-register", response_model=AuthResponse)
async def google_register(
    body: GoogleRegisterRequest,
    service: AuthService = Depends(_service),
) -> AuthResponse:
    # DEBUG stub today; will gain real Google ID-token verification.
    _debug_only()
    return await service.google_register(body.role or "candidate")


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    body: RefreshRequest,
    service: AuthService = Depends(_service),
) -> AuthResponse:
    return await service.refresh(body.refresh_token)


@router.get("/me", response_model=User)
async def me(
    principal: Principal = Depends(get_current_principal),
    service: AuthService = Depends(_service),
) -> User:
    return await service.me(principal.user_id, principal.email)


@router.post("/logout")
async def logout() -> dict[str, bool]:
    # Dev tokens are stateless; nothing to revoke yet. When JWTs land,
    # this is where the refresh token gets blacklisted.
    return {"ok": True}
