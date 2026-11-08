"""Shared test helpers."""

import base64
import json


def hdr(sub: str, role: str) -> dict[str, str]:
    """Authorization header carrying a dev token for `sub` acting as `role`."""
    raw = json.dumps({"sub": sub, "role": role, "iat": 1700000000000})
    return {"Authorization": "Bearer dev_" + base64.b64encode(raw.encode()).decode()}
