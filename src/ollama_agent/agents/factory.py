"""Factory helpers for building smolagents agents backed by Ollama."""

from __future__ import annotations

import logging
from typing import Any

from smolagents import CodeAgent, Tool, ToolCallingAgent
from smolagents.models import OpenAIModel

from ollama_agent.config import AgentType, OllamaConfig
from ollama_agent.models import OllamaModel
from ollama_agent.tools import get_default_tools

logger = logging.getLogger(__name__)


def create_agent(
    config: OllamaConfig | None = None,
    tools: list[Tool] | None = None,
    *,
    extra_tools: list[Tool] | None = None,
) -> CodeAgent | ToolCallingAgent:
    """Build and return a smolagents agent connected to a local Ollama model."""
    if config is None:
        config = OllamaConfig()

    model: OpenAIModel = OllamaModel(
        model_id=config.model,
        base_url=config.base_url,
        temperature=config.temperature,
        max_new_tokens=config.max_new_tokens,
        timeout=config.timeout,
    )

    if tools is None:
        tools = get_default_tools()
        if extra_tools:
            tools = tools + extra_tools
    elif extra_tools:
        tools = tools + extra_tools

    agent_kwargs: dict[str, Any] = {
        "tools": tools,
        "model": model,
        "max_steps": config.max_steps,
        "verbosity_level": 2 if config.verbose else 0,
    }

    if config.system_prompt:
        agent_kwargs["system_prompt"] = config.system_prompt

    if config.agent_type == AgentType.CODE:
        if config.additional_imports:
            agent_kwargs["additional_authorized_imports"] = config.additional_imports
        agent = CodeAgent(**agent_kwargs)
        logger.info("Created CodeAgent with model=%s", config.model)
    else:
        agent = ToolCallingAgent(**agent_kwargs)
        logger.info("Created ToolCallingAgent with model=%s", config.model)

    return agent