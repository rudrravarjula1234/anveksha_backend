"""FastAPI dependencies for authentication & authorisation.

`get_current_principal` extracts the caller's identity from the bearer
token; it accepts dev tokens in DEBUG mode (matching the frontend mock)
and is structured so JWTs can drop in alongside without rewriting call
sites.

`require_roles(...)` returns a dependency factory that 403s unless the
caller has at least one of the listed roles.
"""

from dataclasses import dataclass, field
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from app.auth.dev_tokens import decode_dev_token
from app.core.config import get_settings


@dataclass(frozen=True)
class Principal:
    """The authenticated caller — lightweight value object.

    Distinct from a User document. A Principal represents *who is making
    this request*; whether that maps to a persisted User row is a concern
    for the relevant service layer. For dev-tokens we mint a Principal
    with no DB lookup.
    """

    email: str
    roles: list[str] = field(default_factory=list)
    user_id: Optional[str] = None  # provided by token; not necessarily a Mongo _id

    def has_role(self, role: str) -> bool:
        return role in self.roles


# ── Token extraction ────────────────────────────────────────────────────

def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1]


# ── Dependencies ────────────────────────────────────────────────────────

async def get_current_principal(
    authorization: Optional[str] = Header(default=None),
) -> Principal:
    """Resolve the caller. Raises 401 if no valid token is present."""
    token = _extract_bearer(authorization)
    settings = get_settings()

    # Dev token path — frontend mock contract.
    if settings.DEBUG and token.startswith("dev_"):
        payload = decode_dev_token(token)
        if not payload or "email" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid dev token",
            )
        # role can be a single string in the legacy token or a list.
        raw_role = payload.get("role")
        roles = [raw_role] if isinstance(raw_role, str) else list(raw_role or [])
        return Principal(
            email=payload["email"],
            roles=roles,
            user_id=payload.get("userId"),
        )

    # Future: validate a real JWT here, then look up the User by sub/email.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unsupported token type",
    )


def require_roles(*allowed_roles: str):
    """Dependency factory that enforces role membership.

    Usage:
        @router.get("/admin/...", dependencies=[Depends(require_roles("admin"))])
    """

    async def _enforce(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not any(principal.has_role(r) for r in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(allowed_roles)}",
            )
        return principal

    return _enforce
