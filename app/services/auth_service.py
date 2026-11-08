"""Authentication flows.

- google-register: when GOOGLE_CLIENT_ID is configured, verifies the
  real Google ID token (signature/expiry via Google's tokeninfo,
  audience + email_verified enforced here), then finds the user by
  email — or creates a new candidate on first login. Falls back to the
  DEBUG stub when no client id is configured.
- dev-login: look up the seeded persona (by explicit userId, else by
  role) and mint a `dev_` token pair. DEBUG only.
- refresh: accept any token ending in `.refresh`, re-issue for the same
  user (decoded from the embedded payload).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.auth.dev_tokens import decode_dev_token, make_dev_token
from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.timefmt import to_wire, to_wire_opt
from app.models.user import User as UserModel
from app.repositories.user_repo import UserRepository
from app.schemas.user import AuthResponse, User, UserRole

log = logging.getLogger(__name__)

_GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_schema(row: UserModel) -> User:
    return User(
        id=row.id,
        email=row.email,
        first_name=row.first_name,
        last_name=row.last_name,
        user_name=row.user_name,
        roles=[r.role for r in row.roles],  # already ordered — see UserRole.position
        phone=row.phone,
        is_active=row.is_active,
        created_at=to_wire(row.created_at),
        updated_at=to_wire(row.updated_at),
        last_login=to_wire_opt(row.last_login),
        picture=row.picture,
    )


async def verify_google_id_token(id_token: str, audience: str) -> dict[str, Any]:
    """Validate a Google ID token and return its claims.

    Google's tokeninfo endpoint checks the signature and expiry
    server-side; we additionally enforce the audience (our OAuth client
    id) and that Google has verified the email. Module-level so tests
    can monkeypatch it without touching the service.

    Raises UnauthorizedError on any validation failure.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_GOOGLE_TOKENINFO_URL, params={"id_token": id_token})
    except httpx.HTTPError as exc:
        log.warning("Google tokeninfo unreachable: %s", exc)
        raise UnauthorizedError("Could not verify Google token") from exc

    if resp.status_code != 200:
        raise UnauthorizedError("Invalid or expired Google token")

    claims = resp.json()
    if claims.get("aud") != audience:
        log.warning("Google token audience mismatch: %s", claims.get("aud"))
        raise UnauthorizedError("Google token was issued for a different app")
    if claims.get("email_verified") not in (True, "true"):
        raise UnauthorizedError("Google account email is not verified")
    if not claims.get("email"):
        raise UnauthorizedError("Google token carries no email")
    return claims


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = UserRepository(db)

    # ── Lookups ─────────────────────────────────────────────────────────

    async def _default_user_for_role(self, role: UserRole) -> Optional[UserModel]:
        """The persona the dev-login button for `role` should land on.

        Deterministic: results are sorted by stable seed `id` (usr_cand_001,
        etc.) to match the frontend's keyed lookup. The specialist
        (usr_spec_001) is excluded from role-based resolution — she is only
        reachable via an explicit userId, same as the frontend.
        """
        candidates = await self.repo.list_by_role(role)
        non_specialist = [u for u in candidates if u.id != "usr_spec_001"]
        pool = non_specialist or candidates
        if not pool:
            return None
        # Prefer the persona whose PRIMARY (first) role matches, e.g. for
        # role='interviewer' prefer Maya over a candidate-first overlap.
        exact = [u for u in pool if self._role_at(u, -1) == role or self._role_at(u, 0) == role]
        chosen = sorted(exact or pool, key=lambda u: u.id)
        return chosen[0]

    @staticmethod
    def _role_at(user: UserModel, index: int) -> Optional[str]:
        roles = [r.role for r in user.roles]
        return roles[index] if roles else None

    # ── Token issuance ──────────────────────────────────────────────────

    def _issue(self, user_row: UserModel, role: UserRole) -> AuthResponse:
        access = make_dev_token(user_row.id, role)
        return AuthResponse(
            user=_to_schema(user_row),
            access_token=access,
            refresh_token=access + ".refresh",
            token_type="bearer",
        )

    # ── Flows ───────────────────────────────────────────────────────────

    async def dev_login(self, role: UserRole, user_id: Optional[str] = None) -> AuthResponse:
        if user_id:
            row = await self.repo.find_by_id(user_id)
            if row is None:
                raise NotFoundError(f"User {user_id} not found")
        else:
            row = await self._default_user_for_role(role)
            if row is None:
                raise NotFoundError(f"No seeded user with role {role}")

        if not row.is_active:
            raise ForbiddenError("Account deactivated")

        row = await self.repo.touch_last_login(row.id, _now()) or row
        return self._issue(row, role)

    async def google_register(self, google_token: str, role: UserRole) -> AuthResponse:
        """Sign in (or register) with a Google ID token.

        With GOOGLE_CLIENT_ID configured: verify the token, then resolve
        the user by the token's email. Seeded users keep their assigned
        roles (e.g. an email seeded as admin logs in as admin regardless
        of the `role` hint). Unknown emails are registered as new
        candidates on first login.

        Without a client id (pure-dev): fall back to the role-based stub
        so the frontend's mock-parity flow keeps working.
        """
        settings = get_settings()
        if not settings.GOOGLE_CLIENT_ID:
            if settings.DEBUG:
                return await self.dev_login(role)
            raise UnauthorizedError("Google sign-in is not configured")

        claims = await verify_google_id_token(google_token, settings.GOOGLE_CLIENT_ID)
        email = claims["email"].lower()

        row = await self.repo.find_by_email(email)
        if row is None:
            row = await self._register_from_google(email, claims)
        elif not row.is_active:
            raise ForbiddenError("Account deactivated")

        # The user's primary role wins over the request hint — a seeded
        # admin email must land on the admin portal.
        roles = [r.role for r in row.roles]
        effective_role: UserRole = roles[0] if roles else role
        row = await self.repo.touch_last_login(row.id, _now()) or row
        log.info("Google sign-in: %s as %s", email, effective_role)
        return self._issue(row, effective_role)

    async def _register_from_google(self, email: str, claims: dict[str, Any]) -> UserModel:
        """First-time Google login — create the user from token claims."""
        first = claims.get("given_name") or email.split("@")[0]
        last = claims.get("family_name") or ""
        return await self.repo.insert_with_roles(
            id=f"usr_g_{ULID()}",
            email=email,
            first_name=first,
            last_name=last,
            user_name=email.split("@")[0],
            # Self-registration is always candidate — privileged roles are
            # granted by an admin (or the seed list), never self-asserted.
            roles=["candidate"],
            is_active=True,
        )

    async def refresh(self, refresh_token: str) -> AuthResponse:
        if not refresh_token.endswith(".refresh"):
            raise UnauthorizedError("invalid refresh token")
        payload = decode_dev_token(refresh_token)
        if not payload or "sub" not in payload:
            raise UnauthorizedError("invalid refresh token")
        row = await self.repo.find_by_id(payload["sub"])
        if row is None:
            raise UnauthorizedError("unknown user")
        roles = [r.role for r in row.roles]
        role = payload.get("role") or (roles[0] if roles else "candidate")
        return self._issue(row, role)  # type: ignore[arg-type]

    async def me(self, user_id: Optional[str], email: Optional[str]) -> User:
        row = None
        if user_id:
            row = await self.repo.find_by_id(user_id)
        if row is None and email:
            row = await self.repo.find_by_email(email)
        if row is None:
            raise UnauthorizedError("unauthorized")
        return _to_schema(row)
