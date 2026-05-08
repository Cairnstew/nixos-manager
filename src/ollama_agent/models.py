"""
smolagents-compatible model backed by a local Ollama instance.

Uses Ollama's OpenAI-compatible /v1/chat/completions endpoint so that
tool-calling works reliably across model families.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction, MessageRole, Model

logger = logging.getLogger(__name__)


class OllamaModel(Model):
    def __init__(
        self,
        model_id: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
        max_new_tokens: int = 2048,
        timeout: float = 120.0,
    ) -> None:
        super().__init__()
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_new_tokens = max_new_tokens
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def generate(
        self,
        messages: list[dict[str, Any]],
        stop_sequences: list[str] | None = None,
        grammar: Any = None,
        tools_to_call_from: list[Any] | None = None,
        **kwargs: Any,
    ) -> ChatMessage:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_new_tokens,
            "stream": False,
        }

        if stop_sequences:
            payload["stop"] = stop_sequences

        if tools_to_call_from:
            payload["tools"] = self._build_tool_schemas(tools_to_call_from)
            payload["tool_choice"] = "auto"

        payload.update(kwargs)

        logger.debug("OllamaModel → %s", self.model_id)

        response = self._client.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]["message"]
        content: str = choice.get("content") or ""
        tool_calls_raw = choice.get("tool_calls")

        tool_calls = None
        if tool_calls_raw:
            tool_calls = []
            for tc in tool_calls_raw:
                fn = tc["function"]
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_calls.append(
                    ChatMessageToolCall(
                        id=tc.get("id", ""),
                        type="function",
                        function=ChatMessageToolCallFunction(
                            name=fn["name"],
                            arguments=args,
                        ),
                    )
                )

        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content=content,
            tool_calls=tool_calls,
        )

    @staticmethod
    def _build_tool_schemas(tools: list[Any]) -> list[dict[str, Any]]:
        schemas = []
        for tool in tools:
            try:
                inputs = tool.inputs or {}
                properties: dict[str, Any] = {}
                required: list[str] = []
                for name, meta in inputs.items():
                    prop: dict[str, Any] = {"type": meta.get("type", "string")}
                    if "description" in meta:
                        prop["description"] = meta["description"]
                    properties[name] = prop
                    if meta.get("nullable") is not True:
                        required.append(name)

                schemas.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": {
                                "type": "object",
                                "properties": properties,
                                "required": required,
                            },
                        },
                    }
                )
            except AttributeError:
                logger.warning("Skipping tool %r — unexpected schema format", tool)
        return schemas

    def check_connection(self) -> bool:
        try:
            r = self._client.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            base_tag = self.model_id.split(":")[0]
            return any(m.startswith(base_tag) or m == self.model_id for m in models)
        except Exception as exc:
            logger.error("Ollama connection check failed: %s", exc)
            return False

    def list_models(self) -> list[str]:
        r = self._client.get(f"{self.base_url}/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    def __repr__(self) -> str:
        return f"OllamaModel(model_id={self.model_id!r}, base_url={self.base_url!r})"