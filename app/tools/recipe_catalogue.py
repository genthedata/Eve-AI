from typing import Any, Dict, List

from app.tools.kb_search import KBSearch


class RecipeCatalogueTool:
    """
    Menu knowledge base — backed by KBSearch (RAG-lite retrieval over recipes.json).
    build_menu returns menu_items, portions, and kb_sources for traceability.
    """

    def __init__(self) -> None:
        self._kb = KBSearch()

    def build_menu(
        self,
        guest_count: int,
        dietary_constraints: List[str],
        event_type: str = "default",
        service_style: str = "buffet",
    ) -> Dict[str, Any]:
        return self._kb.build_menu_from_kb(
            guest_count=guest_count,
            dietary_constraints=dietary_constraints,
            event_type=event_type,
            service_style=service_style,
        )
