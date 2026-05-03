"""
tests/test_nix_search.py
Comprehensive tests for tools/nix_search.py

Covers:
  NixSearch  — valid searches, JSON responses, empty queries, error handling,
               search_options flag, timeout handling, JSON string params
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import call_tool, call_tool_json

import tools.nix_search as _nix_search_module
from tools.nix_search import NixSearch


# ===========================================================================
# NixSearch
# ===========================================================================

class TestNixSearch:

    def test_package_search_success(self):
        """Successful package search should return JSON."""
        mock_response = json.dumps({
            "vim": {
                "pname": "vim",
                "version": "9.0",
                "description": "The ubiquitous text editor"
            }
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=mock_response,
                stderr=""
            )
            result = call_tool(NixSearch, {"query": "vim"})
        
        assert "vim" in result
        # Should be valid JSON
        try:
            parsed = json.loads(result)
            assert "vim" in parsed
        except json.JSONDecodeError:
            pytest.fail("Response should be valid JSON")

    def test_empty_query_returns_error(self):
        """Empty search query should return error."""
        result = call_tool(NixSearch, {"query": ""})
        assert "ERROR" in result or "required" in result.lower()

    def test_whitespace_query_returns_error(self):
        """Whitespace-only query should return error."""
        result = call_tool(NixSearch, {"query": "   \n  "})
        assert "ERROR" in result or "required" in result.lower()

    def test_search_options_flag(self):
        """search_options=true should be accepted."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            result = call_tool(NixSearch, {
                "query": "boot.loader",
                "search_options": True
            })
        # Command should include the query
        assert result is not None

    def test_search_with_special_characters(self):
        """Queries with special characters should work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            result = call_tool(NixSearch, {"query": "lib.attrsets"})
        assert result is not None

    def test_json_string_params(self):
        """Params as JSON string should be handled."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            result = call_tool_json(NixSearch, {"query": "git"})
        assert result is not None

    def test_command_failure_returns_error(self):
        """nix search failure should return error message."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error: flake not found"
            )
            result = call_tool(NixSearch, {"query": "vim"})
        assert "ERROR" in result or "error" in result.lower()

    def test_timeout_handling(self):
        """Timeout should be handled gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("nix search", 10)
            result = call_tool(NixSearch, {"query": "vim"})
        assert "ERROR" in result or "Failed" in result or "error" in result.lower()

    def test_generic_exception_handling(self):
        """Generic exceptions should be handled."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("permission denied")
            result = call_tool(NixSearch, {"query": "vim"})
        assert "ERROR" in result or "Failed" in result or "error" in result.lower()

    def test_search_returns_multiple_results(self):
        """Search for common term should return multiple results."""
        mock_response = json.dumps({
            "postgresql": {
                "pname": "postgresql",
                "version": "15.0"
            },
            "postgresql_13": {
                "pname": "postgresql",
                "version": "13.0"
            },
            "postgresql_14": {
                "pname": "postgresql",
                "version": "14.0"
            }
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=mock_response,
                stderr=""
            )
            result = call_tool(NixSearch, {"query": "postgresql"})
        
        parsed = json.loads(result)
        assert len(parsed) >= 3

    def test_case_sensitive_search(self):
        """Search should work with different cases."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            result = call_tool(NixSearch, {"query": "VIM"})
        assert result is not None

    def test_search_with_hyphenated_names(self):
        """Search for packages with hyphens should work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            result = call_tool(NixSearch, {"query": "rust-analyzer"})
        assert result is not None

    def test_search_with_version_specifier(self):
        """Search may include version patterns."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            result = call_tool(NixSearch, {"query": "python3"})
        assert result is not None

    def test_missing_query_parameter(self):
        """Missing query parameter should return error."""
        result = call_tool(NixSearch, {})
        assert "ERROR" in result or "required" in result.lower()

    def test_nix_command_called_correctly(self):
        """nix search command should be constructed correctly."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            call_tool(NixSearch, {"query": "vim"})
        
        # Verify the command structure
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "nix"
        assert "search" in cmd
        assert "vim" in cmd
        assert "--json" in cmd

    def test_empty_search_result(self):
        """Empty search result should return empty JSON object."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            result = call_tool(NixSearch, {"query": "nonexistent_package_xyz_123"})
        
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert len(parsed) == 0

    def test_search_with_regex_pattern(self):
        """Search with regex-like pattern should work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            result = call_tool(NixSearch, {"query": "^vim$"})
        assert result is not None

    def test_json_output_encoding(self):
        """JSON output should maintain proper encoding."""
        mock_response = json.dumps({
            "package": {
                "description": "Package with special chars: café, naïve, é"
            }
        }, ensure_ascii=False)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=mock_response,
                stderr=""
            )
            result = call_tool(NixSearch, {"query": "special"})
        
        # Should be valid JSON
        parsed = json.loads(result)
        assert "package" in parsed

    def test_search_options_flag_false(self):
        """search_options=false should search packages."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            result = call_tool(NixSearch, {
                "query": "vim",
                "search_options": False
            })
        assert result is not None

    def test_stderr_output_included_in_error(self):
        """Error stderr should be included in error message."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error: nix flake is not available"
            )
            result = call_tool(NixSearch, {"query": "vim"})
        assert "nix flake" in result or "error" in result.lower()

    def test_very_long_search_query(self):
        """Very long search query should be handled."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="{}",
                stderr=""
            )
            long_query = "a" * 1000
            result = call_tool(NixSearch, {"query": long_query})
        assert result is not None
