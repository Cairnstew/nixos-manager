"""
tools/nixos_unified_tool.py
-----------------------------------------------------------------------
Search and navigate the nixos-unified documentation at nixos-unified.org.

nixos-unified is a flake-parts module that unifies NixOS + nix-darwin +
home-manager configuration in a single flake, providing one-click activation,
seamless module access to top-level flake inputs, and optional autowiring of
flake outputs from directory structure.

Register in agent.py:
    from tools.nixos_unified_tool import NixosUnifiedTool
    TOOLS = [..., "nixos_unified_docs"]
-----------------------------------------------------------------------
"""

import json
import re
import urllib.request
import urllib.error
from typing import Union

from qwen_agent.tools.base import BaseTool, register_tool


# ---------------------------------------------------------------------------
# Site map — every page on nixos-unified.org (it's a small static site)
# ---------------------------------------------------------------------------

SITE_PAGES: dict[str, str] = {
    "home":           "https://nixos-unified.org/",
    "start":          "https://nixos-unified.org/start",
    "guide":          "https://nixos-unified.org/guide",
    "templates":      "https://nixos-unified.org/guide/templates",
    "activate":       "https://nixos-unified.org/guide/activate",
    "specialargs":    "https://nixos-unified.org/guide/specialArgs",
    "outputs":        "https://nixos-unified.org/guide/outputs",
    "autowiring":     "https://nixos-unified.org/guide/autowiring",
    "howto":          "https://nixos-unified.org/howto",
    "examples":       "https://nixos-unified.org/examples",
    "history":        "https://nixos-unified.org/history",
}

# Keyword → page key(s) to prioritise
KEYWORD_MAP: dict[str, list[str]] = {
    # getting started / setup
    "start":            ["start"],
    "getting started":  ["start"],
    "install":          ["start"],
    "setup":            ["start"],
    "nixos":            ["start", "templates", "activate"],
    "macos":            ["start", "templates"],
    "darwin":           ["start", "templates", "activate"],
    "home-manager":     ["start", "templates", "activate", "specialargs"],
    "home manager":     ["start", "templates", "activate", "specialargs"],
    "linux":            ["start"],
    # templates
    "template":         ["templates"],
    "flake template":   ["templates"],
    "flake.nix":        ["templates", "autowiring"],
    # activation
    "activate":         ["activate"],
    "activation":       ["activate"],
    "deploy":           ["activate"],
    "deployment":       ["activate"],
    "remote":           ["activate"],
    "ssh":              ["activate"],
    "update":           ["activate"],
    "colmena":          ["activate"],
    "deploy-rs":        ["activate"],
    # specialArgs / module arguments
    "specialargs":      ["specialargs"],
    "specialarg":       ["specialargs"],
    "module arguments": ["specialargs"],
    "module args":      ["specialargs"],
    "flake inputs":     ["specialargs"],
    "top-level flake":  ["specialargs"],
    # flake outputs
    "outputs":          ["outputs"],
    "flake outputs":    ["outputs"],
    "nixosconfigurations": ["outputs", "autowiring"],
    "darwinconfigurations":["outputs", "autowiring"],
    "homeconfigurations":  ["outputs", "autowiring"],
    # autowiring
    "autowiring":       ["autowiring"],
    "autowire":         ["autowiring"],
    "directory":        ["autowiring"],
    "directory structure": ["autowiring"],
    "packages/":        ["autowiring"],
    "configurations/":  ["autowiring"],
    "modules/":         ["autowiring"],
    "overlays/":        ["autowiring"],
    "mkflake":          ["autowiring"],
    # howto
    "howto":            ["howto"],
    "how to":           ["howto"],
    "shared config":    ["howto"],
    "shared configuration": ["howto"],
    "username":         ["howto"],
    "email":            ["howto"],
    "config-module":    ["howto"],
    # examples
    "example":          ["examples"],
    "examples":         ["examples"],
    "nixos-config":     ["examples"],
    "nixos-unified-template": ["examples", "templates"],
    # history / changelog
    "history":          ["history"],
    "release":          ["history"],
    "changelog":        ["history"],
    "version":          ["history"],
    # general / overview
    "overview":         ["home"],
    "why":              ["home"],
    "features":         ["home"],
    "flake-parts":      ["home", "autowiring"],
    "nix-darwin":       ["home", "start", "templates"],
    "unified":          ["home"],
}

# Maximum characters returned to the LLM
MAX_OUTPUT = 6000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch(url: str, timeout: int = 10) -> str:
    """Fetch a URL and return plain text (HTML tags stripped)."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "nixos-unified-docs-tool/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return f"ERROR: HTTP {exc.code} — {url}"
    except Exception as exc:
        return f"ERROR: {exc}"

    # Strip <script> and <style> blocks
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.S | re.I)
    # Strip all remaining HTML tags
    text = re.sub(r"<[^>]+>", "", raw)
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _snippets(text: str, query: str, context: int = 500, max_hits: int = 6) -> list[str]:
    """Extract short excerpts from *text* around each occurrence of query words."""
    words = [w.lower() for w in re.split(r"\W+", query) if len(w) > 2]
    if not words:
        return []

    lower = text.lower()
    hits: list[str] = []
    seen: set[int] = set()

    for word in words:
        pos = 0
        while len(hits) < max_hits:
            idx = lower.find(word, pos)
            if idx == -1:
                break
            if all(abs(idx - s) > context for s in seen):
                seen.add(idx)
                s = max(0, idx - context // 2)
                e = min(len(text), idx + context // 2)
                hits.append("…" + text[s:e].strip() + "…")
            pos = idx + 1

    return hits


def _pick_pages(query: str) -> list[str]:
    """Return an ordered list of page keys most relevant to *query*."""
    q_lower = query.lower()
    seen: dict[str, int] = {}  # key → priority score

    for kw, pages in KEYWORD_MAP.items():
        if kw in q_lower:
            for i, page in enumerate(pages):
                seen[page] = seen.get(page, 0) + (10 - i)

    # Sort by descending score, fall back to a sensible default order
    ordered = sorted(seen, key=lambda k: -seen[k])

    # Always include home + guide as backstops if nothing matched
    for fallback in ("home", "guide"):
        if fallback not in ordered:
            ordered.append(fallback)

    return ordered


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

@register_tool("nixos_unified_docs")
class NixosUnifiedTool(BaseTool):
    """Look up nixos-unified documentation."""

    name = "nixos_unified_docs"
    description = (
        "Search and retrieve content from the nixos-unified documentation at "
        "https://nixos-unified.org/. "
        "nixos-unified is a flake-parts module that unifies NixOS, nix-darwin, and "
        "home-manager configuration in a single flake. "
        "Use this tool when the user asks about:\n"
        "  • Setting up or getting started with nixos-unified\n"
        "  • Flake templates for NixOS / macOS / home-manager\n"
        "  • The .#activate or .#update flake apps (one-click deployment)\n"
        "  • Remote activation over SSH\n"
        "  • specialArgs and how modules access top-level flake inputs\n"
        "  • Flake outputs (nixosConfigurations, darwinConfigurations, etc.)\n"
        "  • Autowiring (automatic flake output wiring from directory structure)\n"
        "  • Shared configuration patterns (HOWTO)\n"
        "  • Examples and real-world nixos-unified configs\n"
        "  • Release history / changelog\n"
        "Always call this tool before answering nixos-unified questions instead of "
        "relying on potentially stale training data."
    )
    parameters = [
        {
            "name": "query",
            "type": "string",
            "description": (
                "What the user wants to know, e.g. "
                "'how do I activate on macOS', "
                "'what is autowiring', "
                "'how to share username across modules', "
                "'flake template for home-manager only'."
            ),
            "required": True,
        },
        {
            "name": "page",
            "type": "string",
            "description": (
                "Optional. Force a specific documentation page. "
                "One of: home, start, guide, templates, activate, specialargs, "
                "outputs, autowiring, howto, examples, history."
            ),
            "required": False,
        },
        {
            "name": "full_page",
            "type": "boolean",
            "description": (
                "If true, return the full page text instead of query-matched "
                "snippets. Useful when you want to read the entire section. "
                "Defaults to false."
            ),
            "required": False,
        },
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params) if params.strip() else {}

        query: str = params.get("query", "").strip()
        forced_page: str = params.get("page", "").strip().lower()
        full_page: bool = bool(params.get("full_page", False))

        if not query and not forced_page:
            return "ERROR: 'query' is required."

        # ------------------------------------------------------------------
        # Determine which pages to fetch
        # ------------------------------------------------------------------
        if forced_page:
            if forced_page not in SITE_PAGES:
                valid = ", ".join(sorted(SITE_PAGES))
                return (
                    f"ERROR: Unknown page {forced_page!r}. "
                    f"Valid pages: {valid}"
                )
            page_keys = [forced_page]
        else:
            page_keys = _pick_pages(query)

        # ------------------------------------------------------------------
        # Fetch and search pages until we get good hits
        # ------------------------------------------------------------------
        results: list[str] = []
        pages_checked = 0

        for key in page_keys:
            if pages_checked >= 3:  # cap fetches per call
                break

            url = SITE_PAGES[key]
            text = _fetch(url)
            pages_checked += 1

            if text.startswith("ERROR:"):
                results.append(f"[{url}]\n{text}")
                continue

            if full_page or not query:
                excerpt = text[:MAX_OUTPUT]
                results.append(f"### [{key}]({url})\n\n{excerpt}")
                break

            hits = _snippets(text, query)
            if hits:
                joined = "\n\n---\n\n".join(hits)
                results.append(f"### [{key}]({url})\n\n{joined}")
                # Good match found — no need to check more pages
                break
            else:
                # No keyword hit; include top of page as context and try next
                results.append(
                    f"### [{key}]({url})\n"
                    f"_(No exact match for '{query}' — page summary)_\n\n"
                    + text[:800]
                )
                # Keep looping to find a better page

        if not results:
            return (
                f"No results found for '{query}'. "
                f"Available pages: {', '.join(SITE_PAGES.keys())}"
            )

        output = "\n\n========\n\n".join(results)
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + "\n\n[...truncated — use full_page=true for more]"

        return output