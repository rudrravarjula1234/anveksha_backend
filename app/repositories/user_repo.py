"""Repository for users (Postgres). Extends the generic base with the
domain-specific queries auth needs — email lookup, role-filtered lookup,
and role-list replacement (a child-table operation the generic
`update_by_id` can't express)."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.user import User, UserRole
from app.repositories.sql_base import SqlRepository


class UserRepository(SqlRepository[User]):
    model = User

    # Single-user lookups run on every authenticated request, so roles are
    # JOINed into the same round trip instead of the relationship's default
    # selectin (a second query). List queries keep selectin, which batches
    # all users' roles into one IN (...) query rather than widening rows.

    async def find_by_id(self, item_id: str) -> Optional[User]:
        # db.get() still answers from the identity map when the row is
        # already loaded in this session.
        return await self.db.get(User, item_id, options=[joinedload(User.roles)])

    async def find_by_email(self, email: str) -> Optional[User]:
        # Emails are stored lower-case (ck_users_email_lowercase).
        stmt = select(User).options(joinedload(User.roles)).where(User.email == email.lower())
        result = await self.db.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def list_by_role(self, role: str) -> list[User]:
        stmt = select(User).join(UserRole).where(UserRole.role == role).order_by(User.id)
        result = await self.db.execute(stmt)
        return list(result.scalars().unique().all())

    async def insert_with_roles(self, *, roles: list[str], **fields) -> User:
        if isinstance(fields.get("email"), str):
            fields["email"] = fields["email"].lower()
        user = User(**fields)
        user.roles = [UserRole(role=r, position=i) for i, r in enumerate(roles)]
        self.db.add(user)
        await self.db.flush()
        # Full refresh (not just `roles`) — `created_at`/`updated_at` are
        # server_default-computed and would otherwise stay expired, same
        # MissingGreenlet risk as touch_last_login below.
        await self.db.refresh(user)
        return user

    async def set_roles(self, user_id: str, roles: list[str]) -> Optional[User]:
        """Replace a user's full role list (order preserved).

        Deletes the old rows and flushes BEFORE adding the new ones,
        rather than reassigning `user.roles` in one shot — the new list
        can collide with the old one on the (user_id, role) unique
        constraint (e.g. keeping "candidate" while adding "interviewer"),
        and SQLAlchemy's unit-of-work doesn't guarantee the orphaned
        DELETE is flushed before the new INSERT when they're distinct
        Python objects colliding only on a secondary constraint, not the
        primary key — that ordering has to be forced explicitly.
        """
        user = await self.find_by_id(user_id)
        if user is None:
            return None
        for old_role in list(user.roles):
            await self.db.delete(old_role)
        await self.db.flush()
        user.roles = [UserRole(role=r, position=i) for i, r in enumerate(roles)]
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def touch_last_login(self, user_id: str, when) -> Optional[User]:
        user = await self.find_by_id(user_id)
        if user is None:
            return None
        user.last_login = when
        await self.db.flush()
        # `updated_at` has onupdate=func.now() — the flush above changes
        # it server-side, expiring the Python-side value. Refresh here
        # (still inside the async context) rather than letting callers
        # trigger an implicit lazy-load later, which fails outside the
        # SQLAlchemy async greenlet bridge (MissingGreenlet).
        await self.db.refresh(user)
        return user
