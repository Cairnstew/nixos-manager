"""
Tests for searchix.server lifecycle management.
"""

import os
import signal
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from searchix.server import (
    write_config, find_binary, is_server_ready, is_process_running,
    start, stop, status, ensure_ready,
    CONFIG_DIR, DATA_DIR, CONFIG_FILE, PID_FILE, LOG_FILE,
    ENABLED_SOURCES, SERVER_HOST, SERVER_PORT,
)


class TestConfigGeneration:
    """Test config file generation."""

    def test_write_config_creates_directories(self, temp_home):
        """Test that write_config creates necessary directories."""
        config_path = write_config()
        assert config_path.exists()
        assert CONFIG_DIR.exists()
        assert DATA_DIR.exists()

    def test_write_config_content(self, temp_home):
        """Test config file contains expected sections."""
        write_config()
        content = CONFIG_FILE.read_text()
        
        assert "[Web]" in content
        assert "[Importer]" in content
        assert "GracefulShutdownTimeout" in content
        assert "Port" in content
        assert "BaseURL" in content

    def test_write_config_with_custom_sources(self, temp_home):
        """Test config with specific sources enabled."""
        sources = {"nixos", "nixpkgs"}
        write_config(sources=sources)
        content = CONFIG_FILE.read_text()
        
        assert "nixos" in content
        assert "nixpkgs" in content

    def test_write_config_with_custom_port(self, temp_home):
        """Test config with custom port."""
        port = 8080
        write_config(port=port)
        content = CONFIG_FILE.read_text()
        
        assert f"Port = {port}" in content
        assert f"BaseURL = 'http://localhost:{port}'" in content

    def test_write_config_with_custom_data_dir(self, temp_home):
        """Test config with custom data directory."""
        custom_dir = temp_home / "custom_data"
        write_config(data_dir=custom_dir)
        content = CONFIG_FILE.read_text()
        
        assert str(custom_dir) in content

    def test_write_config_overwrites_existing(self, temp_home):
        """Test that write_config overwrites existing config."""
        write_config(port=3000)
        write_config(port=4000)
        
        content = CONFIG_FILE.read_text()
        assert "Port = 4000" in content


class TestBinaryDetection:
    """Test searchix-web binary detection."""

    def test_find_binary_in_local_bin(self, temp_home):
        """Test finding binary in ~/.local/bin."""
        local_bin = temp_home / ".local" / "bin"
        local_bin.mkdir(parents=True)
        binary_path = local_bin / "searchix-web"
        binary_path.touch()

        result = find_binary()
        assert result == str(binary_path)

    def test_find_binary_in_path(self, temp_home, monkeypatch):
        """Test finding binary in PATH via shutil.which."""
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/searchix-web" if x == "searchix-web" else None)

        result = find_binary()
        assert "/usr/bin/searchix-web" in result

    def test_find_binary_not_found(self, temp_home, monkeypatch):
        """Test error when binary not found."""
        monkeypatch.setattr("shutil.which", lambda x: None)

        with pytest.raises(FileNotFoundError, match="searchix-web not found"):
            find_binary()

    def test_find_binary_error_message_contains_hint(self, temp_home, monkeypatch):
        """Test error message contains installation hint."""
        monkeypatch.setattr("shutil.which", lambda x: None)

        with pytest.raises(FileNotFoundError) as exc_info:
            find_binary()
        
        assert "nix-env" in str(exc_info.value)


class TestServerConnectivity:
    """Test server connectivity checks."""

    def test_is_server_ready_true(self, monkeypatch):
        """Test server ready detection."""
        mock_socket = MagicMock()
        monkeypatch.setattr("socket.create_connection", lambda addr, timeout: mock_socket)

        assert is_server_ready() is True

    def test_is_server_ready_false(self, monkeypatch):
        """Test server not ready detection."""
        def raise_error(addr, timeout):
            raise OSError("Connection refused")
        
        monkeypatch.setattr("socket.create_connection", raise_error)
        assert is_server_ready() is False

    def test_is_server_ready_timeout(self, monkeypatch):
        """Test server ready with timeout."""
        import socket as socket_module
        
        def raise_timeout(addr, timeout):
            raise socket_module.timeout()
        
        monkeypatch.setattr("socket.create_connection", raise_timeout)
        assert is_server_ready() is False

    def test_is_process_running_true(self, monkeypatch):
        """Test process running detection."""
        monkeypatch.setattr("os.kill", lambda pid, sig: None)
        assert is_process_running(1234) is True

    def test_is_process_running_false(self, monkeypatch):
        """Test process not running detection."""
        def raise_lookup(pid, sig):
            raise ProcessLookupError()
        
        monkeypatch.setattr("os.kill", raise_lookup)
        assert is_process_running(1234) is False

    def test_is_process_running_permission_denied(self, monkeypatch):
        """Test permission denied treated as not running."""
        def raise_perm(pid, sig):
            raise PermissionError()
        
        monkeypatch.setattr("os.kill", raise_perm)
        assert is_process_running(1234) is False


class TestServerLifecycle:
    """Test server start/stop/status."""

    def test_status_stopped(self, temp_home):
        """Test status when server is stopped."""
        st = status()
        assert st["running"] is False
        assert st["ready"] is False
        assert st["pid"] is None

    def test_status_with_existing_pidfile(self, temp_home, monkeypatch):
        """Test status reads pid from pidfile."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("12345")
        
        monkeypatch.setattr("searchix.server.is_process_running", lambda pid: False)
        st = status()
        assert st["pid"] is None  # process not running

    @patch("searchix.server.find_binary")
    @patch("subprocess.Popen")
    def test_start_server(self, mock_popen, mock_find_binary, temp_home, monkeypatch):
        """Test starting server."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        # Mock server ready
        ready_calls = [False, True]
        ready_iter = iter(ready_calls)
        monkeypatch.setattr("searchix.server.is_server_ready", lambda **kwargs: next(ready_iter))

        pid = start(wait=True)
        assert pid == 9999
        assert PID_FILE.exists()

    @patch("searchix.server.find_binary")
    @patch("subprocess.Popen")
    def test_start_server_already_running(self, mock_popen, mock_find_binary, temp_home, monkeypatch):
        """Test start when server already running."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("5555")
        
        monkeypatch.setattr("searchix.server.is_process_running", lambda pid: True)
        monkeypatch.setattr("searchix.server.is_server_ready", lambda **kwargs: True)

        pid = start(wait=False)
        assert pid == 5555
        # Popen should not be called
        mock_popen.assert_not_called()

    @patch("searchix.server.find_binary")
    def test_start_server_fails_immediately(self, mock_find_binary, temp_home, monkeypatch):
        """Test handling when server exits immediately."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.poll.return_value = 1  # Process exited with code 1
        mock_proc.returncode = 1
        
        with patch("subprocess.Popen", return_value=mock_proc):
            monkeypatch.setattr("searchix.server.is_server_ready", lambda **kwargs: False)
            
            with pytest.raises(RuntimeError, match="exited immediately"):
                start(wait=True)

    @patch("searchix.server.find_binary")
    def test_start_server_timeout(self, mock_find_binary, temp_home, monkeypatch):
        """Test timeout waiting for server to start."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.poll.return_value = None  # Still running
        
        with patch("subprocess.Popen", return_value=mock_proc):
            monkeypatch.setattr("searchix.server.is_server_ready", lambda **kwargs: False)
            
            with pytest.raises(RuntimeError, match="did not become ready"):
                start(wait=True, wait_timeout=0.1)

    def test_stop_not_running(self, temp_home):
        """Test stop when no server running."""
        result = stop()
        assert result is False

    @patch("os.kill")
    def test_stop_running(self, mock_kill, temp_home, monkeypatch):
        """Test stopping running server."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("7777")
        
        # Simulate process becoming not running after kill
        kill_count = [0]
        def mock_is_running(pid):
            kill_count[0] += 1
            return kill_count[0] < 2  # Running on first call, then not running
        
        monkeypatch.setattr("searchix.server.is_process_running", mock_is_running)

        result = stop()
        assert result is True
        mock_kill.assert_called_once_with(7777, signal.SIGTERM)
        assert not PID_FILE.exists()

    @patch("os.kill")
    def test_stop_needs_sigkill(self, mock_kill, temp_home, monkeypatch):
        """Test sending SIGKILL when SIGTERM doesn't work."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("7777")
        
        # Process keeps running despite SIGTERM
        monkeypatch.setattr("searchix.server.is_process_running", lambda pid: True)

        result = stop()
        assert result is True
        # Should be called twice: once with SIGTERM, once with SIGKILL
        assert mock_kill.call_count == 2
        calls = [call[0] for call in mock_kill.call_args_list]
        assert calls[0] == (7777, signal.SIGTERM)
        assert calls[1] == (7777, signal.SIGKILL)

    def test_status_includes_paths(self, temp_home):
        """Test status includes all required paths."""
        st = status()
        assert "config" in st
        assert "data_dir" in st
        assert "log" in st
        assert "url" in st
        assert str(CONFIG_FILE) == st["config"]


class TestEnsureReady:
    """Test ensure_ready function."""

    @patch("searchix.server.is_server_ready")
    def test_ensure_ready_already_running(self, mock_ready):
        """Test ensure_ready when server already ready."""
        mock_ready.return_value = True
        
        result = ensure_ready()
        assert result == "http://localhost:3000"

    @patch("searchix.server.status")
    @patch("searchix.server.is_server_ready")
    def test_ensure_ready_no_index(self, mock_ready, mock_status, temp_home):
        """Test ensure_ready raises when no index exists."""
        mock_ready.return_value = False
        mock_status.return_value = {"index_exists": False}
        
        with pytest.raises(RuntimeError, match="No searchix index found"):
            ensure_ready()

    @patch("searchix.server.is_server_ready")
    @patch("searchix.server.start")
    def test_ensure_ready_starts_server(self, mock_start, mock_ready, temp_home, monkeypatch):
        """Test ensure_ready starts server when index exists."""
        # Create a fake index
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "searchix.bleve").mkdir(parents=True, exist_ok=True)
        
        ready_calls = [False, True]
        ready_iter = iter(ready_calls)
        mock_ready.side_effect = lambda **kwargs: next(ready_iter)
        mock_start.return_value = None
        
        result = ensure_ready()
        assert result == "http://localhost:3000"
        mock_start.assert_called_once()
