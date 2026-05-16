# Platform: swappable to Microsoft Agent Framework worker (placeholder) — app.agents.platform_bridge

from typing import Any, Dict, List, Optional

from app.agents.llm_mixin import LLMReasoningMixin
from app.context.catering_plan_context import CateringPlanContext
from app.providers.base import LLMProvider


class MonitoringAgent(LLMReasoningMixin):
    """
    Observes the full CateringPlanContext after all specialist steps complete.
    Aggregates risks, flags escalations, and produces an execution health summary.
    """

    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        self.set_provider(provider)

    def process(self, ctx: CateringPlanContext) -> Dict[str, Any]:
        risks: List[str] = []
        escalations: List[str] = []

        # Inventory risks
        inventory = ctx.inventory_snapshot or {}
        shortages = inventory.get("shortages") or {}
        if shortages:
            # shortages is a dict {ingredient: kg_short}; build a readable summary
            shortage_lines = [f"{k}: {v:.2f} kg" for k, v in shortages.items()] if isinstance(shortages, dict) else [str(shortages)]
            risks.append(f"Ingredient shortages detected: {', '.join(shortage_lines)}")
        sim_events = inventory.get("simulation_events", [])
        if sim_events:
            risks.extend(sim_events)
            escalations.extend([e for e in sim_events if "critical" in str(e).lower()])

        # Logistics risks
        logistics = ctx.logistics_plan or {}
        logistics_risks = logistics.get("risks", [])
        if logistics_risks:
            risks.extend(logistics_risks)
            escalations.extend([r for r in logistics_risks if "high" in str(r).lower()])

        # Pricing risks
        pricing = ctx.pricing or {}
        pricing_data = pricing.get("pricing", {})
        if not pricing_data.get("budget_fit", True):
            risks.append("Quote exceeds customer budget — budget fit: False")
            escalations.append("Budget overrun: requires client negotiation or scope reduction")

        # Seasonal / disruption alerts from inventory
        seasonal_alerts = inventory.get("seasonal_disruption_alerts", [])
        for alert in seasonal_alerts:
            risks.append(f"Seasonal risk: {alert.get('disruption')} — {alert.get('mitigation','')}")

        result: Dict[str, Any] = {
            "risk_count": len(risks),
            "risks": risks,
            "escalation_count": len(escalations),
            "escalations": escalations,
            "steps_completed": list(ctx.plan_steps_completed),
            "health_status": "OK" if not escalations else "ESCALATION_REQUIRED",
        }

        reasoning = self.reason(
            prompt=(
                f"Catering plan for thread {ctx.thread_id}.\n"
                f"Steps completed: {ctx.plan_steps_completed}.\n"
                f"Risks identified ({len(risks)}): {risks[:5]}.\n"
                f"Escalations ({len(escalations)}): {escalations}.\n"
                "In 2-3 sentences, summarise the overall execution health of this "
                "catering plan and flag the single most critical issue, if any."
            ),
            system_prompt=(
                "You are the Monitoring Agent for a catering operations platform. "
                "Be direct and flag risks clearly."
            ),
        )
        if reasoning:
            result["reasoning"] = reasoning

        return result
