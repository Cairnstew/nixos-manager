"""
_base.py — MCP client with a persistent per-process server connection.

The original code spawned a fresh subprocess for every single tool call,
causing the MCP server splash screen to appear repeatedly and adding
significant latency.  This version keeps one connection alive for the
lifetime of the process and only restarts it if it dies.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Persistent event loop + session — one per process
# ---------------------------------------------------------------------------

class _MCPConnection:
    """
    Holds a single long-lived MCP stdio connection.
    Thread-safe: a dedicated background thread owns the event loop;
    callers on any thread use run_coroutine_threadsafe().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: ClientSession | None = None
        self._cm_stack: list[Any] = []   # context manager exit callbacks
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Internal async helpers (must be called from self._loop)
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_nixos.server"],
        )
        read_cm = stdio_client(server_params)
        read, write = await read_cm.__aenter__()
        session_cm = ClientSession(read, write)
        session = await session_cm.__aenter__()
        await session.initialize()

        self._session = session
        self._cm_stack = [
            (session_cm, session),
            (read_cm, (read, write)),
        ]

    async def _disconnect(self) -> None:
        for cm, val in reversed(self._cm_stack):
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._session = None
        self._cm_stack = []

    async def _call(self, tool_name: str, payload: dict) -> str:
        if self._session is None:
            await self._connect()
        try:
            result = await self._session.call_tool(tool_name, payload)  # type: ignore[union-attr]
            return "\n".join(b.text for b in result.content if hasattr(b, "text"))
        except Exception:
            # Session died — tear down and reconnect once
            await self._disconnect()
            await self._connect()
            result = await self._session.call_tool(tool_name, payload)  # type: ignore[union-attr]
            return "\n".join(b.text for b in result.content if hasattr(b, "text"))

    # ------------------------------------------------------------------
    # Public synchronous API
    # ------------------------------------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                return self._loop

            loop = asyncio.new_event_loop()
            self._loop = loop

            def _run() -> None:
                loop.run_forever()

            self._thread = threading.Thread(target=_run, daemon=True)
            self._thread.start()
            return loop

    def call(self, tool_name: str, payload: dict) -> str:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._call(tool_name, payload), loop
        )
        return future.result(timeout=120)


# Module-level singleton
_connection = _MCPConnection()


def run_mcp(tool_name: str, payload: dict) -> str:
    """Call an MCP tool on the persistent connection. Thread-safe."""
    try:
        return _connection.call(tool_name, payload)
    except Exception as e:
        return f"MCP error: {e}"


# ---------------------------------------------------------------------------
# Helpers used by tool classes
# ---------------------------------------------------------------------------

def parse_params(params: str | dict) -> dict:
    if isinstance(params, str):
        try:
            return json.loads(params)
        except Exception:
            return {}
    return params or {}


def out(data: dict) -> str:
    return json.dumps(data, indent=2)