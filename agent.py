"""
agent.py  –  NixOS Config Manager
Entry point. Run with:  uv run agent.py

Flags:
  --debug   Show live token stream in terminal while generating
  --log     Also print log output to terminal (default: log file only)
  --gui     Launch Gradio web UI instead of CLI
"""

import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup — must happen BEFORE importing qwen_agent so we capture
# its loggers from the start.
# ---------------------------------------------------------------------------
LOG_FILE = Path(__file__).parent / "nixmgr.log"

def setup_logging(verbose_terminal: bool = False) -> None:
    """
    Always write full DEBUG logs to nixmgr.log.
    Only show WARNING+ on the terminal unless --log is passed.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s"
    )

    # File handler — everything goes here
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Terminal handler — quiet by default, verbose with --log
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.DEBUG if verbose_terminal else logging.WARNING)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # Suppress noisy qwen-agent INFO lines on stderr without clearing
    # handlers wholesale (clearing breaks qwen-agent's internal streaming)
    if not verbose_terminal:
        for name in ("qwen_agent", "qwen_agent.llm", "qwen_agent.llm.base"):
            lg = logging.getLogger(name)
            lg.setLevel(logging.WARNING)


verbose_log = "--log" in sys.argv
setup_logging(verbose_terminal=verbose_log)

# ---------------------------------------------------------------------------
# Now safe to import qwen_agent (its loggers inherit root config above)
# ---------------------------------------------------------------------------
import tools.repo_reader   # noqa: F401  — register_tool decorators
import tools.repo_writer   # noqa: F401
import tools.nix_ops       # noqa: F401
import tools.nix_eval      # noqa: F401
import tools.nix_search    # noqa: F401

from qwen_agent.agents import Assistant
from qwen_agent.gui import WebUI

from config.settings import LLM_CONFIG, NIXOS_REPO_PATH

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""\
You are NixMgr, an expert NixOS configuration assistant with direct access \
to the user's NixOS flake repository at {NIXOS_REPO_PATH}.

Your capabilities:
- Read any .nix file in the repo (list_nix_files, read_nix_file)
- Write or patch files safely, always with automatic backups (write_nix_file, patch_nix_file)
- Run safe git operations: status, diff, log, add, commit (git_op)
- Validate the flake with nix flake check / nix build (nix_check)
- Search across all .nix files (search_nix_files)
- Evaluate Nix expressions directly (nix_eval)
- Search the Nix package index and options (nix_search)

Guidelines:
1. Always read relevant files before suggesting or making changes.
2. Prefer patch_nix_file for small changes; write_nix_file for full rewrites.
3. Run nix_check after edits to catch errors before committing.
4. Explain every change you make in plain language.
5. Never run destructive git ops (push, force-reset, etc.) — they are blocked anyway.
6. When unsure, use dry_run=true to preview writes first.
"""

# ---------------------------------------------------------------------------
# Tool list
# ---------------------------------------------------------------------------
TOOLS = [
    "list_nix_files",
    "read_nix_file",
    "write_nix_file",
    "patch_nix_file",
    "git_op",
    "nix_check",
    "search_nix_files",
    "nix_eval",
    "nix_search",
]


def build_agent() -> Assistant:
    return Assistant(
        llm=LLM_CONFIG,
        name="NixMgr",
        description="NixOS configuration manager",
        system_message=SYSTEM_PROMPT,
        function_list=TOOLS,
    )


def _extract_last_text(msgs: list[dict]) -> str | None:
    """Pull the text content out of the last assistant message."""
    for msg in reversed(msgs):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = [
                    b["text"] for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                return "".join(parts) or None
            return content or None
    return None


def run_cli(agent: Assistant, debug: bool = False) -> None:
    """Simple REPL loop for terminal use."""
    print(f"NixMgr — repo: {NIXOS_REPO_PATH}")
    print(f"Logs → {LOG_FILE}")
    print("Type 'exit' or Ctrl-C to quit.\n")

    messages: list[dict] = []

    while True:
        try:
            user_input = input("You> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break

        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        log.info("User: %s", user_input)

        response_msgs: list[dict] = []
        best_text = ""
        chunk_count = 0
        SPINNER = r"⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

        try:
            for chunk in agent.run(messages=messages):
                if not chunk:
                    continue
                response_msgs = chunk
                candidate = _extract_last_text(chunk) or ""
                if len(candidate) > len(best_text):
                    best_text = candidate
                if debug:
                    spin_char = SPINNER[chunk_count % len(SPINNER)]
                    print(f"\r  {spin_char} thinking…", end="", flush=True)
                    chunk_count += 1

        except Exception as exc:
            log.exception("Agent error")
            if debug:
                print()
            print(f"\n[error] {exc} — see {LOG_FILE} for details\n")
            continue

        if debug:
            print("\r" + " " * 20 + "\r", end="")  # clear spinner line

        # Always print the final response once, cleanly
        if best_text:
            print(f"\nNixMgr> {best_text}\n")
        else:
            print("\n[no response]\n")

        log.info("Assistant: %s", best_text)
        messages = response_msgs


def run_gui(agent: Assistant) -> None:
    """Launch the qwen-agent built-in Gradio web UI."""
    WebUI(agent).run()


def main() -> None:
    agent = build_agent()
    if "--gui" in sys.argv:
        run_gui(agent)
    else:
        run_cli(agent, debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()