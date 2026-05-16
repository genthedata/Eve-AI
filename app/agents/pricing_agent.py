"""
PricingOptimizationAgent — 7-step KB-driven pricing pipeline.

Step 1: Cost of goods          → compute raw food cost per head from menu × current prices
Step 2: Overhead & labour      → add staffing, transport, ops costs for the event profile
Step 3: Seasonal price signals → apply forward-looking surcharges for event date/ingredients
Step 4: Market benchmarks      → position computed cost vs. market tiers; sanity-check
Step 5: Discount & promotion   → apply eligible client discounts; enforce margin floors
Step 6: Historical quotes      → retrieve comparable events; validate margin expectation
Step 7: Price elasticity       → model expected value across price options; pick optimal
Step 8: Output                 → tiered quote (value / standard / premium) + margin summary

Platform: swappable to Microsoft Agent Framework worker (placeholder) — app.agents.platform_bridge
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.agents.llm_mixin import LLMReasoningMixin
from app.providers.base import LLMProvider
from app.tools.currency import lookup_iso
from app.tools.kb_yaml import YAMLKBSearch
from app.tools.pricing_engine import PricingEngineTool


class PricingOptimizationAgent(LLMReasoningMixin):
    def __init__(
        self,
        pricing_engine: PricingEngineTool,
        provider: Optional[LLMProvider] = None,
        kb: Optional[YAMLKBSearch] = None,
    ) -> None:
        self._pricing = pricing_engine
        self._kb = kb or YAMLKBSearch()
        self.set_provider(provider)

    # ── Public entry point ─────────────────────────────────────────────────────

    def process(
        self,
        customer_data: Dict[str, Any],
        inventory_data: Dict[str, Any],
        logistics_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Produce a tiered quote from a full event context.

        customer_data expected keys:
            guest_count, budget, event_type, service_style, currency,
            location/region, event_date, dietary_constraints,
            client_id (optional), is_repeat_client (optional),
            vip_tier (optional), booking_advance_days (optional),
            event_day_of_week (optional), event_month (optional)

        inventory_data expected keys:
            menu_items (list), shortages (list)
            ingredient_brief_for_inventory (dict from menu_agent)

        logistics_data expected keys:
            resource_allocation: {kitchen_staff, delivery_vehicles}
        """
        currency = customer_data.get("currency", "MYR")
        _sym, php_rate = lookup_iso(currency)
        guest_count = int(customer_data.get("guest_count", 100))
        event_type = customer_data.get("event_type", "default")
        service_style = customer_data.get("service_style", "buffet")
        region = customer_data.get("location", customer_data.get("region", "Malaysia"))
        event_date = customer_data.get("event_date", "")
        budget = float(customer_data.get("budget", 0))
        menu_items = (
            inventory_data.get("menu_items", [])
            or inventory_data.get("ingredient_brief_for_inventory", {}).get("menu_items", [])
        )
        dietary = customer_data.get("dietary_constraints", [])
        client_id = customer_data.get("client_id")
        is_repeat = bool(customer_data.get("is_repeat_client", False))
        vip_tier = customer_data.get("vip_tier", "")
        booking_advance_days = int(customer_data.get("booking_advance_days", 0))
        event_month = self._parse_month(event_date)
        event_day = customer_data.get("event_day_of_week", "")

        kb_sources: List[str] = []

        # ── Step 1: Food cost computation ─────────────────────────────────────
        food_cost = self._step1_food_cost(
            menu_items, guest_count, currency, event_date,
            event_type, service_style, kb_sources
        )

        # ── Step 2: Overhead & labour ─────────────────────────────────────────
        overhead = self._step2_overhead(
            guest_count, service_style, kb_sources
        )

        # ── Step 3: Seasonal surcharges ───────────────────────────────────────
        seasonal = self._step3_seasonal_adjustments(
            menu_items, event_month, region, food_cost["base_food_cost_myr"], kb_sources
        )

        # ── Step 4: Market benchmarks ─────────────────────────────────────────
        benchmarks = self._step4_market_benchmarks(
            event_type, region, service_style, guest_count, currency, kb_sources
        )

        # ── Step 5: Discounts & margin floor ─────────────────────────────────
        total_cost_myr = (
            food_cost["adjusted_food_cost_myr"]
            + overhead["total_overhead_myr"]
        )
        discounts = self._step5_discounts(
            is_repeat_client=is_repeat,
            vip_tier=vip_tier,
            guest_count=guest_count,
            booking_advance_days=booking_advance_days,
            event_day=event_day,
            event_month=event_month or "",
            service_style=service_style,
            total_cost_myr=total_cost_myr,
            kb_sources=kb_sources,
        )

        # ── Step 6: Historical validation ─────────────────────────────────────
        history = self._step6_historical_validation(
            event_type, region, guest_count, currency, kb_sources
        )

        # ── Step 7: Price elasticity & EV optimisation ────────────────────────
        elasticity = self._step7_elasticity(
            event_type, region, currency,
            total_cost_myr, discounts["total_discount_pct"],
            guest_count, kb_sources,
        )

        # ── Step 8: Assemble tiered quote output ──────────────────────────────
        # Fallback: also run legacy pricing engine for backward compat
        ra = logistics_data.get("resource_allocation", {})
        legacy = self._pricing.compute(
            guest_count=guest_count,
            budget=budget,
            kitchen_staff=ra.get("kitchen_staff", 3),
            delivery_vehicles=ra.get("delivery_vehicles", 1),
            shortage_count=len(inventory_data.get("shortages") or {}),
            currency=currency,
            php_rate=php_rate,
        )

        result = self._assemble_output(
            customer_data=customer_data,
            guest_count=guest_count,
            currency=currency,
            food_cost=food_cost,
            overhead=overhead,
            seasonal=seasonal,
            benchmarks=benchmarks,
            discounts=discounts,
            history=history,
            elasticity=elasticity,
            legacy=legacy,
            budget=budget,
            kb_sources=kb_sources,
        )

        # ── LLM reasoning ──────────────────────────────────────────────────────
        reasoning = self.reason(
            prompt=self._build_reasoning_prompt(result, customer_data),
            system_prompt=(
                "You are the Pricing and Optimisation Agent for a professional catering company "
                "in Southeast Asia. Give actionable, concise financial advice. "
                "Think like a commercial director: protect margin, win the booking, "
                "advise on strategy — not just arithmetic."
            ),
        )
        if reasoning:
            result["reasoning"] = reasoning

        return result

    # ── Step 1 ─────────────────────────────────────────────────────────────────

    def _step1_food_cost(
        self,
        menu_items: List[str],
        guest_count: int,
        currency: str,
        event_date: str,
        event_type: str,
        service_style: str,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """Compute food cost from menu × dish benchmark prices + drift alerts."""
        kb_data = self._kb.get("pricing/cost_of_goods")
        if not isinstance(kb_data, dict):
            return {
                "base_food_cost_myr": guest_count * 8.0,
                "adjusted_food_cost_myr": guest_count * 8.0,
                "per_head_food_cost_myr": 8.0,
                "drift_alerts": [],
                "dish_costs": [],
            }

        dish_benchmarks = kb_data.get("dish_food_cost_benchmarks_myr", {})
        drift_alerts_raw = kb_data.get("active_drift_alerts", [])

        # Compute per-dish food cost using mid benchmark
        dish_costs: List[Dict] = []
        total_food_cost_myr = 0.0

        if menu_items and dish_benchmarks:
            for dish in menu_items:
                bm = dish_benchmarks.get(dish)
                if bm and isinstance(bm, dict):
                    cost_per_serving = bm.get("mid", bm.get("low", 4.0))
                    dish_total = cost_per_serving * guest_count
                    dish_costs.append({
                        "dish": dish,
                        "cost_per_serving_myr": cost_per_serving,
                        "total_myr": round(dish_total, 2),
                    })
                    total_food_cost_myr += dish_total
                else:
                    # Unknown dish — use average per-dish fallback (MYR 4)
                    fallback = 4.0 * guest_count
                    dish_costs.append({
                        "dish": dish,
                        "cost_per_serving_myr": 4.0,
                        "total_myr": round(fallback, 2),
                        "note": "Estimated — dish not in cost benchmark",
                    })
                    total_food_cost_myr += fallback
        else:
            # No menu — use flat per-head estimate (MYR 8)
            total_food_cost_myr = guest_count * 8.0

        # Apply service style multiplier (plated = 2.2× buffet food cost per dish)
        ss_multipliers = kb_data.get("service_style_food_cost_multiplier", {})
        ss_key = service_style.lower().split("_")[0] if service_style else "buffet"
        ss_multiplier = float(ss_multipliers.get(ss_key, ss_multipliers.get("buffet", 1.0)))

        # Apply waste/yield uplift and miscellaneous overhead
        waste_uplifts = kb_data.get("food_cost_waste_uplift_by_event", {})
        misc_overheads = kb_data.get("food_misc_overhead_per_pax_myr", {})
        minimums = kb_data.get("minimum_food_cost_per_head_myr", {})

        et_key = event_type.lower().replace(" ", "_").replace("-", "_")
        waste_factor = waste_uplifts.get(et_key, waste_uplifts.get("default", 1.10))
        misc_per_pax = float(misc_overheads.get(ss_key, misc_overheads.get("buffet", 8.0)))
        min_per_head = float(minimums.get(et_key, minimums.get("default", 20.0)))

        total_food_cost_myr = (total_food_cost_myr * ss_multiplier * waste_factor
                               + (misc_per_pax * guest_count))

        # Apply minimum floor
        floor_total = min_per_head * guest_count
        total_food_cost_myr = max(total_food_cost_myr, floor_total)
        per_head_myr = round(total_food_cost_myr / guest_count, 2) if guest_count else 0.0

        # Drift alerts
        drift_flags: List[str] = []
        for alert in drift_alerts_raw:
            if not isinstance(alert, dict):
                continue
            if float(alert.get("current_vs_last_pct", 0)) >= kb_data.get("drift_alert_threshold_pct", 12):
                drift_flags.append(
                    f"PRICE DRIFT: {alert.get('procurement_key')} "
                    f"+{alert.get('current_vs_last_pct')}% — {alert.get('action', '')}"
                )

        if dish_costs:
            kb_sources.append(
                f"pricing/cost_of_goods -> {len(dish_costs)} dishes costed "
                f"(MYR {round(total_food_cost_myr, 0):.0f} total food cost)"
            )
        if drift_flags:
            kb_sources.append(f"pricing/cost_of_goods -> {len(drift_flags)} drift alert(s)")

        return {
            "base_food_cost_myr": round(total_food_cost_myr, 2),
            "adjusted_food_cost_myr": round(total_food_cost_myr, 2),
            "per_head_food_cost_myr": per_head_myr,
            "drift_alerts": drift_flags,
            "dish_costs": dish_costs,
        }

    # ── Step 2 ─────────────────────────────────────────────────────────────────

    def _step2_overhead(
        self,
        guest_count: int,
        service_style: str,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """Look up event overhead from staffing model or quick-reference table."""
        kb_data = self._kb.get("pricing/overhead_labour")
        if not isinstance(kb_data, dict):
            return {
                "total_overhead_myr": guest_count * 15.0,
                "per_head_overhead_myr": 15.0,
                "model_matched": None,
                "breakdown": {},
            }

        quick_ref = kb_data.get("overhead_quick_reference_myr", {})
        staffing_models = kb_data.get("event_staffing_models", [])

        # Map pax to quick-reference key
        pax_key = self._map_pax_tier(guest_count)
        qr = quick_ref.get(pax_key, {})

        total_overhead = float(qr.get("total", guest_count * 15.0))
        per_head = round(total_overhead / guest_count, 2) if guest_count else 0

        # Apply plated service uplift (25%)
        is_plated = "plated" in service_style.lower()
        if is_plated:
            uplift = total_overhead * 0.10  # 10% extra overhead for plated
            total_overhead += uplift

        # Match staffing model for detailed breakdown
        matched_model: Optional[str] = None
        for model in staffing_models:
            if not isinstance(model, dict):
                continue
            style = model.get("service_style", "")
            lo, hi = model.get("pax_range", [0, 9999])
            if lo <= guest_count <= hi and style in service_style:
                matched_model = model.get("model_id")
                kb_sources.append(
                    f"pricing/overhead_labour -> staffing model {matched_model}"
                )
                break

        if not matched_model:
            kb_sources.append(f"pricing/overhead_labour -> quick-reference {pax_key}")

        return {
            "total_overhead_myr": round(total_overhead, 2),
            "per_head_overhead_myr": round(total_overhead / guest_count, 2) if guest_count else 0,
            "model_matched": matched_model,
            "breakdown": {k: v for k, v in qr.items() if k != "total"},
            "plated_uplift_applied": is_plated,
        }

    # ── Step 3 ─────────────────────────────────────────────────────────────────

    def _step3_seasonal_adjustments(
        self,
        menu_items: List[str],
        event_month: Optional[str],
        region: str,
        base_food_cost_myr: float,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """Apply forward-looking price surcharges for seasonal ingredient risk."""
        if not event_month:
            return {"surcharge_pct": 0.0, "surcharge_myr": 0.0, "flags": []}

        seasonal_kb = self._kb.get("shared/seasonal_availability")
        cost_kb = self._kb.get("pricing/cost_of_goods")

        flags: List[str] = []
        total_surcharge_pct = 0.0

        if isinstance(seasonal_kb, dict):
            calendar = seasonal_kb.get("calendar", [])
            for entry in calendar:
                if not isinstance(entry, dict):
                    continue
                off_peak = entry.get("off_peak_months", [])
                entry_region = entry.get("region", "")
                region_match = (
                    any(region.lower() in r.lower() for r in entry_region)
                    if isinstance(entry_region, list)
                    else region.lower() in str(entry_region).lower()
                )
                if not region_match or event_month not in off_peak:
                    continue

                ingredient = entry.get("ingredient", "")
                price_idx = float(entry.get("off_peak_price_index", 1.0))
                spike_pct = round((price_idx - 1.0) * 100, 1)

                # Only flag if spike significant (>15%) and ingredient is menu-relevant
                if spike_pct >= 15:
                    notes = str(entry.get("notes", ""))
                    flags.append(
                        f"SEASONAL SURCHARGE: {ingredient} off-peak in {event_month} "
                        f"(+{spike_pct}% price). {notes[:100]}"
                    )
                    total_surcharge_pct = max(total_surcharge_pct, spike_pct * 0.3)

        # Check cost-of-goods for festive spikes
        if isinstance(cost_kb, dict):
            for ingr in cost_kb.get("ingredients", []):
                if not isinstance(ingr, dict):
                    continue
                festive_months = ingr.get("festive_months", [])
                spike = float(ingr.get("festive_spike_pct", 0))
                if event_month in festive_months and spike >= 15:
                    key = ingr.get("procurement_key", "")
                    flags.append(
                        f"FESTIVE SURCHARGE: {key} +{spike}% in {event_month} "
                        f"({ingr.get('notes', '')[:80]})"
                    )
                    total_surcharge_pct = max(total_surcharge_pct, spike * 0.25)

        # Cap surcharge at 20% of food cost
        total_surcharge_pct = min(total_surcharge_pct, 20.0)
        surcharge_myr = round(base_food_cost_myr * total_surcharge_pct / 100, 2)

        if flags:
            kb_sources.append(
                f"shared/seasonal_availability + pricing/cost_of_goods -> "
                f"{len(flags)} seasonal surcharge(s) for {event_month}"
            )

        return {
            "surcharge_pct": round(total_surcharge_pct, 2),
            "surcharge_myr": surcharge_myr,
            "flags": flags,
        }

    # ── Step 4 ─────────────────────────────────────────────────────────────────

    def _step4_market_benchmarks(
        self,
        event_type: str,
        region: str,
        service_style: str,
        guest_count: int,
        currency: str,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """Find the relevant benchmark and assess where our cost-up sits vs market."""
        kb_data = self._kb.get("pricing/market_benchmarks")
        if not isinstance(kb_data, dict):
            return {"matched": None, "tier_range": {}, "positioning": "standard"}

        benchmarks = kb_data.get("benchmarks", [])
        matched: Optional[Dict] = None
        best_score = -1

        for bm in benchmarks:
            if not isinstance(bm, dict):
                continue
            score = 0
            bm_event = bm.get("event_type", "").lower().replace("_", " ")
            bm_region = bm.get("region", "").lower()
            bm_style = bm.get("service_style", "").lower()

            if event_type.lower().replace("_", " ") in bm_event or bm_event in event_type.lower():
                score += 3
            if region.lower() in bm_region or bm_region in region.lower():
                score += 2
            if service_style.lower().split("_")[0] in bm_style or bm_style in service_style.lower():
                score += 1

            if score > best_score:
                best_score = score
                matched = bm

        if not matched:
            return {"matched": None, "tier_range": {}, "positioning": "standard"}

        kb_sources.append(
            f"pricing/market_benchmarks -> {matched.get('benchmark_id')} "
            f"({matched.get('event_type')}, {matched.get('region')})"
        )

        # Extract tier range for the right guest count tier
        tier_range: Dict[str, Any] = {}
        tiers = matched.get("guest_count_tiers", [])
        if tiers:
            for tier in tiers:
                lo, hi = tier.get("pax_range", [0, 9999])
                if lo <= guest_count <= hi:
                    tier_range = {
                        "budget": tier.get("budget"),
                        "standard": tier.get("standard"),
                        "premium": tier.get("premium"),
                        "luxury": tier.get("luxury"),
                        "currency": matched.get("currency", currency),
                        "unit": matched.get("unit", "per_head"),
                    }
                    break
            if not tier_range and tiers:
                # Fallback to first tier
                t = tiers[0]
                tier_range = {
                    "budget": t.get("budget"),
                    "standard": t.get("standard"),
                    "premium": t.get("premium"),
                    "currency": matched.get("currency", currency),
                }

        positioning_notes = kb_data.get("positioning_rules", [])
        positioning = matched.get("our_typical_positioning", "standard")

        return {
            "matched_benchmark_id": matched.get("benchmark_id"),
            "event_type": matched.get("event_type"),
            "region": matched.get("region"),
            "tier_range": tier_range,
            "our_positioning": positioning,
            "benchmark_notes": matched.get("notes", ""),
            "positioning_guidance": [p.get("description", "") for p in positioning_notes[:1]],
        }

    # ── Step 5 ─────────────────────────────────────────────────────────────────

    def _step5_discounts(
        self,
        is_repeat_client: bool,
        vip_tier: str,
        guest_count: int,
        booking_advance_days: int,
        event_day: str,
        event_month: str,
        service_style: str,
        total_cost_myr: float,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """Apply eligible discounts and enforce margin floor."""
        kb_data = self._kb.get("pricing/discount_rules")
        if not isinstance(kb_data, dict):
            return {
                "applied_discounts": [],
                "total_discount_pct": 0.0,
                "margin_floor_pct": 15.0,
                "proactive_suggestions": [],
            }

        floors = kb_data.get("margin_floors", {})
        margin_floor = float(floors.get("recommended_floor_pct", 15.0))
        absolute_floor = float(floors.get("absolute_floor_pct", 10.0))
        max_total_discount = float(kb_data.get("stacking_rules", {}).get("max_total_discount_pct", 15.0))

        applied: List[Dict] = []
        total_discount = 0.0
        suggestions: List[str] = []

        # Loyalty discounts
        loyalty_rules = kb_data.get("loyalty_discounts", [])
        for rule in loyalty_rules:
            if not isinstance(rule, dict):
                continue
            rule_id = rule.get("rule_id", "")
            trigger = rule.get("trigger", "")
            disc = float(rule.get("discount_pct", 0))

            triggered = False
            if "vip_tier == platinum" in trigger and vip_tier.lower() == "platinum":
                triggered = True
            elif "booking count >= 3" in trigger and is_repeat_client:
                triggered = True
            elif "booking count >= 2" in trigger and is_repeat_client and not triggered:
                triggered = True

            if triggered and total_discount + disc <= max_total_discount:
                applied.append({"rule_id": rule_id, "name": rule.get("name"), "discount_pct": disc})
                total_discount += disc
                kb_sources.append(f"pricing/discount_rules -> {rule_id}")
                break  # Only one loyalty tier

        # Volume discounts
        vol_rules = kb_data.get("volume_discounts", [])
        for rule in vol_rules:
            if not isinstance(rule, dict):
                continue
            disc = float(rule.get("discount_pct", 0))
            trigger = rule.get("trigger", "")
            lo, hi = self._parse_volume_trigger(trigger)
            if lo <= guest_count <= hi and total_discount + disc <= max_total_discount:
                applied.append({"rule_id": rule.get("rule_id"), "name": rule.get("name"), "discount_pct": disc})
                total_discount += disc
                kb_sources.append(f"pricing/discount_rules -> {rule.get('rule_id')}")
                break

        # Off-peak / weekday discounts
        offpeak_rules = kb_data.get("off_peak_promotions", [])
        weekday_days = {"Monday", "Tuesday", "Wednesday", "Thursday"}
        low_season_months = {"February", "August"}
        for rule in offpeak_rules:
            if not isinstance(rule, dict):
                continue
            disc = float(rule.get("discount_pct", 0))
            trigger = rule.get("trigger", "")
            triggered_op = False
            if "event_day in" in trigger and event_day in weekday_days:
                triggered_op = True
            elif "event_month in" in trigger and event_month in low_season_months:
                triggered_op = True
            if triggered_op and total_discount + disc <= max_total_discount:
                applied.append({"rule_id": rule.get("rule_id"), "name": rule.get("name"), "discount_pct": disc})
                total_discount += disc
                kb_sources.append(f"pricing/discount_rules -> {rule.get('rule_id')}")

        # Early booking discounts
        early_rules = kb_data.get("early_booking_discounts", [])
        if booking_advance_days >= 90:
            rule = next((r for r in early_rules if "90" in r.get("trigger", "")), None)
            if rule:
                disc = float(rule.get("discount_pct", 0))
                if total_discount + disc <= max_total_discount:
                    applied.append({"rule_id": rule.get("rule_id"), "name": rule.get("name"), "discount_pct": disc})
                    total_discount += disc
                    kb_sources.append(f"pricing/discount_rules -> {rule.get('rule_id')}")
        elif booking_advance_days >= 60:
            rule = next((r for r in early_rules if "60" in r.get("trigger", "")), None)
            if rule:
                disc = float(rule.get("discount_pct", 0))
                if total_discount + disc <= max_total_discount:
                    applied.append({"rule_id": rule.get("rule_id"), "name": rule.get("name"), "discount_pct": disc})
                    total_discount += disc

        # Proactive suggestions (unapplied discounts that could tip a hesitant client)
        promo_triggers = kb_data.get("proactive_suggestions", [])
        for pt in promo_triggers:
            if not isinstance(pt, dict):
                continue
            if not is_repeat_client and "returning" not in pt.get("trigger", ""):
                suggestions.append(pt.get("message", ""))

        return {
            "applied_discounts": applied,
            "total_discount_pct": round(min(total_discount, max_total_discount), 2),
            "margin_floor_pct": margin_floor,
            "absolute_floor_pct": absolute_floor,
            "proactive_suggestions": suggestions[:2],
        }

    # ── Step 6 ─────────────────────────────────────────────────────────────────

    def _step6_historical_validation(
        self,
        event_type: str,
        region: str,
        guest_count: int,
        currency: str,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """Retrieve comparable past quotes and validate margin expectation."""
        kb_data = self._kb.get("pricing/historical_quotes")
        if not isinstance(kb_data, dict):
            return {
                "comparable_quotes": [],
                "expected_margin_pct": 18.0,
                "lessons": [],
                "win_rate_data": [],
            }

        quotes = kb_data.get("quotes", [])
        margin_summary = kb_data.get("margin_summary", {})
        avg_margins = margin_summary.get("average_gross_margin_pct_by_event", {})
        recurring_lessons = kb_data.get("recurring_lessons", [])
        win_rate_data = kb_data.get("win_rate_by_quoted_price", {})

        # Find comparable accepted quotes
        comparable: List[Dict] = []
        for q in quotes:
            if not isinstance(q, dict):
                continue
            q_event = q.get("event_type", "").lower().replace("_", " ")
            q_region = q.get("region", "").lower()
            q_accepted = q.get("accepted", False)
            q_pax = int(q.get("guest_count", 0))

            event_match = (
                event_type.lower().replace("_", " ") in q_event
                or q_event in event_type.lower().replace("_", " ")
            )
            region_match = region.lower() in q_region or q_region in region.lower()
            pax_match = abs(q_pax - guest_count) <= max(guest_count * 0.5, 100)

            if event_match and q_accepted and pax_match:
                comparable.append({
                    "quote_id": q.get("quote_id"),
                    "guest_count": q_pax,
                    "quoted_per_head": q.get("quoted_per_head"),
                    "currency": q.get("currency"),
                    "actual_gross_margin_pct": q.get("actual_gross_margin_pct"),
                    "notes": str(q.get("notes", ""))[:120],
                })
                if len(comparable) >= 3:
                    break

        # Expected margin for this event type
        et_key = event_type.lower().replace(" ", "_").replace("-", "_")
        expected_margin = avg_margins.get(et_key, avg_margins.get("malay_wedding", 18.0))

        # Relevant win rate lookup key
        wr_key = self._map_winrate_key(event_type, currency)
        wr_data = win_rate_data.get(wr_key, [])

        if comparable:
            kb_sources.append(
                f"pricing/historical_quotes -> {len(comparable)} comparable quotes "
                f"(avg margin: {expected_margin}%)"
            )

        return {
            "comparable_quotes": comparable,
            "expected_gross_margin_pct": expected_margin,
            "floor_margin_pct": float(margin_summary.get("floor_gross_margin_never_go_below_pct", 10.0)),
            "lessons": [l for l in recurring_lessons if isinstance(l, str)][:3],
            "win_rate_curve": wr_data,
        }

    # ── Step 7 ─────────────────────────────────────────────────────────────────

    def _step7_elasticity(
        self,
        event_type: str,
        region: str,
        currency: str,
        total_cost_myr: float,
        total_discount_pct: float,
        guest_count: int,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """
        Use price elasticity data to generate 3 price options (value/standard/premium)
        and compute expected value (EV) for each to find the optimal quote.
        """
        kb_data = self._kb.get("pricing/price_elasticity")
        if not isinstance(kb_data, dict):
            return {
                "options": [],
                "recommended_price_per_head_myr": round(total_cost_myr / guest_count * 1.2, 2),
                "expected_value_myr": 0.0,
            }

        curves = kb_data.get("conversion_curves", [])
        seasonal_demand = kb_data.get("seasonal_demand_multipliers", [])

        # Find matching curve
        matched_curve: Optional[Dict] = None
        for curve in curves:
            if not isinstance(curve, dict):
                continue
            et = curve.get("event_type", "").lower().replace("_", " ")
            cr = curve.get("region", "").lower()
            cc = curve.get("currency", "").upper()
            if (
                (event_type.lower().replace("_", " ") in et or et in event_type.lower())
                and currency.upper() == cc
            ):
                matched_curve = curve
                break

        # Compute 3 price tiers: value (floor+), standard (target), premium
        per_head_cost_myr = total_cost_myr / guest_count if guest_count else 20.0
        margin_floor = 0.12  # 12% absolute minimum
        target_margin = 0.20
        premium_margin = 0.32
        discount_factor = 1 - (total_discount_pct / 100)

        value_price = round(per_head_cost_myr / (1 - margin_floor) * discount_factor, 2)
        standard_price = round(per_head_cost_myr / (1 - target_margin) * discount_factor, 2)
        premium_price = round(per_head_cost_myr / (1 - premium_margin) * discount_factor, 2)

        def get_win_rate(price: float) -> float:
            if not matched_curve:
                return 65.0
            pts = matched_curve.get("data_points", [])
            if not pts:
                return 65.0
            prices = [p.get("price", 0) for p in pts]
            rates = [p.get("win_rate_pct", 50) for p in pts]
            if price <= prices[0]:
                return float(rates[0])
            if price >= prices[-1]:
                return float(rates[-1])
            for i in range(len(prices) - 1):
                if prices[i] <= price <= prices[i + 1]:
                    pct = (price - prices[i]) / (prices[i + 1] - prices[i])
                    return rates[i] + pct * (rates[i + 1] - rates[i])
            return 65.0

        options = []
        for label, price in [("value", value_price), ("standard", standard_price), ("premium", premium_price)]:
            win_rate = get_win_rate(price)
            total_quote = round(price * guest_count, 2)
            gross_margin_pct = round((1 - per_head_cost_myr / price) * 100, 1) if price > 0 else 0
            ev = round(win_rate / 100 * total_quote, 2)
            options.append({
                "tier": label,
                "price_per_head_myr": price,
                "total_quote_myr": total_quote,
                "win_rate_pct": round(win_rate, 1),
                "gross_margin_pct": gross_margin_pct,
                "expected_value_myr": ev,
            })

        # Recommend the option with the best EV that clears the margin floor
        valid_options = [o for o in options if o["gross_margin_pct"] >= 12]
        if valid_options:
            best = max(valid_options, key=lambda o: o["expected_value_myr"])
        else:
            best = options[1] if len(options) > 1 else options[0]

        sweet_spot = matched_curve.get("sweet_spot_myr") if matched_curve else None
        rationale = matched_curve.get("sweet_spot_rationale", "") if matched_curve else ""

        if matched_curve:
            kb_sources.append(
                f"pricing/price_elasticity -> {matched_curve.get('event_type')} "
                f"curve (sweet spot: MYR {sweet_spot})"
            )

        return {
            "options": options,
            "recommended_tier": best.get("tier"),
            "recommended_price_per_head_myr": best.get("price_per_head_myr"),
            "recommended_total_quote_myr": best.get("total_quote_myr"),
            "recommended_ev_myr": best.get("expected_value_myr"),
            "sweet_spot_myr": sweet_spot,
            "sweet_spot_rationale": str(rationale)[:200],
        }

    # ── Step 8: Assemble output ────────────────────────────────────────────────

    def _assemble_output(
        self,
        customer_data: Dict[str, Any],
        guest_count: int,
        currency: str,
        food_cost: Dict,
        overhead: Dict,
        seasonal: Dict,
        benchmarks: Dict,
        discounts: Dict,
        history: Dict,
        elasticity: Dict,
        legacy: Dict,
        budget: float,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        total_cost_myr = (
            food_cost["adjusted_food_cost_myr"]
            + overhead["total_overhead_myr"]
            + seasonal["surcharge_myr"]
        )
        per_head_total_cost = round(total_cost_myr / guest_count, 2) if guest_count else 0

        # Final recommended price (from elasticity options)
        rec_price = elasticity.get("recommended_price_per_head_myr", per_head_total_cost * 1.2)
        rec_total = elasticity.get("recommended_total_quote_myr", rec_price * guest_count)
        rec_margin = round((1 - per_head_total_cost / rec_price) * 100, 1) if rec_price > 0 else 0

        # Budget fit
        budget_fit = rec_total <= budget if budget else None

        # All warnings
        all_warnings: List[str] = []
        all_warnings.extend(food_cost.get("drift_alerts", []))
        all_warnings.extend(seasonal.get("flags", []))
        if rec_margin < discounts["absolute_floor_pct"]:
            all_warnings.append(
                f"MARGIN ALERT: Recommended price yields {rec_margin}% gross margin — "
                f"below absolute floor of {discounts['absolute_floor_pct']}%. Senior review required."
            )
        if history.get("lessons"):
            for lesson in history["lessons"][:2]:
                all_warnings.append(f"HISTORICAL NOTE: {lesson}")

        return {
            # Summary
            "recommended_price_per_head_myr": rec_price,
            "recommended_total_quote_myr": rec_total,
            "estimated_gross_margin_pct": rec_margin,
            "budget_fit": budget_fit,
            "currency": currency,

            # Cost breakdown
            "cost_breakdown": {
                "food_cost_myr": food_cost["adjusted_food_cost_myr"],
                "overhead_myr": overhead["total_overhead_myr"],
                "seasonal_surcharge_myr": seasonal["surcharge_myr"],
                "total_cost_myr": round(total_cost_myr, 2),
                "per_head_cost_myr": per_head_total_cost,
            },

            # Tiered quote options (from elasticity)
            "quote_options": elasticity.get("options", []),
            "recommended_tier": elasticity.get("recommended_tier"),

            # Market position
            "market_benchmarks": benchmarks.get("tier_range", {}),
            "benchmark_id": benchmarks.get("matched_benchmark_id"),
            "market_positioning": benchmarks.get("our_positioning"),

            # Discounts applied
            "discounts_applied": discounts.get("applied_discounts", []),
            "total_discount_pct": discounts.get("total_discount_pct", 0.0),
            "proactive_suggestions": discounts.get("proactive_suggestions", []),

            # Historical context
            "comparable_past_quotes": history.get("comparable_quotes", []),
            "expected_gross_margin_pct": history.get("expected_gross_margin_pct", 0.0),
            "historical_lessons": history.get("lessons", []),

            # Expected value model
            "expected_value_myr": elasticity.get("recommended_ev_myr", 0.0),

            # Warnings and flags
            "all_warnings": all_warnings,

            # Legacy engine output (for backward compat with orchestrator)
            "pricing": legacy.get("pricing", {}),
            "cost_breakdown_legacy": legacy.get("cost_breakdown", {}),

            # Traceability
            "kb_sources": list(dict.fromkeys(kb_sources)),
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _map_pax_tier(guest_count: int) -> str:
        if guest_count <= 50:
            return "pax_20_50"
        elif guest_count <= 100:
            return "pax_51_100"
        elif guest_count <= 200:
            return "pax_101_200"
        elif guest_count <= 350:
            return "pax_201_350"
        elif guest_count <= 500:
            return "pax_351_500"
        else:
            return "pax_501_1000"

    @staticmethod
    def _parse_volume_trigger(trigger: str) -> Tuple[int, int]:
        """Extract low and high from trigger strings like 'guest_count >= 200 AND < 400'."""
        import re
        nums = re.findall(r"\d+", trigger)
        if len(nums) >= 2:
            return int(nums[0]), int(nums[1])
        elif len(nums) == 1:
            return int(nums[0]), 9999
        return 0, 9999

    @staticmethod
    def _parse_month(event_date: str) -> Optional[str]:
        if not event_date:
            return None
        try:
            dt = datetime.strptime(event_date[:10], "%Y-%m-%d")
            return dt.strftime("%B")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _map_winrate_key(event_type: str, currency: str) -> str:
        et = event_type.lower().replace(" ", "_").replace("-", "_")
        cur = currency.upper()
        mapping = {
            ("malay_wedding", "MYR"):               "malay_wedding_myr_per_head",
            ("corporate_lunch", "MYR"):             "corporate_lunch_myr_per_head",
            ("corporate_gala_dinner", "MYR"):       "corporate_gala_myr_per_head",
            ("product_launch", "MYR"):              "product_launch_cocktail_myr_per_head",
            ("corporate_gala", "MYR"):              "corporate_gala_myr_per_head",
        }
        return mapping.get((et, cur), "")

    def _build_reasoning_prompt(
        self, result: Dict[str, Any], customer_data: Dict[str, Any]
    ) -> str:
        event_type = customer_data.get("event_type", "")
        pax = result.get("cost_breakdown", {}).get("per_head_cost_myr", 0)
        rec = result.get("recommended_price_per_head_myr", 0)
        margin = result.get("estimated_gross_margin_pct", 0)
        options = result.get("quote_options", [])
        discounts = result.get("discounts_applied", [])
        warnings = result.get("all_warnings", [])
        ev = result.get("expected_value_myr", 0)

        parts = [
            f"Event: {event_type}, {customer_data.get('guest_count')} pax, "
            f"{customer_data.get('service_style', 'buffet')}, {customer_data.get('region', '')}.",
            f"Total cost per head: MYR {pax:.2f}. Recommended quote: MYR {rec:.2f}/head "
            f"({margin:.1f}% gross margin). Expected value of this quote: MYR {ev:,.0f}.",
        ]
        if options:
            opts_str = " | ".join(
                f"{o['tier'].title()} MYR {o['price_per_head_myr']}/head "
                f"({o['win_rate_pct']}% win, {o['gross_margin_pct']}% margin)"
                for o in options
            )
            parts.append(f"Quote options: {opts_str}.")
        if discounts:
            disc_str = ", ".join(d.get("name", "") for d in discounts)
            parts.append(f"Discounts applied: {disc_str}.")
        if warnings:
            parts.append(f"Key warning: {warnings[0]}.")
        parts.append(
            "In 3 sentences: justify the recommended price tier, flag the biggest financial risk, "
            "and suggest one specific action to protect margin or win the booking."
        )
        return " ".join(parts)
