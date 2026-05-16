"""
Inventory & Procurement Agent

Implements the 8-step RAG procurement pipeline:
  1. Receives finalized menu + guest count from menu agent
  2. Queries ingredient_recipe_map KB -> raw ingredient list
  3. Queries real-time stock -> subtracts on-hand quantities
  4. Queries spoilage_waste KB -> applies buffer adjustments
  5. Queries seasonal_availability KB -> flags availability/price risks
  6. Queries supplier_catalog + vendor_performance -> selects best vendor per ingredient
  7. Queries procurement_sop KB -> applies approval rules
  8. Returns purchase plan (logged to shared context for pricing + logistics agents)

Platform: swappable to Microsoft Agent Framework worker (placeholder) — app.agents.platform_bridge
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.llm_mixin import LLMReasoningMixin
from app.providers.base import LLMProvider
from app.tools.inventory_db import InventoryDBTool
from app.tools.kb_yaml import YAMLKBSearch


class InventoryProcurementAgent(LLMReasoningMixin):
    def __init__(
        self,
        inventory_db: InventoryDBTool,
        provider: Optional[LLMProvider] = None,
        kb: Optional[YAMLKBSearch] = None,
    ) -> None:
        self._inventory = inventory_db
        self._kb = kb or YAMLKBSearch()
        self.set_provider(provider)

    # ── Public entry point ───────────────────────────────────────────────────

    def process(self, customer_data: Dict[str, Any], menu_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the full 8-step procurement pipeline and return a structured
        purchase plan. The plan is ready to be logged to shared context for
        the Pricing and Logistics agents.
        """
        guest_count: int = int(customer_data.get("guest_count", 50))
        event_type: str = str(customer_data.get("event_type", "default")).lower()
        service_style: str = str(menu_data.get("service_style", customer_data.get("service_style", "buffet"))).lower()
        location: str = str(customer_data.get("location", "Philippines"))
        event_date: str = str(customer_data.get("event_date", ""))
        menu_items: List[str] = menu_data.get("menu_items", [])

        halal_required: bool = any(
            "halal" in str(c).lower() or "muslim" in str(c).lower()
            for c in customer_data.get("dietary_constraints", [])
        )

        is_urgent: bool = bool(customer_data.get("urgent", False))

        # ── Step 2–7: Full demand_planner pipeline ────────────────────────────
        plan = self._inventory.compute_ingredients_from_menu(
            menu_items=menu_items,
            guest_count=guest_count,
            event_type=event_type,
            service_style=service_style,
            require_halal=halal_required,
            region=location,
            event_date=event_date,
            kb=self._kb,
            is_urgent=is_urgent,
        )

        # ── Supplement with simulation events (if SIMULATE_INVENTORY=true) ───
        sim_events = self._inventory.get_simulation_events()

        # ── Step 8: Compile the purchase plan ────────────────────────────────
        result = self._build_result(
            plan=plan,
            guest_count=guest_count,
            menu_items=menu_items,
            event_type=event_type,
            service_style=service_style,
            halal_required=halal_required,
            sim_events=sim_events,
        )

        # ── LLM reasoning over the plan ──────────────────────────────────────
        reasoning = self._generate_reasoning(result, plan, guest_count, halal_required, is_urgent)
        if reasoning:
            result["reasoning"] = reasoning

        return result

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _build_result(
        self,
        plan: Dict[str, Any],
        guest_count: int,
        menu_items: List[str],
        event_type: str,
        service_style: str,
        halal_required: bool,
        sim_events: List[str],
    ) -> Dict[str, Any]:
        """Assemble the structured result dict from the demand_planner output."""
        ingredient_breakdown = plan.get("ingredient_breakdown", {})
        assigned = plan.get("vendor_assignments", [])
        failures = plan.get("vendor_assignment_failures", [])
        seasonal_warnings = plan.get("seasonal_warnings", [])
        approval = plan.get("approval_requirement", {})
        unmatched = plan.get("unmatched_dishes", [])
        kb_sources: List[str] = list(plan.get("kb_sources", []))

        # Summarise shortages for readability
        shortages = {
            k: v["qty_to_procure"]
            for k, v in ingredient_breakdown.items()
            if v.get("qty_to_procure", 0) > 0
        }

        # Build a concise procurement list for downstream agents
        procurement_list = [
            {
                "item": a["procurement_key"],
                "qty": a["qty_needed_kg_or_l"],
                "units_ordered": a["units_to_order"],
                "unit_size_kg": a["unit_size_kg"],
                "total_ordered": a["total_ordered_kg_or_l"],
                "supplier": a["supplier_name"],
                "supplier_id": a["supplier_id"],
                "sku": a["sku"],
                "estimated_cost": a.get("estimated_cost"),
                "currency": a.get("currency"),
                "lead_days": a.get("lead_days"),
                "cold_chain": a.get("cold_chain"),
                "halal_certified": a.get("halal_certified"),
                "vendor_score": a.get("vendor_score"),
            }
            for a in assigned
        ]

        result: Dict[str, Any] = {
            # Core output
            "menu_items": menu_items,
            "guest_count": guest_count,
            "event_type": event_type,
            "service_style": service_style,
            "halal_required": halal_required,
            "unmatched_dishes": unmatched,

            # Ingredient detail
            "ingredient_breakdown": ingredient_breakdown,
            "shortages": shortages,

            # Procurement plan
            "procurement_list": procurement_list,
            "vendor_assignment_failures": [
                {"item": f["procurement_key"], "reason": f.get("notes", "No vendor found")}
                for f in failures
            ],

            # Financial + approval
            "total_cost_estimate": plan.get("total_cost_estimate", 0.0),
            "currency": plan.get("currency", "PHP"),
            "approval_requirement": approval,

            # Risk signals
            "seasonal_warnings": [
                {
                    "type": w.get("type"),
                    "ingredient": w.get("ingredient") or ", ".join(w.get("affected_procurement_keys", [])),
                    "notes": w.get("mitigation") or w.get("notes", ""),
                    "price_impact_pct": w.get("price_impact_pct"),
                }
                for w in seasonal_warnings
            ],

            # Traceability
            "kb_sources": kb_sources,
        }

        if sim_events:
            result["simulation_events"] = sim_events

        if unmatched:
            result["warning_unmatched_dishes"] = (
                f"{len(unmatched)} dish(es) not found in recipe map — "
                "manual ingredient estimation required: " + ", ".join(unmatched)
            )

        return result

    def _generate_reasoning(
        self,
        result: Dict[str, Any],
        plan: Dict[str, Any],
        guest_count: int,
        halal_required: bool,
        is_urgent: bool,
    ) -> Optional[str]:
        shortages = result.get("shortages", {})
        approval = result.get("approval_requirement", {})
        seasonal = result.get("seasonal_warnings", [])
        failures = result.get("vendor_assignment_failures", [])
        total_cost = result.get("total_cost_estimate", 0.0)
        currency = result.get("currency", "PHP")
        top_shortages = list(shortages.items())[:5]

        prompt_parts = [
            f"Event: {result.get('event_type','?')} for {guest_count} guests ({result.get('service_style','buffet')}).",
            f"Halal required: {halal_required}. Urgent order: {is_urgent}.",
            f"Total procurement estimate: {currency} {total_cost:,.2f}.",
            f"Approval needed: {approval.get('approval_level','?')} from {approval.get('approver','?')}.",
        ]
        if top_shortages:
            shortage_txt = ", ".join(f"{k}: {v:.2f}kg" for k, v in top_shortages)
            prompt_parts.append(f"Top shortages after stock deduction: {shortage_txt}.")
        if seasonal:
            alerts = "; ".join(w.get("ingredient", "") for w in seasonal[:3])
            prompt_parts.append(f"Seasonal risk items: {alerts}.")
        if failures:
            failed_items = ", ".join(f["item"] for f in failures[:3])
            prompt_parts.append(f"Vendor assignment FAILED for: {failed_items}. Manual sourcing needed.")

        prompt_parts.append(
            "In 3 concise sentences: (1) assess procurement urgency and main risks, "
            "(2) flag the most critical items, (3) state whether this PO can proceed "
            "or needs escalation."
        )

        return self.reason(
            prompt=" ".join(prompt_parts),
            system_prompt=(
                "You are the Inventory and Procurement Agent for a professional catering company. "
                "Be direct, specific, and action-oriented. Name exact ingredients and suppliers when relevant."
            ),
        )
