"""
searchix — Python client for a local searchix-web instance.
"""

from __future__ import annotations

import html as html_module
import http.client
import re
import socket
import urllib.parse
from dataclasses import dataclass
from typing import Iterator

__version__ = "0.1.0"
__all__ = [
    "SearchixClient",
    "SearchResult",
    "ALL_SOURCES",
    "SOURCE_LABELS",
    "SearchixError",
]

ALL_SOURCES: list[str] = ["nixos", "nixpkgs", "home-manager", "darwin", "nur"]

SOURCE_LABELS: dict[str, str] = {
    "nixos":        "NixOS Options",
    "nixpkgs":      "Nix Packages",
    "darwin":       "Darwin Options",
    "home-manager": "Home Manager Options",
    "nur":          "NUR Packages",
}

# Per-source search endpoints (the combined / endpoint has a server-side bug)
SOURCE_PATHS: dict[str, str] = {
    "nixos":        "/options/nixos/search",
    "nixpkgs":      "/packages/nixpkgs/search",
    "darwin":       "/options/darwin/search",
    "home-manager": "/options/home-manager/search",
    "nur":          "/packages/nur/search",
}

PACKAGE_SOURCES = {"nixpkgs", "nur"}


@dataclass
class SearchResult:
    source: str
    name: str
    attribute: str
    description: str = ""

    def is_package(self) -> bool:
        return self.source in PACKAGE_SOURCES

    def is_option(self) -> bool:
        return not self.is_package()

    def __str__(self) -> str:
        parts = [self.attribute]
        if self.description:
            short = self.description[:100]
            parts.append(f"— {short}{'…' if len(self.description) > 100 else ''}")
        return "  ".join(parts)


# ---------------------------------------------------------------------------
# HTML parsing
#
# The fetch:true response from a per-source endpoint looks like:
#
#   <table><thead>...</thead><tbody>
#     <tr>
#       <td><a class="open-dialog" href="ghostty?query=ghostty&scoped">ghostty</a></td>
#       <td class="description"><p>Fast terminal emulator</p><dialog>...</dialog></td>
#       <td class="score">...</td>
#     </tr>
#   </tbody></table>
#
# The href is a bare attribute name or dotted option path — no source prefix.
# We reconstruct the full canonical path from the source we queried.
# ---------------------------------------------------------------------------


def _strip_tags(text: str) -> str:
    # Remove <dialog>…</dialog> blocks (contain score JSON noise)
    text = re.sub(r"<dialog[^>]*>.*?</dialog>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_source_fragment(html: str, source: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    rows = re.findall(r"<tr>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        if "<th" in row:
            continue
        link_m = re.search(r'<a[^>]+href="([^"]+)"[^>]*>', row, re.DOTALL | re.IGNORECASE)
        if not link_m:
            continue

        raw_href = html_module.unescape(link_m.group(1))
        attribute = raw_href.split("?")[0]   # e.g. "ghostty" or "programs.ghostty.enable"
        name = attribute.split(".")[-1]

        if source in PACKAGE_SOURCES:
            full_attribute = f"packages/{source}/{attribute}"
        else:
            full_attribute = f"options/{source}/{attribute}"

        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        description = _strip_tags(tds[1]) if len(tds) >= 2 else ""

        results.append(SearchResult(
            source=source,
            name=name,
            attribute=full_attribute,
            description=description,
        ))
    return results


class SearchixError(Exception):
    pass


class SearchixClient:
    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        timeout: float = 10.0,
        auto_start: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.auto_start = auto_start

    def _ensure_server(self) -> None:
        if self.auto_start:
            from .server import ensure_ready
            try:
                ensure_ready()
            except RuntimeError as exc:
                raise SearchixError(str(exc)) from exc

    def _fetch(self, path: str, params: dict) -> str:
        qs = urllib.parse.urlencode(params)
        full_path = f"{path}?{qs}"
        parsed = urllib.parse.urlparse(self.base_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 3000
        use_tls = parsed.scheme == "https"

        headers = {
            "Host": host,
            "Accept": "*/*",
            "fetch": "true",
            "Connection": "close",
            "User-Agent": "searchix-cli/" + __version__,
        }

        try:
            if use_tls:
                import ssl
                conn = http.client.HTTPSConnection(host, port=port, timeout=self.timeout)
            else:
                conn = http.client.HTTPConnection(host, port=port, timeout=self.timeout)
            conn.request("GET", full_path, headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", errors="replace")
            conn.close()
            if resp.status not in (200, 404):
                raise SearchixError(f"HTTP {resp.status} from {self.base_url}{full_path}")
            return body
        except SearchixError:
            raise
        except (socket.timeout, TimeoutError) as exc:
            raise SearchixError(f"Timed out connecting to {host}:{port}") from exc
        except OSError as exc:
            raise SearchixError(f"Connection error: {exc}") from exc

    def _fetch_source(self, source: str, query: str, limit: int) -> list[SearchResult]:
        path = SOURCE_PATHS.get(source)
        if path is None:
            return []
        html = self._fetch(path, {"query": query})
        return _parse_source_fragment(html, source)

    def search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int = 25,
    ) -> list[SearchResult]:
        if sources is not None:
            bad = [s for s in sources if s not in ALL_SOURCES]
            if bad:
                raise ValueError(
                    f"Unknown source(s): {', '.join(bad)}. "
                    f"Valid: {', '.join(ALL_SOURCES)}"
                )
            active_sources = sources
        else:
            active_sources = ALL_SOURCES

        self._ensure_server()
        results: list[SearchResult] = []
        for source in active_sources:
            results.extend(self._fetch_source(source, query, limit))
        return results

    def search_by_source(
        self,
        query: str,
        limit: int = 25,
    ) -> dict[str, list[SearchResult]]:
        self._ensure_server()
        grouped: dict[str, list[SearchResult]] = {}
        for source in ALL_SOURCES:
            grouped[source] = self._fetch_source(source, query, limit)
        return grouped

    def search_raw(self, source: str, query: str, limit: int = 25) -> str:
        """Return raw HTML fragment for one source (for debugging)."""
        path = SOURCE_PATHS.get(source, "/")
        return self._fetch(path, {"query": query, "limit": limit})

    def iter_all(self, query: str, limit: int = 25) -> Iterator[SearchResult]:
        yield from self.search(query, limit=limit)