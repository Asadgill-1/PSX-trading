"""LLM adapter: real Anthropic API or deterministic mock (no key = mock mode).

Each call is a FRESH context — no shared conversation between roles (spec §3:
a fresh-context reviewer outperforms self-critique).
"""
import json
import logging
import re

from .. import config
from . import mock

log = logging.getLogger("agents.llm")

# Cheap model scans wide; stronger model debates and judges.
SCOUT_MODEL = "claude-haiku-4-5-20251001"
DEBATE_MODEL = "claude-sonnet-5"

_client = None


def _anthropic():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def complete_json(role: str, system: str, user: str, model: str) -> dict | list:
    """One fresh-context call, JSON-only reply parsed. role is 'scout'|'devil'|'judge'."""
    if config.MOCK_AGENTS:
        return mock.respond(role, user)
    resp = _anthropic().messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return _parse_json(text, role)


def _parse_json(text: str, role: str) -> dict | list:
    """Boundary validation: models sometimes wrap JSON in prose/fences."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError(f"{role} reply contained no JSON: {text[:200]!r}")
    return json.loads(text[start:text.rfind("}") + 1 if text[start] == "{" else text.rfind("]") + 1])
