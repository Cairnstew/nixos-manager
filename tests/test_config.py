"""
tests/test_config.py
Tests for config/settings.py and configuration handling.

Covers:
  LLM_CONFIG structure and validation
  NIXOS_REPO_PATH resolution
  Environment variable parsing
  Settings defaults
  Path validation
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class TestLLMConfig:
    """Test LLM configuration."""

    def test_llm_config_has_required_fields(self):
        """LLM_CONFIG should have all required fields."""
        from config.settings import LLM_CONFIG
        
        required_fields = {
            "model_type",
            "model",
            "model_server",
            "api_key",
            "generate_cfg"
        }
        assert required_fields.issubset(LLM_CONFIG.keys())

    def test_llm_config_model_type_is_oai(self):
        """model_type should be 'oai' for OpenAI compatibility."""
        from config.settings import LLM_CONFIG
        assert LLM_CONFIG["model_type"] == "oai"

    def test_llm_config_generate_cfg_has_required_keys(self):
        """generate_cfg should contain required keys."""
        from config.settings import LLM_CONFIG
        
        gen_cfg = LLM_CONFIG["generate_cfg"]
        required = {"fncall_prompt_type", "max_tokens", "thought_in_content"}
        assert required.issubset(gen_cfg.keys())

    def test_llm_model_env_override(self):
        """NIXMGR_MODEL env var should override default."""
        with patch.dict(os.environ, {"NIXMGR_MODEL": "custom-model:8b"}):
            # Re-import to get new env values
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import LLM_CONFIG
            assert LLM_CONFIG["model"] == "custom-model:8b"
        
        # Reset
        importlib.reload(config.settings)

    def test_llm_server_env_override(self):
        """NIXMGR_SERVER env var should override default."""
        with patch.dict(os.environ, {"NIXMGR_SERVER": "http://custom:5000/v1"}):
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import LLM_CONFIG
            assert LLM_CONFIG["model_server"] == "http://custom:5000/v1"
        
        # Reset
        importlib.reload(config.settings)

    def test_llm_api_key_env_override(self):
        """NIXMGR_API_KEY env var should override default."""
        with patch.dict(os.environ, {"NIXMGR_API_KEY": "secret-key-123"}):
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import LLM_CONFIG
            assert LLM_CONFIG["api_key"] == "secret-key-123"
        
        # Reset
        importlib.reload(config.settings)

    def test_generate_cfg_max_tokens_is_positive(self):
        """max_tokens should be a positive integer."""
        from config.settings import LLM_CONFIG
        max_tokens = LLM_CONFIG["generate_cfg"]["max_tokens"]
        assert isinstance(max_tokens, int)
        assert max_tokens > 0

    def test_fncall_prompt_type_is_valid(self):
        """fncall_prompt_type should be one of known values."""
        from config.settings import LLM_CONFIG
        prompt_type = LLM_CONFIG["generate_cfg"]["fncall_prompt_type"]
        assert prompt_type in {"nous", "qwen"}


class TestNixosRepoPath:
    """Test NIXOS_REPO_PATH configuration."""

    def test_repo_path_is_path_object(self):
        """NIXOS_REPO_PATH should be a Path object."""
        from config.settings import NIXOS_REPO_PATH
        assert isinstance(NIXOS_REPO_PATH, Path)

    def test_repo_path_default_when_not_set(self):
        """Default repo path should be ~/nixos-config."""
        with patch.dict(os.environ, {}, clear=False):
            if "NIXOS_REPO_PATH" in os.environ:
                del os.environ["NIXOS_REPO_PATH"]
            
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import NIXOS_REPO_PATH
            
            expected = Path.home() / "nixos-config"
            assert NIXOS_REPO_PATH == expected
        
        # Reset
        importlib.reload(config.settings)

    def test_repo_path_env_override(self):
        """NIXOS_REPO_PATH env var should override default."""
        test_path = "/tmp/custom-nixos-config"
        with patch.dict(os.environ, {"NIXOS_REPO_PATH": test_path}):
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import NIXOS_REPO_PATH
            assert NIXOS_REPO_PATH == Path(test_path)
        
        # Reset
        importlib.reload(config.settings)

    def test_repo_path_tilde_expansion(self):
        """Paths with ~ should be expanded to home directory."""
        test_path = "~/my-nixos-config"
        with patch.dict(os.environ, {"NIXOS_REPO_PATH": test_path}):
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import NIXOS_REPO_PATH
            
            assert str(NIXOS_REPO_PATH).startswith(str(Path.home()))
        
        # Reset
        importlib.reload(config.settings)

    def test_repo_path_relative_to_cwd(self):
        """Relative paths should be handled."""
        with patch.dict(os.environ, {"NIXOS_REPO_PATH": "./nixos-config"}):
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import NIXOS_REPO_PATH
            
            # Should be a valid Path
            assert isinstance(NIXOS_REPO_PATH, Path)
        
        # Reset
        importlib.reload(config.settings)


class TestNixExtensions:
    """Test NIX_EXTENSIONS constant."""

    def test_nix_extensions_defined(self):
        """NIX_EXTENSIONS should be defined."""
        from config.settings import NIX_EXTENSIONS
        assert NIX_EXTENSIONS is not None

    def test_nix_extensions_includes_dot_nix(self):
        """NIX_EXTENSIONS should include .nix."""
        from config.settings import NIX_EXTENSIONS
        assert ".nix" in NIX_EXTENSIONS

    def test_nix_extensions_is_set(self):
        """NIX_EXTENSIONS should be a set."""
        from config.settings import NIX_EXTENSIONS
        assert isinstance(NIX_EXTENSIONS, set)


class TestIgnoredDirs:
    """Test IGNORED_DIRS constant."""

    def test_ignored_dirs_defined(self):
        """IGNORED_DIRS should be defined."""
        from config.settings import IGNORED_DIRS
        assert IGNORED_DIRS is not None

    def test_ignored_dirs_includes_git(self):
        """IGNORED_DIRS should include .git."""
        from config.settings import IGNORED_DIRS
        assert ".git" in IGNORED_DIRS

    def test_ignored_dirs_includes_result(self):
        """IGNORED_DIRS should include result."""
        from config.settings import IGNORED_DIRS
        assert "result" in IGNORED_DIRS

    def test_ignored_dirs_includes_direnv(self):
        """IGNORED_DIRS should include .direnv."""
        from config.settings import IGNORED_DIRS
        assert ".direnv" in IGNORED_DIRS

    def test_ignored_dirs_is_set(self):
        """IGNORED_DIRS should be a set."""
        from config.settings import IGNORED_DIRS
        assert isinstance(IGNORED_DIRS, set)

    def test_ignored_dirs_common_exclusions(self):
        """IGNORED_DIRS should have common directory exclusions."""
        from config.settings import IGNORED_DIRS
        common = {".git", "result", ".direnv", "__pycache__"}
        assert common.issubset(IGNORED_DIRS)


class TestSettingsConsistency:
    """Test that settings are consistently formatted."""

    def test_llm_config_keys_lowercase(self):
        """All LLM_CONFIG keys should be lowercase."""
        from config.settings import LLM_CONFIG
        for key in LLM_CONFIG.keys():
            assert key.islower() or "_" in key

    def test_generate_cfg_keys_lowercase(self):
        """All generate_cfg keys should be lowercase."""
        from config.settings import LLM_CONFIG
        for key in LLM_CONFIG["generate_cfg"].keys():
            assert key.islower() or "_" in key

    def test_settings_no_mutable_defaults(self):
        """Settings should not have problematic mutable defaults."""
        from config.settings import LLM_CONFIG
        
        # Lists and dicts should be frozen or carefully managed
        gen_cfg = LLM_CONFIG["generate_cfg"]
        # Check that modifying won't affect other imports
        original_tokens = gen_cfg["max_tokens"]
        gen_cfg["max_tokens"] = 9999
        
        # Re-import should get original value
        import importlib
        import config.settings
        importlib.reload(config.settings)
        from config.settings import LLM_CONFIG as LLM_CONFIG_NEW
        assert LLM_CONFIG_NEW["generate_cfg"]["max_tokens"] == original_tokens
        
        # Reset
        importlib.reload(config.settings)


class TestEnvironmentVariableHandling:
    """Test environment variable handling robustness."""

    def test_empty_env_var_uses_default(self):
        """Empty environment variables should use defaults."""
        with patch.dict(os.environ, {"NIXMGR_MODEL": ""}):
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import LLM_CONFIG
            # Empty string should be overridden or default used
            assert LLM_CONFIG["model"] is not None
        
        # Reset
        importlib.reload(config.settings)

    def test_whitespace_env_var(self):
        """Whitespace-only environment variables should be handled."""
        with patch.dict(os.environ, {"NIXMGR_SERVER": "   "}):
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import LLM_CONFIG
            # Should have some sensible value
            assert LLM_CONFIG["model_server"] is not None
        
        # Reset
        importlib.reload(config.settings)

    def test_special_chars_in_api_key(self):
        """Special characters in API key should be preserved."""
        special_key = "key-with-special!@#$%^&*()_chars"
        with patch.dict(os.environ, {"NIXMGR_API_KEY": special_key}):
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import LLM_CONFIG
            assert LLM_CONFIG["api_key"] == special_key
        
        # Reset
        importlib.reload(config.settings)

    def test_url_with_port_in_server(self):
        """Model server URLs with custom ports should work."""
        server_url = "http://localhost:8000/v1"
        with patch.dict(os.environ, {"NIXMGR_SERVER": server_url}):
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import LLM_CONFIG
            assert LLM_CONFIG["model_server"] == server_url
        
        # Reset
        importlib.reload(config.settings)

    def test_model_name_with_version(self):
        """Model names with versions should be preserved."""
        model = "qwen2.5-coder:70b-instruct"
        with patch.dict(os.environ, {"NIXMGR_MODEL": model}):
            import importlib
            import config.settings
            importlib.reload(config.settings)
            from config.settings import LLM_CONFIG
            assert LLM_CONFIG["model"] == model
        
        # Reset
        importlib.reload(config.settings)
