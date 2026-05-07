"""
config/settings.py  –  runtime configuration for nixos-manager
"""

import os
from pathlib import Path

LLM_CONFIG = {
    "model_type": "oai",
    "model": os.getenv("NIXMGR_MODEL", "qwen2.5:7b-instruct"),
    "model_server": os.getenv("NIXMGR_SERVER", "http://localhost:11434/v1"),
    "api_key": os.getenv("NIXMGR_API_KEY", "ollama"),
    "generate_cfg": {
        "max_tokens": 4096,
    },
}

NIXOS_REPO_PATH = Path(
    os.getenv("NIXOS_REPO_PATH", str(Path.home() / "nixos-config"))
).expanduser()

NIX_EXTENSIONS = {".nix"}
IGNORED_DIRS = {".git", "result", ".direnv", "__pycache__"}

# ---------------------------------------------------------------------------
# Pipeline settings
# ---------------------------------------------------------------------------

PIPELINE_CONFIG = {
    # Confidence threshold — plan steps below this get refined
    "confidence_threshold": float(os.getenv("NIXMGR_CONFIDENCE", "0.75")),

    # How many plan refinement iterations before giving up
    "plan_max_iterations": int(os.getenv("NIXMGR_PLAN_ITER", "4")),

    # How many times to retry a research step that scores not-relevant
    "research_max_retries": int(os.getenv("NIXMGR_RESEARCH_RETRIES", "3")),

    # How many times to re-execute if verify finds bad names
    "verify_max_retries": int(os.getenv("NIXMGR_VERIFY_RETRIES", "2")),
}