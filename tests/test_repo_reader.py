"""
tests/test_repo_reader.py
In-depth tests for tools/repo_reader.py

Covers:
  ListNixFiles  — listing, filtering, subdir scoping, ignored dirs, empty repos
  ReadNixFile   — happy path, missing file, wrong extension, JSON-string params,
                  encoding, empty path guard
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure conftest stubs are active before importing project code
from tests.conftest import call_tool, call_tool_json  # noqa: F401

import tools.repo_reader as _rr_module  # triggers @register_tool side-effects
from tools.repo_reader import ListNixFiles, ReadNixFile


# ===========================================================================
# ListNixFiles
# ===========================================================================

class TestListNixFiles:

    def test_lists_all_nix_files(self, nested_nix_files, repo):
        """Should return one line per .nix file, relative to repo root."""
        result = call_tool(ListNixFiles, {})
        lines = result.strip().splitlines()
        assert len(lines) == 3
        for f in nested_nix_files:
            assert str(f.relative_to(repo)) in lines

    def test_ignores_non_nix_files(self, nested_nix_files, repo):
        result = call_tool(ListNixFiles, {})
        assert "README.md" not in result
        assert "secrets.yaml" not in result

    def test_empty_repo_message(self, repo):
        """An empty repo should return the 'no files found' message."""
        result = call_tool(ListNixFiles, {})
        assert result == "No .nix files found."

    def test_subdir_scoping(self, nested_nix_files, repo):
        """Passing subdir='hosts' should only return files under hosts/."""
        result = call_tool(ListNixFiles, {"subdir": "hosts"})
        assert "hosts/desktop.nix" in result
        assert "flake.nix" not in result
        assert "neovim.nix" not in result

    def test_nonexistent_subdir_returns_error(self, repo):
        result = call_tool(ListNixFiles, {"subdir": "does_not_exist"})
        assert result.startswith("ERROR:")

    def test_ignored_dirs_are_skipped(self, repo):
        """Files inside .git / result / .direnv should be invisible."""
        for ignored in [".git", "result", ".direnv"]:
            ignored_dir = repo / ignored
            ignored_dir.mkdir()
            (ignored_dir / "hidden.nix").write_text("# should be ignored")

        result = call_tool(ListNixFiles, {})
        assert "hidden.nix" not in result

    def test_accepts_json_string_params(self, nested_nix_files, repo):
        """call() must handle params arriving as a JSON string."""
        result = call_tool_json(ListNixFiles, {})
        assert "flake.nix" in result

    def test_accepts_empty_string_params(self, nested_nix_files, repo):
        """An empty string should be treated as no params (list everything)."""
        instance = ListNixFiles()
        result = instance.call("")
        assert "flake.nix" in result

    def test_output_is_sorted(self, repo):
        """Paths should be returned in lexicographic order."""
        for name in ["z.nix", "a.nix", "m.nix"]:
            (repo / name).write_text("# x")
        result = call_tool(ListNixFiles, {})
        lines = result.strip().splitlines()
        assert lines == sorted(lines)

    def test_nested_depth(self, repo):
        """Deeply nested files should still be found."""
        deep = repo / "a" / "b" / "c" / "d.nix"
        deep.parent.mkdir(parents=True)
        deep.write_text("# deep")
        result = call_tool(ListNixFiles, {})
        assert "a/b/c/d.nix" in result


# ===========================================================================
# ReadNixFile
# ===========================================================================

class TestReadNixFile:

    def test_reads_file_content(self, nix_file, repo):
        rel = str(nix_file.relative_to(repo))
        result = call_tool(ReadNixFile, {"path": rel})
        assert 'networking.hostName = "myhost"' in result

    def test_missing_path_param_returns_error(self, repo):
        result = call_tool(ReadNixFile, {"path": ""})
        assert result.startswith("ERROR:")
        assert "required" in result.lower()

    def test_file_not_found_returns_error(self, repo):
        result = call_tool(ReadNixFile, {"path": "nonexistent.nix"})
        assert result.startswith("ERROR:")
        assert "not found" in result.lower()

    def test_wrong_extension_returns_error(self, repo):
        txt = repo / "notes.txt"
        txt.write_text("hello")
        result = call_tool(ReadNixFile, {"path": "notes.txt"})
        assert result.startswith("ERROR:")
        assert ".nix" in result

    def test_accepts_json_string_params(self, nix_file, repo):
        rel = str(nix_file.relative_to(repo))
        result = call_tool_json(ReadNixFile, {"path": rel})
        assert "hostName" in result

    def test_reads_unicode_content(self, repo):
        """Files with non-ASCII content (comments in other scripts) should read fine."""
        f = repo / "unicode.nix"
        content = "# 日本語コメント\n{ }\n"
        f.write_text(content, encoding="utf-8")
        result = call_tool(ReadNixFile, {"path": "unicode.nix"})
        assert "日本語" in result

    def test_reads_large_file(self, repo):
        """No artificial size cap should prevent reading a large file."""
        f = repo / "big.nix"
        content = "# line\n" * 10_000
        f.write_text(content)
        result = call_tool(ReadNixFile, {"path": "big.nix"})
        assert result.count("# line") == 10_000

    def test_reads_empty_file(self, repo):
        """An empty .nix file is valid and should return an empty string."""
        f = repo / "empty.nix"
        f.write_text("")
        result = call_tool(ReadNixFile, {"path": "empty.nix"})
        assert result == ""

    def test_subdirectory_path(self, repo):
        """Relative paths with subdirs should be handled correctly."""
        subdir = repo / "hosts"
        subdir.mkdir()
        f = subdir / "laptop.nix"
        f.write_text('{ networking.hostName = "laptop"; }')
        result = call_tool(ReadNixFile, {"path": "hosts/laptop.nix"})
        assert "laptop" in result
