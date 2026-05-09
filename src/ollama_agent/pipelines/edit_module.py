from __future__ import annotations
import json
from pathlib import Path
from ollama_agent.models import OllamaModel

PLAN_SYSTEM = """\
You are given a NixOS module spec and a list of plain-English edit descriptions.
Return ONLY a JSON array of edit operations. Each op must have the form:
  {"op": "set_default"|"set_description"|"add_option"|"remove_option", "path": "optionName", ...}
No prose, no markdown. Raw JSON array only.
"""

def run(
    name: str,
    edits: list[str],
    repo_path: str = ".",
    model_id: str = "qwen2.5-coder:7b",
    base_url: str = "http://localhost:11434",
    **_,
) -> str:
    # find the spec
    base = Path(repo_path)
    candidates = list(base.glob(f"modules/**/{name}/.module-spec.json"))
    if not candidates:
        return f"No module spec found for '{name}'. Has it been created yet?"
    spec_path = candidates[0]
    spec = json.loads(spec_path.read_text())

    # 1 model call: plan the edits
    model = OllamaModel(model_id=model_id, api_base=f"{base_url.rstrip('/')}/v1",
                        api_key="ollama", temperature=0.0, max_tokens=1024)
    prompt = f"Module spec:\n{json.dumps(spec, indent=2)}\n\nRequested edits:\n" + "\n".join(f"- {e}" for e in edits)
    response = model([
        {"role": "system", "content": PLAN_SYSTEM},
        {"role": "user", "content": prompt},
    ])
    raw = response.content.strip().removeprefix("```json").removesuffix("```").strip()
    ops = json.loads(raw)

    # apply ops deterministically
    for op in ops:
        _apply_op(spec, op)

    spec_path.write_text(json.dumps(spec, indent=2))
    return f"Applied {len(ops)} edit(s) to {spec_path}"


def _apply_op(spec: dict, op: dict) -> None:
    options = spec.setdefault("options", [])
    match op.get("op"):
        case "set_default":
            for o in options:
                if o["path"] == op["path"]:
                    o["default"] = op.get("value", "")
        case "set_description":
            for o in options:
                if o["path"] == op["path"]:
                    o["description"] = op.get("value", "")
        case "add_option":
            if not any(o["path"] == op["path"] for o in options):
                options.append({"path": op["path"], "type": op.get("type", "str"),
                                 "default": op.get("default", ""), "description": ""})
        case "remove_option":
            spec["options"] = [o for o in options if o["path"] != op["path"]]