"""Shared OpenAI client access for advisor structured-output calls."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel

from app.config import get_settings

CACHE_DIR = Path(".cache/llm")


@lru_cache
def get_client() -> OpenAI:
    """Singleton OpenAI client, built from the configured API key."""
    return OpenAI(api_key=get_settings().openai_api_key)


def history_to_messages(system_prompt: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Build a chat-completions message list: system prompt + full history (rule R-2)."""
    return [{"role": "system", "content": system_prompt}] + [
        {"role": turn["role"], "content": turn["content"]} for turn in history
    ]


def _cache_key(
    model: str, temperature: float, messages: list[dict[str, str]], schema_name: str
) -> str:
    payload = json.dumps(
        {"model": model, "temperature": temperature, "messages": messages, "schema": schema_name},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cached_parse[T: BaseModel](
    model: str,
    temperature: float,
    messages: list[dict[str, str]],
    response_format: type[T],
    cache_dir: Path = CACHE_DIR,
) -> T:
    """Structured-output chat completion with a content-addressed disk cache.

    Every LLM decision call in this system goes through here instead of the
    client directly (N-7 cost control, spec §9 "cache LLM responses so it's
    re-runnable and cheap"). A cache key includes the full message list, so
    live conversations naturally get unique keys per turn — this only
    changes behavior for exact-repeat calls (evals, re-runs after a fix).
    """

    key = _cache_key(model, temperature, messages, response_format.__name__)
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists():
        return response_format.model_validate_json(cache_path.read_text(encoding="utf-8"))

    completion = get_client().chat.completions.parse(
        model=model,
        temperature=temperature,
        messages=messages,
        response_format=response_format,
    )
    parsed = completion.choices[0].message.parsed

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(parsed.model_dump_json(), encoding="utf-8")
    return parsed
