"""
tools/nix_repl_tool.py
-----------------------------------------------------------------------
Interact with the nix repl from within qwen-agent.

Supports:
  • evaluate   – evaluate one or more Nix expressions and return results
  • describe   – run :t on an expression to get its type
  • doc        – run :doc on a builtin function
  • multi_step – run a sequence of statements (assignments + expressions)
                 in a single repl session, returning all outputs

Register in agent.py:
    from tools.nix_repl_tool import NixReplTool
    TOOLS = [..., "nix_repl"]
-----------------------------------------------------------------------
"""

import json
import os
import re
import subprocess
import shutil
import tempfile
from typing import Union

from qwen_agent.tools.base import BaseTool, register_tool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _nix_available() -> bool:
    return shutil.which("nix") is not None


def _run_repl(
    statements: list[str],
    load_nixpkgs: bool = False,
    load_file: str = "",
    load_flake: str = "",
    impure: bool = False,
    extra_flags: list[str] | None = None,
    timeout: int = 30,
) -> tuple[str, str]:
    """
    Drive `nix repl` non-interactively via stdin.

    Returns (stdout, stderr) as strings.
    """
    # Build the command
    cmd = ["nix", "repl"]

    if impure:
        cmd.append("--impure")

    if extra_flags:
        cmd.extend(extra_flags)

    # Positional installable (nixpkgs, flake ref, or file)
    if load_nixpkgs:
        cmd.append("<nixpkgs>")
    elif load_flake:
        cmd += ["--extra-experimental-features", "flakes repl-flake", load_flake]
    elif load_file:
        cmd += ["--file", load_file]

    # Build stdin: all statements, then :q so the process exits cleanly
    stdin_text = "\n".join(statements) + "\n:q\n"

    try:
        result = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return "", f"ERROR: nix repl timed out after {timeout}s"
    except FileNotFoundError:
        return "", "ERROR: 'nix' binary not found. Is Nix installed?"
    except Exception as exc:
        return "", f"ERROR: {exc}"


def _clean_repl_output(raw: str) -> str:
    """
    Strip the nix-repl prompts and the startup/shutdown banners,
    leaving only meaningful output lines.
    """
    lines = raw.splitlines()
    cleaned = []
    for line in lines:
        # Remove prompt prefix (nix-repl> or nix-repl< continuation)
        line = re.sub(r"^nix-repl[>< ]+", "", line)
        # Drop the "Welcome to Nix" banner and "Type :? for help" line
        if re.match(r"^Welcome to Nix", line):
            continue
        if re.match(r"^Type :[\?]", line):
            continue
        # Drop blank lines that result from the :q command itself
        cleaned.append(line)

    # Remove leading/trailing blank lines
    text = "\n".join(cleaned).strip()
    return text


def _format_result(stdout: str, stderr: str) -> str:
    out = _clean_repl_output(stdout)
    # Filter stderr: ignore noisy Nix trace lines that aren't real errors
    err_lines = [
        ln for ln in stderr.splitlines()
        if ln.strip()
        and not ln.startswith("trace:")
        and not re.match(r"^(this|these|copying|fetching|building|warning:)", ln, re.I)
    ]
    err = "\n".join(err_lines).strip()

    parts = []
    if out:
        parts.append(out)
    if err:
        parts.append(f"[stderr]\n{err}")
    return "\n".join(parts) if parts else "(no output)"


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

@register_tool("nix_repl")
class NixReplTool(BaseTool):
    """Evaluate Nix expressions in a live nix repl session."""

    name = "nix_repl"
    description = (
        "Run Nix expressions interactively using `nix repl`. "
        "Use this tool to:\n"
        "  • Evaluate any Nix expression (arithmetic, strings, lists, attrs, lambdas)\n"
        "  • Check the type of a value with :t\n"
        "  • Read builtin documentation with :doc\n"
        "  • Run multi-step sessions with variable bindings (x = 1; x + 2)\n"
        "  • Inspect nixpkgs attributes (e.g. pkgs.hello.version) when load_nixpkgs=true\n"
        "  • Load a local .nix file or a flake reference\n"
        "  • Describe derivation attributes or test Nix language constructs\n"
        "Always prefer this tool over guessing the output of a Nix expression."
    )
    parameters = [
        {
            "name": "expressions",
            "type": "array",
            "description": (
                "List of Nix statements/expressions to evaluate in order. "
                "Each entry is one line sent to the repl. "
                "Assignments use `name = expr` syntax. "
                "Prefix a line with ':t ' to get the type, ':doc ' for docs. "
                "Example: ['x = 42', 'x * 2', 'builtins.typeOf x']"
            ),
            "required": True,
        },
        {
            "name": "load_nixpkgs",
            "type": "boolean",
            "description": (
                "If true, start the repl with `<nixpkgs>` loaded so pkgs "
                "attributes are available (e.g. pkgs.hello.version). "
                "Slower to start. Defaults to false."
            ),
            "required": False,
        },
        {
            "name": "load_file",
            "type": "string",
            "description": (
                "Path to a local .nix file to load into scope on startup, "
                "e.g. './default.nix' or '/home/user/project/flake.nix'."
            ),
            "required": False,
        },
        {
            "name": "load_flake",
            "type": "string",
            "description": (
                "A flake reference to load, e.g. 'nixpkgs', "
                "'github:NixOS/nixpkgs/nixos-24.05', or a local path like '.'.\n"
                "Requires flakes experimental feature to be enabled."
            ),
            "required": False,
        },
        {
            "name": "impure",
            "type": "boolean",
            "description": (
                "Pass --impure to allow access to environment variables and "
                "mutable paths. Required for expressions like "
                "builtins.getEnv or importing from $HOME. Defaults to false."
            ),
            "required": False,
        },
        {
            "name": "timeout",
            "type": "integer",
            "description": (
                "Seconds to wait for the repl before killing it. "
                "Default 30. Increase for slow builds or large nixpkgs loads."
            ),
            "required": False,
        },
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        # Normalise params
        if isinstance(params, str):
            params = json.loads(params) if params.strip() else {}

        expressions: list = params.get("expressions", [])
        load_nixpkgs: bool = bool(params.get("load_nixpkgs", False))
        load_file: str = params.get("load_file", "").strip()
        load_flake: str = params.get("load_flake", "").strip()
        impure: bool = bool(params.get("impure", False))
        timeout: int = int(params.get("timeout", 30))

        # Validate
        if not expressions:
            return "ERROR: 'expressions' must be a non-empty list of strings."

        if not _nix_available():
            return (
                "ERROR: 'nix' is not installed or not on PATH. "
                "Install Nix from https://nixos.org/download/ and try again."
            )

        # Sanitise: each expression must be a string
        stmts = [str(e).rstrip() for e in expressions if str(e).strip()]
        if not stmts:
            return "ERROR: All expressions were empty after stripping whitespace."

        # Safety guard: block obviously destructive shell escapes
        dangerous = [";", "$(", "`", "system(", "builtins.exec"]
        for stmt in stmts:
            for d in dangerous:
                # Allow semicolons that are clearly attribute set syntax { a = 1; }
                if d == ";" and re.search(r"[{}]", stmt):
                    continue
                if d in stmt and d != ";":
                    return (
                        f"ERROR: Expression contains potentially unsafe pattern {d!r}. "
                        "Remove it and try again."
                    )

        # Run
        stdout, stderr = _run_repl(
            statements=stmts,
            load_nixpkgs=load_nixpkgs,
            load_file=load_file,
            load_flake=load_flake,
            impure=impure,
            timeout=timeout,
        )

        return _format_result(stdout, stderr)