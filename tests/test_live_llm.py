import pytest
import os
import json
import time
import urllib.request
from agent import build_agent, _extract_last_text
from qwen_agent.llm.base import ModelServiceError
from config.settings import LLM_CONFIG


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
    not _model_is_ready(timeout=60),
    reason="Ollama model not ready within 60s — skipping live LLM tests"
)


def _run_agent(agent, messages: list) -> tuple[str, list]:
    """Run the agent and extract the final assistant text.
    Returns (text, raw_msgs) so callers can include raw structure in failures."""
    response_msgs = []
    best_text = ""
    for chunk in agent.run(messages=messages):
        if not chunk:
            continue
        response_msgs = chunk
        candidate = _extract_last_text(chunk) or ""
        if len(candidate) > len(best_text):
            best_text = candidate
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