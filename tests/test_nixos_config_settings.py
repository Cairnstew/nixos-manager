"""
Tests for nixos_manager.config.settings module.
"""

import os
from pathlib import Path

import pytest

from nixos_manager.config.settings import (
    LLM_CONFIG, NIXOS_REPO_PATH, NIX_EXTENSIONS, IGNORED_DIRS,
)


class TestConfigSettings:
    """Test configuration settings."""

    def test_llm_config_structure(self):
        """Test LLM_CONFIG has required keys."""
        assert "model_type" in LLM_CONFIG
        assert "model" in LLM_CONFIG
        assert "model_server" in LLM_CONFIG
        assert "api_key" in LLM_CONFIG
        assert "generate_cfg" in LLM_CONFIG

    def test_llm_config_model_type(self):
        """Test LLM model type is 'oai'."""
        assert LLM_CONFIG["model_type"] == "oai"

    def test_llm_config_from_env(self, monkeypatch):
        """Test LLM config respects environment variables."""
        monkeypatch.setenv("NIXMGR_MODEL", "test-model:8b")
        monkeypatch.setenv("NIXMGR_SERVER", "http://test.local:11434/v1")
        monkeypatch.setenv("NIXMGR_API_KEY", "test-key")
        
        # Reload the module to pick up env vars
        import importlib
        import nixos_manager.config.settings as settings_module
        importlib.reload(settings_module)
        
        assert settings_module.LLM_CONFIG["model"] == "test-model:8b"
        assert settings_module.LLM_CONFIG["model_server"] == "http://test.local:11434/v1"
        assert settings_module.LLM_CONFIG["api_key"] == "test-key"

    def test_llm_config_defaults(self, monkeypatch):
        """Test LLM config defaults when no env vars set."""
        monkeypatch.delenv("NIXMGR_MODEL", raising=False)
        monkeypatch.delenv("NIXMGR_SERVER", raising=False)
        monkeypatch.delenv("NIXMGR_API_KEY", raising=False)
        
        import importlib
        import nixos_manager.config.settings as settings_module
        importlib.reload(settings_module)
        
        assert "qwen" in settings_module.LLM_CONFIG["model"] or "7b" in settings_module.LLM_CONFIG["model"]
        assert "localhost:11434" in settings_module.LLM_CONFIG["model_server"]
        assert settings_module.LLM_CONFIG["api_key"] == "ollama"

    def test_generate_cfg_parameters(self):
        """Test generate_cfg has expected parameters."""
        gen_cfg = LLM_CONFIG["generate_cfg"]
        assert "fncall_prompt_type" in gen_cfg
        assert "max_tokens" in gen_cfg
        assert "thought_in_content" in gen_cfg

    def test_generate_cfg_fncall_type(self):
        """Test fncall_prompt_type is valid."""
        fncall_type = LLM_CONFIG["generate_cfg"]["fncall_prompt_type"]
        assert fncall_type in ("qwen", "nous")

    def test_nixos_repo_path(self):
        """Test NIXOS_REPO_PATH is a Path object."""
        assert isinstance(NIXOS_REPO_PATH, Path)

    def test_nixos_repo_path_from_env(self, monkeypatch, tmp_path):
        """Test NIXOS_REPO_PATH respects NIXOS_REPO_PATH env var."""
        monkeypatch.setenv("NIXOS_REPO_PATH", str(tmp_path))
        
        import importlib
        import nixos_manager.config.settings as settings_module
        importlib.reload(settings_module)
        
        assert settings_module.NIXOS_REPO_PATH == tmp_path

    def test_nixos_repo_path_expanduser(self, monkeypatch):
        """Test NIXOS_REPO_PATH expands ~ to home."""
        monkeypatch.setenv("NIXOS_REPO_PATH", "~/my-nixos-config")
        
        import importlib
        import nixos_manager.config.settings as settings_module
        importlib.reload(settings_module)
        
        assert "~" not in str(settings_module.NIXOS_REPO_PATH)

    def test_nix_extensions(self):
        """Test NIX_EXTENSIONS includes .nix."""
        assert ".nix" in NIX_EXTENSIONS
        assert isinstance(NIX_EXTENSIONS, set)

    def test_ignored_dirs(self):
        """Test IGNORED_DIRS has expected directories."""
        assert ".git" in IGNORED_DIRS
        assert "result" in IGNORED_DIRS
        assert ".direnv" in IGNORED_DIRS
        assert "__pycache__" in IGNORED_DIRS
        assert isinstance(IGNORED_DIRS, set)
