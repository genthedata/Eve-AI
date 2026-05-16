"""
RAG-lite knowledge base search.
Uses keyword / tag overlap scoring — no external embedding deps required.

PLATFORM: When USE_AZURE_AI_SEARCH=true, hybrid retrieval is stubbed in
app.platform.search.AzureAISearchKBPlaceholder (YAML remains authoritative until indexed).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_json(name: str) -> Any:
    return json.loads((_DATA_DIR / name).read_text(encoding="utf-8"))


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z]+", text.lower())


def _score(query_tokens: List[str], doc_tokens: List[str]) -> float:
    doc_set = set(doc_tokens)
    return sum(1.0 for t in query_tokens if t in doc_set) / max(len(query_tokens), 1)


class KBSearch:
    """
    Retrieval layer over recipes.json and suppliers.json.
    Scores documents by token overlap against a query string or tag list.
    """

    def __init__(self) -> None:
        data = _load_json("recipes.json")
        self._dishes: List[Dict[str, Any]] = data.get("dishes", [])
        self._event_prefs: Dict[str, Any] = data.get("event_type_recommendations", {})
        self._portion_mult: Dict[str, float] = data.get("portion_multipliers", {})
        supplier_data = _load_json("suppliers.json")
        self._suppliers: List[Dict[str, Any]] = supplier_data.get("suppliers", [])

    # ── Recipe search ────────────────────────────────────────────────────────

    def search_recipes(
        self,
        query: str = "",
        required_tags: Optional[List[str]] = None,
        excluded_tags: Optional[List[str]] = None,
        event_type: str = "default",
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Return the top-k dishes matching the query and tag filters.
        required_tags: ALL must be present; excluded_tags: NONE must be present.
        """
        required = set(t.lower() for t in (required_tags or []))
        excluded = set(t.lower() for t in (excluded_tags or []))
        q_tokens = _tokenize(query)

        prefs = self._event_prefs.get(event_type.lower(), self._event_prefs.get("default", {}))
        preferred_cuisines = set(c.lower() for c in prefs.get("preferred_cuisines", []))

        results = []
        for dish in self._dishes:
            tags = set(dish.get("tags", []))
            if required and not required.issubset(tags):
                continue
            if excluded and excluded.intersection(tags):
                continue

            doc_tokens = _tokenize(
                dish["name"] + " " + dish.get("cuisine", "") + " " + " ".join(tags)
            )
            score = _score(q_tokens, doc_tokens) if q_tokens else 0.5
            if dish.get("cuisine", "") in preferred_cuisines:
                score += 0.3
            results.append((score, dish))

        results.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in results[:top_k]]

    def build_menu_from_kb(
        self,
        guest_count: int,
        dietary_constraints: List[str],
        event_type: str = "default",
        service_style: str = "buffet",
    ) -> Dict[str, Any]:
        """
        Build a menu using KB retrieval with dietary tag filtering.
        Returns menu_items list, portions dict, and kb_sources for traceability.
        """
        constraints_lower = [c.lower() for c in dietary_constraints]

        required_tags: List[str] = []
        excluded_tags: List[str] = []

        if "vegetarian" in constraints_lower or "vegan" in constraints_lower:
            required_tags.append("vegetarian")
        if "vegan" in constraints_lower:
            required_tags.append("vegan")
        if "halal" in constraints_lower or "muslim" in constraints_lower:
            required_tags.append("halal")
        if "no_nuts" in constraints_lower or "non halal food" not in constraints_lower:
            if "nuts" in " ".join(constraints_lower) or "no_nuts" in constraints_lower:
                excluded_tags.append("nuts")
        if "gluten" in " ".join(constraints_lower):
            required_tags.append("gluten_free")
        if "non halal" in " ".join(constraints_lower):
            if "halal" in required_tags:
                required_tags.remove("halal")

        dishes = self.search_recipes(
            query=event_type,
            required_tags=required_tags,
            excluded_tags=excluded_tags,
            event_type=event_type,
            top_k=7,
        )

        if not dishes:
            dishes = self.search_recipes(
                query="",
                required_tags=[],
                excluded_tags=excluded_tags,
                event_type=event_type,
                top_k=7,
            )

        menu_items = [d["name"] for d in dishes]

        mult = self._portion_mult
        portions = {
            "mains": int(guest_count * float(mult.get("mains", 1.0))),
            "sides": int(guest_count * float(mult.get("sides", 1.2))),
            "desserts": int(guest_count * float(mult.get("desserts", 0.8))),
        }

        kb_sources = [
            f"{d['name']} ({d['cuisine']}, tags: {', '.join(d.get('tags', []))})"
            for d in dishes
        ]

        return {
            "menu_items": menu_items,
            "portions": portions,
            "kb_sources": kb_sources,
            "dietary_filters_applied": {"required": required_tags, "excluded": excluded_tags},
        }

    # ── Supplier search ───────────────────────────────────────────────────────

    def search_suppliers(
        self,
        item: str,
        require_halal: bool = False,
        region: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return suppliers that stock the given item, optionally filtered by halal/region.
        """
        item_lower = item.lower().replace("_", " ")
        results = []
        for sup in self._suppliers:
            sup_items = [s.lower().replace("_", " ") for s in sup.get("items", [])]
            if not any(item_lower in s or s in item_lower for s in sup_items):
                continue
            if require_halal and not sup.get("halal_certified"):
                continue
            if region and region.lower() not in sup.get("region", "").lower():
                continue
            results.append(sup)
        results.sort(key=lambda s: s.get("reliability_score", 0), reverse=True)
        return results

    def get_procurement_suppliers(
        self,
        procurement_list: List[Dict[str, Any]],
        require_halal: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        For each procurement item, find the best available supplier.
        Returns a list of {item, qty, supplier} dicts.
        """
        assignments = []
        for entry in procurement_list:
            item = entry["item"]
            suppliers = self.search_suppliers(item, require_halal=require_halal)
            best = suppliers[0] if suppliers else None
            assignments.append({
                "item": item,
                "qty": entry["qty"],
                "unit": entry.get("unit", "kg_or_pack"),
                "supplier": best["name"] if best else "Unknown — manual sourcing required",
                "lead_time_days": best["lead_time_days"] if best else None,
                "halal_certified": best["halal_certified"] if best else None,
            })
        return assignments
