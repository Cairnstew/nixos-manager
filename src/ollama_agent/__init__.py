"""
ollama_agent — local LLM agents via Ollama + smolagents + agentrial.

Quick start::

    from ollama_agent import create_agent, OllamaConfig

    cfg = OllamaConfig(model="qwen2.5:7b")
    agent = create_agent(cfg)
    result = agent.run("What is 42 * 17?")
    print(result)
"""

from ollama_agent.agents.factory import create_agent
from ollama_agent.config import OllamaConfig
from ollama_agent.models import OllamaModel

__all__ = ["create_agent", "OllamaConfig", "OllamaModel"]
__version__ = "0.1.0"