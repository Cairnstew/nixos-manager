from qwen_agent.tools.base import BaseTool, register_tool
from ._base import parse_params, out

_STORE: dict[str, str] = {}


@register_tool("scratchpad")
class ScratchpadTool(BaseTool):
    description = (
        "Read or write working notes. "
        "WRITE confirmed package names, option paths, errors, decisions immediately after finding them. "
        "READ at the start of each step to recall what you already know. "
        "Keys: 'plan' | 'facts' | 'errors' | 'decisions'."
    )
    parameters = [
        {"name": "action", "type": "string", "required": True,
         "description": "read | write | append | clear"},
        {"name": "key", "type": "string", "required": True,
         "description": "plan | facts | errors | decisions"},
        {"name": "value", "type": "string", "required": False,
         "description": "Content to store (not needed for read)"},
    ]

    def call(self, params: str | dict, **_) -> str:
        p = parse_params(params)
        action = p.get("action", "read")
        key = p.get("key", "facts")
        value = p.get("value", "")

        if action == "read":
            return out({"key": key, "content": _STORE.get(key, "(empty)"),
                        "next_step": "Continue with your plan. Call nix_planner if you have no plan yet."})

        if action == "write":
            _STORE[key] = value
            return out({"saved": True, "key": key,
                        "next_step": "Scratchpad updated. Continue to the next step in your plan."})

        if action == "append":
            _STORE[key] = f"{_STORE.get(key, '')}\n{value}".strip()
            return out({"saved": True, "key": key,
                        "next_step": "Scratchpad updated. Continue to the next step in your plan."})

        if action == "clear":
            _STORE.pop(key, None)
            return out({"cleared": key, "next_step": "Scratchpad cleared."})

        return out({"error": "Unknown action. Use: read | write | append | clear"})