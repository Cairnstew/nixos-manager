"""
pipeline.py — research-first planning pipeline for NixOS requests.

The 7B model is called for exactly THREE narrow, tightly-scoped tasks:
  1. Classify intent and extract entities  (intake)
  2. Propose research steps as JSON        (plan)
  3. Score search result relevance         (research)

The Claude API (claude-sonnet) is used for ONE task:
  4. Synthesise all research into a structured JSON plan document
     that the next LLM stage can consume directly.

Python controls all sequencing, looping, and tool calls.

KEY DESIGN RULES
- The 7B model NEVER sees the user's config files.  Config is reference-only
  context, passed exclusively to the Claude synthesis step.
- The 7B is always given a single, concrete JSON-only task.  It is never
  asked to "analyse", "review", or "improve" anything.
- The output plan is a JSON document, not human prose, so downstream
  code can parse and act on it without another LLM round-trip.
"""

from __future__ import annotations

import json
import os
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config.settings import LLM_CONFIG, PIPELINE_CONFIG
from .config.context import get_config_context
from .tools._base import run_mcp
from .tools.scratchpad import _STORE as scratch


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _llm(system: str, user: str, max_tokens: int = 512) -> str:
    """Single local model call via OpenAI-compat endpoint. Returns plain text."""
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
    """
    Local model call that MUST return valid JSON.

    Strategy (each attempt is more aggressive than the last):
      1. Use Ollama's native JSON mode via the /api/chat endpoint with
         `format: "json"` — this enables constrained token sampling so
         the model physically cannot output non-JSON characters.
      2. If that endpoint isn't available (non-Ollama server), fall back
         to the OpenAI-compat endpoint with a stripped-down prompt and
         aggressive fence removal.
      3. Last resort: ultra-minimal prompt with only the schema, no context.
    """
    _ENFORCE = (
        "\nRespond with ONLY a valid JSON object. "
        "No explanation. No markdown. No code fences. Start with { and end with }."
    )

    def _clean(raw: str) -> str:
        """Strip everything outside the outermost { }."""
        raw = raw.strip()
        # Remove Gemma control tokens
        for token in ["<start_of_turn>", "<end_of_turn>", "<bos>", "<eos>"]:
            raw = raw.replace(token, "")
        raw = raw.strip()
        # Remove markdown fences
        raw = raw.removeprefix("```json").removeprefix("```")
        raw = raw.removesuffix("```").strip()
        # Find first { and last }
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return raw[start:end + 1]
        return raw

    # Attempt 1: Ollama native /api/chat with format="json"
    # This is the most reliable — constrained decoding at the sampler level
    ollama_base = LLM_CONFIG["model_server"].rstrip("/")
    # /v1 is the OpenAI compat prefix; strip it to get the native base
    native_base = ollama_base.removesuffix("/v1")
    try:
        resp = requests.post(
            f"{native_base}/api/chat",
            json={
                "model": LLM_CONFIG["model"],
                "format": "json",
                "stream": False,
                "options": {"num_predict": max_tokens},
                "messages": [
                    {"role": "system", "content": system + _ENFORCE},
                    {"role": "user",   "content": user},
                ],
            },
            timeout=120,
        )
        if resp.status_code == 200:
            raw = resp.json().get("message", {}).get("content", "").strip()
            raw = _clean(raw)
            parsed = json.loads(raw)
            return parsed
    except (requests.RequestException, json.JSONDecodeError, KeyError):
        pass  # fall through to attempt 2

    # Attempt 2: OpenAI-compat endpoint, stripped prompt, fence removal
    for attempt in range(2):
        prompt = system + _ENFORCE if attempt == 0 else _ENFORCE
        try:
            resp = requests.post(
                f"{ollama_base}/chat/completions",
                headers={"Authorization": f"Bearer {LLM_CONFIG['api_key']}"},
                json={
                    "model": LLM_CONFIG["model"],
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user",   "content": user},
                    ],
                },
                timeout=120,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            raw = _clean(raw)
            return json.loads(raw)
        except json.JSONDecodeError:
            print(f"  [pipeline] JSON parse failed (attempt {attempt + 1}), raw={raw[:200]}")
            continue
        except Exception as e:
            print(f"  [pipeline] LLM call failed: {e}")
            break

    return {}


def _claude(system: str, user: str, max_tokens: int = 4096) -> str:
    """Call the Anthropic Claude API. Falls back to local LLM if key not set."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  [pipeline] ANTHROPIC_API_KEY not set — using local LLM for synthesis")
        return _llm(system, user, max_tokens=min(max_tokens, 2048))

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ResearchFinding:
    source_tool: str
    source_name: str
    query: str
    raw_result: str
    relevance_reason: str
    key_facts: list[str]
    confidence: float


@dataclass
class PlanStep:
    index: int
    goal: str
    tool: str
    query: str
    source: str = "nixos"
    confidence: float = 0.0
    finding: ResearchFinding | None = None


@dataclass
class PipelineState:
    user_request: str
    intent: str = ""
    entities: list[str] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    findings: list[ResearchFinding] = field(default_factory=list)
    web_findings: list[dict] = field(default_factory=list)
    # Loaded once, passed ONLY to Claude synthesis — never to the 7B
    config_context: str = ""
    plan_document: str = ""


# ---------------------------------------------------------------------------
# Stage 1 — Intake  (7B: classify intent, extract entities)
# ---------------------------------------------------------------------------

_INTAKE_SYSTEM = """\
TASK: Extract structured metadata from a NixOS user request.

Output schema (JSON only):
{
  "intent": "configure" | "search" | "debug" | "version" | "explain" | "compare",
  "entities": ["list", "of", "package names", "option paths", "service names"],
  "complexity": "simple" | "moderate" | "complex",
  "search_sources": ["nixos", "home-manager", "wiki", "noogle", "darwin", "flakes"]
}

Rules:
- intent: pick exactly one value
- entities: only things explicitly mentioned in the request
- search_sources: list the 1-3 most relevant sources for this specific request
- complexity: simple = single package/option; moderate = multi-step; complex = involves multiple subsystems
"""


def _stage_intake(request: str) -> PipelineState:
    print("\n[pipeline] stage 1: intake")

    result = _llm_json(system=_INTAKE_SYSTEM, user=f"Request: {request}", max_tokens=256)

    state = PipelineState(user_request=request)
    state.intent = result.get("intent", "configure")
    state.entities = result.get("entities", [])

    scratch["intent"] = state.intent
    scratch["entities"] = json.dumps(state.entities)
    scratch["complexity"] = result.get("complexity", "moderate")
    scratch["search_sources"] = json.dumps(result.get("search_sources", ["nixos"]))

    # Load config context now, stored on state — NOT passed to 7B
    print("  reading config repo...")
    state.config_context = get_config_context()
    has_repo = "not found" not in state.config_context
    print(f"  config context: {'loaded' if has_repo else 'not found (set NIXOS_REPO_PATH)'}")
    print(f"  intent={state.intent}  entities={state.entities}  complexity={result.get('complexity')}")
    return state


# ---------------------------------------------------------------------------
# Stage 2 — Plan  (7B: generate research step list as JSON)
# ---------------------------------------------------------------------------

_PLAN_SYSTEM = """\
TASK: Generate a list of NixOS research steps for a given user request.

You will receive: intent, entities, complexity, preferred sources.
You must output ONLY a JSON object with a "steps" array.

Output schema:
{
  "steps": [
    {
      "goal": "one sentence — what fact this step confirms",
      "tool": "nix_search" | "nix_info" | "nix_versions" | "nix_research" | "wiki_search",
      "query": "exact search string",
      "source": "nixos" | "home-manager" | "darwin" | "wiki" | "noogle" | "flakes" | "nixhub" | "nix-dev",
      "confidence": 0.0-1.0
    }
  ]
}

Rules:
- Each step must gather ONE specific piece of information
- Do NOT describe the user config or suggest changes to it
- Do NOT analyse, review, or summarise anything — only generate search steps
- For each entity: include at minimum one "nix_search" step AND one "nix_info" step
- For home-manager options: always include a step with source="home-manager"
- For wiki/guides: use tool="wiki_search" source="wiki"
- For web/recent info: use tool="nix_research"
- confidence: 0.9 if you are certain this step is needed; 0.6 if unsure
"""

_REFINE_SYSTEM = """\
TASK: Rewrite a low-confidence NixOS research step to be more specific.

You will receive the original step JSON and the user request.
Output ONLY the corrected step as JSON with the same fields:
{goal, tool, query, source, confidence}

The rewritten step must have higher confidence than the original.
Do NOT change the task to config analysis — keep it as a search/lookup step.
"""


def _stage_plan(state: PipelineState) -> PipelineState:
    print("\n[pipeline] stage 2: plan")
    cfg = PIPELINE_CONFIG

    raw = _llm_json(
        system=_PLAN_SYSTEM,
        user=(
            f"intent: {state.intent}\n"
            f"entities: {', '.join(state.entities)}\n"
            f"complexity: {scratch.get('complexity', 'moderate')}\n"
            f"preferred_sources: {scratch.get('search_sources', '[\"nixos\"]')}\n"
            f"user_request: {state.user_request}"
        ),
        max_tokens=1200,
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

    if not steps:
        print("  [pipeline] WARNING: 7B returned 0 steps — check JSON output above")

    for iteration in range(cfg["plan_max_iterations"]):
        weak = [s for s in steps if s.confidence < cfg["confidence_threshold"]]
        if not weak:
            print(f"  plan confident after {iteration} refinement(s), {len(steps)} steps total")
            break
        print(f"  iteration {iteration + 1}: refining {len(weak)} weak step(s)")
        for step in weak:
            refined = _llm_json(
                system=_REFINE_SYSTEM,
                user=(
                    f"original_step: {json.dumps({'goal': step.goal, 'tool': step.tool, 'query': step.query, 'source': step.source})}\n"
                    f"confidence_was: {step.confidence}\n"
                    f"user_request: {state.user_request}"
                ),
                max_tokens=256,
            )
            step.goal       = refined.get("goal",       step.goal)
            step.tool       = refined.get("tool",       step.tool)
            step.query      = refined.get("query",      step.query)
            step.source     = refined.get("source",     step.source)
            step.confidence = float(refined.get("confidence", step.confidence))
            print(f"    step {step.index}: conf={step.confidence:.2f} — {step.goal[:70]}")

    state.steps = steps
    scratch["plan"] = json.dumps(
        [{"index": s.index, "goal": s.goal, "query": s.query, "confidence": s.confidence}
         for s in steps],
        indent=2,
    )
    return state


# ---------------------------------------------------------------------------
# Stage 3 — Research  (7B: relevance scoring only)
# ---------------------------------------------------------------------------

_RELEVANCE_SYSTEM = """\
TASK: Decide if a NixOS search result is relevant to a specific research goal.

Output schema (JSON only):
{
  "relevant": true | false,
  "reason": "one sentence",
  "key_facts": ["exact option path or package attr", "version number", "caveat"]
}

Rules:
- relevant=true only if the result directly answers the goal
- key_facts: extract ONLY concrete strings (option paths, package attrs, version numbers, caveats)
- Do NOT summarise prose — only extract machine-usable facts
"""

_WEB_EVAL_SYSTEM = """\
TASK: Extract concrete NixOS facts from web search snippets.

Output schema (JSON only):
{
  "confident": true | false,
  "refined_query": "better query string if not confident",
  "key_facts": ["concrete fact with source", ...],
  "caveats": ["version-specific note or known issue", ...],
  "summary": "2-3 sentence factual synthesis"
}

Rules:
- key_facts: only concrete, actionable items (option names, package names, commands, URLs)
- caveats: only real issues found in the snippets — do not invent
- confident=true only if the snippets clearly answer the question
"""


def _do_mcp_search(step: PlanStep) -> str:
    action_map = {
        "nix_search":   "search",
        "nix_info":     "info",
        "nix_versions": "search",
        "wiki_search":  "search",
    }
    source = "wiki" if step.tool == "wiki_search" else step.source
    return run_mcp("nix", {
        "action": action_map.get(step.tool, "search"),
        "query":  step.query,
        "source": source,
        "limit":  8,
    })


def _do_web_research(step: PlanStep, brave_key: str) -> dict | None:
    import re
    query = f"NixOS {step.query}"
    snippets: list[str] = []

    if brave_key:
        try:
            resp = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": brave_key,
                },
                params={"q": query, "count": 8, "text_decorations": False},
                timeout=15,
            )
            results = resp.json().get("web", {}).get("results", [])
            snippets = [
                f"[{r['title']}] ({r.get('url', '')}) {r.get('description', '')}"
                for r in results[:8]
            ]
        except Exception as e:
            print(f"    [web] Brave failed: {e}")

    if not snippets:
        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            raw_snippets = re.findall(r'class="result__snippet">(.*?)</a>', resp.text)
            snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in raw_snippets[:8]]
        except Exception as e:
            print(f"    [web] DDG failed: {e}")
            return None

    if not snippets:
        return None

    # Use Claude for web synthesis (much better than 7B at extraction)
    try:
        raw = _claude(
            system=_WEB_EVAL_SYSTEM,
            user=(
                f"goal: {step.goal}\n"
                f"query: {step.query}\n\n"
                f"snippets:\n" + "\n".join(snippets[:10])
            ),
            max_tokens=600,
        )
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
        data["raw_snippets"] = snippets
        return data
    except Exception as e:
        print(f"    [web] synthesis failed: {e}")
        return {"key_facts": snippets[:5], "caveats": [], "summary": "(raw snippets)", "raw_snippets": snippets}


def _stage_research(state: PipelineState) -> PipelineState:
    print("\n[pipeline] stage 3: research")
    cfg = PIPELINE_CONFIG
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")

    for step in state.steps:
        print(f"  step {step.index}: [{step.tool}/{step.source}] {step.goal[:70]}")

        if step.tool == "nix_research":
            web = _do_web_research(step, brave_key)
            if web:
                state.web_findings.append({
                    "step_index": step.index,
                    "goal": step.goal,
                    "query": step.query,
                    **web,
                })
                finding = ResearchFinding(
                    source_tool="web",
                    source_name="web",
                    query=step.query,
                    raw_result=web.get("summary", "") + "\n" + "\n".join(web.get("key_facts", [])),
                    relevance_reason="web research",
                    key_facts=web.get("key_facts", []),
                    confidence=0.9 if web.get("confident") else 0.6,
                )
                step.finding = finding
                state.findings.append(finding)
                print(f"    web: {len(web.get('key_facts', []))} facts")
            continue

        result = ""
        for attempt in range(cfg["research_max_retries"]):
            result = _do_mcp_search(step)

            verdict = _llm_json(
                system=_RELEVANCE_SYSTEM,
                user=f"goal: {step.goal}\n\nresult:\n{result[:1500]}",
                max_tokens=200,
            )

            if verdict.get("relevant"):
                facts = verdict.get("key_facts", [])
                print(f"    attempt {attempt + 1}: relevant — {len(facts)} facts — {verdict.get('reason', '')[:50]}")
                finding = ResearchFinding(
                    source_tool=step.tool,
                    source_name=step.source,
                    query=step.query,
                    raw_result=result[:2000],
                    relevance_reason=verdict.get("reason", ""),
                    key_facts=facts,
                    confidence=step.confidence,
                )
                for fact in facts:
                    state.facts[fact] = result[:300]
                step.finding = finding
                state.findings.append(finding)
                break

            print(f"    attempt {attempt + 1}: not relevant — {verdict.get('reason', '')[:60]}")
            if attempt < cfg["research_max_retries"] - 1:
                step.query = f"{step.query} nixos configuration"

        for entity in state.entities:
            if entity.lower() in result.lower() and entity not in state.facts:
                state.facts[entity] = result[:500]

    scratch["facts"] = json.dumps(state.facts, indent=2)
    print(f"  research complete: {len(state.findings)} findings, {len(state.facts)} facts")
    return state


# ---------------------------------------------------------------------------
# Stage 4 — Synthesise  (Claude: produce structured JSON plan for next stage)
# ---------------------------------------------------------------------------

_SYNTHESISE_SYSTEM = """\
You are a NixOS expert producing a structured implementation plan.
This plan will be consumed by another LLM or Python code — not read by a human.
Output ONLY a valid JSON object matching the schema below. No prose, no markdown.

Output schema:
{
  "title": "short descriptive title",
  "intent": "configure | search | debug | version | explain | compare",
  "entities": ["confirmed entity names"],

  "existing_config_notes": [
    "one observation per item about what already exists in the user config relevant to this task",
    "e.g. 'programs.firefox.enable already set in modules/home/firefox/default.nix line 4'"
  ],

  "prerequisites": [
    {"item": "name or path", "reason": "why it is needed", "confirmed": true | false}
  ],

  "steps": [
    {
      "index": 0,
      "action": "short imperative verb phrase",
      "detail": "full explanation of what to do and why",
      "option_paths": ["programs.firefox.enable", "programs.firefox.profiles"],
      "package_attrs": ["pkgs.firefox"],
      "source": "nixos | home-manager | wiki | web",
      "confirmed": true | false,
      "caveats": ["any caveats specific to this step"]
    }
  ],

  "verified_facts": [
    {"fact": "concrete string", "source": "nixos | home-manager | wiki | web"}
  ],

  "caveats": ["global caveats that apply to the whole plan"],

  "open_questions": [
    {"question": "what needs manual checking", "where_to_look": "specific source or file"}
  ],

  "references": ["source name or URL"]
}

Rules:
- Do NOT invent option paths or package attrs — only use what appears in the research findings
- confirmed=true only for items directly verified by a research finding
- existing_config_notes: reference the user config (file paths, line hints) where relevant;
  do NOT suggest changes to existing config — this is for the code-gen stage to decide
- steps must be sequential and concrete — each one maps to exactly one config change or verification
- If research found nothing for a step, still include it with confirmed=false
"""


def _stage_synthesise(state: PipelineState) -> PipelineState:
    print("\n[pipeline] stage 4: synthesise plan (Claude)")

    # Pack all findings into a compact research block
    findings_block = ""
    for i, f in enumerate(state.findings):
        facts_str = "\n".join(f"  - {fact}" for fact in f.key_facts)
        findings_block += (
            f"\nFINDING {i+1} [{f.source_tool}/{f.source_name}] query='{f.query}'\n"
            f"relevance: {f.relevance_reason}\n"
            f"key_facts:\n{facts_str or '  (none)'}\n"
            f"raw (truncated): {textwrap.shorten(f.raw_result, 500, placeholder='...')}\n"
        )

    web_block = ""
    for wf in state.web_findings:
        facts_str = "\n".join(f"  - {fact}" for fact in wf.get("key_facts", []))
        caveats_str = "\n".join(f"  - {c}" for c in wf.get("caveats", []))
        web_block += (
            f"\nWEB [{wf['query']}]\n"
            f"summary: {wf.get('summary', '(none)')}\n"
            f"key_facts:\n{facts_str or '  (none)'}\n"
            f"caveats:\n{caveats_str or '  (none)'}\n"
        )

    user_prompt = (
        f"user_request: {state.user_request}\n"
        f"intent: {state.intent}\n"
        f"entities: {json.dumps(state.entities)}\n\n"
        f"=== USER CONFIG (reference only — do NOT suggest changes) ===\n"
        f"{state.config_context}\n\n"
        f"=== MCP RESEARCH FINDINGS ===\n{findings_block or '(none)'}\n\n"
        f"=== WEB RESEARCH FINDINGS ===\n{web_block or '(none)'}\n\n"
        f"=== CONFIRMED FACTS ===\n{json.dumps(state.facts, indent=2)}\n"
    )

    raw = _claude(system=_SYNTHESISE_SYSTEM, user=user_prompt, max_tokens=4096)
    # Strip any accidental markdown fences
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    idx = raw.find("{")
    if idx > 0:
        raw = raw[idx:]

    try:
        state.plan_document = raw  # Store raw JSON string
        # Validate it parses
        parsed = json.loads(raw)
        step_count = len(parsed.get("steps", []))
        fact_count = len(parsed.get("verified_facts", []))
        print(f"  plan: {step_count} steps, {fact_count} verified facts")
    except json.JSONDecodeError as e:
        print(f"  [pipeline] WARNING: plan JSON invalid ({e}) — storing raw anyway")
        state.plan_document = raw

    return state


# ---------------------------------------------------------------------------
# Stage 5 — Write plan to file
# ---------------------------------------------------------------------------

def _stage_write_plan(state: PipelineState, output_dir: str | None = None) -> str:
    print("\n[pipeline] stage 5: writing plan to file")

    if output_dir is None:
        output_dir = os.environ.get("NIXMGR_PLAN_DIR", "/tmp/nixos-plans")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    slug = "".join(
        c if c.isalnum() or c == "-" else "-"
        for c in state.user_request[:40].lower()
    ).strip("-")
    ts_short = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"plan-{slug}-{ts_short}.json"
    output_path = str(Path(output_dir) / filename)

    # Wrap the plan JSON with pipeline metadata in the output file
    try:
        plan_data = json.loads(state.plan_document)
    except Exception:
        plan_data = {"raw": state.plan_document}

    output = {
        "_pipeline_meta": {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "user_request": state.user_request,
            "intent": state.intent,
            "entities": state.entities,
            "research_steps": len(state.steps),
            "relevant_findings": len(state.findings),
            "web_research_rounds": len(state.web_findings),
            "step_log": [
                {
                    "index": s.index,
                    "tool": s.tool,
                    "source": s.source,
                    "confidence": round(s.confidence, 2),
                    "goal": s.goal,
                    "found": s.finding is not None,
                }
                for s in state.steps
            ],
        },
        "plan": plan_data,
    }

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    scratch["plan_document_path"] = output_path
    print(f"  plan written -> {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(user_request: str, plan_output_dir: str | None = None) -> str:
    """
    Run the full research-and-plan pipeline.

    Returns the path to the generated plan document (.json file).

    The JSON file contains:
      _pipeline_meta  — provenance, step log, finding counts
      plan            — structured plan ready for a code-generation LLM:
                        steps, option_paths, package_attrs, verified_facts,
                        caveats, open_questions, existing_config_notes

    No Nix code is generated here.
    """
    scratch.clear()
    t0 = time.time()

    state = _stage_intake(user_request)
    state = _stage_plan(state)
    state = _stage_research(state)
    state = _stage_synthesise(state)
    plan_path = _stage_write_plan(state, plan_output_dir)

    print(f"\n[pipeline] done in {time.time() - t0:.1f}s — {plan_path}")
    return plan_path