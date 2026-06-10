"""Development-mode bearer tokens.

The frontend issues two historical payload shapes inside
`dev_<base64(json)>` tokens:

1. `{"sub": "<userId>", "role": "<role>", "iat": <ms>}` — what the mock's
   `makeDevToken` produces (anveksha_ui/src/mocks/data/users.ts). This is
   the shape in circulation today.
2. `{"email": "...", "role": "..."}` — the legacy backend's dev format.

We accept both. Refresh tokens are the access token plus a literal
`.refresh` suffix (mock convention), so decoding strips anything after
the first `.`.

Dev tokens are ONLY honoured when `settings.DEBUG` is true.
"""

import base64
import json
import time
from typing import Optional, TypedDict


class DevTokenPayload(TypedDict, total=False):
    sub: str
    email: str
    role: str
    iat: int


def decode_dev_token(token: str) -> Optional[DevTokenPayload]:
    """Return the embedded payload or None if the token is malformed.

    Caller gates on `settings.DEBUG` — this function makes no assumption
    about runtime mode.
    """
    if not token.startswith("dev_"):
        return None
    try:
        # Strip the `.refresh` suffix (or any dot-extension) before decoding.
        encoded = token[4:].split(".")[0]
        padding = "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(encoded + padding).decode("utf-8")
        payload = json.loads(decoded)
        if not isinstance(payload, dict):
            return None
        return payload  # type: ignore[return-value]
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def make_dev_token(user_id: str, role: str) -> str:
    """Mint a token in the same shape the frontend's mock produces.

    Keeping the format identical means tokens are interchangeable between
    the MSW mock and this backend during the migration — a session started
    against one keeps working against the other.
    """
    payload = json.dumps({"sub": user_id, "role": role, "iat": int(time.time() * 1000)})
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return f"dev_{encoded}"
