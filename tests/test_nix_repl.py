"""
tests/test_nix_repl.py
Comprehensive tests for tools/nix_repl.py

Covers:
  NixReplTool  — basic expressions, loading nixpkgs/files/flakes,
                 type inspection, error handling, safety guards,
                 multi-step sessions, JSON params
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import call_tool, call_tool_json

import tools.nix_repl as _nix_repl_module
from tools.nix_repl import (
    NixReplTool,
    _nix_available,
    _run_repl,
    _clean_repl_output,
    _format_result,
)


# ===========================================================================
# Helper Functions
# ===========================================================================

class TestHelpers:
    """Test utility functions in nix_repl module."""

    def test_nix_available_true(self):
        """Nix should be available in dev shell."""
        # In the dev shell, nix should be available
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/nix"
            assert _nix_available() is True

    def test_nix_available_false(self):
        """Return false when nix is not on PATH."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            assert _nix_available() is False

    def test_clean_repl_output_strips_prompts(self):
        """Should strip nix-repl> prompts."""
        raw = """nix-repl> 1 + 1
2
nix-repl> "hello"
"hello"
nix-repl> :q"""
        cleaned = _clean_repl_output(raw)
        assert "nix-repl" not in cleaned
        assert "2" in cleaned
        assert '"hello"' in cleaned

    def test_clean_repl_output_removes_banner(self):
        """Should remove startup banner."""
        raw = """Welcome to Nix 2.26
Type :? for help.
nix-repl> 1 + 1
2"""
        cleaned = _clean_repl_output(raw)
        assert "Welcome" not in cleaned
        assert "Type :?" not in cleaned
        assert "2" in cleaned

    def test_clean_repl_output_preserves_multiline(self):
        """Should preserve multiline expressions."""
        raw = """nix-repl> {
  a = 1;
  b = 2;
}
{ a = 1; b = 2; }"""
        cleaned = _clean_repl_output(raw)
        # Output should not have excessive prompts
        assert cleaned.count("nix-repl") == 0

    def test_format_result_stdout_only(self):
        """Format with stdout only."""
        result = _format_result("value = 42", "")
        assert "42" in result
        assert "[stderr]" not in result

    def test_format_result_stderr_only(self):
        """Format with stderr only."""
        result = _format_result("", "error message")
        assert "[stderr]" in result
        assert "error message" in result

    def test_format_result_filters_trace_lines(self):
        """Should filter out trace: lines."""
        stderr = "trace: evaluating\nerror: real error\ntrace: more noise"
        result = _format_result("output", stderr)
        assert "real error" in result
        assert "trace:" not in result

    def test_format_result_filters_noisy_warnings(self):
        """Should filter noisy but non-critical lines."""
        stderr = "warning: some warning\nfetching nixpkgs\nbuilding packages"
        result = _format_result("output", stderr)
        # These lines should be filtered
        assert stderr.lower() not in result.lower()

    def test_format_result_empty_returns_no_output(self):
        """Empty result should say '(no output)'."""
        result = _format_result("", "")
        assert "(no output)" in result

    def test_run_repl_timeout(self):
        """Should handle timeout gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("nix repl", 1)
            stdout, stderr = _run_repl(["1 + 1"], timeout=1)
            # stderr should indicate timeout
            assert "timed" in stderr.lower()

    def test_run_repl_nix_not_found(self):
        """Should handle missing nix binary."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            stdout, stderr = _run_repl(["1 + 1"])
            assert "not found" in stderr.lower()

    def test_run_repl_with_nixpkgs(self):
        """Should pass <nixpkgs> to repl when requested."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="42", stderr="")
            _run_repl(["pkgs.hello.version"], load_nixpkgs=True)
            
            cmd = mock_run.call_args[0][0]
            assert "<nixpkgs>" in cmd

    def test_run_repl_with_load_file(self):
        """Should pass --file flag when load_file is specified."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="value", stderr="")
            _run_repl(["test"], load_file="/path/to/file.nix")
            
            cmd = mock_run.call_args[0][0]
            assert "--file" in cmd
            assert "/path/to/file.nix" in cmd

    def test_run_repl_with_impure(self):
        """Should pass --impure flag when requested."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="result", stderr="")
            _run_repl(["builtins.getEnv \"HOME\""], impure=True)
            
            cmd = mock_run.call_args[0][0]
            assert "--impure" in cmd

    def test_run_repl_builds_stdin_correctly(self):
        """Should send expressions as stdin with :q terminator."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="")
            _run_repl(["x = 1", "x + 1"])
            
            stdin_text = mock_run.call_args[1]["input"]
            assert "x = 1" in stdin_text
            assert "x + 1" in stdin_text
            assert ":q" in stdin_text


# ===========================================================================
# NixReplTool
# ===========================================================================

class TestNixReplTool:

    def test_tool_registration(self):
        """Tool should be registered with correct name and metadata."""
        tool = NixReplTool()
        assert tool.name == "nix_repl"
        assert "nix" in tool.description.lower()
        assert "evaluate" in tool.description.lower()
        # Should have required parameters
        param_names = [p["name"] for p in tool.parameters]
        assert "expressions" in param_names
        assert "load_nixpkgs" in param_names
        assert "load_file" in param_names
        assert "impure" in param_names

    def test_empty_expressions_error(self):
        """Tool should error if expressions is empty."""
        result = call_tool(NixReplTool, {"expressions": []})
        assert "ERROR" in result or "non-empty" in result.lower()

    def test_missing_expressions_error(self):
        """Tool should error if expressions parameter is missing."""
        result = call_tool(NixReplTool, {})
        assert "ERROR" in result or "required" in result.lower()

    def test_expressions_whitespace_only_error(self):
        """Expressions that are all whitespace should error."""
        result = call_tool(NixReplTool, {"expressions": ["   ", "\n", "\t"]})
        assert "ERROR" in result

    def test_nix_not_installed_error(self):
        """Should error gracefully if nix is not installed."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = False
            result = call_tool(NixReplTool, {"expressions": ["1 + 1"]})
            assert "ERROR" in result and "not installed" in result.lower()

    def test_dangerous_pattern_semicolon_alone(self):
        """Bare semicolon is not caught by safety guard but rejected by nix."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                # Nix itself will reject bare semicolon
                mock_run.return_value = ("", "error: syntax error, unexpected ';'")
                result = call_tool(NixReplTool, {"expressions": ["1; 2"]})
            # Should have nix error message
            assert "error" in result.lower()

    def test_dangerous_pattern_command_injection(self):
        """Should reject shell command patterns."""
        result = call_tool(NixReplTool, {"expressions": ["builtins.exec \"rm -rf /\""]})
        assert "ERROR" in result or "unsafe" in result.lower()

    def test_dangerous_pattern_backticks(self):
        """Should reject backticks."""
        result = call_tool(NixReplTool, {"expressions": ["`echo hi`"]})
        assert "ERROR" in result or "unsafe" in result.lower()

    def test_dangerous_pattern_dollar_paren(self):
        """Should reject $() patterns."""
        result = call_tool(NixReplTool, {"expressions": ["$(rm /)"]})
        assert "ERROR" in result or "unsafe" in result.lower()

    def test_safe_attribute_set_semicolon(self):
        """Should allow semicolons in attribute sets."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("{ a = 1; b = 2; }", "")
                result = call_tool(NixReplTool, {"expressions": ["{ a = 1; b = 2; }"]})
        
        # Should not error on safe attribute set
        assert "ERROR" not in result or "unsafe" not in result.lower()

    def test_simple_arithmetic_expression(self):
        """Simple arithmetic should work."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("2", "")
                result = call_tool(NixReplTool, {"expressions": ["1 + 1"]})
        
        assert "2" in result

    def test_string_expression(self):
        """String expressions should work."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ('"hello world"', "")
                result = call_tool(NixReplTool, {"expressions": ["\"hello\" + \" \" + \"world\""]})
        
        assert "hello" in result

    def test_list_expression(self):
        """List expressions should work."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("[ 1 2 3 ]", "")
                result = call_tool(NixReplTool, {"expressions": ["[ 1 2 3 ]"]})
        
        assert "[" in result and "1" in result

    def test_multiple_expressions(self):
        """Should handle multiple expressions in sequence."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("42\n84", "")
                result = call_tool(NixReplTool, {
                    "expressions": ["x = 42", "x * 2"]
                })
        
        mock_run.assert_called_once()
        # Check that both statements were passed
        call_args = mock_run.call_args
        assert "x = 42" in call_args[1]["statements"]
        assert "x * 2" in call_args[1]["statements"]

    def test_type_inspection(self):
        """Should support :t for type inspection."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("type = \"int\"", "")
                result = call_tool(NixReplTool, {
                    "expressions": [":t 42"]
                })
        
        assert "type" in result.lower()

    def test_doc_inspection(self):
        """Should support :doc for documentation."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("builtins.add is a builtin that...", "")
                result = call_tool(NixReplTool, {
                    "expressions": [":doc builtins.add"]
                })
        
        assert "builtin" in result.lower()

    def test_load_nixpkgs_flag(self):
        """Should pass load_nixpkgs to _run_repl."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("result", "")
                call_tool(NixReplTool, {
                    "expressions": ["pkgs.hello"],
                    "load_nixpkgs": True
                })
        
        call_args = mock_run.call_args
        assert call_args[1]["load_nixpkgs"] is True

    def test_load_file_parameter(self):
        """Should pass load_file to _run_repl."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("result", "")
                call_tool(NixReplTool, {
                    "expressions": ["test"],
                    "load_file": "/path/to/file.nix"
                })
        
        call_args = mock_run.call_args
        assert call_args[1]["load_file"] == "/path/to/file.nix"

    def test_load_flake_parameter(self):
        """Should pass load_flake to _run_repl."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("result", "")
                call_tool(NixReplTool, {
                    "expressions": ["test"],
                    "load_flake": "github:NixOS/nixpkgs"
                })
        
        call_args = mock_run.call_args
        assert call_args[1]["load_flake"] == "github:NixOS/nixpkgs"

    def test_impure_flag(self):
        """Should pass impure flag to _run_repl."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("result", "")
                call_tool(NixReplTool, {
                    "expressions": ["test"],
                    "impure": True
                })
        
        call_args = mock_run.call_args
        assert call_args[1]["impure"] is True

    def test_timeout_parameter(self):
        """Should pass timeout to _run_repl."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("result", "")
                call_tool(NixReplTool, {
                    "expressions": ["test"],
                    "timeout": 60
                })
        
        call_args = mock_run.call_args
        assert call_args[1]["timeout"] == 60

    def test_default_timeout(self):
        """Default timeout should be 30 seconds."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("result", "")
                call_tool(NixReplTool, {"expressions": ["test"]})
        
        call_args = mock_run.call_args
        assert call_args[1]["timeout"] == 30

    def test_json_string_params(self):
        """Should accept JSON-formatted params string."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("42", "")
                result = call_tool_json(NixReplTool, {
                    "expressions": ["1 + 1"]
                })
        
        assert "ERROR" not in result or "42" in result

    def test_expressions_can_be_strings_or_numbers(self):
        """Expressions can be passed as different types and get stringified."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("42", "")
                result = call_tool(NixReplTool, {
                    "expressions": [1, "+", 1]  # Mixed types
                })
        
        # Should not error, should stringify them
        assert "ERROR" not in result

    def test_builtin_function_calls(self):
        """Should support builtin function calls."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("3", "")
                result = call_tool(NixReplTool, {
                    "expressions": ["builtins.length [1 2 3]"]
                })
        
        assert "3" in result

    def test_lambda_expressions(self):
        """Should support lambda expressions."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("42", "")
                result = call_tool(NixReplTool, {
                    "expressions": ["(x: x * 2) 21"]
                })
        
        assert "42" in result

    def test_complex_nested_expression(self):
        """Should handle complex nested expressions."""
        with patch("tools.nix_repl._nix_available") as mock_avail:
            mock_avail.return_value = True
            with patch("tools.nix_repl._run_repl") as mock_run:
                mock_run.return_value = ("result", "")
                result = call_tool(NixReplTool, {
                    "expressions": [
                        "let x = { a = 1; b = 2; }; in x.a + x.b"
                    ]
                })
        
        assert "ERROR" not in result
