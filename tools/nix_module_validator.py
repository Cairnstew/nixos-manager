"""
tools/nix_module_validator.py
-----------------------------------------------------------------------
Validates a module directory against the conventions defined in AGENT.md.

Checks performed
────────────────
1.  STRUCTURE    — all 4 required files exist (default.nix, meta.nix,
                   tests.nix, README.md)
2.  IMPORTS      — every sidecar .nix file in the module dir (incl.
                   tests.nix) is explicitly imported in default.nix
3.  NAMESPACE    — all `options.*` definitions in default.nix sit under
                   `my.<category>.<name>` (never bare NixOS namespaces)
4.  META SCHEMA  — meta.nix contains all required fields and the
                   namespace field matches the my.* convention
5.  META DRIFT   — the sidecars list in meta.nix matches actual .nix
                   files on disk

Can also scaffold a new empty module that passes all checks (scaffold mode).

Register in agent.py:
    from tools.nix_module_validator import NixModuleValidator
    TOOLS = [..., "nix_module_validator"]
-----------------------------------------------------------------------
"""

import json
import re
import textwrap
from pathlib import Path
from typing import Union

from qwen_agent.tools.base import BaseTool, register_tool

from config.settings import NIXOS_REPO_PATH


# ---------------------------------------------------------------------------
# Required meta.nix fields (must all be present as top-level keys)
# ---------------------------------------------------------------------------
REQUIRED_META_FIELDS = {
    "name",
    "category",
    "description",
    "version",
    "tags",
    "namespace",
    "sidecars",
    "testDescription",
    "status",
}

# Files every module must contain
REQUIRED_FILES = {"default.nix", "meta.nix", "tests.nix", "README.md"}

# options.* assignments that are allowed outside my.* (upstream module extensions)
UPSTREAM_OPTION_PATTERN = re.compile(
    r"options\s*\.\s*(?!my\b)([\w]+)",
    re.MULTILINE,
)

# Detects   options.my.services.foo   or   options = { my = { ... } }
MY_NAMESPACE_PATTERN = re.compile(
    r"options\s*\.\s*my\b",
    re.MULTILINE,
)

# Picks up all `import ./something.nix` style references in default.nix
IMPORT_PATTERN = re.compile(
    r'import\s+\./([^\s;"\']+\.nix)',
    re.MULTILINE,
)

# Parses a bare  key = value;  line from meta.nix (good enough for our scalar fields)
META_KEY_PATTERN = re.compile(
    r'^\s*([\w]+)\s*=\s*"([^"]*)"',
    re.MULTILINE,
)
META_LIST_PATTERN = re.compile(
    r'^\s*([\w]+)\s*=\s*\[([^\]]*)\]',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_meta(text: str) -> dict:
    """
    Lightweight meta.nix parser — extracts scalar strings and string lists.
    Not a full Nix evaluator; relies on the canonical meta.nix format.
    """
    result: dict = {}

    for m in META_KEY_PATTERN.finditer(text):
        result[m.group(1)] = m.group(2)

    for m in META_LIST_PATTERN.finditer(text):
        key = m.group(1)
        if key in result:          # already captured as scalar, skip
            continue
        items_raw = m.group(2)
        # Extract quoted strings and bare words
        items = re.findall(r'"([^"]+)"', items_raw)
        if not items:
            items = re.findall(r'\b(\w[\w-]*)\b', items_raw)
        result[key] = items

    return result


def _sidecar_files(module_dir: Path) -> list[str]:
    """All .nix files in *module_dir* except default.nix and meta.nix."""
    return sorted(
        p.name for p in module_dir.iterdir()
        if p.suffix == ".nix"
        and p.name not in ("default.nix", "meta.nix")
        and p.is_file()
    )


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

def validate_module(module_dir: Path) -> dict:
    """
    Run all checks against *module_dir*.

    Returns a dict:
        {
            "passed": bool,
            "module": str,          # relative path
            "checks": {
                "<check_name>": {
                    "ok": bool,
                    "detail": str
                }
            }
        }
    """
    rel = module_dir.relative_to(NIXOS_REPO_PATH)
    checks: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # CHECK 1 — Required file structure
    # ------------------------------------------------------------------
    missing_files = []
    for fname in sorted(REQUIRED_FILES):
        if not (module_dir / fname).exists():
            missing_files.append(fname)

    checks["structure"] = {
        "ok": len(missing_files) == 0,
        "detail": (
            f"Missing: {', '.join(missing_files)}"
            if missing_files
            else f"All required files present: {', '.join(sorted(REQUIRED_FILES))}"
        ),
    }

    # ------------------------------------------------------------------
    # CHECK 2 — Explicit imports in default.nix
    # ------------------------------------------------------------------
    default_nix = module_dir / "default.nix"
    if default_nix.exists():
        default_text = default_nix.read_text(encoding="utf-8")
        imported = set(IMPORT_PATTERN.findall(default_text))
        sidecars_on_disk = set(_sidecar_files(module_dir))

        not_imported = sidecars_on_disk - imported
        phantom_imports = imported - sidecars_on_disk   # imported but not on disk

        import_ok = (len(not_imported) == 0) and (len(phantom_imports) == 0)
        detail_parts = []
        if not_imported:
            detail_parts.append(f"Sidecar files NOT imported: {', '.join(sorted(not_imported))}")
        if phantom_imports:
            detail_parts.append(f"Imported but missing on disk: {', '.join(sorted(phantom_imports))}")
        if import_ok:
            detail_parts.append(
                f"All sidecars explicitly imported ({', '.join(sorted(sidecars_on_disk)) or 'none'})"
            )

        checks["imports"] = {"ok": import_ok, "detail": " | ".join(detail_parts)}
    else:
        checks["imports"] = {"ok": False, "detail": "default.nix missing — cannot check imports"}

    # ------------------------------------------------------------------
    # CHECK 3 — Namespace constraint (my.* only)
    # ------------------------------------------------------------------
    if default_nix.exists():
        default_text = default_nix.read_text(encoding="utf-8")

        # Look for options.* that are NOT options.my
        bad_namespaces = []
        for m in UPSTREAM_OPTION_PATTERN.finditer(default_text):
            # Allow options.my and options defined inside a let block (heuristic)
            line = default_text[max(0, m.start()-60):m.end()+30]
            if "my" not in m.group(0):
                bad_namespaces.append(m.group(1))

        has_my = bool(MY_NAMESPACE_PATTERN.search(default_text))

        ns_ok = len(bad_namespaces) == 0
        if bad_namespaces:
            detail = f"Options outside my.*: {', '.join(set(bad_namespaces))}"
        elif not has_my:
            detail = "No options.my.* definitions found — check that options are correctly namespaced"
            ns_ok = False
        else:
            detail = "All options under my.* namespace"

        checks["namespace"] = {"ok": ns_ok, "detail": detail}
    else:
        checks["namespace"] = {"ok": False, "detail": "default.nix missing — cannot check namespace"}

    # ------------------------------------------------------------------
    # CHECK 4 — meta.nix schema
    # ------------------------------------------------------------------
    meta_nix = module_dir / "meta.nix"
    if meta_nix.exists():
        meta_text = meta_nix.read_text(encoding="utf-8")
        meta = _parse_meta(meta_text)

        missing_fields = REQUIRED_META_FIELDS - set(meta.keys())
        ns_field = meta.get("namespace", "")
        ns_valid = ns_field.startswith("my.")

        schema_ok = (len(missing_fields) == 0) and ns_valid
        detail_parts = []
        if missing_fields:
            detail_parts.append(f"Missing fields: {', '.join(sorted(missing_fields))}")
        if not ns_valid:
            detail_parts.append(
                f"namespace field {ns_field!r} must start with 'my.'"
            )
        if schema_ok:
            detail_parts.append(
                f"Schema valid — namespace={ns_field!r}, status={meta.get('status','?')!r}"
            )

        checks["meta_schema"] = {"ok": schema_ok, "detail": " | ".join(detail_parts)}
    else:
        checks["meta_schema"] = {"ok": False, "detail": "meta.nix missing — cannot validate schema"}

    # ------------------------------------------------------------------
    # CHECK 5 — meta drift (sidecars list vs disk)
    # ------------------------------------------------------------------
    if meta_nix.exists() and default_nix.exists():
        meta_text = meta_nix.read_text(encoding="utf-8")
        meta = _parse_meta(meta_text)
        declared_sidecars = set(meta.get("sidecars", []))
        actual_sidecars = set(_sidecar_files(module_dir))

        undeclared = actual_sidecars - declared_sidecars
        ghost = declared_sidecars - actual_sidecars

        drift_ok = (len(undeclared) == 0) and (len(ghost) == 0)
        detail_parts = []
        if undeclared:
            detail_parts.append(f"On disk but not in meta.nix sidecars: {', '.join(sorted(undeclared))}")
        if ghost:
            detail_parts.append(f"In meta.nix sidecars but missing on disk: {', '.join(sorted(ghost))}")
        if drift_ok:
            detail_parts.append(
                f"meta.nix sidecars in sync ({', '.join(sorted(actual_sidecars)) or 'none'})"
            )

        checks["meta_drift"] = {"ok": drift_ok, "detail": " | ".join(detail_parts)}
    else:
        checks["meta_drift"] = {
            "ok": False,
            "detail": "meta.nix or default.nix missing — cannot check drift",
        }

    passed = all(c["ok"] for c in checks.values())
    return {"passed": passed, "module": str(rel), "checks": checks}


def _format_report(result: dict) -> str:
    """Render validation result as a readable report string."""
    lines = [
        f"Module: {result['module']}",
        f"Result: {'✅ PASSED' if result['passed'] else '❌ FAILED'}",
        "",
    ]
    for check_name, info in result["checks"].items():
        icon = "✅" if info["ok"] else "❌"
        lines.append(f"  {icon} [{check_name}]  {info['detail']}")

    if not result["passed"]:
        lines += [
            "",
            "Hard gates violated — changes would be rejected by AGENT.md §4.",
            "Fix the above issues before proceeding.",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scaffolding helper
# ---------------------------------------------------------------------------

SCAFFOLD_TEMPLATES = {
    "default.nix": textwrap.dedent("""\
        { config, lib, pkgs, ... }:

        let
          cfg = config.my.{category}.{name};
        in
        {{
          imports = [
            ./tests.nix
          ];

          options.my.{category}.{name} = {{
            enable = lib.mkEnableOption "{name}";
          }};

          config = lib.mkIf cfg.enable {{
            # TODO: implement
          }};
        }}
    """),

    "meta.nix": textwrap.dedent("""\
        {{
          name        = "{name}";
          category    = "{category}";
          description = "TODO: describe {name}";
          version     = "0.1.0";
          tags        = [ "{category}" ];
          namespace   = "my.{category}.{name}";
          requires    = [];
          reads       = [];
          sidecars    = [ "tests.nix" ];
          testDescription = "TODO: describe tests";
          status      = "experimental";
        }}
    """),

    "tests.nix": textwrap.dedent("""\
        { config, lib, pkgs, ... }:

        {{
          # Smoke test — extend with systemd checks or NixOS VM tests as needed
          assertions = [
            {{
              assertion = true;
              message   = "{name}: replace this placeholder assertion";
            }}
          ];
        }}
    """),

    "README.md": textwrap.dedent("""\
        # {name}

        > TODO: one-paragraph description

        ## Options

        | Option | Type | Default | Description |
        |--------|------|---------|-------------|
        | `my.{category}.{name}.enable` | bool | `false` | Enable this module |

        ## Usage

        ```nix
        my.{category}.{name}.enable = true;
        ```
    """),
}


def scaffold_module(module_dir: Path, name: str, category: str, dry_run: bool) -> str:
    """Create a minimal passing module skeleton."""
    lines = [f"Scaffold: modules/{category}/{name}/", ""]
    created = []

    for filename, template in SCAFFOLD_TEMPLATES.items():
        content = template.format(name=name, category=category)
        target = module_dir / filename

        if target.exists():
            lines.append(f"  ⚠️  SKIP {filename} — already exists")
            continue

        if dry_run:
            lines.append(f"  📄 WOULD CREATE {filename} ({len(content)} chars)")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            lines.append(f"  ✅ CREATED {filename}")
            created.append(filename)

    if not dry_run and created:
        lines += ["", f"Created {len(created)} files. Run validate to confirm."]
    elif dry_run:
        lines += ["", "Dry run — nothing written."]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

@register_tool("nix_module_validator")
class NixModuleValidator(BaseTool):
    """
    Validate or scaffold a NixOS config module against AGENT.md conventions.
    """

    name = "nix_module_validator"
    description = (
        "Validate a module directory against the project conventions defined in AGENT.md, "
        "or scaffold a new empty module that passes all checks.\n\n"
        "Validation checks (AGENT.md §4 hard gates):\n"
        "  1. Structure   — default.nix, meta.nix, tests.nix, README.md all present\n"
        "  2. Imports     — every sidecar .nix file is explicitly imported in default.nix\n"
        "  3. Namespace   — all options.* are under my.<category>.<name>\n"
        "  4. Meta schema — meta.nix has all required fields, namespace starts with my.\n"
        "  5. Meta drift  — meta.nix sidecars list matches files on disk\n\n"
        "Use action='validate' before submitting any module change. "
        "Use action='scaffold' to create a new module skeleton. "
        "Use action='list' to see all existing modules and their pass/fail status."
    )
    parameters = [
        {
            "name": "action",
            "type": "string",
            "description": (
                "'validate' — run all checks against an existing module path. "
                "'scaffold'  — create a new minimal passing module. "
                "'list'      — validate every module under modules/ and show a summary."
            ),
            "required": True,
        },
        {
            "name": "module_path",
            "type": "string",
            "description": (
                "Path relative to the repo root, e.g. 'modules/services/foo'. "
                "Required for action='validate' and action='scaffold'."
            ),
            "required": False,
        },
        {
            "name": "name",
            "type": "string",
            "description": "Module name. Required for action='scaffold'.",
            "required": False,
        },
        {
            "name": "category",
            "type": "string",
            "description": (
                "Module category (parent dir under modules/). "
                "Required for action='scaffold'. "
                "e.g. 'services', 'programs', 'system', 'hardware', 'home'."
            ),
            "required": False,
        },
        {
            "name": "dry_run",
            "type": "boolean",
            "description": "For action='scaffold': preview without writing files. Default false.",
            "required": False,
        },
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params) if params.strip() else {}

        action: str = params.get("action", "").strip().lower()
        module_path: str = params.get("module_path", "").strip()
        name: str = params.get("name", "").strip()
        category: str = params.get("category", "").strip()
        dry_run: bool = bool(params.get("dry_run", False))

        # ------------------------------------------------------------------
        if action == "validate":
            if not module_path:
                return "ERROR: 'module_path' is required for action='validate'."
            module_dir = (NIXOS_REPO_PATH / module_path).resolve()
            if not module_dir.exists():
                return f"ERROR: module path does not exist: {module_path}"
            try:
                module_dir.relative_to(NIXOS_REPO_PATH.resolve())
            except ValueError:
                return "ERROR: module_path escapes repository root."

            result = validate_module(module_dir)
            return _format_report(result)

        # ------------------------------------------------------------------
        elif action == "scaffold":
            if not name:
                return "ERROR: 'name' is required for action='scaffold'."
            if not category:
                return "ERROR: 'category' is required for action='scaffold'."

            # Derive module_path from name + category if not supplied
            if not module_path:
                module_path = f"modules/{category}/{name}"

            module_dir = (NIXOS_REPO_PATH / module_path).resolve()
            try:
                module_dir.relative_to(NIXOS_REPO_PATH.resolve())
            except ValueError:
                return "ERROR: resolved module path escapes repository root."

            return scaffold_module(module_dir, name, category, dry_run)

        # ------------------------------------------------------------------
        elif action == "list":
            modules_root = NIXOS_REPO_PATH / "modules"
            if not modules_root.exists():
                return "ERROR: modules/ directory not found in repo root."

            # Find all directories that contain a default.nix
            module_dirs = sorted(
                p.parent for p in modules_root.rglob("default.nix")
                if p.parent != modules_root
            )

            if not module_dirs:
                return "No modules found under modules/."

            lines = [f"{'Status':<8} Module"]
            lines.append("-" * 50)
            passed_count = 0

            for mdir in module_dirs:
                result = validate_module(mdir)
                status = "✅ PASS" if result["passed"] else "❌ FAIL"
                if result["passed"]:
                    passed_count += 1
                failed_checks = [k for k, v in result["checks"].items() if not v["ok"]]
                suffix = "" if result["passed"] else f"  ({', '.join(failed_checks)})"
                lines.append(f"{status}  {result['module']}{suffix}")

            total = len(module_dirs)
            lines += [
                "-" * 50,
                f"{passed_count}/{total} modules passing all checks.",
            ]
            return "\n".join(lines)

        # ------------------------------------------------------------------
        else:
            return (
                f"ERROR: unknown action {action!r}. "
                "Use 'validate', 'scaffold', or 'list'."
            )