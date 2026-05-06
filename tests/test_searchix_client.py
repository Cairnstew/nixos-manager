"""
Tests for searchix.SearchixClient and SearchResult classes.
"""

import pytest
from unittest.mock import MagicMock, patch

from searchix import (
    SearchResult, SearchixClient, SearchixError,
    ALL_SOURCES, SOURCE_LABELS, PACKAGE_SOURCES,
)


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_search_result_creation(self):
        """Test creating a SearchResult."""
        result = SearchResult(
            source="nixpkgs",
            name="python",
            attribute="packages/nixpkgs/python310",
            description="A high-level programming language",
        )
        assert result.source == "nixpkgs"
        assert result.name == "python"
        assert result.attribute == "packages/nixpkgs/python310"
        assert result.description == "A high-level programming language"

    def test_search_result_is_package(self):
        """Test is_package() for package sources."""
        package_result = SearchResult(
            source="nixpkgs",
            name="python",
            attribute="packages/nixpkgs/python310",
        )
        assert package_result.is_package() is True

        nur_result = SearchResult(
            source="nur",
            name="mypackage",
            attribute="packages/nur/mypackage",
        )
        assert nur_result.is_package() is True

    def test_search_result_is_option(self):
        """Test is_option() for option sources."""
        nixos_result = SearchResult(
            source="nixos",
            name="enable",
            attribute="options/nixos/networking.enable",
        )
        assert nixos_result.is_option() is True

        hm_result = SearchResult(
            source="home-manager",
            name="enable",
            attribute="options/home-manager/programs.enable",
        )
        assert hm_result.is_option() is True

    def test_search_result_str_with_description(self):
        """Test string representation with description."""
        result = SearchResult(
            source="nixpkgs",
            name="python",
            attribute="packages/nixpkgs/python310",
            description="A high-level programming language",
        )
        str_result = str(result)
        assert "packages/nixpkgs/python310" in str_result
        assert "A high-level programming language" in str_result

    def test_search_result_str_without_description(self):
        """Test string representation without description."""
        result = SearchResult(
            source="nixpkgs",
            name="python",
            attribute="packages/nixpkgs/python310",
        )
        str_result = str(result)
        assert "packages/nixpkgs/python310" in str_result


class TestSearchixClient:
    """Test SearchixClient class."""

    def test_client_initialization(self):
        """Test client initialization with defaults."""
        client = SearchixClient(auto_start=False)
        assert client.base_url == "http://localhost:3000"
        assert client.timeout == 10.0
        assert client.auto_start is False

    def test_client_initialization_custom(self):
        """Test client initialization with custom values."""
        client = SearchixClient(
            base_url="http://example.com:8080",
            timeout=5.0,
            auto_start=True,
        )
        assert client.base_url == "http://example.com:8080"
        assert client.timeout == 5.0
        assert client.auto_start is True

    def test_client_strips_trailing_slash(self):
        """Test that base_url strips trailing slashes."""
        client = SearchixClient(base_url="http://localhost:3000/", auto_start=False)
        assert client.base_url == "http://localhost:3000"

    def test_fetch_success(self, monkeypatch):
        """Test successful fetch."""
        mock_response = """
        <table><tbody>
            <tr>
                <td><a href="python">python</a></td>
                <td>A language</td>
            </tr>
        </tbody></table>
        """

        mock_conn = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = mock_response.encode("utf-8")
        mock_conn.getresponse.return_value = mock_resp

        def mock_http_conn(host, port=None, timeout=None):
            return mock_conn

        monkeypatch.setattr("http.client.HTTPConnection", mock_http_conn)

        client = SearchixClient(auto_start=False)
        result = client._fetch("/search", {"query": "python"})
        assert "python" in result

    def test_fetch_404_error(self, monkeypatch):
        """Test fetch with 404 error."""
        mock_conn = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.read.return_value = b"Not found"
        mock_conn.getresponse.return_value = mock_resp

        def mock_http_conn(host, port=None, timeout=None):
            return mock_conn

        monkeypatch.setattr("http.client.HTTPConnection", mock_http_conn)

        client = SearchixClient(auto_start=False)
        result = client._fetch("/search", {"query": "nonexistent"})
        # 404 is allowed (empty results)
        assert result == "Not found"

    def test_fetch_server_error(self, monkeypatch):
        """Test fetch with 5xx error."""
        mock_conn = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_conn.getresponse.return_value = mock_resp

        def mock_http_conn(host, port=None, timeout=None):
            return mock_conn

        monkeypatch.setattr("http.client.HTTPConnection", mock_http_conn)

        client = SearchixClient(auto_start=False)
        with pytest.raises(SearchixError):
            client._fetch("/search", {"query": "test"})

    def test_fetch_timeout(self, monkeypatch):
        """Test fetch with timeout."""
        import socket as socket_module

        def mock_http_conn(host, port=None, timeout=None):
            raise socket_module.timeout()

        monkeypatch.setattr("http.client.HTTPConnection", mock_http_conn)

        client = SearchixClient(auto_start=False)
        with pytest.raises(SearchixError, match="Timed out"):
            client._fetch("/search", {"query": "test"})

    def test_fetch_connection_error(self, monkeypatch):
        """Test fetch with connection error."""
        def mock_http_conn(host, port=None, timeout=None):
            raise OSError("Connection refused")

        monkeypatch.setattr("http.client.HTTPConnection", mock_http_conn)

        client = SearchixClient(auto_start=False)
        with pytest.raises(SearchixError, match="Connection error"):
            client._fetch("/search", {"query": "test"})

    def test_search_with_invalid_source(self):
        """Test search with invalid source."""
        client = SearchixClient(auto_start=False)
        with pytest.raises(ValueError, match="Unknown source"):
            client.search("python", sources=["invalid_source"])

    def test_search_single_source(self, monkeypatch):
        """Test search with single source."""
        mock_conn = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"""
        <table><tbody>
            <tr>
                <td><a href="python">python</a></td>
                <td class="description">A language</td>
            </tr>
        </tbody></table>
        """
        mock_conn.getresponse.return_value = mock_resp

        def mock_http_conn(host, port=None, timeout=None):
            return mock_conn

        monkeypatch.setattr("http.client.HTTPConnection", mock_http_conn)
        monkeypatch.setattr("searchix.SearchixClient._ensure_server", MagicMock())

        client = SearchixClient(auto_start=False)
        results = client.search("python", sources=["nixpkgs"])
        assert len(results) > 0
        assert results[0].source == "nixpkgs"

    @patch("searchix.SearchixClient._ensure_server")
    @patch("searchix.SearchixClient._fetch_source")
    def test_search_by_source(self, mock_fetch_source, mock_ensure):
        """Test search_by_source groups results."""
        nixpkgs_results = [
            SearchResult("nixpkgs", "python", "packages/nixpkgs/python310", "A language"),
        ]
        nixos_results = []

        def fetch_side_effect(source, query, limit):
            if source == "nixpkgs":
                return nixpkgs_results
            return nixos_results

        mock_fetch_source.side_effect = fetch_side_effect

        client = SearchixClient(auto_start=False)
        grouped = client.search_by_source("python")

        assert "nixpkgs" in grouped
        assert "nixos" in grouped
        assert len(grouped["nixpkgs"]) == 1
        assert len(grouped["nixos"]) == 0

    @patch("searchix.SearchixClient._ensure_server")
    def test_iter_all(self, mock_ensure):
        """Test iter_all iterator."""
        results = [
            SearchResult("nixpkgs", "python", "packages/nixpkgs/python310", "A language"),
            SearchResult("nixos", "enable", "options/nixos/boot.enable", "Enable boot"),
        ]

        with patch.object(SearchixClient, "search", return_value=results):
            client = SearchixClient(auto_start=False)
            iter_results = list(client.iter_all("python"))
            assert len(iter_results) == 2
            assert iter_results[0].name == "python"
            assert iter_results[1].name == "enable"


class TestSearchResultParsing:
    """Test HTML parsing for SearchResult."""

    def test_parse_empty_html(self):
        """Test parsing empty HTML."""
        from searchix import _parse_source_fragment
        results = _parse_source_fragment("<table><tbody></tbody></table>", "nixpkgs")
        assert len(results) == 0

    def test_parse_single_result(self):
        """Test parsing single result."""
        from searchix import _parse_source_fragment
        html = """
        <table><tbody>
            <tr>
                <td><a href="python">python</a></td>
                <td class="description">A language</td>
            </tr>
        </tbody></table>
        """
        results = _parse_source_fragment(html, "nixpkgs")
        assert len(results) == 1
        assert results[0].name == "python"
        assert results[0].source == "nixpkgs"
        assert results[0].attribute == "packages/nixpkgs/python"

    def test_parse_multiple_results(self):
        """Test parsing multiple results."""
        from searchix import _parse_source_fragment
        html = """
        <table><tbody>
            <tr>
                <td><a href="python">python</a></td>
                <td class="description">A language</td>
            </tr>
            <tr>
                <td><a href="ruby">ruby</a></td>
                <td class="description">Another language</td>
            </tr>
        </tbody></table>
        """
        results = _parse_source_fragment(html, "nixpkgs")
        assert len(results) == 2
        assert results[0].name == "python"
        assert results[1].name == "ruby"

    def test_parse_dotted_path(self):
        """Test parsing dotted attribute path."""
        from searchix import _parse_source_fragment
        html = """
        <table><tbody>
            <tr>
                <td><a href="programs.ghostty.enable">programs.ghostty.enable</a></td>
                <td class="description">Enable ghostty</td>
            </tr>
        </tbody></table>
        """
        results = _parse_source_fragment(html, "nixos")
        assert len(results) == 1
        assert results[0].attribute == "options/nixos/programs.ghostty.enable"
        assert results[0].name == "enable"

    def test_parse_option_source(self):
        """Test parsing option source formats full path correctly."""
        from searchix import _parse_source_fragment
        html = """
        <table><tbody>
            <tr>
                <td><a href="boot.enable">boot.enable</a></td>
                <td class="description">Enable boot</td>
            </tr>
        </tbody></table>
        """
        results = _parse_source_fragment(html, "nixos")
        assert results[0].attribute == "options/nixos/boot.enable"
        assert results[0].is_option() is True

    def test_parse_html_entities(self):
        """Test parsing HTML entities in descriptions."""
        from searchix import _parse_source_fragment
        html = """
        <table><tbody>
            <tr>
                <td><a href="test">test</a></td>
                <td class="description">Description with &lt;brackets&gt; &amp; symbols</td>
            </tr>
        </tbody></table>
        """
        results = _parse_source_fragment(html, "nixpkgs")
        assert "&lt;" not in results[0].description
        assert "<brackets>" in results[0].description

    def test_strip_tags(self):
        """Test HTML tag stripping."""
        from searchix import _strip_tags
        text = "<p>Test <b>bold</b> <dialog>{json}</dialog> text</p>"
        result = _strip_tags(text)
        assert "<" not in result
        assert "Test" in result
        assert "bold" in result
        # dialog content should be stripped
        assert "{json}" not in result

    def test_constants(self):
        """Test module constants."""
        assert "nixpkgs" in ALL_SOURCES
        assert "nixos" in ALL_SOURCES
        assert "home-manager" in ALL_SOURCES
        assert "darwin" in ALL_SOURCES
        assert "nur" in ALL_SOURCES

        assert "nixpkgs" in PACKAGE_SOURCES
        assert "nur" in PACKAGE_SOURCES
        assert "nixos" not in PACKAGE_SOURCES

        assert "NixOS Options" in SOURCE_LABELS.values()
        assert "Nix Packages" in SOURCE_LABELS.values()
