from threading import Lock
from typing import Dict, Optional

from app.context.catering_plan_context import CateringPlanContext


class MemoryContextStore:
    """In-process context persistence (default for local dev)."""

    def __init__(self) -> None:
        self._data: Dict[str, CateringPlanContext] = {}
        self._lock = Lock()

    def load(self, thread_id: str) -> Optional[CateringPlanContext]:
        with self._lock:
            return self._data.get(thread_id)

    def save(self, ctx: CateringPlanContext) -> None:
        with self._lock:
            self._data[ctx.thread_id] = ctx
