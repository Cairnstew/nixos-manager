import pytest
import os
import json
import time
import sys
import urllib.request
from unittest.mock import MagicMock
from agent import build_agent, _extract_last_text
from qwen_agent.llm.base import ModelServiceError
from config.settings import LLM_CONFIG


def _qwen_is_available() -> bool:
    """Check if qwen_agent is actually installed (not mocked by conftest)."""
    # Try to build an agent and check if it's real (not a MagicMock)
    try:
        agent = build_agent()
        # If the agent is a MagicMock, qwen_agent wasn't really imported
        return not isinstance(agent, MagicMock)
    except Exception:
        return False


def _model_is_ready(timeout: int = 60) -> bool:
    """
    Send a minimal generation request and wait up to `timeout` seconds
    for a real response. Returns False if the server is unreachable,
    the model isn't pulled, or it doesn't respond in time.
    """
    server = LLM_CONFIG.get("model_server", "http://localhost:11434/v1")
    model = LLM_CONFIG.get("model", "qwen3:8b")
    url = server.rstrip("/v1").rstrip("/") + "/api/generate"

    payload = json.dumps({
        "model": model,
        "prompt": "hi",
        "stream": False,
        "options": {"num_predict": 1},  # generate exactly 1 token — fast
    }).encode()

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read())
                return bool(body.get("response"))
        except Exception:
            time.sleep(2)
    return False


ollama_available = pytest.mark.skipif(
    not _model_is_ready(timeout=60) or not _qwen_is_available(),
    reason="Ollama model not ready within 60s OR qwen_agent not installed — skipping live LLM tests"
)


def _run_agent(agent, messages: list) -> tuple[str, list]:
    """Run the agent and extract the final assistant text.
    Returns (text, raw_msgs) so callers can include raw structure in failures."""
    response_msgs = []
    best_text = ""
    all_chunks = []  # keep every chunk (including empty) for diagnostics
    for chunk in agent.run(messages=messages):
        all_chunks.append(chunk)
        if not chunk:
            continue
        response_msgs = chunk
        candidate = _extract_last_text(chunk) or ""
        if len(candidate) > len(best_text):
            best_text = candidate

    if not best_text:
        # Emit a detailed diagnostic so we can tell WHY it failed:
        # - all_chunks=[] means agent.run() is itself an empty generator
        # - all_chunks=[[], []] means LLM is yielding only empty-list chunks
        print(
            f"\n[_run_agent diagnostic] total_chunks={len(all_chunks)}, "
            f"non_empty={sum(1 for c in all_chunks if c)}, "
            f"agent_type={type(agent).__name__}, "
            f"function_map_keys={list(agent.function_map.keys())}, "
            f"llm_type={type(getattr(agent, 'llm', None)).__name__}, "
            f"llm_model={getattr(getattr(agent, 'llm', None), 'model', 'N/A')}, "
            f"llm_server={getattr(getattr(agent, 'llm', None), 'model_server', 'N/A')}",
            flush=True,
        )

    return best_text, response_msgs


@pytest.mark.integration
@ollama_available
class TestLiveLLM:
    """
    Live integration tests for the LLM connection.
    Requires Ollama to be running and the model to be pulled.
    Skipped automatically when Ollama is not reachable.
    """

    def test_llm_connection_and_response(self):
        """Tests that the agent can send a message and receive a non-empty response."""
        agent = build_agent()
        messages = [{"role": "user", "content": "Respond with exactly the word 'ACKNOWLEDGE'."}]

        try:
            response_content, raw_msgs = _run_agent(agent, messages)

            assert len(response_content) > 0, (
                f"Agent returned an empty response. Raw msgs: {raw_msgs!r}"
            )
            assert "ACKNOWLEDGE" in response_content.upper(), (
                f"Unexpected response: {response_content!r}"
            )

        except ModelServiceError as e:
            pytest.fail(f"LLM Service Error: Is Ollama running? Error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            pytest.fail(f"Unexpected error during live test: {e}")

    def test_tool_calling_logic_live(self):
        """Verify the agent doesn't crash and returns something coherent."""
        agent = build_agent()
        messages = [{"role": "user", "content": "Can you list the files in my NixOS repository?"}]

        try:
            final_response, raw_msgs = _run_agent(agent, messages)

            assert len(final_response) > 0, (
                f"Agent returned an empty response. Raw msgs: {raw_msgs!r}"
            )

        except ModelServiceError as e:
            pytest.fail(f"LLM Service Error: Is Ollama running? Error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            pytest.fail(f"Unexpected error during live test: {e}")