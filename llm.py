"""Claude structured-output helper."""

from __future__ import annotations

from typing import TypeVar

import anthropic
from pydantic import BaseModel

from .config import CLAUDE_MODEL, PROMPTS_DIR

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


def ask(system: str, user: str, schema: type[T], effort: str = "high") -> T:
    """One Claude call that returns a validated `schema` instance.

    Server-side fallbacks are on so a safety-classifier decline (rare, but possible on
    disaster or crime topics) is retried on a fallback model instead of failing the run.
    """
    response = client().beta.messages.parse(
        model=CLAUDE_MODEL,
        max_tokens=20000,  # about the most a non-streaming call allows; thinking counts too
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined this request: {response.stop_details}")
    if response.parsed_output is None:
        raise RuntimeError(f"No structured output (stop_reason={response.stop_reason})")
    return response.parsed_output
