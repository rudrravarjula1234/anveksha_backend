"""Identifier generation.

Uses ULIDs everywhere: 26-char Crockford-base32 strings that are
lexicographically sortable by creation time. Convenient for Mongo
because they monotonically increase, keeping the natural id index
in append-only insertion order.

We prefix each id with a short collection tag (`mdl_`, `bot_`) to make
references self-describing in logs and the UI.
"""

from ulid import ULID


def _new_ulid() -> str:
    return str(ULID())


def model_id() -> str:
    return f"mdl_{_new_ulid()}"


def bot_id() -> str:
    return f"bot_{_new_ulid()}"
