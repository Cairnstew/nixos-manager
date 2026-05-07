from qwen_agent.tools.base import BaseTool, register_tool
from ._base import run_mcp, parse_params, out


@register_tool("nix_versions_tool")
class NixVersionsTool(BaseTool):
    description = (
        "Look up historical NixOS package versions with nixpkgs commit hashes. "
        "Use when the user needs a specific old version or a reproducible build."
    )
    parameters = [
        {"name": "package", "type": "string", "required": True,
         "description": "Package name, e.g. 'python' or 'nodejs'"},
        {"name": "version", "type": "string", "required": False,
         "description": "Filter to a specific version string"},
        {"name": "limit", "type": "integer", "required": False,
         "description": "Max versions to return"},
    ]

    def call(self, params: str | dict, **_) -> str:
        p = parse_params(params)
        payload = {k: p[k] for k in ["package", "version", "limit"] if k in p}
        result = run_mcp("nix_versions", payload)
        return out({
            "result": result,
            "next_step": (
                "Write the commit hash and version to scratchpad (key='facts'). "
                "Then continue to the next step in your plan."
            ),
        })