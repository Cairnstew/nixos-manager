# NixMgr — Agent Operating Guide

## 0. Repository Layout

This is a NixOS flake repository at the path provided in your system prompt.
The key directories are:

- `modules/home/`   — home-manager modules (per-user programs, dotfiles)
- `modules/nixos/`  — NixOS system modules (services, hardware, system config)
- `modules/flake-parts/` — flake-parts wiring modules
- `configurations/` — per-machine configuration entrypoints
- `packages/`       — custom package derivations
- `overlays/`       — nixpkgs overlays

## 1. Before Creating or Editing Any Module

**Always do these steps first — do not skip them under any circumstance:**

1. Call `list_nix_files` to understand the current repo structure.
2. Find 2-3 existing modules in the **same category** as what you are building or working on.
   - Adding a home-manager browser module? Read `modules/home/firefox.nix` and `modules/home/discord.nix`.
   - Adding a NixOS service? Read a similar service module under `modules/nixos/`.
3. Call `read_nix_file` on those reference modules before writing a single line.
4. Match the structure, option naming style, and import patterns of the existing modules.

**The existing modules are the specification. Do not invent structure.**

## 2. Module Patterns

### Home-manager modules (`modules/home/`)
- Single file is the norm for simple program configs
- Use `programs.<name>`, `services.<name>`, or `home.packages` as appropriate
- Follow the exact option style used in adjacent modules

### NixOS modules (`modules/nixos/`)
- Multi-file modules live in their own subdirectory with a `default.nix` entrypoint
- Sidecars (e.g. `home.nix`, `service.nix`) must be explicitly imported in `default.nix`
- No directory scanning — all imports must be explicit

### Packages (`packages/`)
- Each package is a `pkgs.callPackage`-compatible function
- Single file or directory with `default.nix`

## 3. Namespace Rules

- All custom NixOS options must be defined under `my.*`
  (e.g. `my.services.foo.enable`, `my.programs.bar.settings`)
- Never define options in the global NixOS namespace (e.g. `services.*`)
  unless you are extending an existing upstream module

## 4. Nix Package Lookups

- `nix search` is **slow on first run** (30-120 seconds) — be patient, do not retry immediately
- Most common programs (browsers, editors, media players) already exist in nixpkgs
- When in doubt, check nixpkgs by name: `google-chrome`, `chromium`, `firefox`, etc.
- Prefer `pkgs.<name>` over defining a new derivation if the package exists upstream

## 5. Making Changes

1. Read reference modules first (§1 above)
2. Use `dry_run=true` to preview any write before committing it
3. Use `patch_nix_file` for small targeted edits; `write_nix_file` for new files or full rewrites
4. Run `nix_check` after every write to catch evaluation errors
5. Explain every change in plain language before and after making it

## 6. Hard Rules (never violate these)

- Never write a file without reading at least one structurally similar existing module first
- Never invent a package derivation from scratch if the package exists in nixpkgs
- Never define options outside `my.*` for new custom modules
- Never add a sidecar `.nix` file without importing it explicitly in `default.nix`
- Never commit without running `nix_check` first