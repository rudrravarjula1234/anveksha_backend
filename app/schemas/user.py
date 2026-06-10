"""User + auth schemas.

Mirrors `anveksha_ui/src/types/auth.ts` field-for-field. The frontend
stores these snake_case fields verbatim, so unlike the admin contracts
(camelCase) this module is snake_case on the wire.
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel

UserRole = Literal["candidate", "company", "interviewer", "hr", "admin"]


class User(ReadModel):
    id: str
    email: str
    first_name: str
    last_name: str
    user_name: str
    roles: list[UserRole] = Field(default_factory=list)
    phone: Optional[str] = None
    is_active: bool = True
    created_at: str
    updated_at: str
    last_login: Optional[str] = None
    picture: Optional[str] = None


class AuthResponse(ReadModel):
    user: User
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class GoogleRegisterRequest(AppModel):
    google_token: str
    role: Optional[UserRole] = None


class DevLoginRequest(AppModel):
    email: str
    role: UserRole
    # Optional explicit persona — the login page uses this to pick e.g.
    # the specialist over the default freelance interviewer.
    userId: Optional[str] = None


class RefreshRequest(AppModel):
    refresh_token: str
