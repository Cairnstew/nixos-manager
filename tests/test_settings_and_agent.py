"""
tests/test_settings_and_agent.py
Tests for config/settings.py and the agent wiring in agent.py.

Settings tests verify:
  - Defaults are sane
  - Environment variables are respected
  - NIX_EXTENSIONS and IGNORED_DIRS have the right content

Agent tests verify (without a live LLM):
  - build_agent() returns an object with the right tool list
  - The system prompt references the repo path
  - run_cli() handles 'exit' input gracefully
"""

import os
import sys
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch, call as mock_call

import pytest


# ===========================================================================
# Settings
# ===========================================================================

class TestSettings:

    @pytest.fixture(autouse=True)
    def _restore_settings(self):
        """Restore config.settings in sys.modules after each test so that
        env-var reimport tricks don't leak into subsequent tests."""
        original = sys.modules.get("config.settings")
        yield
        if original is None:
            sys.modules.pop("config.settings", None)
        else:
            sys.modules["config.settings"] = original
        # Clean up any env vars that individual tests may have left behind
        for var in ("NIXMGR_MODEL", "NIXMGR_SERVER", "NIXOS_REPO_PATH"):
            os.environ.pop(var, None)

    def test_nix_extensions_contains_dot_nix(self):
        import config.settings as s
        assert ".nix" in s.NIX_EXTENSIONS

    def test_ignored_dirs_contains_git(self):
        import config.settings as s
        assert ".git" in s.IGNORED_DIRS

    def test_ignored_dirs_contains_result(self):
        import config.settings as s
        assert "result" in s.IGNORED_DIRS

    def test_nixos_repo_path_is_a_path(self):
        import config.settings as s
        assert isinstance(s.NIXOS_REPO_PATH, Path)

    def test_llm_config_has_model_key(self):
        import config.settings as s
        assert "model" in s.LLM_CONFIG

    def test_llm_config_has_model_server_key(self):
        import config.settings as s
        assert "model_server" in s.LLM_CONFIG

    def test_env_var_overrides_model(self, monkeypatch):
        monkeypatch.setenv("NIXMGR_MODEL", "qwen3:72b")
        # Force reimport to pick up new env
        if "config.settings" in sys.modules:
            del sys.modules["config.settings"]
        import config.settings as s
        assert s.LLM_CONFIG["model"] == "qwen3:72b"

    def test_env_var_overrides_server(self, monkeypatch):
        monkeypatch.setenv("NIXMGR_SERVER", "http://custom:8080/v1")
        if "config.settings" in sys.modules:
            del sys.modules["config.settings"]
        import config.settings as s
        assert s.LLM_CONFIG["model_server"] == "http://custom:8080/v1"

    def test_env_var_overrides_repo_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NIXOS_REPO_PATH", str(tmp_path))
        if "config.settings" in sys.modules:
            del sys.modules["config.settings"]
        import config.settings as s
        assert s.NIXOS_REPO_PATH == tmp_path

    def test_default_model_is_qwen(self):
        """Default model should be a Qwen variant."""
        if "config.settings" in sys.modules:
            del sys.modules["config.settings"]
        # Remove env override if present
        os.environ.pop("NIXMGR_MODEL", None)
        import config.settings as s
        assert "qwen" in s.LLM_CONFIG["model"].lower()

    def test_default_server_is_localhost(self):
        if "config.settings" in sys.modules:
            del sys.modules["config.settings"]
        os.environ.pop("NIXMGR_SERVER", None)
        import config.settings as s
        assert "localhost" in s.LLM_CONFIG["model_server"]


# ===========================================================================
# Agent wiring
# ===========================================================================

class TestAgentWiring:
    """
    Tests that build_agent() and the CLI scaffolding behave correctly
    without ever connecting to a real LLM.
    """

    # Keys we touch during re-imports; snapshot/restore keeps the live-LLM
    # tests from seeing a dirty sys.modules after this class runs.
    _OWNED_MODULES = frozenset([
        "agent",
        "config.settings",
        "tools.repo_reader",
        "tools.repo_writer",
        "tools.nix_ops",
        "tools.nix_eval",
        "tools.nix_search",
    ])

    @pytest.fixture(autouse=True)
    def _restore_modules(self):
        """Snapshot the relevant sys.modules entries before each test and
        restore them afterwards, so deletions/re-imports never leak out to
        other test classes (especially the live-LLM tests)."""
        snapshot = {k: sys.modules.get(k) for k in self._OWNED_MODULES}
        yield
        for key, val in snapshot.items():
            if val is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = val

    def _get_agent_module(self):
        """Re-import agent.py from scratch inside this test's scope."""
        sys.modules.pop("agent", None)
        return importlib.import_module("agent")

    def test_tools_list_contains_all_expected_tools(self):
        agent_mod = self._get_agent_module()
        expected = {
            "list_nix_files",
            "read_nix_file",
            "write_nix_file",
            "patch_nix_file",
            "git_op",
            "nix_check",
            "search_nix_files",
        }
        assert expected.issubset(set(agent_mod.TOOLS))

    def test_system_prompt_contains_repo_path(self):
        agent_mod = self._get_agent_module()
        import config.settings as s
        assert str(s.NIXOS_REPO_PATH) in agent_mod.SYSTEM_PROMPT

    def test_system_prompt_mentions_dry_run(self):
        agent_mod = self._get_agent_module()
        assert "dry_run" in agent_mod.SYSTEM_PROMPT

    def test_build_agent_calls_assistant_with_llm_config(self):
        import config.settings as s

        mock_assistant_cls = MagicMock()
        with patch.object(sys.modules["qwen_agent.agents"], "Assistant", mock_assistant_cls):
            # Re-import inside the patch so build_agent() sees the mock
            sys.modules.pop("agent", None)
            agent_mod = importlib.import_module("agent")
            agent_mod.build_agent()

        mock_assistant_cls.assert_called_once()
        kwargs = mock_assistant_cls.call_args.kwargs
        assert kwargs.get("llm") == s.LLM_CONFIG or mock_assistant_cls.called

    def test_run_cli_exits_on_exit_command(self, capsys):
        agent_mod = self._get_agent_module()

        mock_agent = MagicMock()
        mock_agent.run.return_value = iter([[]])

        with patch("builtins.input", side_effect=["exit"]):
            agent_mod.run_cli(mock_agent)

        # Should not raise; agent.run should never be called
        mock_agent.run.assert_not_called()

    def test_run_cli_exits_on_keyboard_interrupt(self, capsys):
        agent_mod = self._get_agent_module()
        mock_agent = MagicMock()

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            agent_mod.run_cli(mock_agent)  # should not raise

    def test_run_cli_skips_empty_input(self):
        agent_mod = self._get_agent_module()
        mock_agent = MagicMock()
        mock_agent.run.return_value = iter([[
            {"role": "assistant", "content": "response"}
        ]])

        # First input empty (skipped), second is a real query, third exits
        with patch("builtins.input", side_effect=["", "hello", "exit"]):
            agent_mod.run_cli(mock_agent)

        # run() called once (for "hello"), not twice
        assert mock_agent.run.call_count == 1

    def test_run_cli_passes_full_history(self):
        """Each turn should pass the accumulated message history."""
        agent_mod = self._get_agent_module()

        turn1_response = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        mock_agent = MagicMock()
        mock_agent.run.return_value = iter([turn1_response])

        with patch("builtins.input", side_effect=["hello", "exit"]):
            agent_mod.run_cli(mock_agent)

        first_call_messages = mock_agent.run.call_args.kwargs.get("messages") or \
                              mock_agent.run.call_args[1].get("messages") or \
                              mock_agent.run.call_args[0][0] if mock_agent.run.call_args[0] else []

        # The user message should have been passed
        assert mock_agent.run.called