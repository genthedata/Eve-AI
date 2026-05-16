"""
Azure AI Search — placeholder RAG layer over YAML knowledge bases.

When USE_AZURE_AI_SEARCH=true, KB retrieval can hybrid-search an index
instead of (or blended with) YAMLKBSearch keyword overlap.

Default remains app/tools/kb_yaml.py (RAG-lite).
"""

from app.platform.search.azure_ai_search_placeholder import AzureAISearchKBPlaceholder
from app.platform.search.kb_index_mapping_placeholder import KB_INDEX_FIELD_MAP

__all__ = ["AzureAISearchKBPlaceholder", "KB_INDEX_FIELD_MAP"]
