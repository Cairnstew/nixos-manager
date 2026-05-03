"""
tools/repo_writer.py
Custom qwen-agent tools for writing / patching NixOS config files.

Safety philosophy:
  - Every write creates a timestamped .bak beside the original first.
  - An optional dry_run flag lets the agent preview changes without touching disk.
  - Writes outside the repo root are rejected.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Union

from qwen_agent.tools.base import BaseTool, register_tool

from config.settings import NIXOS_REPO_PATH, NIX_EXTENSIONS


def _safe_target(rel: str) -> tuple[Path, str | None]:
    """Resolve and validate that the target sits inside the repo root."""
    target = (NIXOS_REPO_PATH / rel).resolve()
    try:
        target.relative_to(NIXOS_REPO_PATH.resolve())
    except ValueError:
        return target, "ERROR: path escapes repository root — write rejected."
    return target, None


# ---------------------------------------------------------------------------
# Tool: write_nix_file
# ---------------------------------------------------------------------------
@register_tool("write_nix_file")
class WriteNixFile(BaseTool):
    """Overwrite (or create) a .nix file with new content."""

    name = "write_nix_file"
    description = (
        "Write content to a .nix file in the NixOS config repository. "
        "The previous version is backed up automatically. "
        "Pass dry_run=true to preview what would be written without changing anything."
    )
    parameters = [
        {
            "name": "path",
            "type": "string",
            "description": "Path relative to the repository root.",
            "required": True,
        },
        {
            "name": "content",
            "type": "string",
            "description": "Full new content for the file.",
            "required": True,
        },
        {
            "name": "dry_run",
            "type": "boolean",
            "description": "If true, return a preview without writing. Default false.",
            "required": False,
        },
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        rel = params.get("path", "")
        content = params.get("content", "")
        dry_run = params.get("dry_run", False)

        if not rel:
            return "ERROR: 'path' is required."
        if not content:
            return "ERROR: 'content' is required."

        target, err = _safe_target(rel)
        if err:
            return err
        if target.suffix not in NIX_EXTENSIONS:
            return f"ERROR: only .nix files are allowed, got: {target.suffix}"

        if dry_run:
            return (
                f"DRY RUN — would write {len(content)} chars to {rel}:\n\n"
                + content[:2000]
                + ("\n…(truncated)" if len(content) > 2000 else "")
            )

        # Backup existing file
        if target.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            bak = target.with_suffix(f".nix.bak_{stamp}")
            shutil.copy2(target, bak)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"OK: wrote {len(content)} chars to {rel}."


# ---------------------------------------------------------------------------
# Tool: patch_nix_file
# ---------------------------------------------------------------------------
@register_tool("patch_nix_file")
class PatchNixFile(BaseTool):
    """Replace an exact substring in a .nix file (surgical edits)."""

    name = "patch_nix_file"
    description = (
        "Replace one exact string with another inside a .nix file. "
        "Safer than rewriting the whole file for small changes. "
        "Fails if old_text appears zero or more than once."
    )
    parameters = [
        {
            "name": "path",
            "type": "string",
            "description": "Path relative to the repository root.",
            "required": True,
        },
        {
            "name": "old_text",
            "type": "string",
            "description": "The exact text to find and replace.",
            "required": True,
        },
        {
            "name": "new_text",
            "type": "string",
            "description": "The replacement text.",
            "required": True,
        },
        {
            "name": "dry_run",
            "type": "boolean",
            "description": "Preview only; do not write.",
            "required": False,
        },
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params)

        rel = params.get("path", "")
        old_text = params.get("old_text", "")
        new_text = params.get("new_text", "")
        dry_run = params.get("dry_run", False)

        if not rel or old_text is None or new_text is None:
            return "ERROR: 'path', 'old_text', and 'new_text' are all required."

        target, err = _safe_target(rel)
        if err:
            return err
        if not target.exists():
            return f"ERROR: file not found: {rel}"

        original = target.read_text(encoding="utf-8")
        count = original.count(old_text)
        if count == 0:
            return "ERROR: old_text not found in file — no changes made."
        if count > 1:
            return f"ERROR: old_text found {count} times; must be unique — no changes made."

        patched = original.replace(old_text, new_text, 1)

        if dry_run:
            return f"DRY RUN — would replace 1 occurrence in {rel}."

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        bak = target.with_suffix(f".nix.bak_{stamp}")
        shutil.copy2(target, bak)

        target.write_text(patched, encoding="utf-8")
        return f"OK: patched {rel} (backup → {bak.name})."