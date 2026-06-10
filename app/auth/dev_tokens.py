"""Development-mode bearer tokens.

The frontend's mock auth flow (anveksha_ui/src/mocks/data/users.ts) issues
self-describing dev tokens of the shape `dev_<base64(json)>` where the
JSON payload is `{"email": "...", "role": "..."}`. This matches the
existing FastAPI backend's contract so the frontend's MSW passthrough
works without any client-side changes.

Dev tokens are ONLY accepted when `settings.DEBUG` is true. In production
the auth dependency falls through to JWT.
"""

import base64
import json
from typing import Optional, TypedDict


class DevTokenPayload(TypedDict, total=False):
    email: str
    role: str
    userId: str


def decode_dev_token(token: str) -> Optional[DevTokenPayload]:
    """Return the embedded payload or None if the token is malformed.

    Caller is expected to gate on `settings.DEBUG` — this function makes
    no assumption about the runtime mode.
    """
    if not token.startswith("dev_"):
        return None
    try:
        encoded = token[4:]
        # Base64 decoding is forgiving — pad if needed.
        padding = "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(encoded + padding).decode("utf-8")
        payload = json.loads(decoded)
        if not isinstance(payload, dict):
            return None
        return payload  # type: ignore[return-value]
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
