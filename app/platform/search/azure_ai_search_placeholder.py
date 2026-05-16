"""
Azure AI Search — knowledge base index placeholder.

Env:
  AZURE_SEARCH_ENDPOINT
  AZURE_SEARCH_API_KEY
  AZURE_SEARCH_INDEX_KB=eve-cater-kb

Future index documents: flattened YAML chunks per KB file with metadata:
  agent_scope, kb_path, chunk_id, text, dietary_tags, event_types
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


class AzureAISearchKBPlaceholder:
    """Stub search client; returns empty hits (YAML path remains authoritative)."""

    def __init__(self) -> None:
        self.endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip()
        self.index_name = os.getenv("AZURE_SEARCH_INDEX_KB", "eve-cater-kb")
        self.api_key = os.getenv("AZURE_SEARCH_API_KEY", "").strip()

    def is_configured(self) -> bool:
        return bool(self.endpoint and self.index_name)

    def search(
        self,
        query: str,
        *,
        kb_path: Optional[str] = None,
        top_k: int = 5,
        filters: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        PLACEHOLDER: hybrid / semantic search over eve-cater-kb index.

        Returns [] — callers merge with YAMLKBSearch results when enabled.
        """
        _ = (query, kb_path, top_k, filters)
        # TODO(Search): SearchClient(endpoint, index).search(...)
        return []

    def metadata(self) -> Dict[str, Any]:
        return {
            "service": "azure_ai_search",
            "status": "placeholder",
            "endpoint": self.endpoint or "(not set)",
            "index": self.index_name,
        }
