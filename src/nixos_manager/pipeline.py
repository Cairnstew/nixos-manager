"""
pipeline.py — deterministic pipeline for NixOS requests.

The 7B model is called for exactly four narrow tasks:
  1. Classify intent and extract entities
  2. Propose and score plan steps
  3. Score search result relevance (yes/no)
  4. Generate Nix output for one step at a time
  5. Extract and fix invalid names

Python controls all sequencing, looping, and tool calls.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import requests

from .config.settings import LLM_CONFIG, PIPELINE_CONFIG
from .tools._base import run_mcp
from .tools.scratchpad import _STORE as scratch


# ---------------------------------------------------------------------------
# LLM call — talks to your local Ollama / vLLM endpoint
# ---------------------------------------------------------------------------

def _llm(system: str, user: str, max_tokens: int = 512) -> str:
    """Single model call. Returns plain text."""
    resp = requests.post(
        f"{LLM_CONFIG['model_server']}/chat/completions",
        headers={"Authorization": f"Bearer {LLM_CONFIG['api_key']}"},
        json={
            "model": LLM_CONFIG["model"],
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _llm_json(system: str, user: str, max_tokens: int = 512) -> dict:
    """LLM call that must return JSON. Retries once on parse failure."""
    enforce = "\n\nRespond ONLY with valid JSON. No explanation, no markdown fences."
    for attempt in range(2):
        raw = _llm(system + enforce, user, max_tokens)
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if attempt == 0:
                continue
            # Second failure — return safe empty dict
            print(f"  [pipeline] JSON parse failed twice, raw={raw[:120]}")
            return {}
    return {}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PlanStep:
    index: int
    goal: str
    tool: str
    query: str
    source: str = "nixos"
    confidence: float = 0.0
    result: str = ""


@dataclass
class PipelineState:
    user_request: str
    intent: str = ""
    entities: list[str] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    final_answer: str = ""


# ---------------------------------------------------------------------------
# Stage 1 — Intake
# ---------------------------------------------------------------------------

def _stage_intake(request: str) -> PipelineState:
    print("\n[pipeline] stage 1: intake")

    result = _llm_json(
        system=(
            "You extract structured information from a NixOS user request.\n"
            "Return JSON:\n"
            "  intent: one of 'configure' | 'search' | 'debug' | 'version' | 'explain'\n"
            "  entities: list of package names, option paths, or keywords mentioned\n"
            "  needs_research: true if the request involves something obscure or recent"
        ),
        user=request,
        max_tokens=256,
    )

    state = PipelineState(user_request=request)
    state.intent = result.get("intent", "configure")
    state.entities = result.get("entities", [])

    scratch["intent"] = state.intent
    scratch["entities"] = json.dumps(state.entities)
    print(f"  intent={state.intent}  entities={state.entities}")
    return state


# ---------------------------------------------------------------------------
# Stage 2 — Plan (the long-thinking phase)
# ---------------------------------------------------------------------------

_PLAN_SYSTEM = """\
You are planning a NixOS task. Given the user request and known entities,
produce a list of concrete research and action steps.

Return JSON:
{
  "steps": [
    {
      "goal": "what this step achieves (one sentence)",
      "tool": "nix_search | nix_info | nix_versions | web_search",
      "query": "exact query string to use",
      "source": "nixos | home-manager | darwin | wiki | noogle",
      "confidence": 0.0-1.0
    }
  ]
}

Confidence means: how sure you are this step is correct and necessary.
Give low confidence (< 0.7) to anything you are uncertain about.
"""

_REFINE_SYSTEM = """\
You are reviewing a NixOS plan step that has low confidence.
Rewrite it to be more specific and correct.

Return JSON with the same fields: goal, tool, query, source, confidence.
The rewritten step should have higher confidence than the original.
"""


def _stage_plan(state: PipelineState) -> PipelineState:
    print("\n[pipeline] stage 2: plan")
    cfg = PIPELINE_CONFIG

    # Initial plan
    raw = _llm_json(
        system=_PLAN_SYSTEM,
        user=(
            f"Request: {state.user_request}\n"
            f"Intent: {state.intent}\n"
            f"Entities: {', '.join(state.entities)}"
        ),
        max_tokens=800,
    )

    steps = [
        PlanStep(
            index=i,
            goal=s.get("goal", ""),
            tool=s.get("tool", "nix_search"),
            query=s.get("query", ""),
            source=s.get("source", "nixos"),
            confidence=float(s.get("confidence", 0.5)),
        )
        for i, s in enumerate(raw.get("steps", []))
    ]

    # Refinement loop — Python decides which steps need rework
    for iteration in range(cfg["plan_max_iterations"]):
        weak = [s for s in steps if s.confidence < cfg["confidence_threshold"]]
        if not weak:
            print(f"  plan confident after {iteration} refinement(s)")
            break

        print(f"  iteration {iteration + 1}: refining {len(weak)} weak step(s)")
        for step in weak:
            refined = _llm_json(
                system=_REFINE_SYSTEM,
                user=(
                    f"Original step: {json.dumps({'goal': step.goal, 'tool': step.tool, 'query': step.query, 'source': step.source})}\n"
                    f"Confidence was: {step.confidence}\n"
                    f"Full request: {state.user_request}"
                ),
                max_tokens=300,
            )
            step.goal       = refined.get("goal",       step.goal)
            step.tool       = refined.get("tool",       step.tool)
            step.query      = refined.get("query",      step.query)
            step.source     = refined.get("source",     step.source)
            step.confidence = float(refined.get("confidence", step.confidence))
            print(f"    step {step.index}: {step.confidence:.2f} — {step.goal[:70]}")

    state.steps = steps
    scratch["plan"] = json.dumps(
        [{"index": s.index, "goal": s.goal, "query": s.query, "confidence": s.confidence}
         for s in steps],
        indent=2,
    )
    return state


# ---------------------------------------------------------------------------
# Stage 3 — Research
# ---------------------------------------------------------------------------

_RELEVANCE_SYSTEM = """\
You are checking if a NixOS search result is useful for a specific task.
Return JSON: {"relevant": true/false, "reason": "one sentence"}
"""


def _do_search(step: PlanStep) -> str:
    action_map = {"nix_search": "search", "nix_info": "info", "nix_versions": "search"}
    return run_mcp("nix", {
        "action": action_map.get(step.tool, "search"),
        "query":  step.query,
        "source": step.source,
        "limit":  5,
    })


def _stage_research(state: PipelineState) -> PipelineState:
    print("\n[pipeline] stage 3: research")
    cfg = PIPELINE_CONFIG

    for step in state.steps:
        print(f"  step {step.index}: {step.goal[:70]}")

        for attempt in range(cfg["research_max_retries"]):
            result = _do_search(step)

            verdict = _llm_json(
                system=_RELEVANCE_SYSTEM,
                user=f"Task: {step.goal}\n\nResult:\n{result[:800]}",
                max_tokens=128,
            )

            if verdict.get("relevant"):
                print(f"    attempt {attempt + 1}: relevant")
                break

            print(f"    attempt {attempt + 1}: not relevant — {verdict.get('reason', '')[:60]}")
            # Python refines the query — model doesn't touch this
            if attempt < cfg["research_max_retries"] - 1:
                step.query = f"{step.query} nixos"

        step.result = result
        for entity in state.entities:
            if entity.lower() in result.lower():
                state.facts[entity] = result[:500]

    scratch["facts"] = json.dumps(state.facts, indent=2)
    return state


# ---------------------------------------------------------------------------
# Stage 4 — Execute
# ---------------------------------------------------------------------------

_EXECUTE_SYSTEM = """\
You are completing ONE step of a NixOS configuration task.
You will be given the goal for this step, relevant facts, and prior output.

Generate ONLY the Nix configuration or answer for THIS step.
Do not plan future steps. Do not repeat prior output.
Use only the package and option names listed in the facts — do not invent names.
"""


def _stage_execute(state: PipelineState) -> PipelineState:
    print("\n[pipeline] stage 4: execute")
    outputs: list[str] = []

    for step in state.steps:
        print(f"  step {step.index}: {step.goal[:70]}")

        output = _llm(
            system=_EXECUTE_SYSTEM,
            user=(
                f"Step goal: {step.goal}\n\n"
                f"Facts:\n{json.dumps(state.facts, indent=2)}\n\n"
                f"Search result:\n{step.result[:600]}\n\n"
                f"Prior output:\n{chr(10).join(outputs[-2:]) if outputs else '(none)'}"
            ),
            max_tokens=600,
        )

        outputs.append(output)

    state.final_answer = "\n\n".join(outputs)
    return state


# ---------------------------------------------------------------------------
# Stage 5 — Verify
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """\
Extract all Nix package names and option paths from this text.
Return JSON: {"packages": [...], "options": [...]}
Only include names that appear in code blocks or as pkgs.X references.
If none, return empty lists.
"""

_FIX_SYSTEM = """\
Fix ONLY the invalid package and option names in this Nix configuration.
Do not change anything else. Replace each invalid name with the correct nixpkgs name.
"""


def _stage_verify(state: PipelineState) -> PipelineState:
    print("\n[pipeline] stage 5: verify")
    cfg = PIPELINE_CONFIG

    for attempt in range(cfg["verify_max_retries"]):
        extracted = _llm_json(
            system=_EXTRACT_SYSTEM,
            user=state.final_answer,
            max_tokens=256,
        )

        packages = extracted.get("packages", [])
        options  = extracted.get("options",  [])
        issues: list[str] = []

        for pkg in packages:
            result = run_mcp("nix", {"action": "info", "query": pkg,
                                      "source": "nixos", "type": "package"})
            if "not found" in result.lower() or "error" in result.lower():
                issues.append(f"package '{pkg}' does not exist in nixpkgs")
                print(f"  FAIL: {pkg}")
            else:
                print(f"  OK:   {pkg}")

        for opt in options:
            src = "home-manager" if opt.startswith(("programs.", "home.")) else "nixos"
            result = run_mcp("nix", {"action": "info", "query": opt, "source": src})
            if "not found" in result.lower() or "error" in result.lower():
                issues.append(f"option '{opt}' does not exist in {src}")
                print(f"  FAIL: {opt}")
            else:
                print(f"  OK:   {opt}")

        if not issues:
            print(f"  verified on attempt {attempt + 1}")
            break

        print(f"  {len(issues)} issue(s) on attempt {attempt + 1} — fixing")
        state.final_answer = _llm(
            system=_FIX_SYSTEM,
            user=(
                f"Configuration:\n{state.final_answer}\n\n"
                f"Invalid names:\n" + "\n".join(f"- {i}" for i in issues)
            ),
            max_tokens=800,
        )

    return state


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(user_request: str) -> str:
    """Run the full pipeline. Returns the final answer string."""
    scratch.clear()
    t0 = time.time()

    state = _stage_intake(user_request)
    state = _stage_plan(state)
    state = _stage_research(state)
    state = _stage_execute(state)
    state = _stage_verify(state)

    print(f"\n[pipeline] completed in {time.time() - t0:.1f}s")
    return state.final_answer