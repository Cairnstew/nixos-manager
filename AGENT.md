# NixMgr — Agent Operating Guide

## 0. Repository Layout

This is a NixOS flake repository at the path provided in your system prompt.
The key directories are:

- `modules/home/`        — home-manager modules (per-user programs, dotfiles)
- `modules/nixos/`       — NixOS system modules (services, hardware, system config)
- `modules/flake-parts/` — flake-parts wiring modules
- `configurations/`      — per-machine configuration entrypoints
- `packages/`            — custom package derivations
- `overlays/`            — nixpkgs overlays

---

## 1. Execution Style — Read This First

**Execute tasks immediately and completely. Do not stop to ask permission between steps.**

- Call tools in sequence without pausing for confirmation.
- Only stop if a tool returns an error you cannot resolve, or if a destructive
  action (e.g. deleting files) requires explicit user approval.
- Never present a plan as code blocks and ask "would you like to proceed?" — just proceed.
- After the final step, give a short summary of what was done.

**Tool invocation format:**
```
When calling a tool, always use named parameters with proper syntax:
  toolname(param1="value", param2=123, param3=[item1, item2])

Example — NOT as plain object, but as an actual function call:
  module_builder(action="build", module_name="chromium", hint="home-manager", requests=["openFirewall"], dry_run=true)
```

---

## 2. Standard Task Sequences

When given a task, follow the matching sequence below **in full, without stopping**.

### Creating a new module (home-manager or NixOS)

Use `module_builder` for automatic discovery, option inference, and repl verification.

**Step 1: Preview**
```
module_builder(
  action="build",
  module_name="chromium",
  hint="home-manager",
  requests=["commandLineArgs", "extensions", "homePage"],
  dry_run=true
)
```

**Step 2: Create (if preview looks good)**
```
module_builder(
  action="build",
  module_name="chromium",
  hint="home-manager",
  requests=["commandLineArgs", "extensions", "homePage"],
  dry_run=false
)
```

**Step 3: Validate**
```
nix_check(command="flake check")
```

Then report the module path, namespace, and test file location.

**Parameters:**
- `action`: Always `"build"` for new modules
- `module_name`: Name of the program/service (e.g. `"chromium"`, `"syncthing"`, `"nginx"`)
- `hint`: Steers discovery — use `"home-manager"`, `"home"`, `"user"` for home-manager; `"nixos"`, `"system"`, `"service"` for NixOS. Omit to auto-detect
- `requests`: List of additional option names to include (e.g. `["openFirewall", "dataDir", "logLevel"]`)
- `dry_run`: Set to `true` first to preview, then `false` to write files

### Editing an existing module

Use `module_builder` to load, modify, and re-verify the spec.

**Step 1: Check current state**
```
module_builder(
  action="status",
  module_name="chromium"
)
```

**Step 2: Preview edits**
```
module_builder(
  action="edit",
  module_name="chromium",
  edits=[
    {op: "set_default", path: "port", value: "8384"},
    {op: "add_option", path: "timeout", type: "int", default: "30"}
  ],
  dry_run=true
)
```

**Step 3: Apply edits (if preview looks good)**
```
module_builder(
  action="edit",
  module_name="chromium",
  edits=[
    {op: "set_default", path: "port", value: "8384"},
    {op: "add_option", path: "timeout", type: "int", default: "30"}
  ],
  dry_run=false
)
```

**Step 4: Validate**
```
nix_check(command="flake check")
```

Then report what changed.

**Edit operations supported:**
- `{op: "set_default", path: "optionName", value: "newValue"}`
- `{op: "set_description", path: "optionName", value: "new description"}`
- `{op: "set_type", path: "optionName", value: "typeString"}`
- `{op: "add_option", path: "optionName", type: "typeString", default: "defaultValue"}`
- `{op: "remove_option", path: "optionName"}`
- `{op: "add_test_check", kind: "port_open", port: 8384}`

### Validating an existing module

**Check module files**
```
module_builder(
  action="check",
  module_name="chromium"
)
```

Then report any parse/eval issues found.

### Searching for a package name

```
1. nix_search(query=<name>)  — first run is slow (30-120s), do NOT retry on timeout
2. Use the result to fill in pkgs.<attrName> in the module.
```

---

## 3. Module Patterns

**`module_builder` generates these patterns automatically.**

All modules now use a unified folder structure for organization:

### Module folder structure
- Each module gets its own folder: `modules/nixos/<name>/`, `modules/home/<name>/`, or `modules/flake-parts/<name>/`
- `default.nix` is the main entry point — defines options and config
- Separate `.nix` files can be organized within the folder for complex modules (imported explicitly in `default.nix`)
- `.module-spec.json` is stored in the folder — drives the module_builder pipeline
- `tests.nix` contains validation assertions and tests

### Home-manager modules (`modules/home/<name>/`)
- `default.nix` implements the module logic
- Options live under `my.programs.<name>` or `my.services.<name>`
- Use `programs.<name>.enable = true` if home-manager has a built-in module
- Use `home.packages = [ pkgs.<name> ]` if no built-in module exists

### NixOS modules (`modules/nixos/<name>/`)
- `default.nix` implements the module logic
- Submodule files (e.g., `services.nix`, `config.nix`) can be created and imported as needed
- `tests.nix` provides VM tests for the module

### Flake-parts modules (`modules/flake-parts/<name>/`)
- `default.nix` implements the module
- Used for flake-parts system extensions

---

## 4. Namespace Rules

- All custom options → `my.*` (e.g. `my.programs.chromium.enable`)
- Never define options in the global NixOS namespace (`services.*`, `programs.*`)
  unless extending an upstream module inside a `config` block

---

## 5. Package Lookups

- `nix search` is slow on first run (30-120s) — do not retry on timeout
- Common packages exist in nixpkgs: `google-chrome`, `chromium`, `firefox`, etc.
- Always prefer `pkgs.<name>` over writing a custom derivation

---

## 6. Hard Rules

- **Always use `module_builder` to create or edit modules** — it handles discovery, type verification, and folder organization automatically
- Never define options outside `my.*` namespace
- Never add a sidecar `.nix` file without an explicit import in `default.nix`
- Never commit without a passing `nix_check`
- Never invent a derivation if the package exists in nixpkgs
- All modules must use folder structure: `modules/{nixos,home,flake-parts}/<name>/default.nix`
- Respect `.module-spec.json` files — they drive module_builder edits and phase re-runs