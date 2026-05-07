import os
import re
import textwrap

import requests
from qwen_agent.tools.base import BaseTool, register_tool
from ._base import parse_params, out


@register_tool("nix_research")
class NixResearchTool(BaseTool):
    description = (
        "Search the web for Nix information and iterate until confident. "
        "Use for: error messages, recent changes, unfamiliar options, anything the MCP tools don't cover. "
        "Returns a synthesised answer with sources."
    )
    parameters = [
        {"name": "question", "type": "string", "required": True,
         "description": "The specific question to research"},
        {"name": "context", "type": "string", "required": False,
         "description": "NixOS version, what you've already tried, relevant facts"},
        {"name": "max_iterations", "type": "integer", "required": False,
         "description": "Search-refine cycles allowed. Default: 3"},
    ]

    _SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
    _EVAL_SYSTEM = textwrap.dedent("""\
        You are evaluating search results for a NixOS question.
        Given the question and search snippets, decide:
        1. Is the answer clear enough to give a confident reply? (confident: true/false)
        2. If not, what refined query would find better results? (refined_query: string)
        3. Summarise what you know so far. (summary: string)

        Respond ONLY with valid JSON: {"confident": bool, "refined_query": str, "summary": str}
    """)

    def call(self, params: str | dict, **_) -> str:
        p = parse_params(params)
        question = p.get("question", "")
        context = p.get("context", "")
        max_iter = int(p.get("max_iterations", 3))

        brave_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if not brave_key:
            return self._ddg_fallback(question)

        query = question
        all_snippets: list[str] = []
        summary = ""
        i = 0

        for i in range(max_iter):
            try:
                resp = requests.get(
                    self._SEARCH_URL,
                    headers={"Accept": "application/json",
                             "Accept-Encoding": "gzip",
                             "X-Subscription-Token": brave_key},
                    params={"q": f"NixOS {query}", "count": 5, "text_decorations": False},
                    timeout=15,
                )
                results = resp.json().get("web", {}).get("results", [])
                snippets = [f"[{r['title']}] {r.get('description', '')}" for r in results[:5]]
                all_snippets.extend(snippets)
            except Exception as e:
                return out({"error": f"Search failed: {e}",
                            "next_step": "Try nix_search_tool instead."})

            if not anthropic_key:
                break

            try:
                eval_resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 400,
                        "system": self._EVAL_SYSTEM,
                        "messages": [{"role": "user", "content":
                            f"Question: {question}\nContext: {context}\n\nSnippets:\n" +
                            "\n".join(all_snippets[-10:])}],
                    },
                    timeout=20,
                )
                raw = eval_resp.json()["content"][0]["text"].strip()
                raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                eval_data = __import__("json").loads(raw)
                summary = eval_data.get("summary", "")
                if eval_data.get("confident"):
                    break
                query = eval_data.get("refined_query", query)
            except Exception:
                break

        return out({
            "question": question,
            "answer": summary or "See raw snippets below.",
            "sources": all_snippets[:8],
            "iterations": i + 1,
            "next_step": (
                "Write key facts to scratchpad (key='facts'), "
                "then continue to the next step in your plan."
            ),
        })

    def _ddg_fallback(self, question: str) -> str:
        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": f"NixOS {question}"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            snippets = re.findall(r'class="result__snippet">(.*?)</a>', resp.text)
            snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets[:6]]
        except Exception as e:
            snippets = [f"Search unavailable: {e}"]

        return out({
            "question": question,
            "answer": "See raw snippets (no Brave API key for confidence evaluation).",
            "sources": snippets,
            "next_step": (
                "Write key facts to scratchpad (key='facts'), "
                "then continue to the next step in your plan."
            ),
        })