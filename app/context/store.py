from typing import Optional, Protocol

from app.context.catering_plan_context import CateringPlanContext


class ContextStore(Protocol):
    def load(self, thread_id: str) -> Optional[CateringPlanContext]: ...

    def save(self, ctx: CateringPlanContext) -> None: ...
