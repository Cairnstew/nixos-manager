"""
agent.py  –  NixOS Config Manager
Entry point. Run with:  python agent.py
"""

import sys

# Import tools so their @register_tool decorators fire
import tools.repo_reader   # noqa: F401
import tools.repo_writer   # noqa: F401
import tools.nix_ops       # noqa: F401

from qwen_agent.agents import Assistant
from qwen_agent.gui import WebUI

from config.settings import LLM_CONFIG, NIXOS_REPO_PATH

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

Guidelines:
1. Always read relevant files before suggesting or making changes.
2. Prefer patch_nix_file for small changes; write_nix_file for full rewrites.
3. Run nix_check after edits to catch errors before committing.
4. Explain every change you make in plain language.
5. Never run destructive git ops (push, force-reset, etc.) — they are blocked anyway.
6. When unsure, use dry_run=true to preview writes first.
"""

# ---------------------------------------------------------------------------
# Tool list passed to the agent
# ---------------------------------------------------------------------------
TOOLS = [
    "list_nix_files",
    "read_nix_file",
    "write_nix_file",
    "patch_nix_file",
    "git_op",
    "nix_check",
    "search_nix_files",
]


def build_agent() -> Assistant:
    return Assistant(
        llm=LLM_CONFIG,
        name="NixMgr",
        description="NixOS configuration manager",
        system_message=SYSTEM_PROMPT,
        function_list=TOOLS,
    )


def run_cli(agent: Assistant) -> None:
    """Simple REPL loop for terminal use."""
    print(f"NixMgr — repo: {NIXOS_REPO_PATH}")
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

        response_msgs = []
        for chunk in agent.run(messages=messages):
            response_msgs = chunk  # agent.run yields incremental message lists

        # Print the last assistant message
        for msg in reversed(response_msgs):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            print(f"\nNixMgr> {block['text']}\n")
                else:
                    print(f"\nNixMgr> {content}\n")
                break

        messages = response_msgs  # keep full history for next turn


def run_gui(agent: Assistant) -> None:
    """Launch the qwen-agent built-in Gradio web UI."""
    WebUI(agent).run()


if __name__ == "__main__":
    agent = build_agent()

    if "--gui" in sys.argv:
        run_gui(agent)
    else:
        run_cli(agent)
