"""Shared pytest fixtures."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ollama_agent.config import AgentType, OllamaConfig
from ollama_agent.models import OllamaModel


@pytest.fixture
def default_config() -> OllamaConfig:
    return OllamaConfig(model="qwen2.5:7b", temperature=0.0, max_steps=5)


@pytest.fixture
def mock_ollama_response() -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "The answer is 42.",
                    "tool_calls": None,
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }


@pytest.fixture
def mock_tags_response() -> dict:
    return {
        "models": [
            {"name": "qwen2.5:7b"},
            {"name": "gemma3:4b"},
            {"name": "llama3.1:8b"},
        ]
    }