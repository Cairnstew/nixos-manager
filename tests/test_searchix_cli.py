"""
Tests for searchix.cli command-line interface.
"""

import io
import sys
from unittest.mock import MagicMock, patch, call

import pytest

from searchix.cli import (
    main, cmd_setup, cmd_serve, cmd_stop, cmd_status, cmd_search,
    _build_parser, _is_explicit_command, _truncate, _fmt,
)
from searchix import SearchResult, SearchixError, ALL_SOURCES


class TestHelperFunctions:
    """Test CLI helper functions."""

    def test_truncate_short_text(self):
        """Test truncate with text shorter than limit."""
        text = "short"
        result = _truncate(text, n=100)
        assert result == "short"

    def test_truncate_long_text(self):
        """Test truncate with text longer than limit."""
        text = "a" * 150
        result = _truncate(text, n=100)
        assert len(result) == 101  # 100 + ellipsis
        assert result.endswith("…")

    def test_fmt_result_with_description(self):
        """Test formatting result with description."""
        result = SearchResult(
            source="nixpkgs",
            name="python",
            attribute="packages/nixpkgs/python310",
            description="A high-level programming language",
        )
        formatted = _fmt(result)
        assert "packages/nixpkgs/python310" in formatted
        assert "programming language" in formatted

    def test_fmt_result_without_description(self):
        """Test formatting result without description."""
        result = SearchResult(
            source="nixpkgs",
            name="python",
            attribute="packages/nixpkgs/python310",
        )
        formatted = _fmt(result)
        assert "packages/nixpkgs/python310" in formatted


class TestArgumentParsing:
    """Test argument parser."""

    def test_parser_help(self):
        """Test parser help output."""
        parser = _build_parser()
        assert parser.prog == "searchix"

    def test_is_explicit_command_setup(self):
        """Test detecting setup command."""
        assert _is_explicit_command(["setup"]) is True

    def test_is_explicit_command_serve(self):
        """Test detecting serve command."""
        assert _is_explicit_command(["serve"]) is True

    def test_is_explicit_command_stop(self):
        """Test detecting stop command."""
        assert _is_explicit_command(["stop"]) is True

    def test_is_explicit_command_status(self):
        """Test detecting status command."""
        assert _is_explicit_command(["status"]) is True

    def test_is_explicit_command_search(self):
        """Test detecting search command."""
        assert _is_explicit_command(["search", "python"]) is True

    def test_is_explicit_command_help(self):
        """Test detecting help flag."""
        assert _is_explicit_command(["-h"]) is True
        assert _is_explicit_command(["--help"]) is True

    def test_is_explicit_command_version(self):
        """Test detecting version flag."""
        assert _is_explicit_command(["--version"]) is True

    def test_is_explicit_command_query(self):
        """Test non-explicit query."""
        assert _is_explicit_command(["python"]) is False
        assert _is_explicit_command(["ghostty"]) is False

    def test_parse_search_query(self):
        """Test parsing search query."""
        parser = _build_parser()
        args = parser.parse_args(["search", "python"])
        assert args.search_query == "python"
        assert args.command == "search"

    def test_parse_search_with_sources(self):
        """Test parsing search with source filter."""
        parser = _build_parser()
        args = parser.parse_args(["search", "python", "-s", "nixpkgs"])
        assert args.sources == "nixpkgs"

    def test_parse_search_with_limit(self):
        """Test parsing search with limit."""
        parser = _build_parser()
        args = parser.parse_args(["search", "python", "-l", "50"])
        assert args.limit == 50

    def test_parse_search_with_json(self):
        """Test parsing search with JSON output."""
        parser = _build_parser()
        args = parser.parse_args(["search", "python", "--json"])
        assert args.json is True

    def test_parse_search_with_names(self):
        """Test parsing search with names only."""
        parser = _build_parser()
        args = parser.parse_args(["search", "python", "--names"])
        assert args.names is True

    def test_parse_setup_command(self):
        """Test parsing setup command."""
        parser = _build_parser()
        args = parser.parse_args(["setup"])
        assert args.command == "setup"

    def test_parse_setup_with_sources(self):
        """Test parsing setup with sources."""
        parser = _build_parser()
        args = parser.parse_args(["setup", "--sources", "nixos,nixpkgs"])
        assert args.sources == "nixos,nixpkgs"

    def test_main_implicit_search(self):
        """Test main converts implicit query to search."""
        argv = ["ghostty"]
        parser = _build_parser()
        
        # Simulate implicit search conversion
        if argv and not _is_explicit_command(argv):
            argv = ["search"] + argv
        
        args = parser.parse_args(argv)
        assert args.command == "search"
        assert args.search_query == "ghostty"


class TestCmdSetup:
    """Test setup command."""

    @patch("searchix.cli.find_binary")
    @patch("searchix.cli.write_config")
    @patch("searchix.cli.ingest")
    def test_cmd_setup_success(self, mock_ingest, mock_write, mock_find_binary, capsys):
        """Test successful setup."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        
        args = MagicMock()
        args.sources = None
        
        result = cmd_setup(args)
        assert result == 0
        mock_find_binary.assert_called_once()
        mock_write.assert_called_once()
        mock_ingest.assert_called_once()

    @patch("searchix.cli.find_binary")
    def test_cmd_setup_binary_not_found(self, mock_find_binary, capsys):
        """Test setup fails when binary not found."""
        mock_find_binary.side_effect = FileNotFoundError("searchix-web not found")
        
        args = MagicMock()
        args.sources = None
        
        result = cmd_setup(args)
        assert result == 1

    @patch("searchix.cli.find_binary")
    @patch("searchix.cli.write_config")
    @patch("searchix.cli.ingest")
    def test_cmd_setup_with_sources(self, mock_ingest, mock_write, mock_find_binary):
        """Test setup with specific sources."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        
        args = MagicMock()
        args.sources = "nixos,nixpkgs"
        
        result = cmd_setup(args)
        assert result == 0

    @patch("searchix.cli.find_binary")
    @patch("searchix.cli.write_config")
    @patch("searchix.cli.ingest")
    def test_cmd_setup_ingest_fails(self, mock_ingest, mock_write, mock_find_binary):
        """Test setup handles ingest failure."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        mock_ingest.side_effect = RuntimeError("Ingest failed")
        
        args = MagicMock()
        args.sources = None
        
        result = cmd_setup(args)
        assert result == 1

    @patch("searchix.cli.find_binary")
    @patch("searchix.cli.write_config")
    @patch("searchix.cli.ingest")
    def test_cmd_setup_interrupted(self, mock_ingest, mock_write, mock_find_binary):
        """Test setup handles keyboard interrupt."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        mock_ingest.side_effect = KeyboardInterrupt()
        
        args = MagicMock()
        args.sources = None
        
        result = cmd_setup(args)
        assert result == 1


class TestCmdServe:
    """Test serve command."""

    @patch("searchix.cli.find_binary")
    @patch("searchix.cli.is_server_ready")
    @patch("searchix.cli.start")
    def test_cmd_serve_success(self, mock_start, mock_ready, mock_find_binary):
        """Test successful server start."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        mock_ready.return_value = False
        mock_start.return_value = 12345
        
        args = MagicMock()
        
        result = cmd_serve(args)
        assert result == 0

    @patch("searchix.cli.find_binary")
    @patch("searchix.cli.is_server_ready")
    def test_cmd_serve_already_running(self, mock_ready, mock_find_binary):
        """Test serve when server already running."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        mock_ready.return_value = True
        
        args = MagicMock()
        
        result = cmd_serve(args)
        assert result == 0

    @patch("searchix.cli.find_binary")
    def test_cmd_serve_binary_not_found(self, mock_find_binary):
        """Test serve fails when binary not found."""
        mock_find_binary.side_effect = FileNotFoundError("searchix-web not found")
        
        args = MagicMock()
        
        result = cmd_serve(args)
        assert result == 1

    @patch("searchix.cli.find_binary")
    @patch("searchix.cli.is_server_ready")
    @patch("searchix.cli.start")
    def test_cmd_serve_start_fails(self, mock_start, mock_ready, mock_find_binary):
        """Test serve handles start failure."""
        mock_find_binary.return_value = "/usr/bin/searchix-web"
        mock_ready.return_value = False
        mock_start.side_effect = RuntimeError("Failed to start")
        
        args = MagicMock()
        
        result = cmd_serve(args)
        assert result == 1


class TestCmdStop:
    """Test stop command."""

    @patch("searchix.cli.stop")
    def test_cmd_stop_success(self, mock_stop):
        """Test successful stop."""
        mock_stop.return_value = True
        
        args = MagicMock()
        result = cmd_stop(args)
        assert result == 0

    @patch("searchix.cli.stop")
    def test_cmd_stop_not_running(self, mock_stop):
        """Test stop when not running."""
        mock_stop.return_value = False
        
        args = MagicMock()
        result = cmd_stop(args)
        assert result == 0


class TestCmdStatus:
    """Test status command."""

    @patch("searchix.cli.status")
    def test_cmd_status_running(self, mock_status):
        """Test status when running."""
        mock_status.return_value = {
            "running": True,
            "ready": True,
            "url": "http://localhost:3000",
            "pid": 12345,
            "config": "/home/user/.config/searchix/config.toml",
            "data_dir": "/home/user/.local/share/searchix",
            "log": "/home/user/.local/share/searchix/searchix.log",
            "index_exists": True,
        }
        
        args = MagicMock()
        result = cmd_status(args)
        assert result == 0

    @patch("searchix.cli.status")
    def test_cmd_status_not_running(self, mock_status):
        """Test status when not running."""
        mock_status.return_value = {
            "running": False,
            "ready": False,
            "url": "http://localhost:3000",
            "pid": None,
            "config": "/home/user/.config/searchix/config.toml",
            "data_dir": "/home/user/.local/share/searchix",
            "log": "/home/user/.local/share/searchix/searchix.log",
            "index_exists": False,
        }
        
        args = MagicMock()
        result = cmd_status(args)
        assert result == 0


class TestCmdSearch:
    """Test search command."""

    @patch("searchix.cli.SearchixClient")
    def test_cmd_search_success(self, mock_client_class):
        """Test successful search."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        results = {
            "nixpkgs": [SearchResult("nixpkgs", "python", "packages/nixpkgs/python310")],
            "nixos": [],
            "home-manager": [],
            "darwin": [],
            "nur": [],
        }
        mock_client.search_by_source.return_value = results
        
        args = MagicMock()
        args.query = "python"
        args.sources = None
        args.limit = 25
        args.timeout = 10.0
        args.json = False
        args.names = False
        
        result = cmd_search(args)
        assert result == 0

    @patch("searchix.cli.SearchixClient")
    def test_cmd_search_json_output(self, mock_client_class):
        """Test search with JSON output."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        results = {
            "nixpkgs": [SearchResult("nixpkgs", "python", "packages/nixpkgs/python310", "A language")],
            "nixos": [],
            "home-manager": [],
            "darwin": [],
            "nur": [],
        }
        mock_client.search_by_source.return_value = results
        
        args = MagicMock()
        args.query = "python"
        args.sources = None
        args.limit = 25
        args.timeout = 10.0
        args.json = True
        args.names = False
        
        result = cmd_search(args)
        assert result == 0

    @patch("searchix.cli.SearchixClient")
    def test_cmd_search_names_output(self, mock_client_class):
        """Test search with names only."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        results = {
            "nixpkgs": [SearchResult("nixpkgs", "python", "packages/nixpkgs/python310")],
            "nixos": [],
            "home-manager": [],
            "darwin": [],
            "nur": [],
        }
        mock_client.search_by_source.return_value = results
        
        args = MagicMock()
        args.query = "python"
        args.sources = None
        args.limit = 25
        args.timeout = 10.0
        args.json = False
        args.names = True
        
        result = cmd_search(args)
        assert result == 0

    @patch("searchix.cli.SearchixClient")
    def test_cmd_search_with_sources(self, mock_client_class):
        """Test search with source filter."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        results = {
            "nixpkgs": [SearchResult("nixpkgs", "python", "packages/nixpkgs/python310")],
        }
        mock_client.search_by_source.return_value = results
        
        args = MagicMock()
        args.query = "python"
        args.sources = "nixpkgs"
        args.limit = 25
        args.timeout = 10.0
        args.json = False
        args.names = False
        
        result = cmd_search(args)
        assert result == 0

    @patch("searchix.cli.SearchixClient")
    def test_cmd_search_invalid_source(self, mock_client_class):
        """Test search with invalid source."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        args = MagicMock()
        args.query = "python"
        args.sources = "invalid_source"
        args.limit = 25
        args.timeout = 10.0
        args.json = False
        args.names = False
        
        result = cmd_search(args)
        assert result == 1

    @patch("searchix.cli.SearchixClient")
    def test_cmd_search_connection_error(self, mock_client_class):
        """Test search handles connection error."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.search_by_source.side_effect = SearchixError("Connection refused")
        
        args = MagicMock()
        args.query = "python"
        args.sources = None
        args.limit = 25
        args.timeout = 10.0
        args.json = False
        args.names = False
        
        result = cmd_search(args)
        assert result == 1


class TestMainFunction:
    """Test main entry point."""

    @patch("searchix.cli.cmd_setup")
    def test_main_setup(self, mock_cmd_setup):
        """Test main invokes setup command."""
        mock_cmd_setup.return_value = 0
        result = main(["setup"])
        assert result == 0
        mock_cmd_setup.assert_called_once()

    @patch("searchix.cli.cmd_serve")
    def test_main_serve(self, mock_cmd_serve):
        """Test main invokes serve command."""
        mock_cmd_serve.return_value = 0
        result = main(["serve"])
        assert result == 0
        mock_cmd_serve.assert_called_once()

    @patch("searchix.cli.cmd_stop")
    def test_main_stop(self, mock_cmd_stop):
        """Test main invokes stop command."""
        mock_cmd_stop.return_value = 0
        result = main(["stop"])
        assert result == 0
        mock_cmd_stop.assert_called_once()

    @patch("searchix.cli.cmd_status")
    def test_main_status(self, mock_cmd_status):
        """Test main invokes status command."""
        mock_cmd_status.return_value = 0
        result = main(["status"])
        assert result == 0
        mock_cmd_status.assert_called_once()

    @patch("searchix.cli.cmd_search")
    def test_main_implicit_search(self, mock_cmd_search):
        """Test main converts implicit query to search."""
        mock_cmd_search.return_value = 0
        result = main(["python"])
        assert result == 0
        mock_cmd_search.assert_called_once()

    @patch("searchix.cli.cmd_search")
    def test_main_explicit_search(self, mock_cmd_search):
        """Test main with explicit search command."""
        mock_cmd_search.return_value = 0
        result = main(["search", "python"])
        assert result == 0
        mock_cmd_search.assert_called_once()
