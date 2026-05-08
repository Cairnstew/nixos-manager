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


class WebSearchTool(Tool):
    """Search the web using DuckDuckGo (no API key needed)."""

    name = "web_search"
    description = "Search the web for current information. Returns top results."
    inputs = {
        "query": {"type": "string", "description": "Search query."},
        "max_results": {
            "type": "integer",
            "description": "Number of results (default 5).",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(self, query: str, max_results: int = 5) -> str:
        try:
            import json
            import urllib.parse
            import urllib.request

            url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
            results = []
            if data.get("AbstractText"):
                results.append(data["AbstractText"])
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if "Text" in topic:
                    results.append(topic["Text"])
            return "\n\n".join(results) if results else "No results found."
        except Exception as exc:
            return f"Error: {exc}"


class PythonReplTool(Tool):
    """Execute Python code and return the output."""

    name = "python_repl"
    description = (
        "Executes Python code in a subprocess and returns stdout/stderr. "
        "Useful for quick calculations, data processing, or testing snippets."
    )
    inputs = {
        "code": {"type": "string", "description": "Python code to execute."},
    }
    output_type = "string"

    def forward(self, code: str) -> str:
        import sys

        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = result.stdout or result.stderr
            return out[:4000] if len(out) > 4000 else out
        except subprocess.TimeoutExpired:
            return "Error: timed out after 30 seconds"
        except Exception as exc:
            return f"Error: {exc}"


class ReadFileTool(Tool):
    """Read a file, with optional line range."""

    name = "read_file"
    description = "Read a file's contents. Optionally specify start/end lines."
    inputs = {
        "path": {"type": "string", "description": "Path to the file."},
        "start_line": {
            "type": "integer",
            "description": "First line to read (1-indexed).",
            "nullable": True,
        },
        "end_line": {
            "type": "integer",
            "description": "Last line to read (inclusive).",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(
        self, path: str, start_line: int | None = None, end_line: int | None = None
    ) -> str:
        try:
            with open(os.path.abspath(path), encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if start_line or end_line:
                s = (start_line or 1) - 1
                e = end_line or len(lines)
                lines = lines[s:e]
            content = "".join(lines)
            return content[:8000] if len(content) > 8000 else content
        except Exception as exc:
            return f"Error: {exc}"


class WriteFileTool(Tool):
    """Write or append content to a file."""

    name = "write_file"
    description = "Write content to a file. Creates the file if it doesn't exist."
    inputs = {
        "path": {"type": "string", "description": "Path to write to."},
        "content": {"type": "string", "description": "Content to write."},
        "append": {
            "type": "boolean",
            "description": "Append instead of overwrite.",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(self, path: str, content: str, append: bool = False) -> str:
        try:
            mode = "a" if append else "w"
            full = os.path.abspath(path)
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, mode, encoding="utf-8") as f:
                f.write(content)
            return f"Written {len(content)} chars to {full}"
        except Exception as exc:
            return f"Error: {exc}"


class ListDirTool(Tool):
    """List directory contents."""

    name = "list_dir"
    description = "List files and directories at a given path."
    inputs = {
        "path": {
            "type": "string",
            "description": "Directory path (default: current dir).",
            "nullable": True,
        },
        "recursive": {
            "type": "boolean",
            "description": "List recursively.",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(self, path: str = ".", recursive: bool = False) -> str:
        try:
            full = os.path.abspath(path)
            if recursive:
                lines = []
                for root, dirs, files in os.walk(full):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    rel = os.path.relpath(root, full)
                    prefix = "" if rel == "." else f"{rel}/"
                    for f in files:
                        lines.append(f"{prefix}{f}")
                return "\n".join(lines[:500])
            else:
                entries = sorted(os.listdir(full))
                return "\n".join(entries)
        except Exception as exc:
            return f"Error: {exc}"


class NixTool(Tool):
    """Run read-only NixOS commands."""

    name = "nix"
    description = (
        "Run nix commands: search packages, show info, evaluate expressions. "
        "Safe read-only nix operations only."
    )
    inputs = {
        "command": {
            "type": "string",
            "description": (
                "A nix CLI subcommand, e.g. 'search nixpkgs python', "
                "'eval --expr 'builtins.currentSystem'', 'show-config'."
            ),
        }
    }
    output_type = "string"

    _BLOCKED = [
        "build", "develop", "run", "shell", "copy",
        "delete", "store gc", "profile install", "profile remove",
    ]

    def forward(self, command: str) -> str:
        for blocked in self._BLOCKED:
            if command.strip().startswith(blocked):
                return f"Blocked: '{blocked}' is not permitted (read-only nix commands only)."
        try:
            result = subprocess.run(
                f"nix {command}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = result.stdout or result.stderr
            return out[:4000] if len(out) > 4000 else out
        except subprocess.TimeoutExpired:
            return "Error: timed out"
        except Exception as exc:
            return f"Error: {exc}"


# --------------------------------------------------------------------------- #
# Registry                                                                     #
# --------------------------------------------------------------------------- #

BUILTIN_TOOLS: dict[str, type[Tool]] = {
    "calculator": CalculatorTool,
    "datetime": DateTimeTool,
    "shell": ShellTool,
    "file_reader": FileReaderTool,
    "web_search": WebSearchTool,
    "python_repl": PythonReplTool,
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "list_dir": ListDirTool,
    "nix": NixTool,
}

TOOL_PRESETS: dict[str, list[str]] = {
    "minimal":  ["calculator", "datetime"],
    "coding":   ["calculator", "datetime", "python_repl", "read_file", "write_file", "list_dir", "shell"],
    "nixos":    ["calculator", "datetime", "python_repl", "read_file", "write_file", "list_dir", "shell", "nix"],
    "research": ["calculator", "datetime", "web_search", "python_repl"],
    "full":     list(BUILTIN_TOOLS.keys()),
}


def get_default_tools() -> list[Tool]:
    """Return the default safe toolset (calculator + datetime)."""
    return [CalculatorTool(), DateTimeTool()]


def get_preset_tools(preset: str) -> list[Tool]:
    """Return a named tool preset.

    Special presets:
      ``mcp-nixos``   — real NixOS package/option data via mcp-nixos
      ``nixos-full``  — local nix tool + mcp-nixos combined
    """
    if preset == "mcp-nixos":
        from ollama_agent.tools.mcp_tools import get_mcp_nixos_tools
        return get_mcp_nixos_tools()

    if preset == "nixos-full":
        from ollama_agent.tools.mcp_tools import get_mcp_nixos_tools
        base = [BUILTIN_TOOLS[n]() for n in TOOL_PRESETS["nixos"]]
        return base + get_mcp_nixos_tools()

    names = TOOL_PRESETS.get(preset)
    if names is None:
        raise ValueError(
            f"Unknown preset '{preset}'. "
            f"Choose from: {list(TOOL_PRESETS) + ['mcp-nixos', 'nixos-full']}"
        )
    return [BUILTIN_TOOLS[n]() for n in names]