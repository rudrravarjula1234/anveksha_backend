"""FastAPI dependencies for authentication & authorisation.

`get_current_principal` extracts the caller's identity from the bearer
token. In DEBUG mode it accepts the frontend's dev tokens (both the
`{sub, role}` and legacy `{email, role}` payload shapes) and enriches
the principal from the seeded users collection when a matching user
exists — DB roles are more authoritative than the single role baked
into the token.

`require_roles(...)` returns a dependency that 403s unless the caller
has at least one of the listed roles.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from app.auth.dev_tokens import decode_dev_token
from app.core.config import get_settings
from app.db.mongo import get_database

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller — lightweight value object.

    Distinct from a User document. A Principal represents *who is making
    this request*; the linked user document (when one exists) rides along
    in `user_doc` for handlers that need profile fields.
    """

    email: str
    roles: list[str] = field(default_factory=list)
    user_id: Optional[str] = None
    user_doc: Optional[dict] = None  # raw users-collection document, if resolved

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


async def _resolve_user(sub: Optional[str], email: Optional[str]) -> Optional[dict]:
    """Look up the user document by id first, then email. Best-effort —
    returns None rather than raising so unseeded principals still work."""
    try:
        db = get_database()
    except RuntimeError:
        return None
    users = db["users"]
    if sub:
        doc = await users.find_one({"id": sub})
        if doc:
            return doc
    if email:
        doc = await users.find_one({"email": email})
        if doc:
            return doc
    return None


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
        if not payload or ("sub" not in payload and "email" not in payload):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid dev token",
            )

        sub = payload.get("sub")
        email = payload.get("email")
        raw_role = payload.get("role")
        token_roles = [raw_role] if isinstance(raw_role, str) else list(raw_role or [])

        user_doc = await _resolve_user(sub, email)
        if user_doc is not None:
            if not user_doc.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account deactivated",
                )
            return Principal(
                email=user_doc["email"],
                roles=list(user_doc.get("roles", token_roles)),
                user_id=user_doc["id"],
                user_doc=user_doc,
            )

        # No seeded user — trust the token contents (pure-dev scenario).
        return Principal(email=email or "", roles=token_roles, user_id=sub)

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
