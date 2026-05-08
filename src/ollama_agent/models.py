"""
OllamaModel: thin wrapper around smolagents' OpenAIModel pointed at a local Ollama server.

Ollama exposes a fully OpenAI-compatible /v1/chat/completions endpoint, so
we don't need a custom implementation — just configure the base URL correctly.
"""

from __future__ import annotations

import logging

import httpx
from smolagents.models import OpenAIModel

logger = logging.getLogger(__name__)


def OllamaModel(
    model_id: str = "qwen2.5-coder:7b",
    base_url: str = "http://localhost:11434",
    temperature: float = 0.0,
    max_new_tokens: int = 2048,
    timeout: float = 120.0,
) -> OpenAIModel:
    """Return a smolagents OpenAIModel configured for a local Ollama server.

    Args:
        model_id: Ollama model tag, e.g. ``"qwen2.5-coder:7b"``, ``"gemma3:4b"``.
        base_url: Ollama server base URL.
        temperature: Sampling temperature.
        max_new_tokens: Maximum tokens to generate.
        timeout: HTTP timeout in seconds.

    Returns:
        A configured :class:`~smolagents.models.OpenAIModel` instance.
    """
    return OpenAIModel(
        model_id=model_id,
        api_base=f"{base_url.rstrip('/')}/v1",
        api_key="ollama",          # Ollama ignores the key but openai client requires a non-empty value
        temperature=temperature,
        max_tokens=max_new_tokens,
        timeout=timeout,
    )


def check_connection(
    model_id: str = "qwen2.5-coder:7b",
    base_url: str = "http://localhost:11434",
    timeout: float = 5.0,
) -> bool:
    """Ping the Ollama server and verify the model is available."""
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        base_tag = model_id.split(":")[0]
        return any(m.startswith(base_tag) or m == model_id for m in models)
    except Exception as exc:
        logger.error("Ollama connection check failed: %s", exc)
        return False


def list_models(
    base_url: str = "http://localhost:11434",
    timeout: float = 5.0,
) -> list[str]:
    """Return all model tags available on the Ollama server."""
    r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]