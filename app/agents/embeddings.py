"""Gemini text embeddings for the Graph-RAG question bank.

The agent stack has no embeddings path (GeminiProvider is chat-only), so
this is a small, dedicated helper: it reuses the stored ``google`` provider
credential (the same key the chat bots use) and calls Gemini's
OpenAI-compatible ``/embeddings`` endpoint, requesting 768 dimensions so the
vectors fit a pgvector HNSW index.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.agents.credentials import get_credential
from app.models.question_bank import EMBED_DIM

logger = logging.getLogger(__name__)

EMBED_MODEL = "gemini-embedding-001"
# OpenAI-compatible Gemini base; the stored credential's endpoint already
# points here, but default defensively.
_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


async def _resolve_key_and_base() -> tuple[str, str]:
    cred = await get_credential("google")
    if not cred or not cred.get("api_key"):
        raise RuntimeError("No active 'google' credential configured for embeddings.")
    base = (cred.get("endpoint") or _DEFAULT_BASE).rstrip("/")
    return cred["api_key"], base


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts, returning one ``EMBED_DIM``-length vector each
    (order preserved). Raises on a failed call — callers decide whether to
    degrade; seeding should fail loudly, request-time retrieval should fall
    back to a non-vector path."""
    if not texts:
        return []
    api_key, base = await _resolve_key_and_base()
    url = f"{base}/embeddings"
    payload = {"model": EMBED_MODEL, "input": texts, "dimensions": EMBED_DIM}
    async with httpx.AsyncClient(timeout=30.0) as client:
        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                resp = await client.post(
                    url, json=payload, headers={"Authorization": f"Bearer {api_key}"}
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                # The endpoint returns items with an `index`; sort to be safe.
                ordered = sorted(data, key=lambda d: d.get("index", 0))
                return [item["embedding"] for item in ordered]
            except Exception as exc:  # noqa: BLE001 - retried once, then re-raised
                last_exc = exc
                logger.warning("embed_texts attempt %d failed: %s", attempt + 1, exc)
        raise RuntimeError(f"embed_texts failed after retries: {last_exc}")


async def embed_text(text: str) -> list[float]:
    """Embed a single string."""
    out = await embed_texts([text])
    return out[0]
