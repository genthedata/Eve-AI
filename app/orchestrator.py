import os
from typing import Any, Dict, List, Optional, Tuple

from app.agents.customer_agent import CustomerInteractionAgent
from app.agents.inventory_agent import InventoryProcurementAgent
from app.agents.logistics_agent import LogisticsPlanningAgent
from app.agents.menu_agent import MenuPlanningAgent
from app.agents.monitoring_agent import MonitoringAgent
from app.agents.pricing_agent import PricingOptimizationAgent
from app.context.catering_plan_context import CateringPlanContext
from app.context.cosmos_store import CosmosContextStore
from app.context.memory_store import MemoryContextStore
from app.context.store import ContextStore
from app.models import AgentMessage, SessionState
from app.providers.base import LLMProvider
from app.tools.registry import ToolRegistry

# Platform switch: Microsoft Agent Framework / AI Foundry / Azure AI Search (placeholders)
from app.platform.config import platform_metadata


PlanStep = Tuple[str, str, str]  # (step_id, agent_name, description)


def _get_provider() -> Optional[LLMProvider]:
    """Build provider from env if USE_LLM is enabled."""
    if os.getenv("USE_LLM", "false").strip().lower() not in ("1", "true", "yes"):
        return None
    try:
        from app.providers import build_provider
        return build_provider()
    except Exception:
        return None


class OrchestratorAgent:
    """
    Decompose (fixed DAG) -> route specialists -> persist shared context ->
    assemble final report.  When USE_LLM=true, each agent reasons with the
    configured LLM provider (Ollama, OpenAI-compatible, or Azure OpenAI).

    Swappable via ORCHESTRATION_BACKEND / USE_MS_AGENT_FRAMEWORK (see app.platform).
    MAF placeholder runs this same DAG until Agent Framework workers are wired.
    """

    def __init__(
        self,
        context_store: Optional[ContextStore] = None,
        tools: Optional[ToolRegistry] = None,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        self._store = context_store if context_store is not None else default_context_store()
        self._tools = tools or ToolRegistry()
        self._provider = provider if provider is not None else _get_provider()

        _kb = self._tools.kb_yaml
        self.customer_agent = CustomerInteractionAgent(kb=_kb)
        self.menu_agent = MenuPlanningAgent(self._tools.recipe_catalogue, self._provider, kb=_kb)
        self.inventory_agent = InventoryProcurementAgent(self._tools.inventory_db, self._provider, kb=_kb)
        self.logistics_agent = LogisticsPlanningAgent(self._tools.scheduler, self._provider, kb=_kb)
        self.pricing_agent = PricingOptimizationAgent(self._tools.pricing_engine, self._provider, kb=_kb)
        self.monitoring_agent = MonitoringAgent(self._provider)

    def _send(
        self,
        state: SessionState,
        sender: str,
        recipient: str,
        msg_type: str,
        payload: Dict[str, Any],
        reasoning: Optional[str] = None,
        kb_sources: Optional[List[str]] = None,
        simulation_events: Optional[List[str]] = None,
    ) -> None:
        state.messages.append(
            AgentMessage(
                sender=sender,
                recipient=recipient,
                msg_type=msg_type,
                payload=payload,
                reasoning=reasoning,
                kb_sources=kb_sources or [],
                simulation_events=simulation_events or [],
            )
        )

    def _persist(self, ctx: CateringPlanContext) -> None:
        self._store.save(ctx)

    def decompose_plan(self) -> List[PlanStep]:
        return [
            ("intake", "customer_agent", "Intake and parse customer requirements"),
            ("menu", "menu_agent", "Recommend menu and portions"),
            ("inventory", "inventory_agent", "Stock check and procurement list"),
            ("logistics", "logistics_agent", "Timeline and resource allocation"),
            ("pricing", "pricing_agent", "Cost and pricing strategy"),
        ]

    def run(self, request: Dict[str, Any], thread_id: str) -> SessionState:
        state = SessionState(request=request, thread_id=thread_id)
        ctx = CateringPlanContext(thread_id=thread_id)

        self._send(
            state,
            "orchestrator",
            "customer_agent",
            "plan_decomposed",
            {"steps": [s[0] for s in self.decompose_plan()], "thread_id": thread_id},
        )

        # Step: customer
        customer_data = self.customer_agent.process(request)
        ctx.customer_profile = customer_data
        ctx.plan_steps_completed.append("intake")
        self._persist(ctx)
        state.outputs["customer"] = customer_data
        self._send(state, "customer_agent", "menu_agent", "customer_profile", customer_data)

        # Step: menu
        menu_data = self.menu_agent.process(customer_data)
        ctx.menu_plan = menu_data
        ctx.plan_steps_completed.append("menu")
        self._persist(ctx)
        state.outputs["menu"] = menu_data
        self._send(
            state, "menu_agent", "inventory_agent", "menu_plan",
            {k: v for k, v in menu_data.items() if k != "reasoning"},
            reasoning=menu_data.get("reasoning"),
            kb_sources=menu_data.get("kb_sources", []),
        )

        # Step: inventory
        inventory_data = self.inventory_agent.process(customer_data, menu_data)
        ctx.inventory_snapshot = inventory_data
        ctx.plan_steps_completed.append("inventory")
        self._persist(ctx)
        state.outputs["inventory"] = inventory_data
        self._send(
            state, "inventory_agent", "logistics_agent", "procurement_status",
            {"shortages": inventory_data["shortages"]},
            reasoning=inventory_data.get("reasoning"),
            kb_sources=inventory_data.get("kb_sources", []),
            simulation_events=inventory_data.get("simulation_events", []),
        )

        # Step: logistics — pass menu_data so equipment/transport steps know what's being cooked
        logistics_data = self.logistics_agent.process(customer_data, inventory_data, menu_data)
        ctx.logistics_plan = logistics_data
        ctx.plan_steps_completed.append("logistics")
        self._persist(ctx)
        state.outputs["logistics"] = logistics_data
        self._send(
            state, "logistics_agent", "pricing_agent", "logistics_plan",
            {k: v for k, v in logistics_data.items() if k != "reasoning"},
            reasoning=logistics_data.get("reasoning"),
        )

        # Step: pricing
        pricing_data = self.pricing_agent.process(customer_data, inventory_data, logistics_data)
        ctx.pricing = pricing_data
        ctx.plan_steps_completed.append("pricing")
        self._persist(ctx)
        state.outputs["pricing"] = pricing_data
        self._send(
            state, "pricing_agent", "orchestrator", "final_pricing",
            {k: v for k, v in pricing_data.items() if k != "reasoning"},
            reasoning=pricing_data.get("reasoning"),
        )

        # Monitoring (observes full context)
        monitoring_data = self.monitoring_agent.process(ctx)
        ctx.monitoring = monitoring_data
        ctx.plan_steps_completed.append("monitoring")
        self._persist(ctx)
        state.outputs["monitoring"] = monitoring_data
        self._send(
            state, "monitoring_agent", "orchestrator", "execution_review",
            {k: v for k, v in monitoring_data.items() if k != "reasoning"},
            reasoning=monitoring_data.get("reasoning"),
        )

        plan_narrative = self._optional_plan_narrative(ctx)
        state.outputs["final_report"] = self._build_final_report(state.outputs, ctx, plan_narrative)
        state.catering_context = ctx.to_dict()
        return state

    def _optional_plan_narrative(self, ctx: CateringPlanContext) -> Optional[str]:
        if os.getenv("USE_LLM", "false").strip().lower() not in ("1", "true", "yes"):
            return None
        if self._provider is None:
            return None
        try:
            ev = ctx.customer_profile or {}
            pricing = ctx.pricing or {}
            return self._provider.generate(
                f"Event: {ev.get('event_type')}, {ev.get('guest_count')} guests, "
                f"budget: {ev.get('budget')} {ev.get('currency','PHP')}.\n"
                f"Quote: {pricing.get('pricing',{}).get('suggested_quote')} {pricing.get('currency','')}. "
                f"Budget fit: {pricing.get('pricing',{}).get('budget_fit')}.\n"
                "Write 3 short bullet points summarising this catering plan for the client.",
                system_prompt="You are the Orchestrator. Be concise and client-friendly.",
            )
        except Exception:
            return None

    def _build_final_report(
        self,
        outputs: Dict[str, Any],
        ctx: CateringPlanContext,
        plan_narrative: Optional[str],
    ) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "thread_id": ctx.thread_id,
            "event_summary": outputs["customer"],
            "recommended_menu": outputs["menu"],
            "procurement_plan": {
                "ingredient_breakdown": outputs["inventory"].get(
                    "ingredient_breakdown",
                    outputs["inventory"].get("ingredients_needed", {}),
                ),
                "shortages": outputs["inventory"].get("shortages", {}),
                "procurement_list": outputs["inventory"].get("procurement_list", []),
                "suppliers": outputs["inventory"].get("suppliers", []),
                "total_cost_estimate": outputs["inventory"].get("total_cost_estimate"),
                "currency": outputs["inventory"].get("currency"),
                "approval_requirement": outputs["inventory"].get("approval_requirement"),
                "seasonal_warnings": outputs["inventory"].get("seasonal_warnings", []),
                "vendor_assignment_failures": outputs["inventory"].get("vendor_assignment_failures", []),
            },
            "logistics_plan": outputs["logistics"],
            "cost_and_pricing": outputs["pricing"],
            "monitoring": outputs["monitoring"],
            "shared_context_snapshot": ctx.to_dict(),
        }
        if plan_narrative:
            report["orchestrator_plan_narrative"] = plan_narrative
        report["platform"] = platform_metadata()
        return report


def default_context_store() -> ContextStore:
    if os.getenv("AZURE_COSMOS_ENDPOINT", "").strip():
        return CosmosContextStore()
    return MemoryContextStore()
