import json
import os
import re
import textwrap

import requests
from qwen_agent.tools.base import BaseTool, register_tool
from ._base import run_mcp, parse_params, out


@register_tool("nix_verify")
class NixVerifyTool(BaseTool):
    description = (
        "CALL THIS before giving any final answer containing Nix code. "
        "Extracts every package name and option path from your proposed answer "
        "and verifies each one actually exists via MCP. "
        "Returns a verdict and a list of any hallucinated names to fix."
    )
    parameters = [
        {"name": "proposed_answer", "type": "string", "required": True,
         "description": "The Nix config or answer you're about to give the user"},
        {"name": "original_goal", "type": "string", "required": True,
         "description": "What the user originally asked for"},
    ]

    _EXTRACT_SYSTEM = textwrap.dedent("""\
        Extract all Nix package names and NixOS/Home Manager option paths from the text.
        Respond ONLY with valid JSON:
        {
          "packages": ["name1", "name2", ...],
          "options": ["services.nginx.enable", ...]
        }
        If none found, return empty lists.
    """)

    def call(self, params: str | dict, **_) -> str:
        p = parse_params(params)
        answer = p.get("proposed_answer", "")

        packages, options = self._extract_names(answer)

        if not packages and not options:
            return out({
                "verdict": "no_nix_content",
                "message": "No package or option names found to verify.",
                "next_step": "Safe to present answer to user.",
            })

        issues: list[str] = []
        verified: list[str] = []

        for pkg in packages:
            result = run_mcp("nix", {"action": "info", "query": pkg,
                                      "source": "nixos", "type": "package"})
            if "not found" in result.lower() or "error" in result.lower():
                issues.append(f"Package '{pkg}' — not found in nixpkgs")
            else:
                verified.append(f"Package '{pkg}' — OK")

        for opt in options:
            source = "home-manager" if opt.startswith(("programs.", "services.", "home.")) else "nixos"
            result = run_mcp("nix", {"action": "info", "query": opt, "source": source})
            if "not found" in result.lower() or "error" in result.lower():
                issues.append(f"Option '{opt}' — not found in {source}")
            else:
                verified.append(f"Option '{opt}' — OK")

        passed = len(issues) == 0
        return out({
            "verdict": "pass" if passed else "fail",
            "verified": verified,
            "issues": issues,
            "next_step": (
                "Answer verified. Safe to present to user."
                if passed else
                f"Fix {len(issues)} issue(s) listed above, then call nix_verify again."
            ),
        })

    def _extract_names(self, text: str) -> tuple[list[str], list[str]]:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            try:
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 400,
                        "system": self._EXTRACT_SYSTEM,
                        "messages": [{"role": "user", "content": text}],
                    },
                    timeout=20,
                )
                raw = resp.json()["content"][0]["text"].strip()
                raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                data = json.loads(raw)
                return data.get("packages", []), data.get("options", [])
            except Exception:
                pass

        options = re.findall(r'\b(?:services|programs|home|boot|networking|environment)\.\S+', text)
        packages = re.findall(r'\bpkgs\.([a-z][a-z0-9\-_]+)', text)
        return list(set(packages)), list(set(options))