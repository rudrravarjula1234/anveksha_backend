"""Small Gemini chat helper for the question-bank subsystem.

The full AutoGen path (app/agents/service.py) needs the model cache + the
orchestration machinery; for the question bank we only need a plain
"prompt in → JSON out" call, so this talks to Gemini's OpenAI-compatible
chat-completions endpoint directly with the stored ``google`` credential —
the same pattern the RAW bot-worker uses, kept server-side here.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.agents.credentials import get_credential

logger = logging.getLogger(__name__)

# Fast, non-thinking flash-lite model for the question bank (generation +
# per-ask next-probe). gemini-3.8-flash reasons before answering and takes
# 90s+ per call — unusable for bulk/realtime; the -lite model replies in
# ~1s. (2.x non-lite is blocked for new users.) Override by passing `model=`.
DEFAULT_TEXT_MODEL = "gemini-flash-lite-latest"
_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


async def complete(
    system: str,
    user: str,
    *,
    model: str = DEFAULT_TEXT_MODEL,
    max_tokens: int = 1200,
    temperature: float = 0.4,
) -> str:
    """One chat completion → raw assistant text."""
    cred = await get_credential("google")
    if not cred or not cred.get("api_key"):
        raise RuntimeError("No active 'google' credential configured for Gemini text.")
    base = (cred.get("endpoint") or _DEFAULT_BASE).rstrip("/")
    # gemini-3.8-flash reasons before answering; a multi-question JSON
    # generation can take well over a minute. Give it room.
    async with httpx.AsyncClient(timeout=200.0) as client:
        resp = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {cred['api_key']}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _extract_json(raw: str) -> Any:
    """Pull the first JSON value out of a model reply — tolerant of
    ```json fences and surrounding prose, mirroring feedback_service."""
    fenced = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        obj = re.search(r"[\[{].*[\]}]", raw, re.DOTALL)
        candidate = obj.group(0) if obj else raw
    return json.loads(candidate)


async def complete_json(
    system: str,
    user: str,
    *,
    model: str = DEFAULT_TEXT_MODEL,
    max_tokens: int = 1500,
    temperature: float = 0.4,
) -> Any:
    """Chat completion whose reply is expected to be JSON; returns the parsed
    value. Raises on unparseable output (callers decide how to degrade)."""
    raw = await complete(system, user, model=model, max_tokens=max_tokens, temperature=temperature)
    return _extract_json(raw)
