"""Tests for OllamaConfig."""

import pytest

from ollama_agent.config import AgentType, OllamaConfig


class TestOllamaConfig:
    def test_defaults(self) -> None:
        cfg = OllamaConfig()
        assert cfg.model == "qwen2.5:7b"
        assert cfg.base_url == "http://localhost:11434"
        assert cfg.agent_type == AgentType.CODE
        assert cfg.temperature == 0.0
        assert cfg.max_new_tokens == 2048
        assert cfg.max_steps == 10
        assert cfg.verbose is False
        assert cfg.additional_imports == []

    def test_custom_values(self) -> None:
        cfg = OllamaConfig(model="gemma3:4b", temperature=0.7, max_steps=20,
                           agent_type=AgentType.TOOL_CALLING, verbose=True)
        assert cfg.model == "gemma3:4b"
        assert cfg.temperature == 0.7
        assert cfg.agent_type == AgentType.TOOL_CALLING

    def test_preset_qwen_7b(self) -> None:
        assert OllamaConfig.qwen_7b().model == "qwen2.5:7b"

    def test_preset_gemma_4b(self) -> None:
        assert OllamaConfig.gemma_4b().model == "gemma3:4b"

    def test_preset_llama_8b(self) -> None:
        assert OllamaConfig.llama_8b().model == "llama3.1:8b"

    def test_preset_kwargs_override(self) -> None:
        cfg = OllamaConfig.qwen_7b(temperature=0.5, verbose=True)
        assert cfg.model == "qwen2.5:7b"
        assert cfg.temperature == 0.5

    def test_additional_imports_mutable_default(self) -> None:
        cfg1, cfg2 = OllamaConfig(), OllamaConfig()
        cfg1.additional_imports.append("os")
        assert cfg2.additional_imports == []

    def test_agent_type_enum_values(self) -> None:
        assert AgentType.CODE.value == "code"
        assert AgentType.TOOL_CALLING.value == "tool_calling"