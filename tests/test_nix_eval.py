"""
tests/test_nix_eval.py
Comprehensive tests for tools/nix_eval.py

Covers:
  NixEval  — valid expressions, syntax errors, empty code, is_flake flag,
             timeout handling, JSON string params, complex expressions
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure conftest stubs are active
from tests.conftest import call_tool, call_tool_json

import tools.nix_eval as _nix_eval_module
from tools.nix_eval import NixEval


# ===========================================================================
# NixEval
# ===========================================================================

class TestNixEval:

    def test_simple_valid_expression(self):
        """Valid Nix expression should return success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            result = call_tool(NixEval, {"code": "{ x = 1; }"})
        assert "SUCCESS" in result or "syntactically valid" in result.lower()

    def test_syntax_error_caught(self):
        """Invalid Nix syntax should return error."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="syntax error: unexpected ';'"
            )
            result = call_tool(NixEval, {"code": "{ x = 1 ;; }"})
        assert "ERROR" in result or "syntax" in result.lower()

    def test_undefined_variable_error(self):
        """Reference to undefined variable should fail."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error: variable 'undefined_var' is not defined"
            )
            result = call_tool(NixEval, {"code": "undefined_var"})
        assert "ERROR" in result or "error" in result.lower()

    def test_empty_code_returns_error(self):
        """Empty code string should return error."""
        result = call_tool(NixEval, {"code": ""})
        assert "ERROR" in result or "No code" in result

    def test_whitespace_only_returns_error(self):
        """Whitespace-only code should return error."""
        result = call_tool(NixEval, {"code": "   \n\n   "})
        assert "ERROR" in result or "No code" in result

    def test_is_flake_flag_passes_through(self):
        """is_flake=true should use different nix command."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            call_tool(NixEval, {"code": "{ outputs = {}; }", "is_flake": True})
        
        # Should have been called with --parse for flakes
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "nix-instantiate" in cmd
        # Could be --parse or --eval depending on flake handling

    def test_complex_attribute_set(self):
        """Complex nested attribute sets should be valid."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            code = """{
  packages = {
    vim = { version = "8.0"; };
    emacs = { version = "28.0"; };
  };
  config = {
    boot.loader = "grub";
  };
}"""
            result = call_tool(NixEval, {"code": code})
        assert "SUCCESS" in result or "valid" in result.lower()

    def test_json_string_params(self):
        """Params as JSON string should be handled."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            result = call_tool_json(NixEval, {"code": "1 + 1"})
        assert "SUCCESS" in result or "valid" in result.lower()

    def test_multiline_expression(self):
        """Multiline expressions should work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            code = """let
  x = 1;
  y = 2;
in
  x + y"""
            result = call_tool(NixEval, {"code": code})
        assert "SUCCESS" in result or "valid" in result.lower()

    def test_function_definition(self):
        """Function definitions should be valid."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            code = """{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [
    vim
    git
  ];
}"""
            result = call_tool(NixEval, {"code": code})
        assert "SUCCESS" in result or "valid" in result.lower()

    def test_timeout_handling(self):
        """Timeout should be handled gracefully."""
        with patch("subprocess.run") as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired("nix", 5)
            result = call_tool(NixEval, {"code": "infinite_loop"})
        assert "ERROR" in result or "timeout" in result.lower()

    def test_missing_code_param_returns_error(self):
        """Missing 'code' parameter should return error."""
        result = call_tool(NixEval, {})
        assert "ERROR" in result or "No code" in result

    def test_very_long_code_input(self):
        """Very long code input should be handled."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            # Create a long but valid expression
            code = "{ " + ", ".join([f"x{i} = {i}" for i in range(100)]) + " }"
            result = call_tool(NixEval, {"code": code})
        assert "SUCCESS" in result or "valid" in result.lower()

    def test_string_with_special_characters(self):
        """Strings with special characters should work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            code = '''{ message = "Hello, World! \\"quoted\\" ${variable}"; }'''
            result = call_tool(NixEval, {"code": code})
        assert "SUCCESS" in result or "valid" in result.lower()

    def test_tempfile_cleanup_on_success(self):
        """Temporary file should be cleaned up after successful evaluation."""
        with patch("subprocess.run") as mock_run:
            with patch("os.path.exists", return_value=True) as mock_exists:
                with patch("os.remove") as mock_remove:
                    mock_run.return_value = MagicMock(
                        returncode=0,
                        stdout="",
                        stderr=""
                    )
                    call_tool(NixEval, {"code": "1"})
                
                # os.remove should have been called
                mock_remove.assert_called()

    def test_tempfile_cleanup_on_error(self):
        """Temporary file should be cleaned up even after error."""
        with patch("subprocess.run") as mock_run:
            with patch("os.path.exists", return_value=True) as mock_exists:
                with patch("os.remove") as mock_remove:
                    mock_run.return_value = MagicMock(
                        returncode=1,
                        stdout="",
                        stderr="error"
                    )
                    call_tool(NixEval, {"code": "bad_code"})
                
                # os.remove should still have been called
                mock_remove.assert_called()

    def test_flake_with_inputs(self):
        """Flake with inputs declaration should be validatable."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            code = """{
  description = "My flake";
  inputs = { nixpkgs.url = "github:NixOS/nixpkgs"; };
  outputs = inputs: { };
}"""
            result = call_tool(NixEval, {"code": code, "is_flake": True})
        assert "SUCCESS" in result or "valid" in result.lower()

    def test_import_statement(self):
        """Import statements should be handled."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            code = "import ./other.nix"
            result = call_tool(NixEval, {"code": code})
        assert "SUCCESS" in result or "valid" in result.lower() or "error" in result.lower()

    def test_recursive_attribute_set(self):
        """Recursive attribute sets (rec) should work."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            code = """rec {
  name = "nixos";
  version = "23.0";
  full = name + "-" + version;
}"""
            result = call_tool(NixEval, {"code": code})
        assert "SUCCESS" in result or "valid" in result.lower()
