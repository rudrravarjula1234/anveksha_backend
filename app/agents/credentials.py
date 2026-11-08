"""Provider credential storage with Fernet encryption — one row per
provider in ``model_credentials`` (``app.models.credentials.ModelCredential``).

The Fernet key comes from ``settings.CREDENTIAL_ENCRYPTION_KEY``; when unset
and ``DEBUG`` is true, a stable dev key is derived from ``JWT_SECRET`` (not
suitable for production).

Each function takes an optional ``db: AsyncSession`` — pass the
request-scoped session when called from a route; when omitted (agent
runner, app-startup hook, neither with a request-scoped session), a
short-lived session is opened and committed internally.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.exceptions import ConfigurationError
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models.credentials import ModelCredential

logger = logging.getLogger(__name__)


# ── Encryption helpers ───────────────────────────────────────────────────

def get_encryption_key() -> bytes:
    """Resolve the Fernet key (32 url-safe base64-encoded bytes)."""
    settings = get_settings()
    key = settings.CREDENTIAL_ENCRYPTION_KEY
    if key:
        return key.encode()
    if settings.DEBUG:
        # Stable dev key derived from JWT_SECRET — survives restarts without
        # any extra configuration, but is only acceptable for development.
        digest = hashlib.sha256(
            f"anveksha-dev-credential-key:{settings.JWT_SECRET}".encode()
        ).digest()
        return base64.urlsafe_b64encode(digest)
    raise ConfigurationError(
        "CREDENTIAL_ENCRYPTION_KEY must be set when DEBUG is false "
        "(generate one with: python -c \"from cryptography.fernet import Fernet; "
        'print(Fernet.generate_key().decode())")'
    )


def get_encryption() -> Fernet:
    """Get Fernet encryption instance"""
    return Fernet(get_encryption_key())


def mask_api_key(api_key: str) -> str:
    """Mask a plaintext key for display: keep first/last 4 chars."""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}{'*' * 8}{api_key[-4:]}"


def _decrypt(encrypted: Any) -> str:
    encryption = get_encryption()
    data = encrypted.encode() if isinstance(encrypted, str) else encrypted
    return encryption.decrypt(data).decode()


def _masked_row(row: ModelCredential, api_key: Optional[str]) -> Dict[str, Any]:
    return {
        "provider": row.provider,
        "api_key_masked": mask_api_key(api_key) if api_key else "<undecryptable>",
        "endpoint": row.endpoint,
        "additional_config": row.additional_config or {},
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


# ── CRUD ─────────────────────────────────────────────────────────────────

async def _get_credential(db: AsyncSession, provider: str) -> Optional[Dict[str, Any]]:
    row = await db.get(ModelCredential, provider.lower())
    if row is None or not row.is_active:
        return None
    try:
        api_key = _decrypt(row.api_key_encrypted)
    except Exception:  # noqa: BLE001 - mirror legacy leniency (InvalidToken et al.)
        logger.warning("Failed to decrypt credential for provider %s", provider)
        return None
    return {
        "provider": row.provider,
        "api_key": api_key,
        "endpoint": row.endpoint,
        "additional_config": row.additional_config or {},
    }


async def get_credential(provider: str, db: Optional[AsyncSession] = None) -> Optional[Dict[str, Any]]:
    """Get the decrypted credential for a provider (or None).

    Returns ``{"provider", "api_key", "endpoint", "additional_config"}``.
    """
    if db is not None:
        return await _get_credential(db, provider)
    async with get_sessionmaker()() as session:
        return await _get_credential(session, provider)


async def upsert_credential(
    provider: str,
    api_key: str,
    endpoint: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
    db: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Create or update the credential for a provider. Returns a masked row."""
    encryption = get_encryption()
    encrypted = encryption.encrypt(api_key.encode()).decode()  # store as string
    provider_key = provider.lower()

    async def _apply(session: AsyncSession) -> ModelCredential:
        row = await session.get(ModelCredential, provider_key)
        if row is None:
            row = ModelCredential(provider=provider_key)
            session.add(row)
        row.api_key_encrypted = encrypted
        row.endpoint = endpoint
        row.additional_config = extra or {}
        row.is_active = True
        return row

    if db is not None:
        row = await _apply(db)
        await db.flush()
        await db.refresh(row)
        return _masked_row(row, api_key)
    async with get_sessionmaker()() as session:
        row = await _apply(session)
        await session.commit()
        await session.refresh(row)
        return _masked_row(row, api_key)


async def list_credentials(active_only: bool = True, db: Optional[AsyncSession] = None) -> List[Dict[str, Any]]:
    """List stored credentials with masked keys (never returns plaintext)."""

    async def _list(session: AsyncSession) -> List[Dict[str, Any]]:
        stmt = select(ModelCredential).order_by(ModelCredential.provider)
        if active_only:
            stmt = stmt.where(ModelCredential.is_active.is_(True))
        rows = (await session.execute(stmt)).scalars().all()

        result: List[Dict[str, Any]] = []
        for row in rows:
            try:
                api_key: Optional[str] = _decrypt(row.api_key_encrypted)
            except Exception:  # noqa: BLE001
                api_key = None
            result.append(_masked_row(row, api_key))
        return result

    if db is not None:
        return await _list(db)
    async with get_sessionmaker()() as session:
        return await _list(session)


async def delete_credential(provider: str, db: Optional[AsyncSession] = None) -> bool:
    """Delete a credential (soft delete, mirroring the legacy service)."""

    async def _delete(session: AsyncSession) -> bool:
        row = await session.get(ModelCredential, provider.lower())
        if row is None:
            return False
        row.is_active = False
        return True

    if db is not None:
        deleted = await _delete(db)
        await db.flush()
        return deleted
    async with get_sessionmaker()() as session:
        deleted = await _delete(session)
        await session.commit()
        return deleted


async def get_all_credentials_dict() -> Dict[str, Dict[str, Any]]:
    """
    Get all active credentials as a dictionary (for the startup cache).
    Returns: {provider: {"api_key": decrypted_key, "endpoint": endpoint, ...}}

    Port of the legacy ``get_all_credentials_dict`` — credentials that fail
    to decrypt are skipped silently.
    """
    async with get_sessionmaker()() as db:
        stmt = select(ModelCredential).where(ModelCredential.is_active.is_(True))
        rows = (await db.execute(stmt)).scalars().all()

        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            try:
                api_key = _decrypt(row.api_key_encrypted)
            except Exception:  # noqa: BLE001 - skip credentials that fail to decrypt
                continue
            result[row.provider] = {
                "api_key": api_key,
                "endpoint": row.endpoint,
                "additional_config": row.additional_config or {},
            }
        return result


async def configured_providers(db: Optional[AsyncSession] = None) -> List[str]:
    """Provider keys that currently have an active credential (no decryption)."""
    stmt = (
        select(ModelCredential.provider)
        .where(ModelCredential.is_active.is_(True))
        .order_by(ModelCredential.provider)
    )
    if db is not None:
        return list((await db.execute(stmt)).scalars().all())
    async with get_sessionmaker()() as session:
        return list((await session.execute(stmt)).scalars().all())
