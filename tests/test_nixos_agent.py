"""
Tests for nixos_manager.agent module.
"""

from unittest.mock import MagicMock, patch, call

import pytest

from nixos_manager.agent import bot, main


class TestAgentInitialization:
    """Test agent initialization."""

    def test_bot_exists(self):
        """Test bot is initialized."""
        assert bot is not None

    def test_bot_has_name(self):
        """Test bot has correct name."""
        assert bot.name == "NixManager"

    def test_bot_has_description(self):
        """Test bot has description."""
        assert bot.description is not None
        assert "NixOS" in bot.description
        assert "expert" in bot.description.lower()

    def test_bot_has_system_message(self):
        """Test bot has system message."""
        assert bot.system_message is not None
        assert "NixOS" in bot.system_message
        assert "nix_search_tool" in bot.system_message

    def test_bot_has_llm_config(self):
        """Test bot has LLM config."""
        assert hasattr(bot, "llm")
        assert bot.llm is not None

    def test_bot_has_function_list(self):
        """Test bot has function map."""
        assert hasattr(bot, "function_map")
        assert isinstance(bot.function_map, dict)
        assert "nix_search_tool" in bot.function_map
        assert "code_interpreter" in bot.function_map


class TestAgentBehavior:
    """Test agent behavior and capabilities."""

    def test_agent_has_run_method(self):
        """Test bot has run method."""
        assert hasattr(bot, "run")
        assert callable(bot.run)

    @patch("nixos_manager.agent.bot.run")
    def test_agent_run_with_messages(self, mock_run):
        """Test bot.run accepts messages."""
        mock_run.return_value = [{"role": "assistant", "content": "test response"}]
        
        messages = [{"role": "user", "content": "Add PostgreSQL to nixos config"}]
        responses = bot.run(messages)
        
        mock_run.assert_called_once_with(messages)

    def test_agent_system_message_mentions_best_practices(self):
        """Test system message includes best practices."""
        assert "verify" in bot.system_message.lower()
        assert "syntax" in bot.system_message.lower()


class TestMainFunction:
    """Test main entry point."""

    def test_main_function_exists(self):
        """Test main function exists."""
        assert callable(main)

    @patch("nixos_manager.agent.bot.run")
    def test_main_basic_execution(self, mock_run):
        """Test main function basic execution."""
        mock_run.return_value = [
            {"role": "assistant", "content": "I'll add PostgreSQL..."},
            {"role": "assistant", "content": "Here's the config..."}
        ]
        
        # Main should execute without error
        try:
            main()
        except Exception as e:
            pytest.fail(f"main() raised {type(e).__name__}: {e}")

    @patch("nixos_manager.agent.bot.run")
    @patch("builtins.print")
    def test_main_prints_response(self, mock_print, mock_run):
        """Test main prints bot responses."""
        mock_run.return_value = [
            {"role": "assistant", "content": "response1"},
            {"role": "assistant", "content": "response2"}
        ]
        
        main()
        
        # Check that print was called
        assert mock_print.called

    @patch("nixos_manager.agent.bot.run")
    def test_main_uses_default_message(self, mock_run):
        """Test main uses default search message."""
        mock_run.return_value = [{"role": "assistant", "content": "response"}]
        
        main()
        
        # Verify run was called with default message about PostgreSQL
        call_args = mock_run.call_args
        messages = call_args[0][0] if call_args[0] else call_args[1]["messages"]
        assert len(messages) > 0
        assert "postgresql" in messages[0]["content"].lower() or "postgres" in messages[0]["content"].lower()


class TestAgentImports:
    """Test that required modules are imported correctly."""

    def test_assistant_imported(self):
        """Test Assistant class is imported."""
        from qwen_agent.agents import Assistant
        assert Assistant is not None

    def test_llm_config_imported(self):
        """Test LLM config is imported."""
        from nixos_manager.config.settings import LLM_CONFIG
        assert LLM_CONFIG is not None
        assert "model" in LLM_CONFIG

    def test_nix_search_tool_imported(self):
        """Test NixSearchTool is imported."""
        from nixos_manager.tools.nix_search import NixSearchTool
        assert NixSearchTool is not None


class TestAgentConfiguration:
    """Test agent configuration details."""

    def test_agent_llm_type(self):
        """Test agent uses OAI model type."""
        from nixos_manager.config.settings import LLM_CONFIG
        assert LLM_CONFIG["model_type"] == "oai"

    def test_agent_tool_availability(self):
        """Test tools are available to agent."""
        tools = ["nix_search_tool", "code_interpreter"]
        # Check that all tools are in the function_map
        for tool in tools:
            assert tool in bot.function_map

    def test_agent_system_prompt_quality(self):
        """Test system prompt has good quality."""
        prompt = bot.system_message
        # Should be fairly detailed
        assert len(prompt) > 50
        # Should mention key concepts
        assert "NixOS" in prompt
        assert "administrator" in prompt or "expert" in prompt.lower()


class TestMainEntryPoint:
    """Test main as CLI entry point."""

    def test_main_no_args(self):
        """Test main with no arguments."""
        with patch("nixos_manager.agent.bot.run") as mock_run:
            mock_run.return_value = [{"role": "assistant", "content": "response"}]
            try:
                main()
            except SystemExit:
                pass  # Expected if it calls sys.exit

    @patch("nixos_manager.agent.bot.run")
    def test_main_error_handling(self, mock_run):
        """Test main handles errors gracefully."""
        mock_run.side_effect = Exception("API error")
        
        with pytest.raises(Exception):
            main()
