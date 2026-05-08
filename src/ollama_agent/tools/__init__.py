"""Built-in tools for ollama_agent."""

from __future__ import annotations

import datetime
import math
import os
import subprocess
from typing import Any

from smolagents import Tool


class CalculatorTool(Tool):
    """Safely evaluate simple mathematical expressions."""

    name = "calculator"
    description = (
        "Evaluates a mathematical expression and returns the numeric result. "
        "Supports +, -, *, /, **, sqrt, sin, cos, log, abs, round, etc."
    )
    inputs = {
        "expression": {
            "type": "string",
            "description": "A Python-compatible math expression, e.g. '2 ** 10' or 'sqrt(144)'.",
        }
    }
    output_type = "string"

    _SAFE_GLOBALS: dict[str, Any] = {
        "__builtins__": {},
        **{name: getattr(math, name) for name in dir(math) if not name.startswith("_")},
        "abs": abs,
        "round": round,
        "int": int,
        "float": float,
    }

    def forward(self, expression: str) -> str:
        try:
            result = eval(expression, self._SAFE_GLOBALS, {})  # noqa: S307
            return str(result)
        except Exception as exc:
            return f"Error: {exc}"


class DateTimeTool(Tool):
    """Return the current UTC date and time."""

    name = "datetime"
    description = "Returns the current UTC date and time in ISO 8601 format."
    inputs: dict[str, Any] = {}
    output_type = "string"

    def forward(self) -> str:
        return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


class ShellTool(Tool):
    """Run a shell command and capture its output.

    Warning: only enable in trusted environments.
    """

    name = "shell"
    description = (
        "Runs a shell command and returns its stdout/stderr. "
        "Use only for safe, non-destructive commands."
    )
    inputs = {
        "command": {
            "type": "string",
            "description": "Shell command to execute.",
        }
    }
    output_type = "string"

    _BLOCKED_PATTERNS = ["rm -rf", "mkfs", "dd if=", ":(){:|:&};:"]

    def forward(self, command: str) -> str:
        for pat in self._BLOCKED_PATTERNS:
            if pat in command:
                return f"Blocked: command contains forbidden pattern '{pat}'"
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30
            )
            output = result.stdout or result.stderr
            return output[:4000] if len(output) > 4000 else output
        except subprocess.TimeoutExpired:
            return "Error: command timed out after 30 seconds"
        except Exception as exc:
            return f"Error: {exc}"


class FileReaderTool(Tool):
    """Read a text file from the local filesystem."""

    name = "file_reader"
    description = "Reads a text file and returns its contents."
    inputs = {
        "path": {
            "type": "string",
            "description": "Absolute or relative path to the file.",
        },
        "max_chars": {
            "type": "integer",
            "description": "Maximum characters to return (default 8000).",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(self, path: str, max_chars: int = 8000) -> str:
        try:
            with open(os.path.abspath(path), encoding="utf-8", errors="replace") as fh:
                return fh.read(max_chars)
        except Exception as exc:
            return f"Error reading file: {exc}"


BUILTIN_TOOLS: dict[str, type[Tool]] = {
    "calculator": CalculatorTool,
    "datetime": DateTimeTool,
    "shell": ShellTool,
    "file_reader": FileReaderTool,
}


def get_default_tools() -> list[Tool]:
    """Return the default safe toolset (calculator + datetime)."""
    return [CalculatorTool(), DateTimeTool()]