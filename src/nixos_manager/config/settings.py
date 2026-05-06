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
    "model_type": "oai",
    "model": os.getenv("NIXMGR_MODEL", "qwen2.5:7b-instruct"),
    "model_server": os.getenv("NIXMGR_SERVER", "http://localhost:11434/v1"),
    "api_key": os.getenv("NIXMGR_API_KEY", "ollama"),
    "generate_cfg": {
        "fncall_prompt_type": "nous",   # ← 'qwen' or 'nous' — NOT 'qwen25'
        "max_tokens": 4096,
        "thought_in_content": False,
    },
}

# ---------------------------------------------------------------------------
# NixOS config repository
# ---------------------------------------------------------------------------
NIXOS_REPO_PATH = Path(
    os.getenv("NIXOS_REPO_PATH", str(Path.home() / "nixos-config"))
).expanduser()

# File extensions treated as Nix source
NIX_EXTENSIONS = {".nix"}

# Directories to ignore when scanning the repo
IGNORED_DIRS = {".git", "result", ".direnv", "__pycache__"}
