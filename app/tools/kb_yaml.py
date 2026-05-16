"""
YAML Knowledge Base loader and RAG-lite search.

Covers all agent-specific and shared KBs in app/tools/data/kb/:
  customer/  — dietary_restrictions, event_profiles, interaction_history
  menu/      — recipe_library, cuisine_trends, portion_yield
  pricing/   — market_benchmarks, historical_quotes, cost_of_goods
  inventory/ — supplier_catalog, spoilage_waste, procurement_sop
  logistics/ — venue_profiles, staff_scheduling, equipment_inventory
  shared/    — event_postmortems, sop_compliance, seasonal_availability,
               competitor_pricing, social_trends, carbon_footprint, guest_feedback

Usage:
    from app.tools.kb_yaml import YAMLKBSearch
    kb = YAMLKBSearch()
    results = kb.search("menu/cuisine_trends", "halal wedding trending dishes", top_k=3)
    scoped  = kb.search_scope("shared", "outdoor event risk lessons")
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # pyyaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_KB_DIR = Path(__file__).resolve().parent / "data" / "kb"


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z]+", str(text).lower())


def _score_item(query_tokens: List[str], item: Any) -> float:
    """Keyword overlap score between query tokens and flattened item text."""
    if not query_tokens:
        return 0.5
    doc_tokens = set(_tokenize(str(item)))
    return sum(1.0 for t in query_tokens if t in doc_tokens) / len(query_tokens)


class YAMLKBSearch:
    """
    Loads all YAML knowledge bases at startup and provides keyword-overlap search.

    KBs are indexed by path relative to the kb/ directory, using forward slashes:
        'customer/dietary_restrictions'
        'shared/event_postmortems'

    Each YAML file is expected to have one or more top-level list keys that
    hold the searchable documents (e.g. profiles, templates, recipes, trends…).
    """

    def __init__(self) -> None:
        self._kbs: Dict[str, Any] = {}
        if not _YAML_AVAILABLE:
            return
        self._load_all()

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        if not _KB_DIR.exists():
            return
        for path in sorted(_KB_DIR.rglob("*.yaml")):
            key = path.relative_to(_KB_DIR).with_suffix("").as_posix()
            try:
                content = yaml.safe_load(path.read_text(encoding="utf-8"))
                self._kbs[key] = content or {}
            except Exception:
                self._kbs[key] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def available_kbs(self) -> List[str]:
        """Return sorted list of all loaded KB keys."""
        return sorted(self._kbs.keys())

    def get(self, kb_key: str) -> Any:
        """Return the full parsed content of a KB by key."""
        return self._kbs.get(kb_key, {})

    def search(
        self,
        kb_key: str,
        query: str,
        collection_key: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Any]:
        """
        Search a list collection within a KB and return top-k items by keyword score.

        Args:
            kb_key:         KB identifier, e.g. 'menu/cuisine_trends'.
            query:          Free-text search query.
            collection_key: Explicit key of the list inside the KB root.
                            If None, the first list found at root level is used.
            top_k:          Maximum number of results to return.
        """
        # PLATFORM PLACEHOLDER: hybrid RAG via Azure AI Search (no-op until index wired)
        try:
            from app.platform.config import use_azure_ai_search

            if use_azure_ai_search():
                from app.platform.search import AzureAISearchKBPlaceholder

                AzureAISearchKBPlaceholder().search(query, kb_path=kb_key, top_k=top_k)
        except Exception:
            pass

        kb = self._kbs.get(kb_key, {})
        if not isinstance(kb, dict):
            return []

        items: List[Any] = []
        if collection_key:
            raw = kb.get(collection_key, [])
            items = raw if isinstance(raw, list) else []
        else:
            # Auto-detect: use the first top-level list in the KB
            for val in kb.values():
                if isinstance(val, list) and val:
                    items = val
                    break

        if not items:
            return []

        if not query.strip():
            return items[:top_k]

        q_tokens = _tokenize(query)
        scored = [(_score_item(q_tokens, item), item) for item in items]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def search_scope(
        self,
        scope: str,
        query: str,
        top_k: int = 3,
    ) -> Dict[str, List[Any]]:
        """
        Search all KBs within an agent scope (subfolder prefix) in one call.

        Args:
            scope:  Agent category prefix, e.g. 'customer', 'menu', 'shared'.
            query:  Free-text search query.
            top_k:  Results per KB.

        Returns:
            Dict mapping short KB name → list of top-k matching items.
            Only KBs with at least one hit are included.
        """
        prefix = scope.rstrip("/") + "/"
        results: Dict[str, List[Any]] = {}
        for key in self._kbs:
            if key.startswith(prefix):
                kb_name = key[len(prefix):]
                hits = self.search(key, query, top_k=top_k)
                if hits:
                    results[kb_name] = hits
        return results

    def search_multi(
        self,
        kb_keys: List[str],
        query: str,
        top_k: int = 3,
    ) -> Dict[str, List[Any]]:
        """
        Search multiple specific KB keys in one call.

        Returns:
            Dict mapping KB key → list of top-k matching items.
        """
        results: Dict[str, List[Any]] = {}
        for key in kb_keys:
            hits = self.search(key, query, top_k=top_k)
            if hits:
                results[key] = hits
        return results

    def format_kb_sources(
        self,
        results: Dict[str, List[Any]],
        max_per_kb: int = 2,
    ) -> List[str]:
        """
        Convert search results dict into a flat list of short source strings
        suitable for inclusion in an agent's kb_sources field.

        Each string is: 'kb_key → <name or id field> (<type>)'
        """
        sources: List[str] = []
        for kb_key, items in results.items():
            for item in items[:max_per_kb]:
                if not isinstance(item, dict):
                    sources.append(f"{kb_key} -> {str(item)[:80]}")
                    continue
                # Try common identifier fields in order of preference
                label = (
                    item.get("name")
                    or item.get("title")
                    or item.get("trend_id")
                    or item.get("rule_id")
                    or item.get("sop_id")
                    or item.get("reg_id")
                    or item.get("log_id")
                    or item.get("postmortem_id")
                    or item.get("quote_id")
                    or item.get("benchmark_id")
                    or item.get("feedback_id")
                    or item.get("venue_id")
                    or item.get("role_id")
                    or item.get("equipment_id")
                    or item.get("supplier_id")
                    or item.get("competitor_id")
                    or item.get("ingredient")
                    or item.get("event_type")
                    or str(item)[:60]
                )
                sources.append(f"{kb_key} -> {label}")
        return sources
