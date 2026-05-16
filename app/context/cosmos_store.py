import os
from typing import Optional

from app.context.catering_plan_context import CateringPlanContext
from app.context.memory_store import MemoryContextStore


class CosmosContextStore:
    """
    Placeholder for Azure Cosmos DB persistence (shared thread / CateringPlanContext).

    PLATFORM: MAF ThreadStore and Foundry session state can map to this store when
    ORCHESTRATION_BACKEND=ms_agent_framework — see docs/microsoft-agent-framework-architecture.md.

    When AZURE_COSMOS_ENDPOINT is set but wiring is incomplete, falls back to memory
    and records intent in docs; replace load/save with cosmos SDK calls.
    """

    def __init__(self) -> None:
        self._endpoint = os.getenv("AZURE_COSMOS_ENDPOINT", "").strip()
        self._fallback = MemoryContextStore()
        self._use_cosmos = bool(self._endpoint and os.getenv("AZURE_COSMOS_KEY", "").strip())

    def load(self, thread_id: str) -> Optional[CateringPlanContext]:
        if self._use_cosmos:
            # Phase: wire azure-cosmos SDK; until then use fallback for safety.
            return self._fallback.load(thread_id)
        return self._fallback.load(thread_id)

    def save(self, ctx: CateringPlanContext) -> None:
        self._fallback.save(ctx)
