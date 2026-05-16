from app.tools.inventory_db import InventoryDBTool
from app.tools.kb_yaml import YAMLKBSearch
from app.tools.pricing_engine import PricingEngineTool
from app.tools.recipe_catalogue import RecipeCatalogueTool
from app.tools.scheduler_api import SchedulerAPITool

# PLATFORM PLACEHOLDER: Azure AI Search RAG over KB index (USE_AZURE_AI_SEARCH=true)
_search_placeholder = None


class ToolRegistry:
    """Bundles tool surface for specialist agents."""

    def __init__(
        self,
        recipe_catalogue: RecipeCatalogueTool | None = None,
        inventory_db: InventoryDBTool | None = None,
        scheduler: SchedulerAPITool | None = None,
        pricing_engine: PricingEngineTool | None = None,
        kb_yaml: YAMLKBSearch | None = None,
    ) -> None:
        self.recipe_catalogue = recipe_catalogue or RecipeCatalogueTool()
        self.inventory_db = inventory_db or InventoryDBTool()
        self.scheduler = scheduler or SchedulerAPITool()
        self.pricing_engine = pricing_engine or PricingEngineTool()
        self.kb_yaml = kb_yaml or YAMLKBSearch()

    @property
    def azure_ai_search_kb(self):
        """Azure AI Search KB client (placeholder; returns stub until index is wired)."""
        global _search_placeholder
        if _search_placeholder is None:
            from app.platform.search import AzureAISearchKBPlaceholder

            _search_placeholder = AzureAISearchKBPlaceholder()
        return _search_placeholder
