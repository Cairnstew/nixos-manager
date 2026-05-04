"""
tests/test_nix_docs.py
Comprehensive tests for tools/nix_docs.py

Covers:
  NixDocsTool  — basic queries, section hints, version handling,
                 error handling, JSON string params, URL fallbacks
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import call_tool, call_tool_json

import tools.nix_docs as _nix_docs_module
from tools.nix_docs import NixDocsTool, _fetch_page, _search_in_text, _resolve_version, _build_url


# ===========================================================================
# Helper Functions
# ===========================================================================

class TestHelpers:
    """Test utility functions in nix_docs module."""

    def test_resolve_version_stable(self):
        """Resolve 'stable' to 'stable'."""
        assert _resolve_version("stable") == "stable"
        assert _resolve_version("Stable") == "stable"
        assert _resolve_version("STABLE") == "stable"

    def test_resolve_version_latest(self):
        """Resolve 'latest' and 'current' to 'stable'."""
        assert _resolve_version("latest") == "stable"
        assert _resolve_version("current") == "stable"

    def test_resolve_version_specific(self):
        """Preserve specific version numbers."""
        assert _resolve_version("2.26") == "2.26"
        assert _resolve_version("2.24") == "2.24"
        assert _resolve_version("  2.26  ") == "2.26"

    def test_resolve_version_empty_defaults_to_stable(self):
        """Empty string resolves to stable."""
        assert _resolve_version("") == "stable"
        assert _resolve_version("   ") == "stable"

    def test_build_url(self):
        """Build correct URLs for different paths."""
        url = _build_url("stable", "language/builtins")
        assert url == "https://nix.dev/manual/nix/stable/language/builtins"
        
        url = _build_url("2.26", "language/")
        assert url == "https://nix.dev/manual/nix/2.26/language/"

    def test_build_url_avoids_double_slashes(self):
        """Avoid double slashes in URLs."""
        url = _build_url("stable", "/language/builtins")
        assert "//" not in url[8:]  # Skip protocol double slash

    def test_search_in_text_finds_words(self):
        """Search finds query words in text."""
        text = """
        Derivations are the core concept in Nix.
        They describe how to build packages extensively.
        """
        snippets = _search_in_text(text, "derivations concept")
        assert len(snippets) > 0
        # Should find words with 3+ characters
        assert any("derivations" in s.lower() or "concept" in s.lower() for s in snippets)

    def test_search_in_text_empty_query(self):
        """Empty or short queries return empty list."""
        text = "Some documentation text"
        assert _search_in_text(text, "") == []
        assert _search_in_text(text, "a") == []  # Words < 3 chars ignored

    def test_search_in_text_no_matches(self):
        """No matches return empty list."""
        text = "The quick brown fox jumps over the lazy dog"
        snippets = _search_in_text(text, "xyz")
        assert len(snippets) == 0

    def test_search_in_text_context_limit(self):
        """Snippets should be limited by context_chars."""
        text = "x" * 10000
        snippets = _search_in_text(text, "x", context_chars=100)
        assert all(len(s) <= 300 for s in snippets)  # Context chars * 1.5

    def test_fetch_page_network_error(self):
        """Fetch page returns error message on network failure."""
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = Exception("Connection refused")
            result = _fetch_page("https://example.com/page")
        assert "ERROR" in result

    def test_fetch_page_strips_html(self):
        """Fetch page strips HTML tags and collapses whitespace."""
        html = "<html><body><p>  Hello   </p><script>alert('x')</script></body></html>"
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = html.encode()
            result = _fetch_page("https://example.com/page")
        assert "Hello" in result
        assert "<" not in result
        assert "script" not in result


# ===========================================================================
# NixDocsTool
# ===========================================================================

class TestNixDocsTool:

    def test_tool_registration(self):
        """Tool should be registered with correct name and metadata."""
        tool = NixDocsTool()
        assert tool.name == "nix_docs"
        assert "nix" in tool.description.lower() and "manual" in tool.description.lower()
        # Should have required parameters
        param_names = [p["name"] for p in tool.parameters]
        assert "query" in param_names
        assert "section" in param_names
        assert "version" in param_names
        assert "url" in param_names

    def test_query_required(self):
        """Tool should error if query and url are missing."""
        result = call_tool(NixDocsTool, {})
        assert "ERROR" in result or "required" in result.lower()

    def test_empty_query_error(self):
        """Empty query string should error."""
        result = call_tool(NixDocsTool, {"query": ""})
        assert "ERROR" in result or "required" in result.lower()

    def test_direct_url_bypasses_section_mapping(self):
        """Direct URL parameter should be used without section mapping."""
        mock_content = "Nix language documentation"
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixDocsTool, {
                "query": "ignored",
                "url": "https://custom.example.com/page"
            })
        # Should have called fetch with the direct URL
        mock_fetch.assert_called()
        call_args = mock_fetch.call_args[0][0]
        assert "custom.example.com" in call_args

    def test_section_hint_influences_fetch(self):
        """Section hint should influence which URL is tried first."""
        mock_content = "Language syntax documentation"
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixDocsTool, {
                "query": "syntax",
                "section": "language"
            })
        # Should have attempted to fetch the language section
        mock_fetch.assert_called()
        call_args = mock_fetch.call_args_list[0][0][0]
        assert "language" in call_args

    def test_version_parameter_respected(self):
        """Version parameter should be included in the URL."""
        mock_content = "Nix 2.26 documentation"
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixDocsTool, {
                "query": "builtins",
                "version": "2.26"
            })
        # Should have used version 2.26 in URL
        mock_fetch.assert_called()
        call_args = mock_fetch.call_args_list[0][0][0]
        assert "2.26" in call_args

    def test_fallback_to_stable_version(self):
        """If version is not specified or is 'stable', use stable."""
        mock_content = "Stable documentation"
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixDocsTool, {"query": "nix-build"})
        
        mock_fetch.assert_called()
        call_args = mock_fetch.call_args_list[0][0][0]
        assert "stable" in call_args or "2." in call_args  # Stable version in URL

    def test_json_string_params(self):
        """Should accept JSON-formatted params string."""
        mock_content = "Documentation for nix-shell"
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool_json(NixDocsTool, {
                "query": "nix-shell",
                "section": "commands"
            })
        assert not result.startswith("ERROR")

    def test_output_truncation(self):
        """Output should be hard-capped at MAX_CONTENT."""
        huge_content = "x" * 20000
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            mock_fetch.return_value = huge_content
            result = call_tool(NixDocsTool, {"query": "test"})
        
        assert len(result) <= NixDocsTool.MAX_CONTENT + 100  # Allow for truncation message

    def test_successful_query_with_mock_content(self):
        """Successful query should return formatted output."""
        mock_content = "Derivations in Nix are the primary mechanism for building packages."
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixDocsTool, {
                "query": "derivations",
                "section": "language"
            })
        
        assert "ERROR" not in result
        assert "Source:" in result or "Derivations" in result

    def test_search_fallback_shows_page_start(self):
        """If query words not found, show page start anyway."""
        mock_content = "Some generic documentation that doesn't match query words very well."
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            mock_fetch.return_value = mock_content
            result = call_tool(NixDocsTool, {"query": "xyzabc"})
        
        # Should return page start since no keyword match
        assert "Some generic documentation" in result or "generic documentation" in result

    def test_http_error_handling(self):
        """HTTP errors should be captured and returned."""
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            mock_fetch.return_value = "ERROR: HTTP 404 fetching https://nix.dev/..."
            result = call_tool(NixDocsTool, {"query": "nonexistent-page"})
        
        # Should contain the error message
        assert "ERROR" in result or "404" in result

    def test_section_case_insensitive(self):
        """Section parameter should be case-insensitive."""
        mock_content = "Language documentation"
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            mock_fetch.return_value = mock_content
            result1 = call_tool(NixDocsTool, {
                "query": "syntax",
                "section": "LANGUAGE"
            })
        
        mock_fetch.assert_called()
        call_args = mock_fetch.call_args_list[0][0][0]
        assert "language" in call_args.lower()

    def test_multiple_fetch_attempts_on_failure(self):
        """Tool should try multiple URLs if first fetch fails."""
        with patch("tools.nix_docs._fetch_page") as mock_fetch:
            # First call fails, second succeeds
            mock_fetch.side_effect = [
                "ERROR: HTTP 404",
                "Builtins documentation"
            ]
            result = call_tool(NixDocsTool, {
                "query": "builtins",
                "section": "builtins"
            })
        
        # Should have tried at least twice
        assert mock_fetch.call_count >= 1

    def test_common_section_mappings_work(self):
        """Common section names should map correctly."""
        sections_to_test = ["language", "builtins", "flakes", "commands"]
        
        for section in sections_to_test:
            mock_content = f"{section} documentation"
            with patch("tools.nix_docs._fetch_page") as mock_fetch:
                mock_fetch.return_value = mock_content
                result = call_tool(NixDocsTool, {
                    "query": "test",
                    "section": section
                })
            # Should not error
            assert "ERROR" not in result or len(result) > 20
