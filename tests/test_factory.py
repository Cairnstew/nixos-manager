"""Tests for create_agent factory."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from smolagents import CodeAgent, Tool, ToolCallingAgent

from ollama_agent.agents.factory import create_agent
from ollama_agent.config import AgentType, OllamaConfig


def _patch_model():
    return patch("ollama_agent.agents.factory.OllamaModel", autospec=True)


class TestCreateAgent:
    def test_returns_code_agent_by_default(self) -> None:
        with _patch_model():
            assert isinstance(create_agent(OllamaConfig(agent_type=AgentType.CODE)), CodeAgent)

    def test_returns_tool_calling_agent(self) -> None:
        with _patch_model():
            assert isinstance(create_agent(OllamaConfig(agent_type=AgentType.TOOL_CALLING)), ToolCallingAgent)

    def test_default_tools_populated(self) -> None:
        with _patch_model():
            agent = create_agent(OllamaConfig())
        names = [t.name for t in agent.tools.values()]
        assert "calculator" in names
        assert "datetime" in names

    def test_explicit_tools_override_defaults(self) -> None:
        from ollama_agent.tools import CalculatorTool
        with _patch_model():
            agent = create_agent(OllamaConfig(), tools=[CalculatorTool()])
        names = [t.name for t in agent.tools.values()]
        assert "calculator" in names
        assert "datetime" not in names

    def test_extra_tools_appended(self) -> None:
        class FakeShellTool(Tool):
            name = "shell"
            description = "Run shell"
            inputs: dict = {}
            output_type = "string"
            def forward(self) -> str:
                return ""

        with _patch_model():
            agent = create_agent(OllamaConfig(), extra_tools=[FakeShellTool()])
        names = [t.name for t in agent.tools.values()]
        assert "calculator" in names
        assert "shell" in names

    def test_none_config_uses_defaults(self) -> None:
        with _patch_model():
            assert isinstance(create_agent(None), CodeAgent)

    def test_model_created_with_correct_params(self) -> None:
        with _patch_model() as mock_cls:
            create_agent(OllamaConfig(model="gemma3:4b", temperature=0.5, timeout=60.0))
        kw = mock_cls.call_args.kwargs
        assert kw["model_id"] == "gemma3:4b"
        assert kw["temperature"] == 0.5

    def test_additional_imports_passed_to_code_agent(self) -> None:
        cfg = OllamaConfig(agent_type=AgentType.CODE, additional_imports=["pandas", "numpy"])
        with _patch_model():
            agent = create_agent(cfg)
        assert "pandas" in agent.additional_authorized_imports