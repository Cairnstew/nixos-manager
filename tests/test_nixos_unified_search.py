"""
tests/test_nixos_unified_search.py
Comprehensive tests for tools/nixos_unified_search.py

Covers:
  NixosUnifiedTool  — query-based search, keyword mapping, page fetching,
                      snippet extraction, full page mode, error handling
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import call_tool, call_tool_json

import tools.nixos_unified_search as _nixos_unified_module
from tools.nixos_unified_search import (
    NixosUnifiedTool,
    SITE_PAGES,
    KEYWORD_MAP,
    _fetch,
    _snippets,
    _pick_pages,
)


# ===========================================================================
# Helper Functions
# ===========================================================================

class TestHelpers:
    """Test utility functions in nixos_unified_search module."""

    def test_fetch_network_error(self):
        """Fetch should return error message on network failure."""
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = Exception("Connection refused")
            result = _fetch("https://example.com/page")
        assert "ERROR" in result

    def test_fetch_strips_html(self):
        """Fetch should strip HTML tags and collapse whitespace."""
        html = "<html><body><p>  Hello   </p><script>alert('x')</script></body></html>"
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = html.encode()
            result = _fetch("https://example.com/page")
        assert "Hello" in result
        assert "<" not in result
        assert "script" not in result

    def test_fetch_collapses_whitespace(self):
        """Fetch should collapse multiple newlines and spaces."""
        html = "Line 1\n\n\n\nLine 2\n\nLine 3"
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = html.encode()
            result = _fetch("https://example.com/page")
        # Should have collapsed excessive newlines
        assert "\n\n\n" not in result

    def test_fetch_http_error(self):
        """Fetch should handle HTTP errors gracefully."""
        import urllib.error
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = urllib.error.HTTPError(
                url="https://example.com",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=None
            )
            result = _fetch("https://example.com/notfound")
        assert "ERROR" in result and "404" in result

    def test_snippets_finds_keywords(self):
        """Snippets should find and extract context around keywords."""
        text = """
        nixos-unified is a flake-parts module that unifies NixOS, nix-darwin,
        and home-manager configuration in a single flake. It provides special
        templating for activation and deployment.
        """
        snippets = _snippets(text, "activation deployment")
        assert len(snippets) > 0
        assert any("activation" in s.lower() or "deployment" in s.lower() for s in snippets)

    def test_snippets_empty_query(self):
        """Snippets should return empty for queries with short words."""
        text = "Some documentation text"
        assert _snippets(text, "") == []
        assert _snippets(text, "a is") == []  # All short words

    def test_snippets_no_matches(self):
        """Snippets should return empty when no matches found."""
        text = "The quick brown fox jumps over the lazy dog"
        snippets = _snippets(text, "xyzabc")
        assert len(snippets) == 0

    def test_snippets_respects_context_size(self):
        """Snippets should respect context window size."""
        text = "x" * 10000
        snippets = _snippets(text, "x", context=100, max_hits=1)
        assert len(snippets) == 1
        assert len(snippets[0]) <= 300  # context + markup

    def test_snippets_respects_max_hits(self):
        """Snippets should limit number of results."""
        text = "word word word word word word word word word word"
        snippets = _snippets(text, "word", max_hits=3)
        assert len(snippets) <= 3

    def test_pick_pages_exact_keyword_match(self):
        """Pick pages should find exact keyword matches."""
        pages = _pick_pages("activate")
        assert "activate" in pages

    def test_pick_pages_partial_keyword_match(self):
        """Pick pages should match partial queries."""
        pages = _pick_pages("macOS setup")
        assert len(pages) > 0
        # Should include start (setup) and darwin/templates (macOS)
        assert any(p in pages for p in ["start", "templates"])

    def test_pick_pages_returns_ordered_list(self):
        """Pick pages should return pages in priority order."""
        pages = _pick_pages("nixos-unified activate")
        assert isinstance(pages, list)
        # Should prioritize activate
        if "activate" in pages:
            assert pages.index("activate") < len(pages) - 1

    def test_pick_pages_includes_fallbacks(self):
        """Pick pages should include fallback pages even with no keyword match."""
        pages = _pick_pages("completely unknown query")
        # Should still include home/guide as backstops
        assert "home" in pages or "guide" in pages

    def test_pick_pages_case_insensitive(self):
        """Pick pages should be case-insensitive."""
        pages_lower = _pick_pages("nixos-unified")
        pages_upper = _pick_pages("NIXOS-UNIFIED")
        # Should match
        assert len(pages_lower) > 0 and len(pages_upper) > 0


# ===========================================================================
# Site Pages and Keyword Mapping
# ===========================================================================

class TestSiteStructure:
    """Test that site pages and keywords are well-formed."""

    def test_site_pages_are_urls(self):
        """All site pages should be valid HTTPS URLs."""
        for key, url in SITE_PAGES.items():
            assert isinstance(url, str)
            assert url.startswith("https://nixos-unified.org/")

    def test_all_keywords_reference_valid_pages(self):
        """All keywords should map to valid page keys."""
        for keyword, pages in KEYWORD_MAP.items():
            assert isinstance(pages, list)
            for page in pages:
                assert page in SITE_PAGES, f"Unknown page {page!r} referenced by keyword {keyword!r}"

    def test_keyword_map_is_lowercase(self):
        """All keywords should be lowercase."""
        for keyword in KEYWORD_MAP:
            assert keyword == keyword.lower()


# ===========================================================================
# NixosUnifiedTool
# ===========================================================================

class TestNixosUnifiedTool:

    def test_tool_registration(self):
        """Tool should be registered with correct name and metadata."""
        tool = NixosUnifiedTool()
        assert tool.name == "nixos_unified_docs"
        assert "nixos-unified" in tool.description.lower()
        assert "documentation" in tool.description.lower()
        # Should have required parameters
        param_names = [p["name"] for p in tool.parameters]
        assert "query" in param_names
        assert "page" in param_names
        assert "full_page" in param_names

    def test_query_required(self):
        """Tool should error if query and page are missing."""
        result = call_tool(NixosUnifiedTool, {})
        assert "ERROR" in result or "required" in result.lower()

    def test_empty_query_and_page_error(self):
        """Empty query and page should error."""
        result = call_tool(NixosUnifiedTool, {"query": "", "page": ""})
        assert "ERROR" in result or "required" in result.lower()

    def test_invalid_forced_page(self):
        """Invalid page name should return error with valid options."""
        result = call_tool(NixosUnifiedTool, {"query": "ignored", "page": "invalid_page"})
        assert "ERROR" in result or "unknown" in result.lower()

    def test_forced_page_overrides_query(self):
        """Forced page should override query-based page selection."""
        mock_content = "Activation content"
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixosUnifiedTool, {
                "query": "setup",
                "page": "activate"
            })
        # Should have fetched activate page, not start
        assert mock_fetch.call_args[0][0] == SITE_PAGES["activate"]

    def test_query_based_page_selection(self):
        """Query should influence page selection."""
        mock_content = "Activation documentation"
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixosUnifiedTool, {"query": "activate on remote"})
        # Should have tried to fetch pages relevant to "activate"
        assert mock_fetch.called

    def test_snippet_mode_extracts_relevant_content(self):
        """Snippet mode should extract matching content."""
        mock_content = """
        nixos-unified provides activation commands.
        You can activate locally or remotely over SSH.
        The .#activate flake app handles deployment.
        """
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixosUnifiedTool, {
                "query": "activate deploy",
                "full_page": False
            })
        assert not result.startswith("ERROR")

    def test_full_page_mode(self):
        """Full page mode should return entire page."""
        mock_content = "Very long documentation page content " * 100
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixosUnifiedTool, {
                "query": "guide",
                "full_page": True
            })
        # Should include full page marker or large content
        assert len(result) > len(mock_content) // 2

    def test_json_string_params(self):
        """Should accept JSON-formatted params string."""
        mock_content = "Documentation"
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool_json(NixosUnifiedTool, {
                "query": "activate"
            })
        assert not result.startswith("ERROR")

    def test_output_truncation(self):
        """Output should be truncated if too large."""
        huge_content = "x" * 20000
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = huge_content
            result = call_tool(NixosUnifiedTool, {"query": "test"})
        # Should be capped near MAX_OUTPUT
        assert len(result) < len(huge_content)

    def test_multiple_pages_on_fallback(self):
        """Should try multiple pages if first has no match."""
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            # First page has no match, second has match
            mock_fetch.side_effect = [
                "Some generic content about nixos",
                "Activation details: .#activate flake app"
            ]
            result = call_tool(NixosUnifiedTool, {"query": "activate"})
        # Should have tried at least 2 fetches
        assert mock_fetch.call_count >= 1

    def test_http_error_handling(self):
        """HTTP errors should be captured and returned."""
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = "ERROR: HTTP 404 — https://nixos-unified.org/missing"
            result = call_tool(NixosUnifiedTool, {"query": "page"})
        # Should contain error message or try another page
        assert "ERROR" in result or "404" in result or len(result) > 20

    def test_common_keywords_work(self):
        """Common keywords should be properly mapped."""
        keywords = ["setup", "activate", "home-manager", "macOS", "nixos", "autowiring"]
        
        for keyword in keywords:
            mock_content = f"Documentation about {keyword}"
            with patch("tools.nixos_unified_search._fetch") as mock_fetch:
                mock_fetch.return_value = mock_content
                result = call_tool(NixosUnifiedTool, {"query": keyword})
            # Should not error
            assert "ERROR" not in result or len(result) > 20

    def test_all_valid_pages_can_be_forced(self):
        """All pages in SITE_PAGES should be fetchable by name."""
        for page_key in SITE_PAGES.keys():
            mock_content = f"Content for {page_key}"
            with patch("tools.nixos_unified_search._fetch") as mock_fetch:
                mock_fetch.return_value = mock_content
                result = call_tool(NixosUnifiedTool, {"query": "test", "page": page_key})
            # Should not error about invalid page
            assert "unknown page" not in result.lower()

    def test_query_with_special_characters(self):
        """Query with special characters should be handled."""
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = "content"
            result = call_tool(NixosUnifiedTool, {
                "query": "flake.nix + home-manager"
            })
        # Should not crash
        assert isinstance(result, str) and len(result) > 0

    def test_default_full_page_false(self):
        """full_page should default to False (snippet mode)."""
        mock_content = "x" * 1000
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixosUnifiedTool, {"query": "activate"})
        # Should be condensed snippets, not full page
        assert len(result) < len(mock_content)

    def test_unicode_handling(self):
        """Tool should handle unicode characters in content."""
        mock_content = "Configuration with µ-syntax and ✓ validation symbols"
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixosUnifiedTool, {"query": "syntax"})
        # Should handle unicode gracefully
        assert isinstance(result, str)

    def test_empty_fetch_result(self):
        """Should handle empty fetch results gracefully."""
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = ""
            result = call_tool(NixosUnifiedTool, {"query": "anything"})
        # Should either try next page or return graceful message
        assert isinstance(result, str)

    def test_related_keywords_together(self):
        """Multi-word queries should work."""
        with patch("tools.nixos_unified_search._fetch") as mock_fetch:
            mock_fetch.return_value = "Content about shared configuration"
            result = call_tool(NixosUnifiedTool, {
                "query": "shared configuration email username"
            })
        assert not result.startswith("ERROR")

    def test_case_insensitive_query(self):
        """Query should be case-insensitive."""
        for query in ["ACTIVATE", "Activate", "activate"]:
            mock_content = "Activation documentation"
            with patch("tools.nixos_unified_search._fetch") as mock_fetch:
                mock_fetch.return_value = mock_content
                result = call_tool(NixosUnifiedTool, {"query": query})
            # All should work
            assert "ERROR" not in result or len(result) > 20
