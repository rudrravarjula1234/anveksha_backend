"""Base Pydantic configuration shared by every schema.

The frontend's mock contracts use camelCase field names verbatim. We
preserve that on the wire — the JSON shape Python emits matches what
the TypeScript types expect, byte-for-byte. We do NOT use `alias_generator`
because the canonical field names *are* camelCase here; aliases would add
indirection without benefit.
"""

from pydantic import BaseModel, ConfigDict


class AppModel(BaseModel):
    """Base for every request/response model.

    - `extra='forbid'` rejects unknown fields on write paths so typos
      surface immediately (the read models override this if they need
      to be lenient with legacy data).
    - `str_strip_whitespace` cleans up incidental padding from the UI.
    - `populate_by_name=True` allows constructing from either alias or
      field name (handy for tests).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class ReadModel(AppModel):
    """Variant for response models — tolerates extra fields from older
    documents in the DB (forward-compatible reads, strict writes)."""

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        populate_by_name=True,
    )
