from __future__ import annotations
from searchix import SearchixClient, SearchixError

def run(query: str, sources: list[str] | None = None, **_) -> str:
    client = SearchixClient()
    try:
        results = client.search(query, sources=sources, limit=20)
    except SearchixError as e:
        return f"Search error: {e}"
    if not results:
        return f"No results for '{query}'"
    lines = [f"{r.attribute}  —  {r.description[:80]}" for r in results]
    return "\n".join(lines)