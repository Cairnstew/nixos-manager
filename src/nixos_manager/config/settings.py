"""
config/settings.py — runtime configuration for nixos-manager
"""

import os
from pathlib import Path

LLM_CONFIG = {
    "model_type": "oai",
    "model": os.getenv("NIXMGR_MODEL", "gemma3:e4b"),
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

    # (Legacy — no longer used now that execute/verify stages are removed)
    "verify_max_retries": int(os.getenv("NIXMGR_VERIFY_RETRIES", "2")),
}

# ---------------------------------------------------------------------------
# Plan document output
# ---------------------------------------------------------------------------

# Directory where plan .md files are written.
# Override with NIXMGR_PLAN_DIR env var.
PLAN_OUTPUT_DIR = Path(
    os.getenv("NIXMGR_PLAN_DIR", "/tmp/nixos-plans")
).expanduser()

# ---------------------------------------------------------------------------
# NixOS config context
# ---------------------------------------------------------------------------

# Maximum number of lines to read from each .nix file when building context.
# Increase if your files are large and you want more detail.
# Set to 0 to read entire files (no truncation).
NIXOS_CONTEXT_MAX_LINES_PER_FILE = int(
    os.getenv("NIXMGR_CONTEXT_MAX_LINES", "120")
)

# Maximum total characters for the entire config context blob injected into
# the pipeline.  Keeps prompt size sane for large repos.
NIXOS_CONTEXT_MAX_CHARS = int(
    os.getenv("NIXMGR_CONTEXT_MAX_CHARS", "12000")
)

# ---------------------------------------------------------------------------
# External research API keys (optional — pipeline degrades gracefully)
# ---------------------------------------------------------------------------
# ANTHROPIC_API_KEY    — used for web-result synthesis and plan generation.
#                        Falls back to local 7B model if not set.
# BRAVE_SEARCH_API_KEY — used for web research steps.
#                        Falls back to DuckDuckGo HTML scraping if not set.