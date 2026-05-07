import os
import shutil
import subprocess
import tempfile

from qwen_agent.tools.base import BaseTool, register_tool
from ._base import parse_params, out


@register_tool("nix_check_tool")
class NixCheckTool(BaseTool):
    description = (
        "Check Nix code for syntax errors, formatting issues, and antipatterns. "
        "Provide 'code' (a snippet) or 'path' (a file). "
        "Mode: 'syntax' | 'format' | 'lint' | 'all' (default)."
    )
    parameters = [
        {"name": "code", "type": "string", "required": False,
         "description": "Raw Nix snippet to check"},
        {"name": "path", "type": "string", "required": False,
         "description": "Absolute path to a .nix file"},
        {"name": "mode", "type": "string", "required": False,
         "description": "syntax | format | lint | all (default: all)"},
    ]

    _MODE_MAP = {
        "syntax": ["syntax"],
        "format": ["nixfmt"],
        "lint":   ["statix", "deadnix"],
        "all":    ["syntax", "nixfmt", "statix", "deadnix"],
    }
    _EXECUTABLES = {
        "syntax":  "nix-instantiate",
        "nixfmt":  "nixfmt",
        "statix":  "statix",
        "deadnix": "deadnix",
    }

    def _run_checker(self, name: str, filepath: str) -> dict:
        exe = self._EXECUTABLES[name]
        if not shutil.which(exe):
            install = "nix" if exe == "nix-instantiate" else f"nixpkgs.{exe}"
            return {
                "checker": name, "available": False, "passed": None,
                "output": f"'{exe}' not found. Install: nix-env -iA {install}",
            }
        cmd_map = {
            "syntax":  ["nix-instantiate", "--parse", filepath],
            "nixfmt":  ["nixfmt", "--check", filepath],
            "statix":  ["statix", "check", filepath],
            "deadnix": ["deadnix", "--fail", filepath],
        }
        try:
            proc = subprocess.run(cmd_map[name], capture_output=True, text=True, timeout=15)
            out_text = "\n".join(filter(None, [proc.stdout.strip(), proc.stderr.strip()])) or "(no output)"
            return {"checker": name, "available": True, "passed": proc.returncode == 0, "output": out_text}
        except subprocess.TimeoutExpired:
            return {"checker": name, "available": True, "passed": False, "output": "Timed out (15s)"}
        except Exception as e:
            return {"checker": name, "available": True, "passed": False, "output": str(e)}

    def call(self, params: str | dict, **_) -> str:
        p = parse_params(params)
        code = p.get("code", "").strip()
        path = p.get("path", "").strip()
        mode = p.get("mode", "all").lower()

        if mode not in self._MODE_MAP:
            return out({"error": f"Unknown mode '{mode}'. Use: syntax | format | lint | all"})
        if not code and not path:
            return out({"error": "Provide 'code' or 'path'."})

        tmp = None
        results = []
        try:
            if code and not path:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".nix",
                                                 delete=False, prefix="nix_check_") as f:
                    f.write(code)
                    tmp = f.name
                target = tmp
            else:
                if not os.path.isfile(path):
                    return out({"error": f"File not found: {path}"})
                target = path

            for c in self._MODE_MAP[mode]:
                results.append(self._run_checker(c, target))
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

        ran = [r for r in results if r["available"]]
        skipped = [r for r in results if not r["available"]]
        passed = all(r["passed"] for r in ran) if ran else None
        issues = [r for r in ran if not r["passed"]]

        next_step = (
            "All checks passed. Write this to scratchpad (key='facts') and call nix_verify next."
            if passed else
            f"{len(issues)} check(s) failed. Fix the issues above, then re-run nix_check_tool."
        )

        return out({
            "passed": passed,
            "mode": mode,
            "summary": (
                f"{sum(r['passed'] for r in ran)}/{len(ran)} checks passed"
                + (f", {len(skipped)} skipped (not installed)" if skipped else "")
            ),
            "results": results,
            "next_step": next_step,
        })