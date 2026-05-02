"""
tools/example_custom_tool.py
-----------------------------------------------------------------------
TEMPLATE — copy this file, rename it, and fill in the blanks.
Register the new tool by importing it in agent.py and adding its name
to the TOOLS list there.
-----------------------------------------------------------------------

How qwen-agent tools work:
  1. Subclass BaseTool.
  2. Set `name` (string id), `description` (shown to the LLM), `parameters`.
  3. Implement `call(self, params, **kwargs) -> str`.
  4. Decorate the class with @register_tool(name).
  5. The LLM will invoke it automatically when it decides the tool is needed.
"""

import json
from typing import Union

from qwen_agent.tools.base import BaseTool, register_tool


@register_tool("my_custom_tool")
class MyCustomTool(BaseTool):
    """One-line summary shown in tool listings."""

    name = "my_custom_tool"
    description = (
        "Describe WHAT the tool does and WHEN the LLM should call it. "
        "Be specific — the model decides whether to use the tool based solely on this text."
    )
    parameters = [
        # Each entry becomes a JSON Schema property.
        {
            "name": "my_param",
            "type": "string",           # string | integer | boolean | array | object
            "description": "What this argument controls.",
            "required": True,
        },
        {
            "name": "optional_flag",
            "type": "boolean",
            "description": "Optional toggle. Defaults to False.",
            "required": False,
        },
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        # params may arrive as a JSON string — normalise it:
        if isinstance(params, str):
            params = json.loads(params) if params.strip() else {}

        my_param = params.get("my_param", "")
        optional_flag = params.get("optional_flag", False)

        if not my_param:
            return "ERROR: 'my_param' is required."

        # --- your logic here ---
        result = f"Tool called with my_param={my_param!r}, flag={optional_flag}"

        # Always return a plain string.  The LLM reads this as the tool result.
        return result
