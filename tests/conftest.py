"""
Pytest configuration and shared fixtures for nixos-manager tests.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src directory to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def temp_home(tmp_path):
    """Provide a temporary home directory for testing."""
    old_home = os.environ.get("HOME")
    test_home = tmp_path / "home"
    test_home.mkdir()
    os.environ["HOME"] = str(test_home)
    yield test_home
    if old_home:
        os.environ["HOME"] = old_home


@pytest.fixture
def mock_subprocess(monkeypatch):
    """Mock subprocess for testing server start/stop without actually running it."""
    mock_popen = MagicMock()
    mock_popen.pid = 12345
    mock_popen.poll.return_value = None  # Process still running
    
    def mock_popen_factory(*args, **kwargs):
        return mock_popen
    
    monkeypatch.setattr("subprocess.Popen", mock_popen_factory)
    return mock_popen


@pytest.fixture
def mock_socket(monkeypatch):
    """Mock socket for testing server connectivity checks."""
    mock_conn = MagicMock()
    
    def mock_create_connection(address, timeout):
        # By default, simulate successful connection
        return mock_conn
    
    monkeypatch.setattr("socket.create_connection", mock_create_connection)
    return mock_conn


@pytest.fixture
def mock_server_unavailable(monkeypatch):
    """Mock socket to simulate server unavailable."""
    def mock_create_connection(address, timeout):
        raise OSError("Connection refused")
    
    monkeypatch.setattr("socket.create_connection", mock_create_connection)


@pytest.fixture
def sample_html_response():
    """Sample HTML response from searchix-web."""
    return """
    <table><thead></thead><tbody>
      <tr>
        <td><a class="open-dialog" href="ghostty?query=ghostty&scoped">ghostty</a></td>
        <td class="description"><p>Fast terminal emulator</p><dialog>{"score": 0.95}</dialog></td>
        <td class="score">0.95</td>
      </tr>
      <tr>
        <td><a class="open-dialog" href="programs.ghostty.enable?query=enable&scoped">programs.ghostty.enable</a></td>
        <td class="description"><p>Enable ghostty</p><dialog>{"score": 0.87}</dialog></td>
        <td class="score">0.87</td>
      </tr>
    </tbody></table>
    """


@pytest.fixture
def sample_empty_response():
    """Sample empty HTML response from searchix-web."""
    return "<table><thead></thead><tbody></tbody></table>"
