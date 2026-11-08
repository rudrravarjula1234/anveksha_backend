"""Wire format for `timestamptz` columns that the API exposes as strings.

The API contract (and the frontend mocks it mirrors) spells instants as
`2026-05-30T08:14:00.000Z` — UTC, millisecond precision, `Z` suffix.
`to_wire` reproduces that exactly, so a seeded value round-trips through
a real `timestamptz` column byte-identically; `parse_wire` accepts both
that form and Python's `+00:00` isoformat.
"""

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_wire(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_wire_opt(value: Optional[str]) -> Optional[datetime]:
    return parse_wire(value) if value else None


def to_wire(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def to_wire_opt(value: Optional[datetime]) -> Optional[str]:
    return to_wire(value) if value is not None else None
