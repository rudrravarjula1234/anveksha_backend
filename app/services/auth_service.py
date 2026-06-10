"""Authentication flows.

DEBUG-mode flows mirror the frontend mock exactly so the migration is
transparent:

- dev-login: look up the seeded persona (by explicit userId, else by
  role) and mint a `dev_` token pair.
- refresh: accept any token ending in `.refresh`, re-issue for the same
  user (decoded from the embedded payload).
- google-register: stub — resolves to the seeded persona for the
  requested role. Real Google ID-token verification lands when we leave
  DEBUG-only auth.
"""

from datetime import datetime, timezone
from typing import Optional

from app.auth.dev_tokens import decode_dev_token, make_dev_token
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.db.mongo import get_database
from app.schemas.user import AuthResponse, User, UserRole


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuthService:
    def _users(self):
        return get_database()["users"]

    # ── Lookups ─────────────────────────────────────────────────────────

    async def _user_by_id(self, user_id: str) -> Optional[dict]:
        return await self._users().find_one({"id": user_id})

    async def _default_user_for_role(self, role: UserRole) -> Optional[dict]:
        """The persona the dev-login button for `role` should land on.

        Sorted by `id` for determinism — the seed ids are stable
        (usr_cand_001 etc.) so this matches the frontend's keyed lookup.
        Specialist (usr_spec_001) intentionally never wins a role-based
        lookup because Maya (usr_ver_001) sorts after... actually `usr_spec`
        sorts before `usr_ver`, so we exclude the specialist explicitly:
        she is only reachable via explicit userId, same as the frontend.
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

    async def google_register(self, role: UserRole) -> AuthResponse:
        """DEBUG stub — resolves to the seeded persona for the role.

        Production implementation will verify the Google ID token, then
        find-or-create the user. The response contract stays identical.
        """
        return await self.dev_login(role)

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
