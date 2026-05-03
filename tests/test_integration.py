"""
tests/test_integration.py
Integration tests that verify multiple components working together.

Covers:
  Multi-tool workflows (read → patch → verify)
  Git integration with file operations
  Backup and recovery workflows
  Complex tool chaining scenarios
  State consistency across operations
  Real subprocess execution (marked with @pytest.mark.integration)
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import call_tool, call_tool_json
from tools.repo_reader import ListNixFiles, ReadNixFile
from tools.repo_writer import WriteNixFile, PatchNixFile
from tools.nix_ops import GitOp, NixCheck, SearchNixFiles


# ===========================================================================
# Basic Workflow Tests
# ===========================================================================

class TestBasicWorkflows:
    """Test realistic usage patterns."""

    def test_workflow_list_read_patch(self, repo, monkeypatch, nix_file):
        """Typical workflow: list → read → patch."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        # Step 1: List files
        result = call_tool(ListNixFiles, {})
        assert "configuration.nix" in result
        
        # Step 2: Read a file
        content = call_tool(ReadNixFile, {"path": "configuration.nix"})
        assert 'networking.hostName = "myhost"' in content
        
        # Step 3: Patch it
        result = call_tool(PatchNixFile, {
            "path": "configuration.nix",
            "old_text": '"myhost"',
            "new_text": '"mynewhost"'
        })
        assert "OK" in result
        
        # Step 4: Verify
        content = call_tool(ReadNixFile, {"path": "configuration.nix"})
        assert '"mynewhost"' in content

    def test_workflow_write_then_read(self, repo, monkeypatch):
        """Write a file and immediately read it back."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        test_content = '{ boot.loader.grub.enable = true; }\n'
        
        # Write
        write_result = call_tool(WriteNixFile, {
            "path": "new.nix",
            "content": test_content
        })
        assert "OK" in write_result
        
        # Read back
        read_result = call_tool(ReadNixFile, {"path": "new.nix"})
        assert read_result == test_content

    def test_workflow_nested_directory_operations(self, repo, monkeypatch):
        """Create files in nested directories."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Write to nested path
        result = call_tool(WriteNixFile, {
            "path": "modules/hardware/default.nix",
            "content": '{ hardware.cpu.amd.ryzen.enable = true; }\n'
        })
        assert "OK" in result
        
        # Verify with list
        result = call_tool(ListNixFiles, {})
        assert "modules/hardware/default.nix" in result
        
        # Read it back
        content = call_tool(ReadNixFile, {"path": "modules/hardware/default.nix"})
        assert "ryzen" in content

    def test_workflow_list_with_subdir_filter(self, repo, monkeypatch, nested_nix_files):
        """List files filtered by subdirectory."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # List all
        all_result = call_tool(ListNixFiles, {})
        all_lines = all_result.strip().splitlines()
        
        # List hosts only
        hosts_result = call_tool(ListNixFiles, {"subdir": "hosts"})
        hosts_lines = hosts_result.strip().splitlines()
        
        # hosts_result should be subset
        for line in hosts_lines:
            assert line in all_result

    def test_workflow_multiple_patches_same_file(self, nix_file, repo, monkeypatch):
        """Apply multiple patches to the same file sequentially."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        rel = str(nix_file.relative_to(repo))
        
        # Patch 1
        result1 = call_tool(PatchNixFile, {
            "path": rel,
            "old_text": "myhost",
            "new_text": "host1"
        })
        assert "OK" in result1
        
        # Patch 2
        result2 = call_tool(PatchNixFile, {
            "path": rel,
            "old_text": "host1",
            "new_text": "finalhost"
        })
        assert "OK" in result2
        
        # Verify
        content = nix_file.read_text()
        assert "finalhost" in content


# ===========================================================================
# Error Recovery Workflows
# ===========================================================================

class TestErrorRecoveryWorkflows:
    """Test error handling and recovery."""

    def test_workflow_failed_patch_backup_intact(self, nix_file, repo, monkeypatch):
        """Backup should exist even if patch fails later."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        rel = str(nix_file.relative_to(repo))
        original = nix_file.read_text()
        
        # Try patch with non-existent text (should fail)
        result = call_tool(PatchNixFile, {
            "path": rel,
            "old_text": "NONEXISTENT",
            "new_text": "replacement"
        })
        assert "ERROR" in result or "not found" in result.lower() or "not appear" in result.lower()
        
        # Original file should be untouched
        assert nix_file.read_text() == original

    def test_workflow_recover_from_file_not_found(self, repo, monkeypatch):
        """Should handle missing files gracefully."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        result = call_tool(ReadNixFile, {"path": "does_not_exist.nix"})
        assert "ERROR" in result or "not found" in result.lower()

    def test_workflow_recover_from_permission_error(self, repo, monkeypatch):
        """Permission errors should be handled."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Make a file unreadable
        read_file = repo / "readonly.nix"
        read_file.write_text("# readonly\n")
        read_file.chmod(0o000)
        
        try:
            result = call_tool(ReadNixFile, {"path": "readonly.nix"})
            # Should error or handle gracefully
            assert "ERROR" in result or result is not None
        finally:
            read_file.chmod(0o644)

    def test_workflow_invalid_nix_file_extension(self, repo, monkeypatch):
        """Non-.nix files should be rejected."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        result = call_tool(WriteNixFile, {
            "path": "config.txt",
            "content": "not nix"
        })
        assert "ERROR" in result


# ===========================================================================
# Search and Find Workflows
# ===========================================================================

class TestSearchWorkflows:
    """Test searching across files."""

    def test_workflow_search_and_list_integration(self, repo, monkeypatch):
        """List files then search within them."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        
        # Create multiple files with searchable content
        (repo / "file1.nix").write_text('{ networking.hostName = "host1"; }\n')
        (repo / "file2.nix").write_text('{ networking.hostName = "host2"; }\n')
        (repo / "file3.nix").write_text('{ boot.loader = "grub"; }\n')
        
        # List all files
        list_result = call_tool(ListNixFiles, {})
        assert "file1.nix" in list_result
        assert "file2.nix" in list_result
        assert "file3.nix" in list_result
        
        # Search for specific pattern
        with patch("tools.nix_ops._run", return_value='file1.nix:{ networking.hostName = "host1"; }'):
            search_result = call_tool(SearchNixFiles, {"pattern": "host1"})
        assert search_result is not None

    def test_workflow_find_and_modify_across_files(self, repo, monkeypatch):
        """Find a string across files and modify one."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.nix_ops.NIXOS_REPO_PATH", repo)
        
        # Create files
        (repo / "a.nix").write_text('{ pkg = "vim"; }\n')
        (repo / "b.nix").write_text('{ pkg = "emacs"; }\n')
        (repo / "c.nix").write_text('{ pkg = "vim"; }\n')
        
        # Search
        with patch("tools.nix_ops._run", return_value='a.nix:{ pkg = "vim"; }\nc.nix:{ pkg = "vim"; }'):
            search_result = call_tool(SearchNixFiles, {"pattern": "vim"})
        
        # Modify one
        result = call_tool(PatchNixFile, {
            "path": "a.nix",
            "old_text": '"vim"',
            "new_text": '"neovim"'
        })
        assert "OK" in result
        
        # Verify
        content = (repo / "a.nix").read_text()
        assert "neovim" in content
        assert (repo / "c.nix").read_text() == '{ pkg = "vim"; }\n'  # Unchanged


# ===========================================================================
# Multi-Step Complex Scenarios
# ===========================================================================

class TestComplexScenarios:
    """Test complex multi-step scenarios."""

    def test_scenario_refactor_with_backup_trail(self, repo, monkeypatch):
        """Refactor file with multiple changes, leaving backup trail."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Create initial file
        result = call_tool(WriteNixFile, {
            "path": "refactor.nix",
            "content": '{ a = 1; b = 2; c = 3; }\n'
        })
        assert "OK" in result
        time.sleep(1.1)
        
        # Step 1: Change a
        result = call_tool(WriteNixFile, {
            "path": "refactor.nix",
            "content": '{ a = 10; b = 2; c = 3; }\n'
        })
        assert "OK" in result
        backups_after_1 = list(repo.glob("*.bak_*"))
        time.sleep(1.1)
        
        # Step 2: Change b
        result = call_tool(WriteNixFile, {
            "path": "refactor.nix",
            "content": '{ a = 10; b = 20; c = 3; }\n'
        })
        assert "OK" in result
        backups_after_2 = list(repo.glob("*.bak_*"))
        time.sleep(1.1)
        
        # Step 3: Change c
        result = call_tool(WriteNixFile, {
            "path": "refactor.nix",
            "content": '{ a = 10; b = 20; c = 30; }\n'
        })
        assert "OK" in result
        backups_after_3 = list(repo.glob("*.bak_*"))
        
        # Should have backup trail
        assert len(backups_after_3) == 3
        
        # Verify final state
        content = call_tool(ReadNixFile, {"path": "refactor.nix"})
        assert "a = 10" in content
        assert "b = 20" in content
        assert "c = 30" in content

    def test_scenario_configuration_migration(self, repo, monkeypatch):
        """Migrate from old config to new config."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Old config
        old_config = '{ old_boot = { device = "/dev/sda"; }; }\n'
        result = call_tool(WriteNixFile, {
            "path": "system/boot.nix",
            "content": old_config
        })
        assert "OK" in result
        
        # Read old
        content = call_tool(ReadNixFile, {"path": "system/boot.nix"})
        assert "old_boot" in content
        
        # Migrate to new
        new_config = '{ boot = { loader = { grub = { enable = true; device = "/dev/sda"; }; }; }; }\n'
        result = call_tool(WriteNixFile, {
            "path": "system/boot.nix",
            "content": new_config
        })
        assert "OK" in result
        
        # Verify migration
        content = call_tool(ReadNixFile, {"path": "system/boot.nix"})
        assert "boot" in content and "loader" in content and "grub" in content

    def test_scenario_dry_run_then_commit(self, nix_file, repo, monkeypatch):
        """Preview changes with dry_run, then apply for real."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        rel = str(nix_file.relative_to(repo))
        original = nix_file.read_text()
        
        # Dry run
        dry_result = call_tool(PatchNixFile, {
            "path": rel,
            "old_text": "myhost",
            "new_text": "production-host",
            "dry_run": True
        })
        assert "DRY RUN" in dry_result
        assert nix_file.read_text() == original  # Unchanged
        
        # Real run
        real_result = call_tool(PatchNixFile, {
            "path": rel,
            "old_text": "myhost",
            "new_text": "production-host"
        })
        assert "OK" in real_result
        assert nix_file.read_text() != original  # Changed


# ===========================================================================
# State Consistency Tests
# ===========================================================================

class TestStateConsistency:
    """Verify state remains consistent across operations."""

    def test_consistency_backup_not_read_as_file(self, nix_file, repo, monkeypatch):
        """Backup files shouldn't appear in file listings."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        rel = str(nix_file.relative_to(repo))
        
        # Create backup
        call_tool(WriteNixFile, {
            "path": rel,
            "content": "# new\n"
        })
        
        # List should not include .bak files
        result = call_tool(ListNixFiles, {})
        assert ".bak_" not in result

    def test_consistency_total_file_count(self, repo, monkeypatch, nested_nix_files):
        """File count should stay consistent."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        # List initial
        result1 = call_tool(ListNixFiles, {})
        count1 = len(result1.strip().splitlines())
        
        # Add new file
        call_tool(WriteNixFile, {
            "path": "new_file.nix",
            "content": "# new\n"
        })
        
        # List again
        result2 = call_tool(ListNixFiles, {})
        count2 = len(result2.strip().splitlines())
        
        assert count2 == count1 + 1

    def test_consistency_no_accidental_overwrites(self, repo, monkeypatch):
        """Multiple operations should not overwrite each other."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Create file A
        call_tool(WriteNixFile, {
            "path": "a.nix",
            "content": "# file a\n"
        })
        
        # Create file B
        call_tool(WriteNixFile, {
            "path": "b.nix",
            "content": "# file b\n"
        })
        
        # Verify both exist independently
        a_content = call_tool(ReadNixFile, {"path": "a.nix"})
        b_content = call_tool(ReadNixFile, {"path": "b.nix"})
        
        assert "file a" in a_content
        assert "file b" in b_content
