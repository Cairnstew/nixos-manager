# nixos-manager

A local AI agent for managing your NixOS flake configuration,
powered by [qwen-agent](https://github.com/QwenLM/Qwen-Agent) and a locally-running
Qwen3 or Qwen2.5-Coder 8B model.

---

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) (or any OpenAI-compatible local server)
- A NixOS flake repo somewhere on disk

---

## Setup

```bash
# 1. Pull a model (pick one)
ollama pull qwen2.5-coder:8b
ollama pull qwen3:8b

# 2. Install Python deps
pip install -r requirements.txt

# 3. Point the agent at your config repo
export NIXOS_REPO_PATH="$HOME/nixos-config"   # default shown

# Optional overrides
export NIXMGR_MODEL="qwen3:8b"                # which model to use
export NIXMGR_SERVER="http://localhost:11434/v1"  # Ollama default
```

---

## Running

```bash
# Terminal REPL (default)
python agent.py

# Built-in Gradio web UI
python agent.py --gui
```

---

## Project layout

```
nixos-manager/
├── agent.py                  ← entry point; wires everything together
├── requirements.txt
├── config/
│   └── settings.py           ← LLM endpoint + repo path config
└── tools/
    ├── repo_reader.py         ← list_nix_files, read_nix_file
    ├── repo_writer.py         ← write_nix_file, patch_nix_file (with auto-backup)
    ├── nix_ops.py             ← git_op, nix_check, search_nix_files
    └── example_custom_tool.py ← template for your own tools
```

---

## Built-in tools

| Tool | What it does |
|---|---|
| `list_nix_files` | Tree of all `.nix` files in the repo |
| `read_nix_file` | Read a single file |
| `write_nix_file` | Overwrite / create a file (auto-backup) |
| `patch_nix_file` | Replace an exact substring (safer for small edits) |
| `git_op` | Safe git commands: status, diff, log, add, commit, show, stash |
| `nix_check` | `nix flake check / show / build` to validate before committing |
| `search_nix_files` | grep across the whole repo |

---

## Adding your own tools

1. Copy `tools/example_custom_tool.py` to a new file.
2. Fill in `name`, `description`, `parameters`, and `call()`.
3. Import the module in `agent.py` (top imports section).
4. Add the tool name string to the `TOOLS` list in `agent.py`.

The `@register_tool("your_tool_name")` decorator handles the rest.

---

## Safety notes

- `write_nix_file` and `patch_nix_file` always create a timestamped `.bak` file before modifying anything.
- `git_op` only allows: `status diff log add commit show stash` — push/reset/force are blocked.
- `nix_check` only allows: `flake check`, `flake show`, `build`, `eval`.
- All file writes are rejected if the resolved path escapes the repo root.
