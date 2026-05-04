"""
tools/nix_docs_tool.py
-----------------------------------------------------------------------
A tool for navigating and searching the official Nix reference manual.
Register by importing in agent.py and adding "nix_docs" to TOOLS.
-----------------------------------------------------------------------
"""

import json
import re
import urllib.request
import urllib.error
from typing import Union

from qwen_agent.tools.base import BaseTool, register_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Known top-level sections and their URL slugs (relative to the manual root).
# Used to map vague topics to the most relevant starting page.
SECTION_MAP = {
    # language
    "language": "language/",
    "nix language": "language/",
    "syntax": "language/syntax",
    "types": "language/types",
    "data types": "language/types",
    "builtins": "language/builtins",
    "built-ins": "language/builtins",
    "operators": "language/operators",
    "derivations": "language/derivations",
    "string interpolation": "language/string-interpolation",
    "scoping": "language/scope",
    # store
    "store": "store/",
    "nix store": "store/",
    "store path": "store/store-path",
    "store object": "store/store-object",
    "store types": "store/types/",
    # installation
    "installation": "installation/",
    "install": "installation/",
    "uninstall": "installation/uninstall",
    "upgrade": "installation/upgrading",
    "docker": "installation/installing-docker",
    # package management
    "package management": "package-management/",
    "profiles": "package-management/profiles",
    "garbage collection": "package-management/garbage-collection",
    "gc": "package-management/garbage-collection",
    # commands
    "commands": "command-ref/",
    "command reference": "command-ref/",
    "nix-build": "command-ref/nix-build",
    "nix-shell": "command-ref/nix-shell",
    "nix-store": "command-ref/nix-store",
    "nix-env": "command-ref/nix-env",
    "nix-channel": "command-ref/nix-channel",
    "nix-collect-garbage": "command-ref/nix-collect-garbage",
    "nix-copy-closure": "command-ref/nix-copy-closure",
    "nix-daemon": "command-ref/nix-daemon",
    "nix-hash": "command-ref/nix-hash",
    "nix-instantiate": "command-ref/nix-instantiate",
    "nix-prefetch-url": "command-ref/nix-prefetch-url",
    # new-style nix CLI
    "new cli": "command-ref/new-cli/nix",
    "nix flake": "command-ref/new-cli/nix3-flake",
    "flakes": "command-ref/new-cli/nix3-flake",
    "nix develop": "command-ref/new-cli/nix3-develop",
    "nix run": "command-ref/new-cli/nix3-run",
    "nix build": "command-ref/new-cli/nix3-build",
    "nix profile": "command-ref/new-cli/nix3-profile",
    # advanced
    "advanced topics": "advanced-topics/",
    "remote builds": "advanced-topics/distributed-builds",
    "binary cache": "package-management/binary-cache-substituter",
    # config
    "configuration": "command-ref/conf-file",
    "config": "command-ref/conf-file",
    "settings": "command-ref/conf-file",
    "environment variables": "command-ref/env-common",
    # misc
    "introduction": "introduction",
    "quick start": "quick-start",
    "glossary": "glossary",
    "release notes": "release-notes/",
}


def _resolve_version(version: str) -> str:
    """Normalise version string, e.g. '2.26' or 'stable' or ''."""
    v = version.strip()
    if not v or v.lower() in ("latest", "stable", "current"):
        return "stable"
    return v


def _build_url(version: str, path: str) -> str:
    base = f"https://nix.dev/manual/nix/{version}/"
    # Avoid double slashes
    path = path.lstrip("/")
    return base + path


def _fetch_page(url: str, timeout: int = 60) -> str:
    """Fetch a URL and return its text content, stripping HTML tags."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "nix-docs-tool/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return f"ERROR: HTTP {exc.code} fetching {url}"
    except Exception as exc:
        return f"ERROR: {exc}"

    # Strip script / style blocks first
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.S | re.I)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", raw)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _search_in_text(text: str, query: str, context_chars: int = 400) -> list[str]:
    """Return snippets from *text* around every occurrence of *query* words."""
    words = [w.lower() for w in query.split() if len(w) > 2]
    if not words:
        return []

    lower_text = text.lower()
    hits: list[str] = []
    seen_positions: set[int] = set()

    for word in words:
        start = 0
        while True:
            pos = lower_text.find(word, start)
            if pos == -1:
                break
            # Avoid overlapping snippets
            if all(abs(pos - s) > context_chars for s in seen_positions):
                seen_positions.add(pos)
                snippet_start = max(0, pos - context_chars // 2)
                snippet_end = min(len(text), pos + context_chars // 2)
                snippet = text[snippet_start:snippet_end].strip()
                hits.append(f"…{snippet}…")
            start = pos + 1
            if len(hits) >= 8:
                break
        if len(hits) >= 8:
            break

    return hits


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

@register_tool("nix_docs")
class NixDocsTool(BaseTool):
    """Browse and search the official Nix reference manual."""

    name = "nix_docs"
    description = (
        "Fetch and search the official Nix reference manual at nix.dev. "
        "Use this tool whenever the user asks about Nix language syntax, built-ins, "
        "derivations, nix commands (nix-build, nix-shell, nix-env, nix flakes, etc.), "
        "the Nix store, profiles, garbage collection, configuration options, or any "
        "other topic covered by the Nix documentation. "
        "Provide a 'query' describing what to look up and optionally a 'section' "
        "(e.g. 'language', 'builtins', 'nix-build', 'flakes', 'store', 'configuration') "
        "and a 'version' (e.g. '2.26'; defaults to 'stable')."
    )
    parameters = [
        {
            "name": "query",
            "type": "string",
            "description": (
                "What to look up in the Nix documentation, e.g. "
                "'how to write a derivation', 'builtins.fetchGit', 'nix-shell flags'."
            ),
            "required": True,
        },
        {
            "name": "section",
            "type": "string",
            "description": (
                "Optional. Hint for which section to open first. "
                "Examples: 'language', 'builtins', 'derivations', 'nix-build', "
                "'nix-shell', 'flakes', 'store', 'configuration', 'garbage collection', "
                "'installation', 'commands', 'quick start'."
            ),
            "required": False,
        },
        {
            "name": "version",
            "type": "string",
            "description": (
                "Nix manual version to consult, e.g. '2.26', '2.24', 'stable'. "
                "Defaults to 'stable' (the current stable release)."
            ),
            "required": False,
        },
        {
            "name": "url",
            "type": "string",
            "description": (
                "Optional. Exact nix.dev manual URL to fetch directly, "
                "e.g. 'https://nix.dev/manual/nix/2.26/language/builtins'. "
                "Takes precedence over section/query-based navigation."
            ),
            "required": False,
        },
    ]

    # Maximum characters returned to the LLM to stay within context limits.
    MAX_CONTENT = 6000

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params) if params.strip() else {}

        query: str = params.get("query", "").strip()
        section: str = params.get("section", "").strip().lower()
        version: str = _resolve_version(params.get("version", "stable"))
        direct_url: str = params.get("url", "").strip()

        if not query and not direct_url:
            return "ERROR: 'query' is required (or provide a direct 'url')."

        # ------------------------------------------------------------------
        # 1. Determine which URL(s) to fetch
        # ------------------------------------------------------------------
        urls_to_try: list[str] = []

        if direct_url:
            urls_to_try.append(direct_url)
        else:
            # Map section hint to a URL path
            section_path = SECTION_MAP.get(section, "")

            # Also try to derive a path from the query itself
            query_path = SECTION_MAP.get(query.lower(), "")

            # Build candidate URLs (most specific first)
            if section_path:
                urls_to_try.append(_build_url(version, section_path))
            if query_path and query_path != section_path:
                urls_to_try.append(_build_url(version, query_path))
            # Always include the index as a fallback
            urls_to_try.append(_build_url(version, ""))

        # ------------------------------------------------------------------
        # 2. Fetch pages and search for the query
        # ------------------------------------------------------------------
        results: list[str] = []

        for url in urls_to_try:
            text = _fetch_page(url)
            if text.startswith("ERROR:"):
                results.append(f"[{url}]\n{text}")
                continue

            snippets = _search_in_text(text, query)
            if snippets:
                joined = "\n---\n".join(snippets)
                results.append(
                    f"[Source: {url}]\n\n{joined}"
                )
                # If we found good hits, no need to fall through
                break
            else:
                # Return first MAX_CONTENT chars of the page even if no
                # keyword hit — the LLM can still reason over it.
                results.append(
                    f"[Source: {url}]\n"
                    f"(No exact keyword match for '{query}' — showing page start)\n\n"
                    + text[: self.MAX_CONTENT]
                )
                break  # One page is enough for the LLM to work with

        if not results:
            return f"Could not retrieve Nix documentation for query: {query!r}"

        output = "\n\n========\n\n".join(results)
        # Hard-cap total length
        if len(output) > self.MAX_CONTENT:
            output = output[: self.MAX_CONTENT] + "\n\n[...truncated...]"

        return output