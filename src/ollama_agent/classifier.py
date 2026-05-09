# src/ollama_agent/classifier.py
from __future__ import annotations
import json
from ollama_agent.models import OllamaModel

JOBS = ["create_module", "edit_module", "search", "nix_check", "unknown"]

SYSTEM_PROMPT = """\
You are a NixOS assistant router. Classify the user's request into exactly one job.
Respond ONLY with a JSON object — no prose, no markdown, no explanation.

Schema:
{
  "job": "<one of: create_module | edit_module | search | nix_check | unknown>",
  "args": { <job-specific fields> }
}

Args per job:
  create_module: { "name": str, "hint": "home-manager"|"nixos", "requests": [str] }
  edit_module:   { "name": str, "edits": [str] }   // edits = plain English descriptions
  search:        { "query": str, "sources": [str] } // sources from: nixos,nixpkgs,home-manager
  nix_check:     {}
  unknown:       { "reason": str }
"""

def classify(user_message: str, model_id: str = "qwen2.5-coder:7b") -> dict:
    model = OllamaModel(model_id=model_id, temperature=0.0, max_new_tokens=256)
    response = model([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ])
    raw = response.content  # smolagents OpenAIModel returns a ChatMessage
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # strip markdown fences if model ignored instructions
        cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(cleaned)