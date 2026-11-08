"""Identifier generation. ULIDs (26-char, lexicographically sortable by
creation time) prefixed with a short domain tag (`mdl_`, `bot_`, ...) so
references are self-describing in logs and the UI.
"""

from ulid import ULID


def _new_ulid() -> str:
    return str(ULID())


def model_id() -> str:
    return f"mdl_{_new_ulid()}"


def bot_id() -> str:
    return f"bot_{_new_ulid()}"


def token_usage_id() -> str:
    return f"tok_{_new_ulid()}"
