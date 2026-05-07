from qwen_agent.tools.base import BaseTool, register_tool
from ._base import run_mcp, parse_params, out

_PARAM_KEYS = ["action", "query", "source", "type", "channel", "limit", "version", "system"]


@register_tool("nix_search_tool")
class NixSearchTool(BaseTool):
    description = (
        "Query real NixOS data: packages, options, wiki, home-manager, flakes, etc. "
        "Actions: search | info | stats | options | cache | channels | flake-inputs. "
        "Sources: nixos | home-manager | darwin | flakes | flakehub | nixvim | noogle | wiki | nix-dev | nixhub."
    )
    parameters = [
        {"name": "action", "type": "string", "required": True,
         "description": "search | info | stats | options | cache | channels | flake-inputs"},
        {"name": "query", "type": "string", "required": False,
         "description": "Package name, option path, or search term"},
        {"name": "source", "type": "string", "required": False, "default": "nixos",
         "description": "nixos | home-manager | darwin | flakes | flakehub | nixvim | noogle | wiki | nix-dev | nixhub"},
        {"name": "type", "type": "string", "required": False,
         "description": "For nixos: 'packages' or 'options'. For flake-inputs: 'list', 'ls', or 'read'"},
        {"name": "channel", "type": "string", "required": False,
         "description": "'stable' or 'unstable'"},
        {"name": "limit", "type": "integer", "required": False,
         "description": "Max results"},
        {"name": "version", "type": "string", "required": False,
         "description": "Specific version (for cache action)"},
        {"name": "system", "type": "string", "required": False,
         "description": "e.g. 'x86_64-linux' (for cache action)"},
    ]

    def call(self, params: str | dict, **_) -> str:
        p = parse_params(params)
        payload = {k: p[k] for k in _PARAM_KEYS if k in p}
        result = run_mcp("nix", payload)
        return out({
            "result": result,
            "next_step": (
                "If this confirmed a package or option name, write it to scratchpad (key='facts'). "
                "Then continue to the next step in your plan. "
                "If unsure, call nix_search_tool again with action='info' to verify."
            ),
        })