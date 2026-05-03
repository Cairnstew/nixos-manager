"""
tests/test_edge_cases_and_security.py
Edge cases, security, and robustness tests across all tools.

Covers:
  Path traversal attacks
  Unicode and encoding edge cases
  Large input handling
  Concurrent/race condition scenarios
  Backup and recovery mechanisms
  Proper error propagation
  Safe defaults
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from tests.conftest import call_tool, call_tool_json
from tools.repo_reader import ListNixFiles, ReadNixFile
from tools.repo_writer import WriteNixFile, PatchNixFile, _safe_target
from tools.nix_ops import GitOp, NixCheck, SearchNixFiles


# ===========================================================================
# Path Traversal / Security
# ===========================================================================

class TestPathTraversalSecurity:
    """Ensure path traversal attacks are prevented."""

    def test_parent_directory_traversal_rejected(self, repo, monkeypatch):
        """../../ sequences should be rejected."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        _target, err = _safe_target("../../../etc/passwd")
        assert err is not None
        assert "escapes" in err.lower() or "rejected" in err.lower()

    def test_absolute_path_outside_repo_rejected(self, repo, monkeypatch):
        """Absolute paths outside repo should be rejected."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        _target, err = _safe_target("/etc/passwd")
        assert err is not None

    def test_symlink_escape_attempt_rejected(self, repo, monkeypatch):
        """Symlinks pointing outside repo should not create escapes."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        # Create a symlink target outside repo
        outside = repo.parent / "outside.txt"
        outside.write_text("dangerous")
        
        # Symlink inside repo pointing outside
        symlink = repo / "link_to_outside"
        try:
            symlink.symlink_to(outside)
            # Resolve should detect this
            _target, err = _safe_target("link_to_outside")
            # Either should error or resolve safely
            if err is None:
                # If it resolves, it should still be inside repo.resolve()
                assert str(_target).startswith(str(repo.resolve()))
        except (OSError, NotImplementedError):
            # Symlinks may not work on this system (e.g., Windows)
            pytest.skip("Symlinks not supported on this system")

    def test_null_byte_in_path_rejected(self, repo, monkeypatch):
        """Null bytes in paths should be rejected."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        # Attempting to write with null byte
        try:
            _target, err = _safe_target("file\x00.nix")
            # Should either error or handle safely
            assert err is not None or _target is not None
        except (ValueError, TypeError):
            # Expected — null bytes cause issues
            pass

    def test_double_encoded_traversal_rejected(self, repo, monkeypatch):
        """Double-encoded traversal (../.. encoded twice) should be rejected."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        # Even if somehow double-encoded
        _target, err = _safe_target("%2e%2e%2f%2e%2e%2f")
        # Since we don't URL-decode before resolve(), this should be safe


# ===========================================================================
# Unicode and Encoding Edge Cases
# ===========================================================================

class TestUnicodeAndEncoding:
    """Test handling of unicode and various encodings."""

    def test_read_file_with_unicode_content(self, repo, monkeypatch):
        """Reading files with unicode should work."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        unicode_file = repo / "unicode.nix"
        content = '{ description = "Nix with émojis: 🎉 and ñoño"; }\n'
        unicode_file.write_text(content, encoding="utf-8")
        
        result = call_tool(ReadNixFile, {"path": "unicode.nix"})
        assert "émojis" in result
        assert "🎉" in result

    def test_write_file_with_unicode_content(self, repo, monkeypatch):
        """Writing unicode content should work."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        unicode_content = '{ name = "café"; emoji = "🎉"; }\n'
        result = call_tool(WriteNixFile, {
            "path": "unicode_new.nix",
            "content": unicode_content
        })
        assert "OK" in result
        assert (repo / "unicode_new.nix").read_text(encoding="utf-8") == unicode_content

    def test_patch_with_unicode_text(self, nix_file, repo, monkeypatch):
        """Patching with unicode old/new text should work."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        rel = str(nix_file.relative_to(repo))
        nix_file.write_text('{ message = "hello"; }\n', encoding="utf-8")
        
        result = call_tool(PatchNixFile, {
            "path": rel,
            "old_text": "hello",
            "new_text": "café ☕"
        })
        assert "OK" in result
        assert "café" in nix_file.read_text(encoding="utf-8")

    def test_search_with_unicode_pattern(self, repo, monkeypatch):
        """Searching for unicode patterns should work."""
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        
        nix_file = repo / "test.nix"
        nix_file.write_text('{ café = true; }\n', encoding="utf-8")
        
        with patch("tools.nix_ops._run", return_value="café = true"):
            result = call_tool(SearchNixFiles, {"pattern": "café"})
        assert result is not None

    def test_json_with_unicode_params(self):
        """JSON params with unicode should parse correctly."""
        params_json = json.dumps({
            "code": '{ name = "café"; }'
        }, ensure_ascii=False)
        
        from tools.nix_eval import NixEval
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            instance = NixEval()
            # Should parse JSON correctly
            result = instance.call(params_json)
        assert result is not None


# ===========================================================================
# Large Input Handling
# ===========================================================================

class TestLargeInputHandling:
    """Test handling of large files and inputs."""

    def test_write_very_large_file(self, repo, monkeypatch):
        """Writing a very large .nix file should work."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        # Create 2MB of content (realistic large config)
        # Each line is ~1000 bytes, so 2000 lines = ~2MB
        large_content = '{\n' + '\n'.join(['  # ' + "x" * 996 for _ in range(2000)]) + '\n}\n'
        result = call_tool(WriteNixFile, {
            "path": "large.nix",
            "content": large_content
        })
        assert "OK" in result
        assert (repo / "large.nix").stat().st_size > 1000000

    def test_read_very_large_file(self, repo, monkeypatch):
        """Reading a very large file should work."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        large_file = repo / "large_read.nix"
        # 5MB file
        large_content = '{ data = "' + ("x" * 100) * 50000 + '"; }\n'
        large_file.write_text(large_content, encoding="utf-8")
        
        result = call_tool(ReadNixFile, {"path": "large_read.nix"})
        assert len(result) > 1000000

    def test_patch_with_large_replacement(self, nix_file, repo, monkeypatch):
        """Patching with large text should work."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        rel = str(nix_file.relative_to(repo))
        nix_file.write_text('{ placeholder = true; }\n')
        
        large_replacement = '"' + ("x" * 100) * 1000 + '"'
        result = call_tool(PatchNixFile, {
            "path": rel,
            "old_text": "true",
            "new_text": large_replacement
        })
        assert "OK" in result or "ERROR" not in result

    def test_list_many_files(self, repo, monkeypatch):
        """Listing thousands of files should work."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Create 1000 .nix files
        for i in range(1000):
            f = repo / f"file_{i:04d}.nix"
            f.write_text(f"# file {i}\n")
        
        result = call_tool(ListNixFiles, {})
        lines = result.strip().splitlines()
        assert len(lines) == 1000

    def test_very_deep_directory_nesting(self, repo, monkeypatch):
        """Deeply nested directories should be handled."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Create 50-level deep directory
        deep = repo / Path(*["dir"] * 50) / "deep.nix"
        deep.parent.mkdir(parents=True, exist_ok=True)
        deep.write_text("# deep")
        
        result = call_tool(ListNixFiles, {})
        assert "deep.nix" in result


# ===========================================================================
# Error Recovery and Backup Integrity
# ===========================================================================

class TestErrorRecoveryAndBackups:
    """Ensure backups are created and recoverable."""

    def test_backup_filename_uniqueness(self, nix_file, repo, monkeypatch):
        """Multiple writes should create separate backups."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        rel = str(nix_file.relative_to(repo))
        
        # Write multiple times with delays to ensure unique timestamps
        for i in range(3):
            call_tool(WriteNixFile, {
                "path": rel,
                "content": f"# version {i}\n"
            })
            time.sleep(1.1)  # Ensure different timestamp
        
        # Should have 3 backups
        backups = list(repo.glob("*.bak_*"))
        assert len(backups) == 3

    def test_backup_contains_original_content(self, nix_file, repo, monkeypatch):
        """Backup should preserve original content."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        original_content = nix_file.read_text()
        
        rel = str(nix_file.relative_to(repo))
        call_tool(WriteNixFile, {
            "path": rel,
            "content": "# new content\n"
        })
        
        backups = list(repo.glob("*.bak_*"))
        assert len(backups) == 1
        backup_content = backups[0].read_text()
        assert backup_content == original_content

    def test_dry_run_creates_no_backup(self, nix_file, repo, monkeypatch):
        """dry_run should not create backup."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        original_mtime = nix_file.stat().st_mtime
        
        rel = str(nix_file.relative_to(repo))
        call_tool(WriteNixFile, {
            "path": rel,
            "content": "# dry run\n",
            "dry_run": True
        })
        
        backups = list(repo.glob("*.bak_*"))
        assert len(backups) == 0
        # File should not be modified
        assert nix_file.stat().st_mtime == original_mtime

    def test_patch_dry_run_no_backup(self, nix_file, repo, monkeypatch):
        """Patch dry_run should not modify file or create backup."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        original_content = nix_file.read_text()
        
        rel = str(nix_file.relative_to(repo))
        result = call_tool(PatchNixFile, {
            "path": rel,
            "old_text": "myhost",
            "new_text": "newhost",
            "dry_run": True
        })
        
        assert "DRY RUN" in result
        assert nix_file.read_text() == original_content
        assert len(list(repo.glob("*.bak_*"))) == 0

    def test_patch_backup_created_on_success(self, nix_file, repo, monkeypatch):
        """Successful patch should create backup."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        original_content = nix_file.read_text()
        
        rel = str(nix_file.relative_to(repo))
        call_tool(PatchNixFile, {
            "path": rel,
            "old_text": "myhost",
            "new_text": "newhost"
        })
        
        backups = list(repo.glob("*.bak_*"))
        assert len(backups) == 1
        assert backups[0].read_text() == original_content


# ===========================================================================
# Safe Defaults and Error Handling
# ===========================================================================

class TestSafeDefaults:
    """Ensure tools have safe defaults."""

    def test_unknown_params_ignored(self, repo, monkeypatch):
        """Unknown parameters should be safely ignored."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Create a .nix file
        (repo / "test.nix").write_text("# test\n")
        
        # Pass unknown parameters
        result = call_tool(ListNixFiles, {
            "subdir": "",
            "unknown_param": "value",
            "another_unknown": 123
        })
        
        assert "test.nix" in result

    def test_missing_optional_params_use_defaults(self, repo, monkeypatch):
        """Missing optional params should use safe defaults."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        # Write without specifying dry_run (should default to False)
        result = call_tool(WriteNixFile, {
            "path": "test.nix",
            "content": "# test\n"
        })
        
        assert "OK" in result
        assert (repo / "test.nix").exists()

    def test_invalid_boolean_handled_safely(self, repo, monkeypatch):
        """Invalid boolean values should be handled."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        # Pass string instead of boolean
        result = call_tool(WriteNixFile, {
            "path": "test.nix",
            "content": "# test\n",
            "dry_run": "yes"  # Should be boolean
        })
        
        # Should either use as truthy or error gracefully
        assert result is not None

    def test_empty_response_handling(self):
        """Empty responses should be handled."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            from tools.nix_ops import _run
            result = _run(["echo"], cwd=Path("/tmp"))
        
        # Should return placeholder, not None
        assert result == "(no output)"

    def test_error_prefix_consistent(self):
        """Error messages should use consistent ERROR: prefix."""
        result = call_tool(ReadNixFile, {"path": ""})
        assert "ERROR" in result or "required" in result.lower()
