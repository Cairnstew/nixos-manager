"""bot.py — thin wrapper so gui.py and agent.py stay unchanged."""

import json
from pathlib import Path

from .pipeline import run_pipeline


class _PipelineBot:
    def run(self, messages: list[dict]) -> list[dict]:
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        plan_path = run_pipeline(user_text)

        try:
            data = json.loads(Path(plan_path).read_text(encoding="utf-8"))
            content = (
                f"**Plan saved to:** `{plan_path}`\n\n"
                f"```json\n{json.dumps(data, indent=2)}\n```"
            )
        except Exception as e:
            content = f"Plan written to `{plan_path}` (read error: {e})"

        return [{"role": "assistant", "content": content}]


_bot: _PipelineBot | None = None


def get_bot() -> _PipelineBot:
    global _bot
    if _bot is None:
        _bot = _PipelineBot()
    return _bot