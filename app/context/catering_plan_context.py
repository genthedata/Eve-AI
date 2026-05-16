from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CateringPlanContext:
    """
    Shared catering plan state (Azure Foundry thread / Cosmos analogue in-repo).
    Updated after each specialist step and persisted via ContextStore.
    """

    thread_id: str
    customer_profile: Optional[Dict[str, Any]] = None
    menu_plan: Optional[Dict[str, Any]] = None
    inventory_snapshot: Optional[Dict[str, Any]] = None
    logistics_plan: Optional[Dict[str, Any]] = None
    pricing: Optional[Dict[str, Any]] = None
    monitoring: Optional[Dict[str, Any]] = None
    plan_steps_completed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "customer_profile": self.customer_profile,
            "menu_plan": self.menu_plan,
            "inventory_snapshot": self.inventory_snapshot,
            "logistics_plan": self.logistics_plan,
            "pricing": self.pricing,
            "monitoring": self.monitoring,
            "plan_steps_completed": list(self.plan_steps_completed),
        }
