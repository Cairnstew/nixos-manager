"""agentrial integration for ollama_agent."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

try:
    from agentrial.types import AgentInput, AgentMetadata, AgentOutput
    from agentrial.runner.adapters import wrap_smolagents_agent  # noqa: F401
    _AGENTRIAL_AVAILABLE = True
except ImportError:
    _AGENTRIAL_AVAILABLE = False
    AgentInput = AgentOutput = AgentMetadata = None  # type: ignore[assignment, misc]


def _require_agentrial() -> None:
    if not _AGENTRIAL_AVAILABLE:
        raise ImportError(
            "agentrial is required for evaluation features. "
            "Install it with: pip install agentrial"
        )


def wrap_for_agentrial(agent: Any) -> Callable[[Any], Any]:
    """Wrap a smolagents agent to satisfy the agentrial runner protocol."""
    _require_agentrial()

    try:
        from agentrial.runner.adapters import wrap_smolagents_agent
        return wrap_smolagents_agent(agent)
    except (ImportError, AttributeError):
        pass

    def _call(inp: Any) -> Any:
        query: str = inp.query if hasattr(inp, "query") else str(inp)
        start = time.perf_counter()
        success = True
        output = ""
        try:
            output = str(agent.run(query))
        except Exception as exc:
            output = f"ERROR: {exc}"
            success = False
        duration_ms = (time.perf_counter() - start) * 1000

        return AgentOutput(  # type: ignore[call-arg]
            output=output,
            steps=[],
            metadata=AgentMetadata(total_tokens=0, cost=0.0, duration_ms=duration_ms),  # type: ignore[call-arg]
            success=success,
        )

    return _call