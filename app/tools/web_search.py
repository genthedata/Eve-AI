"""
Lightweight web search using the DuckDuckGo Instant Answer API.
No API key required. Returns plain-text snippets suitable for LLM injection.
"""

from __future__ import annotations

from typing import List

import requests


def search_event_ideas(query: str, max_results: int = 4) -> List[str]:
    """
    Search DuckDuckGo for event / catering ideas.
    Returns a list of text snippets (may be empty on failure).
    """
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
                "t": "cater_ai",
            },
            timeout=8,
            headers={"User-Agent": "CaterAI/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        results: List[str] = []

        abstract = data.get("AbstractText", "").strip()
        if abstract:
            results.append(abstract)

        for topic in data.get("RelatedTopics", []):
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(topic["Text"].strip())
            elif isinstance(topic, dict):
                for sub in topic.get("Topics", []):
                    if isinstance(sub, dict) and sub.get("Text"):
                        results.append(sub["Text"].strip())
            if len(results) >= max_results:
                break

        return [r for r in results if r][:max_results]
    except Exception:
        return []


def format_search_context(query: str, event_type: str = "") -> str:
    """
    Return enriched context for LLM injection.
    Tries DuckDuckGo first; falls back to local KB recommendations.
    """
    snippets = search_event_ideas(query)
    parts: List[str] = []

    if snippets:
        parts.append(f"[Web search: '{query}']")
        parts.extend(f"  • {s}" for s in snippets)

    # Always include relevant KB menu suggestions as additional context
    kb_ctx = _kb_context(event_type or query)
    if kb_ctx:
        parts.append(f"[Local knowledge base suggestions]")
        parts.extend(f"  • {item}" for item in kb_ctx)

    return "\n".join(parts) if parts else ""


def _kb_context(hint: str, top_k: int = 5) -> List[str]:
    """Pull top KB dish suggestions relevant to the hint."""
    try:
        from app.tools.kb_search import KBSearch
        kb = KBSearch()
        dishes = kb.search_recipes(query=hint, top_k=top_k)
        return [
            f"{d['name']} ({d['cuisine']}, {', '.join(d.get('tags', [])[:3])})"
            for d in dishes
        ]
    except Exception:
        return []
