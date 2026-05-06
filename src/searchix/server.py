"""
searchix.server — lifecycle management for a local searchix-web instance.

Handles config generation, index ingestion, and server start/stop.
The server runs as a background process; state is tracked via a pidfile.
"""

from __future__ import annotations

import http.client
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR  = Path.home() / ".config"  / "searchix"
DATA_DIR    = Path.home() / ".local" / "share" / "searchix"
CONFIG_FILE = CONFIG_DIR / "config.toml"
PID_FILE    = DATA_DIR / "searchix.pid"
LOG_FILE    = DATA_DIR / "searchix.log"

SERVER_HOST = "localhost"
SERVER_PORT = 3000
SERVER_URL  = f"http://{SERVER_HOST}:{SERVER_PORT}"

ENABLED_SOURCES = {"nixos", "nixpkgs", "home-manager"}

# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------

CONFIG_TEMPLATE = """\
DataPath = '{data_path}'

[Web]
GracefulShutdownTimeout = '5s'
ListenAddress = 'localhost'
Port = {port}
BaseURL = 'http://localhost:{port}'
Environment = 'production'
LogRequests = false
SearchTimeout = '5s'

[Importer]
LowMemory = false
BatchSize = 10000
Timeout = '60m0s'
UpdateAt = '03:00:00'

[Importer.Sources]

[Importer.Sources.nixos]
Name = 'NixOS'
Order = 0
Key = 'nixos'
Enable = {nixos}
Fetcher = 'channel'
Importer = 'options'
Channel = 'nixpkgs'
URL = 'https://channels.nixos.org/nixos-unstable/nixexprs.tar.xz'
Attribute = 'options'
ImportPath = 'nixos/release.nix'
Timeout = '30m0s'
OutputPath = 'share/doc/nixos'
JSONDepth = 1
[Importer.Sources.nixos.Repo]
Type = 'github'
Owner = 'NixOS'
Repo = 'nixpkgs'
[Importer.Sources.nixos.Programs]
Enable = false
Attribute = ''
[Importer.Sources.nixos.Manpages]
Enable = false
Path = ''

[Importer.Sources.nixpkgs]
Name = 'Nix Packages'
Order = 3
Key = 'nixpkgs'
Enable = {nixpkgs}
Fetcher = 'channel-nixpkgs'
Importer = 'packages'
Channel = 'nixos-unstable'
URL = ''
Attribute = ''
ImportPath = ''
Timeout = '30m0s'
OutputPath = 'packages.json.br'
JSONDepth = 2
[Importer.Sources.nixpkgs.Repo]
Type = 'github'
Owner = 'NixOS'
Repo = 'nixpkgs'
[Importer.Sources.nixpkgs.Programs]
Enable = true
Attribute = 'programs.sqlite'
[Importer.Sources.nixpkgs.Manpages]
Enable = true
Path = '/doc/manpage-urls.json'

[Importer.Sources.darwin]
Name = 'Darwin'
Order = 1
Key = 'darwin'
Enable = false
Fetcher = 'channel'
Importer = 'options'
Channel = 'darwin'
URL = 'https://github.com/LnL7/nix-darwin/archive/master.tar.gz'
Attribute = 'docs.optionsJSON'
ImportPath = 'release.nix'
Timeout = '5m0s'
OutputPath = 'share/doc/darwin'
JSONDepth = 1
[Importer.Sources.darwin.Repo]
Type = 'github'
Owner = 'LnL7'
Repo = 'nix-darwin'
[Importer.Sources.darwin.Programs]
Enable = false
Attribute = ''
[Importer.Sources.darwin.Manpages]
Enable = false
Path = ''

[Importer.Sources.home-manager]
Name = 'Home Manager'
Order = 2
Key = 'home-manager'
Enable = {home_manager}
Fetcher = 'channel'
Importer = 'options'
Channel = 'home-manager'
URL = 'https://github.com/nix-community/home-manager/archive/master.tar.gz'
Attribute = 'docs.json'
ImportPath = 'default.nix'
Timeout = '10m0s'
OutputPath = 'share/doc/home-manager'
JSONDepth = 1
[Importer.Sources.home-manager.Repo]
Type = 'github'
Owner = 'nix-community'
Repo = 'home-manager'
[Importer.Sources.home-manager.Programs]
Enable = false
Attribute = ''
[Importer.Sources.home-manager.Manpages]
Enable = false
Path = ''

[Importer.Sources.nur]
Name = 'NUR'
Order = 4
Key = 'nur'
Enable = false
Fetcher = 'download'
Importer = 'packages'
Channel = ''
URL = 'https://alinnow.github.io/nix-options/nur'
Attribute = ''
ImportPath = ''
Timeout = '5m0s'
OutputPath = ''
JSONDepth = 1
[Importer.Sources.nur.Repo]
Type = 'github'
Owner = 'nix-community'
Repo = 'nur'
[Importer.Sources.nur.Programs]
Enable = false
Attribute = ''
[Importer.Sources.nur.Manpages]
Enable = false
Path = ''
"""


def _bool(enabled: bool) -> str:
    return "true" if enabled else "false"


def write_config(
    sources: set[str] = ENABLED_SOURCES,
    data_dir: Path = DATA_DIR,
    port: int = SERVER_PORT,
) -> Path:
    """Write a searchix config.toml and return its path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    content = CONFIG_TEMPLATE.format(
        data_path=str(data_dir),
        port=port,
        nixos=_bool("nixos" in sources),
        nixpkgs=_bool("nixpkgs" in sources),
        home_manager=_bool("home-manager" in sources),
    )
    CONFIG_FILE.write_text(content)
    return CONFIG_FILE


# ---------------------------------------------------------------------------
# Binary detection
# ---------------------------------------------------------------------------


def find_binary() -> str:
    """Return the path to searchix-web, or raise if not found."""
    # Check for patched version in ~/.local/bin first
    local_path = Path.home() / ".local" / "bin" / "searchix-web"
    if local_path.exists():
        return str(local_path)
    
    path = shutil.which("searchix-web")
    if path:
        return path
    raise FileNotFoundError(
        "searchix-web not found in PATH.\n"
        "Install it with: nix-env -iA nixpkgs.searchix\n"
        "or add it to your NixOS/home-manager config."
    )


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


def ingest(
    sources: set[str] = ENABLED_SOURCES,
    data_dir: Path = DATA_DIR,
    port: int = SERVER_PORT,
) -> None:
    """
    Write config and run searchix-web ingest (blocking, streams output).
    This is the slow step — expect 10-30 minutes on first run.
    """
    binary = find_binary()

    if not CONFIG_FILE.exists():
        print(f"Writing config to {CONFIG_FILE}")
        write_config(sources, data_dir, port)
    else:
        print(f"Using existing config at {CONFIG_FILE}")
        print("(delete it and re-run setup to regenerate)")

    print(f"\nStarting ingest — this will take a while on first run...")
    print(f"Index will be stored in {data_dir}\n")

    cmd = [binary, "--config", str(CONFIG_FILE), "ingest"]
    try:
        proc = subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"searchix-web ingest failed (exit {e.returncode})") from e
    except KeyboardInterrupt:
        print("\nIngest interrupted.")
        raise


# ---------------------------------------------------------------------------
# Server start / stop / status
# ---------------------------------------------------------------------------


def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def _clear_pid() -> None:
    PID_FILE.unlink(missing_ok=True)


def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def is_server_ready(host: str = SERVER_HOST, port: int = SERVER_PORT, timeout: float = 1.0) -> bool:
    """Return True if the server is accepting TCP connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def start(
    sources: set[str] = ENABLED_SOURCES,
    data_dir: Path = DATA_DIR,
    port: int = SERVER_PORT,
    wait: bool = True,
    wait_timeout: float = 15.0,
) -> int:
    """
    Start searchix-web serve in the background.
    Returns the PID. Raises if it fails to start.
    """
    binary = find_binary()

    # ensure config exists
    if not CONFIG_FILE.exists():
        write_config(sources, data_dir, port)

    # check if already running
    pid = _read_pid()
    if pid and is_process_running(pid):
        if is_server_ready(port=port):
            return pid  # already up

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a")

    # Avoid systemd notify errors when not running under systemd
    env = os.environ.copy()
    if "NOTIFY_SOCKET" not in env:
        env["NOTIFY_SOCKET"] = ""

    proc = subprocess.Popen(
        [binary, "--config", str(CONFIG_FILE), "serve"],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # detach from terminal
        env=env,
    )

    _write_pid(proc.pid)

    if wait:
        deadline = time.monotonic() + wait_timeout
        while time.monotonic() < deadline:
            if is_server_ready(port=port):
                return proc.pid
            if proc.poll() is not None:
                log.close()
                _clear_pid()
                raise RuntimeError(
                    f"searchix-web exited immediately (code {proc.returncode}).\n"
                    f"Check logs: {LOG_FILE}"
                )
            time.sleep(0.25)

        proc.terminate()
        _clear_pid()
        raise RuntimeError(
            f"searchix-web did not become ready within {wait_timeout}s.\n"
            f"Check logs: {LOG_FILE}\n"
            f"You may need to run: searchix setup"
        )

    return proc.pid


def stop() -> bool:
    """Stop the background server. Returns True if a process was stopped."""
    pid = _read_pid()
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        # wait up to 5s for clean exit
        for _ in range(20):
            time.sleep(0.25)
            if not is_process_running(pid):
                break
        else:
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # already gone
    _clear_pid()
    return True


def status() -> dict:
    """Return a dict describing the current server state."""
    pid = _read_pid()
    running = pid is not None and is_process_running(pid)
    ready = is_server_ready() if running else False
    index_exists = (DATA_DIR / "searchix.bleve").exists() or any(DATA_DIR.glob("*.bleve"))
    return {
        "pid": pid if running else None,
        "running": running,
        "ready": ready,
        "url": SERVER_URL,
        "config": str(CONFIG_FILE),
        "data_dir": str(DATA_DIR),
        "log": str(LOG_FILE),
        "index_exists": index_exists,
    }


def ensure_ready(
    sources: set[str] = ENABLED_SOURCES,
    port: int = SERVER_PORT,
    wait_timeout: float = 15.0,
) -> str:
    """
    Ensure the server is running and ready. Start it if not.
    Returns the base URL.
    Raises RuntimeError with a helpful message if the index doesn't exist yet.
    """
    if is_server_ready(port=port):
        return SERVER_URL

    # Check the index exists before trying to start
    st = status()
    if not st["index_exists"]:
        raise RuntimeError(
            "No searchix index found. Run this first:\n\n"
            "  searchix setup\n\n"
            "This will download and index nixpkgs, NixOS options, and\n"
            "home-manager options. It takes 10-30 minutes on first run."
        )

    start(sources=sources, port=port, wait=True, wait_timeout=wait_timeout)
    return SERVER_URL