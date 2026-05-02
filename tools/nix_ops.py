"""
tools/nix_ops.py
Custom qwen-agent tools for running nix / git commands against the config repo.
All commands are sandboxed to the repo path and have an allow-list of safe ops.
"""

import json
import subprocess
from pathlib import Path
from typing import Union

from qwen_agent.tools.base import BaseTool, register_tool

from config.settings import NIXOS_REPO_PATH

# Commands the agent is allowed to run (prefix match)
_ALLOWED_GIT = {"status", "diff", "log", "add", "commit", "show", "stash"}
_ALLOWED_NIX = {"flake check", "flake show", "build", "eval"}


def _run(cmd: list[str], cwd: Path, timeout: int = 60) -> str:
    """Run a subprocess and return combined stdout/stderr."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout + result.stderr
        return out.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {timeout}s."
    except FileNotFoundError as exc:
        return f"ERROR: command not found — {exc}"
    except Exception as exc:
        return f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# Tool: git_op
# ---------------------------------------------------------------------------
@register_tool("git_op")
class GitOp(BaseTool):
    """Run a safe git command inside the NixOS config repository."""

    name = "git_op"
    description = (
        "Run a git command (status, diff, log, add, commit, show, stash) "
        "inside the NixOS configuration repository. "
        "Destructive commands like push/reset/force are blocked."
    )
    parameters = [
        {
            "name": "args",
            "type": "string",
            "description": (
                "git sub-command and arguments as a single string, "
                "e.g. 'status', 'diff HEAD~1', 'commit -m \"fix: update hostname\"'"
            ),
            "required": True,
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        args_str = params.get("args", "").strip()
        if not args_str:
            return "ERROR: 'args' is required."

        # Safety check
        first_word = args_str.split()[0]
        if first_word not in _ALLOWED_GIT:
            return (
                f"ERROR: git '{first_word}' is not in the allow-list. "
                f"Allowed: {sorted(_ALLOWED_GIT)}"
            )

        import shlex
        cmd = ["git"] + shlex.split(args_str)
        return _run(cmd, cwd=NIXOS_REPO_PATH)


# ---------------------------------------------------------------------------
# Tool: nix_check
# ---------------------------------------------------------------------------
@register_tool("nix_check")
class NixCheck(BaseTool):
    """Run nix flake check or nix eval to validate the configuration."""

    name = "nix_check"
    description = (
        "Validate the NixOS flake by running 'nix flake check', "
        "'nix flake show', or 'nix build'. "
        "Use this after edits to catch syntax / evaluation errors before committing."
    )
    parameters = [
        {
            "name": "command",
            "type": "string",
            "description": (
                "Which nix command to run. "
                "One of: 'flake check', 'flake show', 'build .#<attr>'."
            ),
            "required": True,
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        cmd_str = params.get("command", "").strip()
        if not cmd_str:
            return "ERROR: 'command' is required."

        # Safety: must start with an allowed prefix
        allowed = any(cmd_str.startswith(p) for p in _ALLOWED_NIX)
        if not allowed:
            return (
                f"ERROR: nix '{cmd_str}' is not allowed. "
                f"Allowed prefixes: {sorted(_ALLOWED_NIX)}"
            )

        import shlex
        cmd = ["nix"] + shlex.split(cmd_str)
        return _run(cmd, cwd=NIXOS_REPO_PATH, timeout=120)


# ---------------------------------------------------------------------------
# Tool: search_nix_files
# ---------------------------------------------------------------------------
@register_tool("search_nix_files")
class SearchNixFiles(BaseTool):
    """Grep for a pattern across all .nix files in the repository."""

    name = "search_nix_files"
    description = (
        "Search (grep) for a text pattern across all .nix files in the repo. "
        "Useful for finding where an option, package, or string is defined."
    )
    parameters = [
        {
            "name": "pattern",
            "type": "string",
            "description": "The text or regex pattern to search for.",
            "required": True,
        },
        {
            "name": "case_sensitive",
            "type": "boolean",
            "description": "Default true. Set false for case-insensitive search.",
            "required": False,
        },
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        pattern = params.get("pattern", "")
        case_sensitive = params.get("case_sensitive", True)

        if not pattern:
            return "ERROR: 'pattern' is required."

        flags = ["-rn", "--include=*.nix"]
        if not case_sensitive:
            flags.append("-i")

        cmd = ["grep"] + flags + [pattern, str(NIXOS_REPO_PATH)]
        return _run(cmd, cwd=NIXOS_REPO_PATH)
