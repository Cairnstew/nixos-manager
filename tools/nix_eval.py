import subprocess
import json
import tempfile
import os
from typing import Union
from qwen_agent.tools.base import BaseTool, register_tool

@register_tool("nix_eval")
class NixEval(BaseTool):
    """Validate Nix code snippets for syntax and evaluation errors."""

    name = "nix_eval"
    description = (
        "Evaluates a string of Nix code to check for syntax errors or undefined variables. "
        "Call this BEFORE presenting Nix code to the user to ensure it is valid."
    )
    parameters = [
        {
            "name": "code",
            "type": "string",
            "description": "The Nix expression to evaluate.",
            "required": True,
        },
        {
            "name": "is_flake",
            "type": "boolean",
            "description": "Set to True if testing a full flake.nix structure.",
            "required": False,
        },
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            params = json.loads(params) if params.strip() else {}

        code = params.get("code", "")
        is_flake = params.get("is_flake", False)

        if not code:
            return "ERROR: No code provided for evaluation."

        # Create a temporary file to evaluate
        with tempfile.NamedTemporaryFile(suffix=".nix", delete=False) as tmp:
            tmp.write(code.encode('utf-8'))
            tmp_path = tmp.name

        try:
            if is_flake:
                # Flakes require a directory, so we check syntax only for snippet safety
                cmd = ["nix-instantiate", "--parse", tmp_path]
            else:
                # Standard expression check
                cmd = ["nix-instantiate", "--eval", tmp_path]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                return "SUCCESS: Code is syntactically valid."
            else:
                return f"SYNTAX ERROR: {result.stderr}"
        
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)