"""
config/context.py — reads the user's NixOS config repo and produces
a compact context snapshot for injection into the pipeline.

Called once per pipeline run (cheap — just filesystem reads).
Produces two things:
  1. A file-tree string  (always included)
  2. A concatenated excerpt of all .nix files  (truncated to NIXOS_CONTEXT_MAX_CHARS)
"""

from __future__ import annotations

from pathlib import Path

from .settings import (
    NIXOS_REPO_PATH,
    NIX_EXTENSIONS,
    IGNORED_DIRS,
    NIXOS_CONTEXT_MAX_LINES_PER_FILE,
    NIXOS_CONTEXT_MAX_CHARS,
)


def _iter_nix_files(root: Path) -> list[Path]:
    """Walk root and return all .nix files, skipping ignored dirs."""
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        # Skip any path component that is an ignored dir
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.suffix in NIX_EXTENSIONS and path.is_file():
            files.append(path)
    return files


def build_file_tree(root: Path) -> str:
    """
    Returns a compact tree string like:
        nixos-config/
          flake.nix
          modules/
            home/firefox/default.nix
            nixos/postgresql/default.nix
    """
    if not root.exists():
        return f"(config repo not found at {root})"

    lines = [f"{root.name}/"]
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root)
        depth = len(rel.parts)
        indent = "  " * depth
        suffix = "/" if path.is_dir() else ""
        lines.append(f"{indent}{rel.name}{suffix}")

    return "\n".join(lines)


def build_file_excerpts(files: list[Path], root: Path) -> str:
    """
    Concatenate excerpts of all .nix files, each headed by its relative path.
    Truncated to NIXOS_CONTEXT_MAX_CHARS total.
    """
    parts: list[str] = []
    total = 0

    for f in files:
        rel = f.relative_to(root)
        try:
            raw_lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        if NIXOS_CONTEXT_MAX_LINES_PER_FILE > 0:
            truncated = raw_lines[:NIXOS_CONTEXT_MAX_LINES_PER_FILE]
            tail = f"\n  ... ({len(raw_lines) - len(truncated)} more lines)" if len(raw_lines) > len(truncated) else ""
        else:
            truncated = raw_lines
            tail = ""

        block = f"### {rel}\n" + "\n".join(truncated) + tail + "\n"

        if total + len(block) > NIXOS_CONTEXT_MAX_CHARS:
            remaining = NIXOS_CONTEXT_MAX_CHARS - total
            if remaining > 80:
                parts.append(block[:remaining] + "\n... (truncated)")
            break

        parts.append(block)
        total += len(block)

    return "\n".join(parts)


def get_config_context() -> str:
    """
    Main entry point.  Returns a Markdown-formatted string containing:
      - The repo path
      - A file tree
      - Excerpts of every .nix file (within size limits)

    Returns a short message if the repo path doesn't exist,
    so the pipeline can still run without a config.
    """
    root = NIXOS_REPO_PATH

    if not root.exists():
        return (
            f"## NixOS Config Context\n"
            f"No config found at `{root}`. "
            f"Set NIXOS_REPO_PATH to your config directory.\n"
        )

    nix_files = _iter_nix_files(root)
    tree = build_file_tree(root)
    excerpts = build_file_excerpts(nix_files, root)

    return (
        f"## NixOS Config Context\n"
        f"**Repo:** `{root}`  "
        f"**Files:** {len(nix_files)} .nix files\n\n"
        f"### File Tree\n```\n{tree}\n```\n\n"
        f"### File Contents\n{excerpts}"
    )