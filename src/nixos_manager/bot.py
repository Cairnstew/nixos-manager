"""bot.py — thin wrapper so gui.py and agent.py stay unchanged."""

from .pipeline import run_pipeline


class _PipelineBot:
    """
    Mimics the qwen-agent bot interface (bot.run returns an iterable)
    so gui.py needs zero changes.
    """

    def run(self, messages: list[dict]) -> list[dict]:
        # Extract the last user message
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        answer = run_pipeline(user_text)
        return [{"role": "assistant", "content": answer}]


_bot: _PipelineBot | None = None


def get_bot() -> _PipelineBot:
    global _bot
    if _bot is None:
        _bot = _PipelineBot()
    return _bot