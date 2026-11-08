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
from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dev_tokens import decode_dev_token
from app.core.config import get_settings
from app.core.timefmt import to_wire, to_wire_opt
from app.db.session import get_session

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. Distinct from a User row: represents
    *who is making this request*; the linked user (when one exists) rides
    along in `user_doc` (a plain dict, for handlers that need profile
    fields via dict-style access) rather than the ORM row.
    """

    email: str
    roles: list[str] = field(default_factory=list)
    user_id: Optional[str] = None
    user_doc: Optional[dict[str, Any]] = None
    # The loaded ORM row, held only to keep it alive for the request: the
    # session's identity map is weak-referencing, so without a strong ref
    # the row is collected and any later `db.get(User, id)` in the same
    # request (e.g. AuthService.me) re-queries users + user_roles.
    _user_row: Any = field(default=None, repr=False, compare=False)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @property
    def actor_id(self) -> str:
        """Who to record as having done something (reviewer, editor, ...):
        the caller's user id, else their email. Never a stand-in identity:
        an action nobody can be credited with is refused."""
        actor = self.user_id or self.email
        if not actor:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Caller has no identity to record")
        return actor


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


def _user_to_dict(user) -> dict[str, Any]:
    """Match the shape Mongo documents used to have — see Principal's
    docstring for why this dict shape (not the ORM row) is preserved."""
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "user_name": user.user_name,
        "roles": [r.role for r in user.roles],
        "phone": user.phone,
        "is_active": user.is_active,
        "created_at": to_wire(user.created_at),
        "updated_at": to_wire(user.updated_at),
        "last_login": to_wire_opt(user.last_login),
        "picture": user.picture,
    }


async def _resolve_user(
    db: AsyncSession, sub: Optional[str], email: Optional[str]
) -> Optional[Any]:
    """Look up the user by id first, then email. Best-effort — returns
    None rather than raising so unseeded principals still work."""
    from app.repositories.user_repo import UserRepository

    repo = UserRepository(db)
    row = None
    if sub:
        row = await repo.find_by_id(sub)
    if row is None and email:
        row = await repo.find_by_email(email)
    return row


# ── Dependencies ────────────────────────────────────────────────────────

async def get_current_principal(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_session),
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

        user_row = await _resolve_user(db, sub, email)
        if user_row is not None:
            user_doc = _user_to_dict(user_row)
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
                _user_row=user_row,
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
