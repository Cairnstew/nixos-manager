"""
tests/test_nix_ops.py
In-depth tests for tools/nix_ops.py

Because _run() shells out, subprocess calls are mocked so the suite runs
anywhere (no git / nix required).  A separate integration section marks
tests that need the real binaries.

Covers:
  _run          — success, empty output, timeout, binary not found, exception
  GitOp         — allow-listed commands pass, blocked commands rejected,
                  empty args, JSON string params, shlex splitting
  NixCheck      — allowed prefixes pass, blocked commands rejected,
                  empty command, JSON string params
  SearchNixFiles — pattern forwarded to grep, case-insensitive flag, empty pattern
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call as mock_call

import pytest

from tests.conftest import call_tool, call_tool_json
import tools.nix_ops as _nix_module
from tools.nix_ops import GitOp, NixCheck, SearchNixFiles, _run, _ALLOWED_GIT, _ALLOWED_NIX


# ===========================================================================
# Helpers
# ===========================================================================

def _make_completed(stdout="", stderr="", returncode=0):
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.stdout = stdout
    r.stderr = stderr
    r.returncode = returncode
    return r


# ===========================================================================
# _run (internal subprocess helper)
# ===========================================================================

class TestRunHelper:

    def test_returns_stdout(self, tmp_path):
        with patch("subprocess.run", return_value=_make_completed(stdout="hello\n")):
            result = _run(["echo", "hello"], cwd=tmp_path)
        assert result == "hello"

    def test_combines_stdout_and_stderr(self, tmp_path):
        with patch("subprocess.run", return_value=_make_completed(stdout="out", stderr="err")):
            result = _run(["cmd"], cwd=tmp_path)
        assert "out" in result and "err" in result

    def test_empty_output_placeholder(self, tmp_path):
        with patch("subprocess.run", return_value=_make_completed(stdout="", stderr="")):
            result = _run(["cmd"], cwd=tmp_path)
        assert result == "(no output)"

    def test_timeout_returns_error(self, tmp_path):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 60)):
            result = _run(["cmd"], cwd=tmp_path, timeout=60)
        assert "timed out" in result.lower()
        assert "60" in result

    def test_binary_not_found_returns_error(self, tmp_path):
        with patch("subprocess.run", side_effect=FileNotFoundError("no such file")):
            result = _run(["nonexistent_binary"], cwd=tmp_path)
        assert result.startswith("ERROR:")
        assert "not found" in result.lower()

    def test_generic_exception_returns_error(self, tmp_path):
        with patch("subprocess.run", side_effect=OSError("disk full")):
            result = _run(["cmd"], cwd=tmp_path)
        assert result.startswith("ERROR:")

    def test_strips_trailing_whitespace(self, tmp_path):
        with patch("subprocess.run", return_value=_make_completed(stdout="result\n\n  ")):
            result = _run(["cmd"], cwd=tmp_path)
        assert result == "result"


# ===========================================================================
# GitOp
# ===========================================================================

class TestGitOp:

    @pytest.mark.parametrize("cmd", sorted(_ALLOWED_GIT))
    def test_allowed_commands_pass_through(self, cmd, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="ok") as mock_run:
            result = call_tool(GitOp, {"args": cmd})
        assert result == "ok"
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "git"
        assert called_cmd[1] == cmd

    @pytest.mark.parametrize("blocked", ["push", "reset", "force-push", "clean", "rm"])
    def test_blocked_commands_rejected(self, blocked, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        result = call_tool(GitOp, {"args": blocked})
        assert result.startswith("ERROR:")
        assert "allow-list" in result.lower() or "not in" in result.lower()

    def test_empty_args_returns_error(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        result = call_tool(GitOp, {"args": ""})
        assert result.startswith("ERROR:")
        assert "required" in result.lower()

    def test_status_with_extra_flags(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="clean") as mock_run:
            result = call_tool(GitOp, {"args": "status --short"})
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd == ["git", "status", "--short"]

    def test_commit_with_message(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="committed") as mock_run:
            call_tool(GitOp, {"args": 'commit -m "fix: update hostname"'})
        called_cmd = mock_run.call_args[0][0]
        assert "commit" in called_cmd
        assert "-m" in called_cmd
        assert "fix: update hostname" in called_cmd

    def test_diff_with_range(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="diff output") as mock_run:
            call_tool(GitOp, {"args": "diff HEAD~3"})
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd == ["git", "diff", "HEAD~3"]

    def test_json_string_params(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="ok"):
            result = call_tool_json(GitOp, {"args": "status"})
        assert result == "ok"

    def test_cwd_is_repo_path(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="ok") as mock_run:
            call_tool(GitOp, {"args": "status"})
        args, kwargs = mock_run.call_args
        cwd = kwargs.get("cwd", args[1] if len(args) > 1 else None)
        assert cwd == repo

    def test_add_with_dot(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="ok") as mock_run:
            call_tool(GitOp, {"args": "add ."})
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd == ["git", "add", "."]


# ===========================================================================
# NixCheck
# ===========================================================================

class TestNixCheck:

    @pytest.mark.parametrize("cmd,expected_prefix", [
        ("flake check", ["nix", "flake", "check"]),
        ("flake show", ["nix", "flake", "show"]),
        ("build .#nixosConfigurations.myhost", ["nix", "build", ".#nixosConfigurations.myhost"]),
        ("eval .#nixosConfigurations", ["nix", "eval", ".#nixosConfigurations"]),
    ])
    def test_allowed_commands(self, cmd, expected_prefix, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="ok") as mock_run:
            result = call_tool(NixCheck, {"command": cmd})
        assert result == "ok"
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[:len(expected_prefix)] == expected_prefix

    @pytest.mark.parametrize("blocked", [
        "shell", "run", "develop", "store delete", "copy", "profile install"
    ])
    def test_blocked_commands_rejected(self, blocked, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        result = call_tool(NixCheck, {"command": blocked})
        assert result.startswith("ERROR:")
        assert "not allowed" in result.lower()

    def test_empty_command_returns_error(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        result = call_tool(NixCheck, {"command": ""})
        assert result.startswith("ERROR:")
        assert "required" in result.lower()

    def test_timeout_is_extended_for_nix(self, repo, monkeypatch):
        """nix builds can be slow — timeout should be 120s, not the 60s default."""
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="ok") as mock_run:
            call_tool(NixCheck, {"command": "flake check"})
        _, kwargs = mock_run.call_args
        timeout = kwargs.get("timeout", mock_run.call_args[1].get("timeout", None))
        # Accept positional arg at index 2 as well
        if timeout is None:
            args = mock_run.call_args[0]
            timeout = args[2] if len(args) > 2 else None
        assert timeout == 120

    def test_json_string_params(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="ok"):
            result = call_tool_json(NixCheck, {"command": "flake check"})
        assert result == "ok"

    def test_cwd_is_repo_path(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="ok") as mock_run:
            call_tool(NixCheck, {"command": "flake check"})
        args, kwargs = mock_run.call_args
        cwd = kwargs.get("cwd", args[1] if len(args) > 1 else None)
        assert cwd == repo


# ===========================================================================
# SearchNixFiles
# ===========================================================================

class TestSearchNixFiles:

    def test_pattern_forwarded_to_grep(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="match") as mock_run:
            call_tool(SearchNixFiles, {"pattern": "hostName"})
        called_cmd = mock_run.call_args[0][0]
        assert "grep" in called_cmd
        assert "hostName" in called_cmd

    def test_includes_nix_filter(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="x") as mock_run:
            call_tool(SearchNixFiles, {"pattern": "x"})
        called_cmd = mock_run.call_args[0][0]
        assert "--include=*.nix" in called_cmd

    def test_case_sensitive_by_default(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="x") as mock_run:
            call_tool(SearchNixFiles, {"pattern": "Foo"})
        called_cmd = mock_run.call_args[0][0]
        assert "-i" not in called_cmd

    def test_case_insensitive_flag(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="x") as mock_run:
            call_tool(SearchNixFiles, {"pattern": "foo", "case_sensitive": False})
        called_cmd = mock_run.call_args[0][0]
        assert "-i" in called_cmd

    def test_empty_pattern_returns_error(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        result = call_tool(SearchNixFiles, {"pattern": ""})
        assert result.startswith("ERROR:")
        assert "required" in result.lower()

    def test_json_string_params(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="found"):
            result = call_tool_json(SearchNixFiles, {"pattern": "services"})
        assert result == "found"

    def test_repo_path_passed_to_grep(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="x") as mock_run:
            call_tool(SearchNixFiles, {"pattern": "x"})
        called_cmd = mock_run.call_args[0][0]
        assert str(repo) in called_cmd

    def test_recursive_flag_present(self, repo, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        with patch("tools.nix_ops._run", return_value="x") as mock_run:
            call_tool(SearchNixFiles, {"pattern": "x"})
        called_cmd = mock_run.call_args[0][0]
        assert any(f.startswith("-") and "r" in f for f in called_cmd)


# ===========================================================================
# Integration tests (skipped unless real binaries present)
# ===========================================================================

def _has_binary(name: str) -> bool:
    import shutil
    return shutil.which(name) is not None


@pytest.mark.skipif(not _has_binary("git"), reason="git not installed")
class TestGitOpIntegration:

    def test_git_status_in_real_git_repo(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", tmp_path)
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        result = call_tool(GitOp, {"args": "status"})
        # Should get some real git output, not an ERROR
        assert not result.startswith("ERROR:")

    def test_git_log_empty_repo(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", tmp_path)
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        result = call_tool(GitOp, {"args": "log"})
        # Empty repo has no commits; git exits non-zero but we still get output
        assert isinstance(result, str)
