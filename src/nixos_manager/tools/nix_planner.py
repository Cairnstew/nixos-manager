import json
import os
import textwrap

import requests
from qwen_agent.tools.base import BaseTool, register_tool
from ._base import parse_params, out
from .scratchpad import _STORE as _SCRATCHPAD


@register_tool("nix_planner")
class NixPlannerTool(BaseTool):
    description = (
        "CALL THIS FIRST for any non-trivial task. "
        "Breaks the goal into numbered steps and tells you exactly which tool to call for each. "
        "Returns a plan you must follow step by step."
    )
    parameters = [
        {"name": "goal", "type": "string", "required": True,
         "description": "The user's request, in your own words"},
        {"name": "known_facts", "type": "string", "required": False,
         "description": "Anything already confirmed: package names, option paths, etc."},
        {"name": "uncertainties", "type": "string", "required": False,
         "description": "What you don't know yet and need to look up"},
    ]

    _SYSTEM = textwrap.dedent("""\
        You are a NixOS planning assistant. Given a goal, produce a numbered action plan.

        Rules:
        - Steps must be concrete and sequential.
        - Each step must name EXACTLY ONE tool: nix_research, nix_search_tool,
          nix_versions_tool, nix_check_tool, scratchpad, or nix_verify.
        - Flag any package names or option paths that need verification.
        - Keep steps short: one sentence each.

        Respond ONLY with valid JSON matching this schema exactly:
        {
          "steps": [
            {"step": 1, "action": "one sentence", "tool": "tool_name"},
            ...
          ],
          "must_verify": ["package-or-option-name", ...],
          "first_tool": "the tool to call right now"
        }
    """)

    def call(self, params: str | dict, **_) -> str:
        p = parse_params(params)
        goal = p.get("goal", "")
        known = p.get("known_facts", "none")
        unknowns = p.get("uncertainties", "none")

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return self._fallback_plan(goal)

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
                    "max_tokens": 1000,
                    "system": self._SYSTEM,
                    "messages": [{"role": "user", "content":
                        f"Goal: {goal}\nAlready known: {known}\nUncertainties: {unknowns}"}],
                },
                timeout=30,
            )
            raw = resp.json()["content"][0]["text"].strip()
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            plan = json.loads(raw)
        except Exception as e:
            return self._fallback_plan(goal, error=str(e))

        _SCRATCHPAD["plan"] = json.dumps(plan["steps"], indent=2)

        return out({
            **plan,
            "next_step": f"Call {plan.get('first_tool', 'nix_search_tool')} now. Follow the plan step by step.",
        })

    def _fallback_plan(self, goal: str, error: str = "") -> str:
        steps = [
            {"step": 1, "action": f"Search for: {goal}", "tool": "nix_search_tool"},
            {"step": 2, "action": "Write confirmed facts to scratchpad", "tool": "scratchpad"},
            {"step": 3, "action": "Verify all package names and options", "tool": "nix_verify"},
        ]
        _SCRATCHPAD["plan"] = json.dumps(steps, indent=2)
        note = f" (API error: {error})" if error else " (no ANTHROPIC_API_KEY set)"
        return out({
            "steps": steps,
            "must_verify": [],
            "first_tool": "nix_search_tool",
            "note": f"Fallback plan generated{note}",
            "next_step": "Call nix_search_tool now. Follow the plan step by step.",
        })