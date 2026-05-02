"""
config/settings.py  –  runtime configuration for nixos-manager
Edit this file or export environment variables to override.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# LLM endpoint
# qwen-agent can speak to any OpenAI-compatible server (Ollama, vLLM, LMStudio…)
# ---------------------------------------------------------------------------
LLM_CONFIG = {
    "model": os.getenv("NIXMGR_MODEL", "qwen2.5-coder:8b"),   # or "qwen3:8b"
    "model_server": os.getenv("NIXMGR_SERVER", "http://localhost:11434/v1"),  # Ollama default
    "api_key": os.getenv("NIXMGR_API_KEY", "ollama"),           # placeholder for local
    # Uncomment to cap token spend:
    # "generate_cfg": {"max_tokens": 4096},
}

# ---------------------------------------------------------------------------
# NixOS config repository
# ---------------------------------------------------------------------------
NIXOS_REPO_PATH = Path(
    os.getenv("NIXOS_REPO_PATH", str(Path.home() / "nixos-config"))
)

# File extensions treated as Nix source
NIX_EXTENSIONS = {".nix"}

# Directories to ignore when scanning the repo
IGNORED_DIRS = {".git", "result", ".direnv", "__pycache__"}
