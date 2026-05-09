# src/ollama_agent/router.py
from __future__ import annotations
from ollama_agent.classifier import classify
from ollama_agent.pipelines import create_module, edit_module, search, nix_check

def dispatch(user_message: str, repo_path: str, model_id: str, base_url: str = "http://localhost:11434", verbose: bool = False) -> str:

    intent = classify(user_message, model_id=model_id)
    job  = intent.get("job", "unknown")
    args = intent.get("args", {})

    match job:
        case "create_module":
            return create_module.run(repo_path=repo_path, model_id=model_id, base_url=base_url, **args)
        case "edit_module":
            return edit_module.run(repo_path=repo_path, model_id=model_id, base_url=base_url, **args)
        case "search":
            return search.run(**args)
        case "nix_check":
            return nix_check.run(repo_path=repo_path)
        case _:
            return f"Could not understand request: {args.get('reason', user_message)}"