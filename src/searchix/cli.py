"""
searchix.cli — command-line interface
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import ALL_SOURCES, SOURCE_LABELS, SearchixClient, SearchixError, SearchResult, __version__
from .server import (
    CONFIG_FILE, DATA_DIR, LOG_FILE, SERVER_URL,
    ENABLED_SOURCES,
    find_binary, ingest, is_server_ready, start, stop, status, write_config,
)

_USE_COLOUR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
def _c(code): return code if _USE_COLOUR else ""

BOLD   = _c("\033[1m")
DIM    = _c("\033[2m")
CYAN   = _c("\033[36m")
GREEN  = _c("\033[32m")
YELLOW = _c("\033[33m")
RED    = _c("\033[31m")
RESET  = _c("\033[0m")


def _truncate(text, n=100):
    return text[:n] + "…" if len(text) > n else text


def _fmt(r: SearchResult) -> str:
    lines = [f"  {BOLD}{GREEN}{r.attribute}{RESET}"]
    if r.description:
        lines.append(f"    {DIM}{_truncate(r.description)}{RESET}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_setup(args) -> int:
    """Write config + run ingest."""
    try:
        find_binary()
    except FileNotFoundError as e:
        print(f"{RED}Error:{RESET} {e}", file=sys.stderr)
        return 1

    sources = set(args.sources.split(",")) if args.sources else ENABLED_SOURCES

    print(f"{BOLD}Writing config{RESET} → {CONFIG_FILE}")
    write_config(sources=sources)

    print(f"{BOLD}Starting ingest{RESET} (this takes 10–30 min on first run)\n")
    try:
        ingest(sources=sources)
    except RuntimeError as e:
        print(f"\n{RED}Error:{RESET} {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted.{RESET} Re-run `searchix setup` to resume.")
        return 1

    print(f"\n{BOLD}{GREEN}Setup complete!{RESET}")
    print(f"Run a search: searchix ghostty")
    return 0


def cmd_serve(args) -> int:
    """Start the server in the background."""
    try:
        find_binary()
    except FileNotFoundError as e:
        print(f"{RED}Error:{RESET} {e}", file=sys.stderr)
        return 1

    if is_server_ready():
        print(f"Server already running at {SERVER_URL}")
        return 0

    print(f"Starting searchix-web... ", end="", flush=True)
    try:
        pid = start(wait=True)
        print(f"{GREEN}ready{RESET} (pid {pid})")
        print(f"Listening at {SERVER_URL}")
        print(f"Logs: {LOG_FILE}")
    except RuntimeError as e:
        print(f"{RED}failed{RESET}")
        print(f"{RED}Error:{RESET} {e}", file=sys.stderr)
        return 1
    return 0


def cmd_stop(args) -> int:
    """Stop the background server."""
    if stop():
        print("Server stopped.")
    else:
        print("Server was not running.")
    return 0


def cmd_status(args) -> int:
    """Show server status."""
    st = status()
    ready_str = f"{GREEN}ready{RESET}" if st["ready"] else (
        f"{YELLOW}starting{RESET}" if st["running"] else f"{RED}stopped{RESET}"
    )
    index_str = f"{GREEN}yes{RESET}" if st["index_exists"] else f"{RED}no — run: searchix setup{RESET}"

    print(f"  status:      {ready_str}")
    print(f"  url:         {st['url']}")
    print(f"  pid:         {st['pid'] or '—'}")
    print(f"  index built: {index_str}")
    print(f"  config:      {st['config']}")
    print(f"  data dir:    {st['data_dir']}")
    print(f"  log:         {st['log']}")
    return 0


def cmd_search(args) -> int:
    """Search for a query."""
    sources = None
    if args.sources:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        bad = [s for s in sources if s not in ALL_SOURCES]
        if bad:
            print(f"{RED}Unknown source(s): {', '.join(bad)}{RESET}", file=sys.stderr)
            print(f"Valid: {', '.join(ALL_SOURCES)}", file=sys.stderr)
            return 1

    client = SearchixClient(timeout=args.timeout, auto_start=True)

    try:
        grouped = client.search_by_source(args.query, limit=args.limit)
    except SearchixError as e:
        print(f"{RED}Error:{RESET} {e}", file=sys.stderr)
        return 1

    display_sources = sources if sources else list(ALL_SOURCES)
    grouped = {s: grouped.get(s, []) for s in display_sources}

    if args.json:
        payload = {
            s: [{"attribute": r.attribute, "name": r.name, "description": r.description}
                for r in items]
            for s, items in grouped.items()
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.names:
        for items in grouped.values():
            for r in items:
                print(r.attribute)
        return 0

    total = 0
    for source, items in grouped.items():
        label = SOURCE_LABELS.get(source, source)
        noun = "result" if len(items) == 1 else "results"
        print(f"\n{BOLD}{CYAN}── {label}{RESET}  {DIM}({len(items)} {noun}){RESET}")
        if not items:
            print(f"  {DIM}no results{RESET}")
        else:
            for r in items:
                print(_fmt(r))
            total += len(items)

    print(f"\n{DIM}{'─' * 44}{RESET}")
    print(f"{BOLD}Total:{RESET} {total} result(s)\n")
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="searchix",
        description="Search NixOS, nixpkgs, and home-manager options/packages locally.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
sources:  {', '.join(ALL_SOURCES)}

examples:
  searchix setup                  # first-time setup (download + index)
  searchix ghostty                # search all sources
  searchix ghostty -s nixpkgs     # packages only
  searchix git -s nixos,home-manager --limit 30
  searchix status                 # show server status
  searchix serve                  # start server manually
  searchix stop                   # stop server
""",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", required=False)

    # setup
    p_setup = sub.add_parser("setup", help="Download and index all sources (first-time setup)")
    p_setup.add_argument(
        "--sources", metavar="SOURCES",
        help=f"Comma-separated sources to enable (default: nixos,nixpkgs,home-manager)",
    )

    # serve / stop / status
    sub.add_parser("serve",  help="Start the server in the background")
    sub.add_parser("stop",   help="Stop the background server")
    sub.add_parser("status", help="Show server status")

    # search (default command)
    p_search = sub.add_parser("search", help="Search (explicit subcommand)")
    _add_search_args(p_search)

    # also support: searchix ghostty (no subcommand)
    parser.add_argument("query",   nargs="?", help="Search term, e.g. ghostty")
    parser.add_argument("-s", "--sources", metavar="SOURCES",
                        help="Comma-separated source filter")
    parser.add_argument("-l", "--limit", type=int, default=25, metavar="N",
                        help="Max results (default: 25)")
    parser.add_argument("--timeout", type=float, default=10.0, metavar="SECS")
    parser.add_argument("--json",  action="store_true", help="JSON output")
    parser.add_argument("--names", action="store_true", help="Attribute names only")

    return parser


def _add_search_args(p):
    p.add_argument("search_query", help="Search term")
    p.add_argument("-s", "--sources", metavar="SOURCES")
    p.add_argument("-l", "--limit", type=int, default=25, metavar="N")
    p.add_argument("--timeout", type=float, default=10.0, metavar="SECS")
    p.add_argument("--json",  action="store_true")
    p.add_argument("--names", action="store_true")


def _is_explicit_command(argv: list[str]) -> bool:
    for arg in argv:
        if arg in ("-h", "--help", "--version"):
            return True
        if arg.startswith("-"):
            continue
        return arg in ("setup", "serve", "stop", "status", "search")
    return False


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if argv and not _is_explicit_command(argv):
        argv = ["search"] + argv

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "serve":
        return cmd_serve(args)
    if args.command == "stop":
        return cmd_stop(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "search":
        args.query = args.search_query
        return cmd_search(args)

    # default: treat positional as a search query
    if args.query:
        return cmd_search(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())