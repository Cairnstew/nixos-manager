"""Central configuration for the ollama_agent module."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentType(str, Enum):
    """Supported smolagents agent types."""

    CODE = "code"
    TOOL_CALLING = "tool_calling"


@dataclass
class OllamaConfig:
    """Configuration for a local Ollama-backed agent.

    Args:
        model: Ollama model tag, e.g. ``"qwen2.5:7b"``, ``"gemma3:4b"``.
        base_url: Base URL of the Ollama HTTP server.
        agent_type: Whether to use a CodeAgent or ToolCallingAgent.
        temperature: Sampling temperature (0.0 – 1.0).
        max_new_tokens: Maximum tokens the model may generate per turn.
        max_steps: Maximum ReAct iterations before the agent gives up.
        system_prompt: Optional system prompt override.
        additional_imports: Extra Python imports available inside CodeAgent.
        verbose: Stream step-level output to stdout.
        timeout: HTTP timeout (seconds) for calls to the Ollama server.
    """

    model: str = "qwen2.5:7b-instruct"
    base_url: str = "http://localhost:11434"
    agent_type: AgentType = AgentType.CODE
    temperature: float = 0.0
    max_new_tokens: int = 2048
    max_steps: int = 10
    system_prompt: str | None = None
    additional_imports: list[str] = field(default_factory=list)
    verbose: bool = False
    timeout: float = 120.0

    @classmethod
    def qwen_7b(cls, **kwargs: object) -> "OllamaConfig":
        """Preset for Qwen 2.5 7B."""
        return cls(model="qwen2.5:7b-instruct", **kwargs)  # type: ignore[arg-type]

    @classmethod
    def gemma_4b(cls, **kwargs: object) -> "OllamaConfig":
        """Preset for Gemma 3 4B."""
        return cls(model="gemma3:4b", **kwargs)  # type: ignore[arg-type]

    @classmethod
    def llama_8b(cls, **kwargs: object) -> "OllamaConfig":
        """Preset for Llama 3.1 8B."""
        return cls(model="llama3.1:8b", **kwargs)  # type: ignore[arg-type]