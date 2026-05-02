"""
tools/repo_reader.py
Custom qwen-agent tools for reading the NixOS config repository.
"""

from pathlib import Path
from typing import Union

from qwen_agent.tools.base import BaseTool, register_tool

from config.settings import NIXOS_REPO_PATH, NIX_EXTENSIONS, IGNORED_DIRS


# ---------------------------------------------------------------------------
# Tool: list_nix_files
# ---------------------------------------------------------------------------
@register_tool("list_nix_files")
class ListNixFiles(BaseTool):
    """Return a tree of all .nix files in the managed repository."""

    name = "list_nix_files"
    description = (
        "List every .nix file in the NixOS configuration repository, "
        "showing their relative paths. Use this to understand the layout "
        "before reading or editing files."
    )
    parameters = [
        {
            "name": "subdir",
            "type": "string",
            "description": (
                "Optional subdirectory relative to the repo root to limit the listing. "
                "Omit to list everything."
            ),
            "required": False,
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            import json
            params = json.loads(params) if params.strip() else {}

        subdir = params.get("subdir", "")
        root = NIXOS_REPO_PATH / subdir if subdir else NIXOS_REPO_PATH

        if not root.exists():
            return f"ERROR: path does not exist: {root}"

        lines = []
        for path in sorted(root.rglob("*")):
            # Skip ignored dirs
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if path.suffix in NIX_EXTENSIONS and path.is_file():
                lines.append(str(path.relative_to(NIXOS_REPO_PATH)))

        if not lines:
            return "No .nix files found."
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: read_nix_file
# ---------------------------------------------------------------------------
@register_tool("read_nix_file")
class ReadNixFile(BaseTool):
    """Read the contents of a single .nix file from the repository."""

    name = "read_nix_file"
    description = (
        "Read and return the full contents of a specific .nix file "
        "from the NixOS configuration repository."
    )
    parameters = [
        {
            "name": "path",
            "type": "string",
            "description": "Path to the file, relative to the repository root.",
            "required": True,
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            import json
            params = json.loads(params)

        rel = params.get("path", "")
        if not rel:
            return "ERROR: 'path' parameter is required."

        target = NIXOS_REPO_PATH / rel
        if not target.exists():
            return f"ERROR: file not found: {target}"
        if target.suffix not in NIX_EXTENSIONS:
            return f"ERROR: not a .nix file: {rel}"

        try:
            return target.read_text(encoding="utf-8")
        except Exception as exc:
            return f"ERROR reading file: {exc}"
