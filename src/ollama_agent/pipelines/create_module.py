from __future__ import annotations
import json, subprocess
from pathlib import Path
from searchix import SearchixClient
from ollama_agent.models import OllamaModel

PICK_SYSTEM = """\
Given Nix search results, return ONLY a JSON object:
{"attribute": "<best matching attribute>", "source": "nixpkgs|home-manager|nixos"}
Pick the single most relevant result. No prose, no markdown.
"""

DESCRIBE_SYSTEM = """\
Fill in the "description" field for each option in this module spec JSON.
Return the spec unchanged except for description fields. Return ONLY valid JSON.
"""

def _model(model_id, base_url):
    return OllamaModel(
        model_id=model_id,
        base_url=base_url,
        temperature=0.0,
        max_new_tokens=1024,
    )

def _search(name): 
    results = SearchixClient().search(name, sources=["nixpkgs","home-manager","nixos"], limit=10)
    return [{"attribute": r.attribute, "description": r.description} for r in results]

def _pick(results, name, hint, model):
    prompt = f"User wants a module for: {name} (hint: {hint})\n\nResults:\n{json.dumps(results, indent=2)}"
    resp = model([{"role":"system","content":PICK_SYSTEM},{"role":"user","content":prompt}])
    return json.loads(resp.content.strip().removeprefix("```json").removesuffix("```").strip())

def _build_template(name, picked, hint, requests):
    ns = "my.programs" if hint in ("home-manager","home","user") else "my.services"
    options = [{"path":"enable","type":"bool","default":"false","description":""}]
    for r in requests:
        options.append({"path":r,"type":"str","default":"","description":""})
    return {"name":name,"namespace":ns,"attribute":picked["attribute"],
            "source":picked["source"],"options":options}

def _fill_descriptions(spec, model):
    resp = model([{"role":"system","content":DESCRIBE_SYSTEM},
                  {"role":"user","content":json.dumps(spec, indent=2)}])
    return json.loads(resp.content.strip().removeprefix("```json").removesuffix("```").strip())

def _render_nix(spec):
    opts = []
    for o in spec["options"]:
        t = "bool" if o["type"]=="bool" else "str"
        d = o["default"] or ("false" if t=="bool" else "\"\"")
        opts.append(
            f'      {o["path"]} = lib.mkOption {{\n'
            f'        type = lib.types.{t};\n'
            f'        default = {d};\n'
            f'        description = "{o["description"]}";\n'
            f'      }};'
        )
    return (
        f'{{ config, lib, pkgs, ... }}:\n'
        f'let cfg = config.{spec["namespace"]}.{spec["name"]}; in\n'
        f'{{\n'
        f'  options.{spec["namespace"]}.{spec["name"]} = {{\n'
        + "\n".join(opts) +
        f'\n  }};\n\n'
        f'  config = lib.mkIf cfg.enable {{\n'
        f'    # TODO: fill in config\n'
        f'  }};\n'
        f'}}\n'
    )

def _write(repo_path, spec):
    subdir = "home" if "programs" in spec["namespace"] else "nixos"
    module_dir = Path(repo_path) / "modules" / subdir / spec["name"]
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / ".module-spec.json").write_text(json.dumps(spec, indent=2))
    (module_dir / "default.nix").write_text(_render_nix(spec))
    return module_dir

def _nix_check(repo_path):
    r = subprocess.run(["nix","flake","check","--no-build"],
                       cwd=repo_path, capture_output=True, text=True, timeout=120)
    return "ok" if r.returncode == 0 else r.stderr

def run(name, hint="home-manager", requests=None, repo_path=".",
        model_id="qwen2.5-coder:7b", base_url="http://localhost:11434",
        dry_run=False, **_):
    model = _model(model_id, base_url)
    results = _search(name)
    if not results:
        return f"No search results for '{name}' — is searchix running? Try: searchix setup"
    picked   = _pick(results, name, hint, model)
    spec     = _build_template(name, picked, hint, requests or [])
    spec     = _fill_descriptions(spec, model)
    if dry_run:
        return json.dumps(spec, indent=2)
    module_dir = _write(repo_path, spec)
    check = _nix_check(repo_path)
    return f"Created {module_dir}\nnix check: {check}"