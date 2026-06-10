"""Provider credential storage with Fernet encryption.

Replacement for the legacy ``services/model_credential_service.py``. Stores
one document per provider in the ``model_credentials`` collection:

    {
        "provider": "google",              # lowercase provider key
        "api_key_encrypted": "<fernet>",   # encrypted at rest, never returned
        "endpoint": "https://...",         # optional custom endpoint
        "additional_config": {...},
        "is_active": true,
        "created_at": ..., "updated_at": ...
    }

The Fernet key comes from ``settings.CREDENTIAL_ENCRYPTION_KEY``. When unset
and ``DEBUG`` is true, a stable dev key is derived from ``JWT_SECRET`` so
local environments work out of the box (NOT suitable for production — keys
encrypted with the dev key are unreadable once a real key is configured).
"""

from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet

from app.agents.exceptions import ConfigurationError
from app.core.config import get_settings
from app.db.mongo import get_database

logger = logging.getLogger(__name__)

COLLECTION = "model_credentials"


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


def _masked_row(doc: Dict[str, Any], api_key: Optional[str]) -> Dict[str, Any]:
    return {
        "provider": doc["provider"],
        "api_key_masked": mask_api_key(api_key) if api_key else "<undecryptable>",
        "endpoint": doc.get("endpoint"),
        "additional_config": doc.get("additional_config", {}),
        "is_active": doc.get("is_active", True),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


# ── CRUD ─────────────────────────────────────────────────────────────────

async def get_credential(provider: str) -> Optional[Dict[str, Any]]:
    """Get the decrypted credential for a provider (or None).

    Returns ``{"provider", "api_key", "endpoint", "additional_config"}``.
    """
    db = get_database()
    doc = await db[COLLECTION].find_one({"provider": provider.lower(), "is_active": True})
    if not doc:
        return None
    try:
        api_key = _decrypt(doc["api_key_encrypted"])
    except Exception:  # noqa: BLE001 - mirror legacy leniency (InvalidToken et al.)
        logger.warning("Failed to decrypt credential for provider %s", provider)
        return None
    return {
        "provider": doc["provider"],
        "api_key": api_key,
        "endpoint": doc.get("endpoint"),
        "additional_config": doc.get("additional_config", {}),
    }


async def upsert_credential(
    provider: str,
    api_key: str,
    endpoint: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create or update the credential for a provider. Returns a masked row."""
    db = get_database()
    encryption = get_encryption()
    now = datetime.now(timezone.utc)

    encrypted = encryption.encrypt(api_key.encode()).decode()  # store as string

    await db[COLLECTION].update_one(
        {"provider": provider.lower()},
        {
            "$set": {
                "api_key_encrypted": encrypted,
                "endpoint": endpoint,
                "additional_config": extra or {},
                "is_active": True,
                "updated_at": now,
            },
            "$setOnInsert": {"provider": provider.lower(), "created_at": now},
        },
        upsert=True,
    )
    doc = await db[COLLECTION].find_one({"provider": provider.lower()})
    return _masked_row(doc, api_key)


async def list_credentials(active_only: bool = True) -> List[Dict[str, Any]]:
    """List stored credentials with masked keys (never returns plaintext)."""
    db = get_database()
    query: Dict[str, Any] = {"is_active": True} if active_only else {}
    docs = await db[COLLECTION].find(query).sort("provider", 1).to_list(length=None)

    rows: List[Dict[str, Any]] = []
    for doc in docs:
        try:
            api_key: Optional[str] = _decrypt(doc["api_key_encrypted"])
        except Exception:  # noqa: BLE001
            api_key = None
        rows.append(_masked_row(doc, api_key))
    return rows


async def delete_credential(provider: str) -> bool:
    """Delete a credential (soft delete, mirroring the legacy service)."""
    db = get_database()
    result = await db[COLLECTION].update_one(
        {"provider": provider.lower()},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count > 0


async def get_all_credentials_dict() -> Dict[str, Dict[str, Any]]:
    """
    Get all active credentials as a dictionary (for the startup cache).
    Returns: {provider: {"api_key": decrypted_key, "endpoint": endpoint, ...}}

    Port of the legacy ``get_all_credentials_dict`` — credentials that fail
    to decrypt are skipped silently.
    """
    db = get_database()
    docs = await db[COLLECTION].find({"is_active": True}).to_list(length=None)

    result: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        try:
            api_key = _decrypt(doc["api_key_encrypted"])
        except Exception:  # noqa: BLE001 - skip credentials that fail to decrypt
            continue
        result[doc["provider"]] = {
            "api_key": api_key,
            "endpoint": doc.get("endpoint"),
            "additional_config": doc.get("additional_config", {}),
        }
    return result


async def configured_providers() -> List[str]:
    """Provider keys that currently have an active credential (no decryption)."""
    db = get_database()
    return sorted(await db[COLLECTION].distinct("provider", {"is_active": True}))
