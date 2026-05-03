import subprocess
import json
from typing import Union
from qwen_agent.tools.base import BaseTool, register_tool

@register_tool("nix_search")
class NixSearch(BaseTool):
    """Search for packages or options in Nixpkgs."""

    name = "nix_search"
    description = (
        "Search for package names, descriptions, or NixOS options. "
        "Use this when you aren't sure of the exact attribute name for a package "
        "or want to find available versions."
    )
    parameters = [
        {
            "name": "query",
            "type": "string",
            "description": "The search term (e.g., 'postgresql', 'ripgrep').",
            "required": True,
        },
        {
            "name": "search_options",
            "type": "boolean",
            "description": "If True, searches NixOS options instead of packages.",
            "required": False,
        },
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params) if params.strip() else {}

        query = params.get("query", "")
        search_options = params.get("search_options", False)

        if not query or not query.strip():
            return "ERROR: Search query is required."

        try:
            # Using 'nix search' by default for compatibility
            # nixpkgs is the standard flake reference
            cmd = ["nix", "search", "nixpkgs", query, "--json"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return f"Error running nix search: {result.stderr}"
            
            return result.stdout
        except Exception as e:
            return f"Failed to execute search: {str(e)}"