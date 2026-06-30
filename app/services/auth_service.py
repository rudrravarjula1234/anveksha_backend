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
from ulid import ULID

from app.auth.dev_tokens import decode_dev_token, make_dev_token
from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.db.mongo import get_database
from app.schemas.user import AuthResponse, User, UserRole

log = logging.getLogger(__name__)

_GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    def _users(self):
        return get_database()["users"]

    # ── Lookups ─────────────────────────────────────────────────────────

    async def _user_by_id(self, user_id: str) -> Optional[dict]:
        return await self._users().find_one({"id": user_id})

    async def _default_user_for_role(self, role: UserRole) -> Optional[dict]:
        """The persona the dev-login button for `role` should land on.

        Deterministic: results are sorted by stable seed `id` (usr_cand_001,
        etc.) to match the frontend's keyed lookup. The specialist
        (usr_spec_001) is excluded from role-based resolution — she is only
        reachable via an explicit userId, same as the frontend.
        """
        cursor = self._users().find({"roles": role})
        candidates = await cursor.to_list(length=50)
        non_specialist = [u for u in candidates if u.get("id") != "usr_spec_001"]
        pool = non_specialist or candidates
        if not pool:
            return None
        # Prefer the persona whose PRIMARY (first) role matches, e.g. for
        # role='interviewer' prefer Maya over a candidate-first overlap.
        exact = [u for u in pool if u.get("roles", [None])[-1] == role or u.get("roles", [None])[0] == role]
        chosen = sorted(exact or pool, key=lambda u: u.get("id", ""))
        return chosen[0]

    # ── Token issuance ──────────────────────────────────────────────────

    def _issue(self, user_doc: dict, role: UserRole) -> AuthResponse:
        access = make_dev_token(user_doc["id"], role)
        return AuthResponse(
            user=User.model_validate({k: v for k, v in user_doc.items() if k != "_id"}),
            access_token=access,
            refresh_token=access + ".refresh",
            token_type="bearer",
        )

    async def _touch_last_login(self, user_id: str) -> None:
        await self._users().find_one_and_update(
            {"id": user_id},
            {"$set": {"last_login": _now_iso(), "updated_at": _now_iso()}},
        )

    # ── Flows ───────────────────────────────────────────────────────────

    async def dev_login(self, role: UserRole, user_id: Optional[str] = None) -> AuthResponse:
        if user_id:
            doc = await self._user_by_id(user_id)
            if doc is None:
                raise NotFoundError(f"User {user_id} not found")
        else:
            doc = await self._default_user_for_role(role)
            if doc is None:
                raise NotFoundError(f"No seeded user with role {role}")

        if not doc.get("is_active", True):
            raise ForbiddenError("Account deactivated")

        await self._touch_last_login(doc["id"])
        # Re-read so the response reflects the bumped last_login.
        doc = await self._user_by_id(doc["id"]) or doc
        return self._issue(doc, role)

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

        doc = await self._users().find_one({"email": email})
        if doc is None:
            doc = await self._register_from_google(email, claims)
        elif not doc.get("is_active", True):
            raise ForbiddenError("Account deactivated")

        # The user's primary role wins over the request hint — a seeded
        # admin email must land on the admin portal.
        effective_role: UserRole = (doc.get("roles") or [role])[0]
        await self._touch_last_login(doc["id"])
        doc = await self._user_by_id(doc["id"]) or doc
        log.info("Google sign-in: %s as %s", email, effective_role)
        return self._issue(doc, effective_role)

    async def _register_from_google(self, email: str, claims: dict[str, Any]) -> dict:
        """First-time Google login — create the user from token claims."""
        first = claims.get("given_name") or email.split("@")[0]
        last = claims.get("family_name") or ""
        doc = {
            "id": f"usr_g_{ULID()}",
            "email": email,
            "first_name": first,
            "last_name": last,
            "user_name": email.split("@")[0],
            # Self-registration is always candidate — privileged roles are
            # granted by an admin (or the seed list), never self-asserted.
            "roles": ["candidate"],
            "is_active": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "last_login": None,
        }
        await self._users().insert_one(doc)
        log.info("Registered new Google user %s (%s)", email, doc["id"])
        return doc

    async def refresh(self, refresh_token: str) -> AuthResponse:
        if not refresh_token.endswith(".refresh"):
            raise UnauthorizedError("invalid refresh token")
        payload = decode_dev_token(refresh_token)
        if not payload or "sub" not in payload:
            raise UnauthorizedError("invalid refresh token")
        doc = await self._user_by_id(payload["sub"])
        if doc is None:
            raise UnauthorizedError("unknown user")
        role = payload.get("role") or (doc.get("roles") or ["candidate"])[0]
        return self._issue(doc, role)  # type: ignore[arg-type]

    async def me(self, user_id: Optional[str], email: Optional[str]) -> User:
        doc = None
        if user_id:
            doc = await self._user_by_id(user_id)
        if doc is None and email:
            doc = await self._users().find_one({"email": email})
        if doc is None:
            raise UnauthorizedError("unauthorized")
        return User.model_validate({k: v for k, v in doc.items() if k != "_id"})
