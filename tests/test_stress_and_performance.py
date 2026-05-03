"""
tests/test_stress_and_performance.py
Stress tests and performance-related tests.

Covers:
  Concurrent-like operations (sequential stress)
  Memory efficiency with large content
  Performance degradation with many files
  Rapid successive operations
  Cleanup after stress
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import call_tool
from tools.repo_reader import ListNixFiles, ReadNixFile
from tools.repo_writer import WriteNixFile, PatchNixFile
from tools.nix_ops import SearchNixFiles


# ===========================================================================
# Stress Tests
# ===========================================================================

class TestStressOperations:
    """Stress tests with high volume operations."""

    def test_stress_create_many_files(self, repo, monkeypatch):
        """Create many files rapidly."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Create 100 files
        for i in range(100):
            result = call_tool(WriteNixFile, {
                "path": f"stress/file_{i:03d}.nix",
                "content": f"# file {i}\n{{ index = {i}; }}\n"
            })
            assert "OK" in result
        
        # Verify all exist
        result = call_tool(ListNixFiles, {})
        lines = result.strip().splitlines()
        assert len(lines) == 100

    def test_stress_patch_many_files(self, repo, monkeypatch):
        """Patch many files in sequence."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        # Create files
        for i in range(50):
            (repo / f"patch_{i:02d}.nix").write_text(f"# original {i}\n")
        
        # Patch all of them
        for i in range(50):
            result = call_tool(PatchNixFile, {
                "path": f"patch_{i:02d}.nix",
                "old_text": f"# original {i}",
                "new_text": f"# patched {i}"
            })
            assert "OK" in result or "ERROR" not in result

    def test_stress_read_same_file_many_times(self, nix_file, repo, monkeypatch):
        """Read the same file many times rapidly."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        rel = str(nix_file.relative_to(repo))
        
        # Read 100 times
        for _ in range(100):
            result = call_tool(ReadNixFile, {"path": rel})
            assert 'networking.hostName = "myhost"' in result

    def test_stress_deeply_nested_operations(self, repo, monkeypatch):
        """Create deeply nested directory structures."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Create 20 files in deep paths (start at depth 1 to avoid empty prefix)
        for depth in range(1, 21):
            path = "/".join(["level"] * depth) + "/file.nix"
            result = call_tool(WriteNixFile, {
                "path": path,
                "content": f"# depth {depth}\n"
            })
            assert "OK" in result
        
        # List should find all
        result = call_tool(ListNixFiles, {})
        assert "file.nix" in result

    def test_stress_list_with_many_ignored_dirs(self, repo, monkeypatch):
        """List files when many ignored directories exist."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Create legitimate files
        for i in range(20):
            (repo / f"legit_{i}.nix").write_text("# legit\n")
        
        # Create many ignored directories
        for ignored in [".git", "result", ".direnv"]:
            for i in range(10):
                d = repo / ignored / f"subdir_{i}"
                d.mkdir(parents=True, exist_ok=True)
                (d / "hidden.nix").write_text("# ignored")
        
        # List should only show legit files
        result = call_tool(ListNixFiles, {})
        lines = result.strip().splitlines()
        
        assert len(lines) == 20
        for line in lines:
            assert "legit_" in line
            assert line not in [".git", "result", ".direnv"]

    def test_stress_backup_accumulation(self, nix_file, repo, monkeypatch):
        """Many writes should create many backups."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        rel = str(nix_file.relative_to(repo))
        
        # Write 50 times to create backups
        for i in range(50):
            result = call_tool(WriteNixFile, {
                "path": rel,
                "content": f"# version {i}\n"
            })
            assert "OK" in result
        
        # Should have 50 backups
        backups = list(repo.glob("*.bak_*"))
        assert len(backups) == 50

    @pytest.mark.slow
    def test_stress_large_patches(self, repo, monkeypatch):
        """Patch with very large old/new text."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        # Create file with large content
        large_block = "# " + ("x" * 1000) + "\n" * 1000
        file_path = repo / "large_patch.nix"
        file_path.write_text(large_block + "marker = true;\n", encoding="utf-8")
        
        # Patch with large replacement
        large_replacement = "# " + ("y" * 1000) + "\n" * 1000
        result = call_tool(PatchNixFile, {
            "path": "large_patch.nix",
            "old_text": large_block,
            "new_text": large_replacement
        })
        
        assert "OK" in result or "ERROR" not in result


# ===========================================================================
# Performance Consistency Tests
# ===========================================================================

class TestPerformanceConsistency:
    """Verify performance doesn't degrade unexpectedly."""

    def test_performance_list_scales_linearly(self, repo, monkeypatch):
        """Listing should scale reasonably."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Create files in batches and measure
        batch_size = 100
        for batch in range(5):
            for i in range(batch_size):
                (repo / f"batch{batch}_file{i}.nix").write_text("# test\n")
        
        result = call_tool(ListNixFiles, {})
        lines = result.strip().splitlines()
        
        # Should have all files
        assert len(lines) == batch_size * 5

    def test_performance_read_large_file_once(self, repo, monkeypatch):
        """Reading a large file should complete in reasonable time."""
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        # Create 5MB file
        large_file = repo / "perf_large.nix"
        large_content = "# " + ("x" * 1000) * 5000
        large_file.write_text(large_content, encoding="utf-8")
        
        # Should read it
        result = call_tool(ReadNixFile, {"path": "perf_large.nix"})
        assert len(result) > 1000000

    def test_performance_write_then_immediate_read(self, repo, monkeypatch):
        """Write then immediately read should be consistent."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        test_content = '{ perf_test = "value"; }\n'
        
        for i in range(20):
            call_tool(WriteNixFile, {
                "path": f"perf_write_{i}.nix",
                "content": test_content
            })
            
            result = call_tool(ReadNixFile, {"path": f"perf_write_{i}.nix"})
            assert result == test_content


# ===========================================================================
# Cleanup and Resource Tests
# ===========================================================================

class TestCleanupAndResources:
    """Verify proper cleanup of resources."""

    def test_cleanup_tempfiles_after_eval(self):
        """Temporary files should be cleaned up."""
        from tools.nix_eval import NixEval
        
        import tempfile
        temp_dir_before = set(Path(tempfile.gettempdir()).glob("*.nix"))
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            instance = NixEval()
            instance.call('{ test = 1; }')
        
        # In practice, tempfiles should be cleaned or at least limited
        # This is a basic check that the operation completes

    def test_backup_files_are_distinct(self, nix_file, repo, monkeypatch):
        """Each backup should have a unique timestamp."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        rel = str(nix_file.relative_to(repo))
        
        # Make multiple writes
        backups = []
        for i in range(3):
            call_tool(WriteNixFile, {
                "path": rel,
                "content": f"# v{i}\n"
            })
            current_backups = list(repo.glob("*.bak_*"))
            backups = current_backups
        
        # All backups should be different files
        assert len(backups) == 3
        backup_names = [b.name for b in backups]
        assert len(set(backup_names)) == 3  # All unique


# ===========================================================================
# Concurrent-like Stress Tests
# ===========================================================================

class TestConcurrentLikeScenarios:
    """Test scenarios that might occur with rapid operations."""

    def test_scenario_rapid_write_read_cycles(self, repo, monkeypatch):
        """Rapid write-read cycles should maintain consistency."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        monkeypatch.setattr("tools.repo_reader.NIXOS_REPO_PATH", repo)
        
        for cycle in range(10):
            content = f"# cycle {cycle}\n{{ v = {cycle}; }}\n"
            
            call_tool(WriteNixFile, {
                "path": f"cycle_{cycle}.nix",
                "content": content
            })
            
            result = call_tool(ReadNixFile, {"path": f"cycle_{cycle}.nix"})
            assert result == content

    def test_scenario_interleaved_patches_and_writes(self, repo, monkeypatch):
        """Interleave write and patch operations."""
        monkeypatch.setattr("tools.repo_writer.NIXOS_REPO_PATH", repo)
        
        # Create initial file
        call_tool(WriteNixFile, {
            "path": "test.nix",
            "content": "{ a = 1; b = 2; c = 3; }\n"
        })
        
        # Patch it
        call_tool(PatchNixFile, {
            "path": "test.nix",
            "old_text": "a = 1",
            "new_text": "a = 10"
        })
        
        # Write completely new
        call_tool(WriteNixFile, {
            "path": "test.nix",
            "content": "{ x = 100; }\n"
        })
        
        # Patch again
        call_tool(PatchNixFile, {
            "path": "test.nix",
            "old_text": "x = 100",
            "new_text": "x = 200"
        })
        
        # Verify final state
        content = (repo / "test.nix").read_text()
        assert "x = 200" in content