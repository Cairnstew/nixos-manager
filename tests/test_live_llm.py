import pytest
import os
from agent import build_agent
from qwen_agent.llm.base import ModelServiceError

# Use the mark you defined in pyproject.toml
@pytest.mark.integration
class TestLiveLLM:
    """
    Live integration tests for the LLM connection.
    Requires Ollama to be running and the model to be pulled.
    """

    def test_llm_connection_and_response(self):
        """
        Tests that the agent can send a message to the local Ollama
        and receive a non-empty string response.
        """
        # 1. Initialize the real agent using settings (which pull from ENV)
        agent = build_agent()
        
        # 2. Prepare a simple "ping" message
        messages = [{"role": "user", "content": "Respond with exactly the word 'ACKNOWLEDGE'."}]
        
        try:
            # 3. Execute the run (it's a generator)
            response_content = ""
            for responses in agent.run(messages=messages):
                if responses:
                    response_content = responses[-1]['content']
            
            # 4. Assertions
            assert len(response_content) > 0, "Agent returned an empty response."
            assert "ACKNOWLEDGE" in response_content.upper(), f"Unexpected response: {response_content}"
            
        except ModelServiceError as e:
            pytest.fail(f"LLM Service Error: Is Ollama running? Error: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error during live test: {e}")

    def test_tool_calling_logic_live(self):
        """
        Verify that the LLM understands the tools available by asking
        it which tool it would use for a specific Nix task.
        """
        agent = build_agent()
        
        # We ask a question that *should* trigger thoughts about tools
        query = "Can you list the files in my NixOS repository?"
        messages = [{"role": "user", "content": query}]
        
        responses = list(agent.run(messages=messages))
        final_response = responses[-1][-1]['content']
        
        # We aren't testing if it actually runs the tool (that's risky for a test),
        # but that it doesn't crash and returns a coherent thought.
        assert len(final_response) > 0
        # A good agent will likely mention 'list_nix_files' in its thought process