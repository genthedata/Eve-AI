"""
Demand Planner — the intelligence core of the Inventory Agent.

Implements the 8-step RAG pipeline:
  1. Translate menu items + guest count -> raw ingredient list
     (via ingredient_recipe_map.yaml)
  2. Apply waste buffer adjustments
     (via spoilage_waste.yaml aggregate_insights)
  3. Subtract real-time stock (caller passes current stock dict)
  4. Check seasonal availability signals
     (via shared/seasonal_availability.yaml)
  5. Score and select best vendor per ingredient
     (via supplier_catalog.yaml + vendor_performance.yaml + procurement_sop.yaml)
  6. Apply approval rules (surface the approval tier for the total PO value)
  7. Return structured procurement plan with full traceability
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from app.tools.kb_yaml import YAMLKBSearch


# ── Ingredient translation ────────────────────────────────────────────────────

def build_ingredient_list(
    menu_items: List[str],
    guest_count: int,
    kb: YAMLKBSearch,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """
    Translate a list of dish names + guest count into a raw ingredient dict.

    Returns:
        ingredients: {procurement_key: {qty_g_or_ml, unit, dishes, cold_chain}}
        unmatched:   dish names not found in recipe map
    """
    recipe_map_data = kb.get("inventory/ingredient_recipe_map")
    dishes_data: List[Dict] = recipe_map_data.get("dishes", [])

    # Build a normalized lookup: lower-case name / normalized_key -> dish entry
    dish_index: Dict[str, Dict] = {}
    for dish in dishes_data:
        dish_index[dish.get("dish_name", "").lower()] = dish
        dish_index[dish.get("normalized_key", "").lower()] = dish

    ingredients: Dict[str, Dict[str, Any]] = {}
    unmatched: List[str] = []

    for menu_item in menu_items:
        key = menu_item.lower().replace(" ", "_").replace("-", "_")
        dish = dish_index.get(menu_item.lower()) or dish_index.get(key)

        if not dish:
            unmatched.append(menu_item)
            continue

        prep_waste_pct = float(dish.get("prep_waste_pct", 5)) / 100.0
        cold_chain = dish.get("cold_chain", "ambient")

        for ing in dish.get("ingredients_per_serving", []):
            p_key = ing.get("procurement_key", "")
            if not p_key:
                continue

            raw_qty = float(ing.get("qty", 0))
            unit = ing.get("unit", "g")

            # Scale to guest count with prep waste
            scaled_qty = raw_qty * guest_count * (1.0 + prep_waste_pct)

            if p_key not in ingredients:
                ingredients[p_key] = {
                    "qty": 0.0,
                    "unit": unit,
                    "dishes": [],
                    "cold_chain": cold_chain,
                }

            ingredients[p_key]["qty"] += scaled_qty
            if menu_item not in ingredients[p_key]["dishes"]:
                ingredients[p_key]["dishes"].append(menu_item)
            # Escalate cold chain requirement to strictest level
            _escalate_cold_chain(ingredients[p_key], cold_chain)

    # Convert g -> kg, ml -> l for standardisation
    _normalise_units(ingredients)
    return ingredients, unmatched


def _escalate_cold_chain(entry: Dict, incoming: str) -> None:
    rank = {"ambient": 0, "chilled": 1, "frozen": 2}
    current = entry.get("cold_chain", "ambient")
    if rank.get(incoming, 0) > rank.get(current, 0):
        entry["cold_chain"] = incoming


def _normalise_units(ingredients: Dict[str, Dict[str, Any]]) -> None:
    """Convert gram/ml quantities to kg/litre for procurement."""
    for entry in ingredients.values():
        unit = entry.get("unit", "g")
        if unit == "g":
            entry["qty"] = round(entry["qty"] / 1000.0, 4)
            entry["unit"] = "kg"
        elif unit == "ml":
            entry["qty"] = round(entry["qty"] / 1000.0, 4)
            entry["unit"] = "l"
        else:
            entry["qty"] = round(entry["qty"], 4)


# ── Waste buffer ──────────────────────────────────────────────────────────────

def apply_waste_buffers(
    ingredients: Dict[str, Dict[str, Any]],
    event_type: str,
    service_style: str,
    kb: YAMLKBSearch,
) -> Dict[str, Dict[str, Any]]:
    """
    Apply per-ingredient waste buffer factors from spoilage_waste.yaml,
    plus event-type and service-style global buffers.

    Modifies ingredients in-place (qty_with_buffer added).
    Returns the same dict enriched with buffer metadata.
    """
    waste_data = kb.get("inventory/spoilage_waste")
    agg = waste_data.get("aggregate_insights", {})

    event_buffers: Dict[str, int] = agg.get("event_type_buffer_pct", {})
    style_buffers: Dict[str, int] = agg.get("service_style_buffer_pct", {})
    high_waste: List[Dict] = agg.get("high_waste_items", [])
    zero_waste: List[Dict] = agg.get("zero_waste_items", [])

    base_event_pct = event_buffers.get(event_type.lower(), event_buffers.get("default", 10))
    base_style_pct = style_buffers.get(service_style.lower(), 8)
    base_buffer = 1.0 + (max(base_event_pct, base_style_pct) / 100.0)

    # Index waste rules by procurement_key
    high_waste_index: Dict[str, Dict] = {}
    for rule in high_waste:
        applies = rule.get("applies_to", ["all_events"])
        if "all_events" in applies or event_type.lower() in applies:
            high_waste_index[rule["procurement_key"]] = rule

    zero_waste_index: Dict[str, Dict] = {}
    for rule in zero_waste:
        applies = rule.get("applies_to", ["all_events"])
        if "all_events" in applies or event_type.lower() in applies:
            zero_waste_index[rule["procurement_key"]] = rule

    for p_key, entry in ingredients.items():
        raw_qty = entry["qty"]
        buffer_factor = base_buffer
        buffer_reason = f"base buffer ({max(base_event_pct, base_style_pct)}% for {event_type}/{service_style})"

        if p_key in zero_waste_index:
            rule = zero_waste_index[p_key]
            buffer_factor = rule.get("adjustment_factor", 1.15)
            buffer_reason = f"zero-waste override: {rule.get('category','')} runs out fast (+{int((buffer_factor-1)*100)}%)"

        elif p_key in high_waste_index:
            rule = high_waste_index[p_key]
            buffer_factor = min(buffer_factor, rule.get("adjustment_factor", 0.75))
            buffer_reason = f"high-waste reduction: {rule.get('category','')} historically wasted (factor {buffer_factor:.2f})"

        buffered_qty = round(raw_qty * buffer_factor, 4)
        entry["qty_raw"] = raw_qty
        entry["qty_with_buffer"] = buffered_qty
        entry["buffer_factor"] = buffer_factor
        entry["buffer_reason"] = buffer_reason

    return ingredients


# ── Seasonal checks ───────────────────────────────────────────────────────────

def check_seasonal_availability(
    ingredients: Dict[str, Dict[str, Any]],
    location: str,
    event_date: str,
    kb: YAMLKBSearch,
) -> List[Dict[str, Any]]:
    """
    Cross-reference ingredient list against seasonal_availability.yaml.
    Returns list of availability warnings that the agent should surface.
    """
    seasonal_data = kb.get("shared/seasonal_availability")
    disruptions: List[Dict] = seasonal_data.get("supply_disruption_alerts", [])
    calendar: List[Dict] = seasonal_data.get("calendar", [])

    warnings: List[Dict[str, Any]] = []

    # Extract month from event_date (YYYY-MM-DD)
    event_month: Optional[str] = None
    if event_date and len(event_date) >= 7:
        try:
            from datetime import datetime
            dt = datetime.strptime(event_date[:7], "%Y-%m")
            event_month = dt.strftime("%B")
        except Exception:
            pass

    # Check disruption alerts
    location_lower = location.lower()
    for alert in disruptions:
        alert_region = str(alert.get("region", "")).lower()
        if location_lower not in alert_region and alert_region not in location_lower:
            continue
        affected = [str(a).lower() for a in alert.get("affected_ingredients", [])]
        matched_keys = [k for k in ingredients if any(a in k for a in affected)]
        if matched_keys:
            warnings.append({
                "type": "disruption_alert",
                "disruption": alert.get("disruption"),
                "affected_procurement_keys": matched_keys,
                "price_impact_pct": alert.get("price_impact_pct"),
                "mitigation": alert.get("mitigation"),
            })

    # Check calendar for out-of-season ingredients
    if event_month:
        for cal_entry in calendar:
            peak_months = cal_entry.get("peak_months", [])
            off_peak_months = cal_entry.get("off_peak_months", [])
            ingredient_name = cal_entry.get("ingredient", "").lower()
            matched_key = next((k for k in ingredients if ingredient_name in k), None)
            if matched_key and event_month in off_peak_months:
                warnings.append({
                    "type": "seasonal_off_peak",
                    "ingredient": cal_entry.get("ingredient"),
                    "procurement_key": matched_key,
                    "event_month": event_month,
                    "price_index": cal_entry.get("off_peak_price_index"),
                    "notes": cal_entry.get("notes", ""),
                })

    return warnings


# ── Vendor selection ──────────────────────────────────────────────────────────

def select_vendor(
    procurement_key: str,
    qty_needed: float,
    unit: str,
    require_halal: bool,
    region: str,
    is_urgent: bool,
    kb: YAMLKBSearch,
) -> Dict[str, Any]:
    """
    Select the best vendor for a procurement key using:
      - preferred_vendor_priority from procurement_sop.yaml
      - vendor_performance.yaml scoring
      - supplier_catalog.yaml for product details and credit limits
      - halal filter (hard filter, not a scoring factor)

    Returns a vendor assignment dict with:
      supplier_id, name, sku, price_per_unit, lead_days,
      total_order_qty, total_cost_estimate, cold_chain,
      score, notes, substitution_available
    """
    sop_data = kb.get("inventory/procurement_sop")
    perf_data = kb.get("inventory/vendor_performance")
    catalog_data = kb.get("inventory/supplier_catalog")

    priority_map: Dict[str, List[str]] = sop_data.get("preferred_vendor_priority", {})
    perf_list: List[Dict] = perf_data.get("suppliers", [])
    catalog_list: List[Dict] = catalog_data.get("suppliers", [])
    blacklist: List[Dict] = perf_data.get("blacklisted_suppliers", []) or []
    weights: Dict = perf_data.get("vendor_selection_weights", {
        "on_time_delivery": 0.35, "quality_pass_rate": 0.35,
        "price_stability": 0.15, "urgent_responsiveness": 0.15,
    })
    resp_scores: Dict = perf_data.get("responsiveness_scores", {
        "very_high": 1.0, "high": 0.80, "medium": 0.55, "low": 0.25,
    })

    blacklisted_ids = {b.get("vendor_id") for b in blacklist}
    perf_index: Dict[str, Dict] = {p["supplier_id"]: p for p in perf_list}
    catalog_index: Dict[str, Dict] = {c["supplier_id"]: c for c in catalog_list}

    preferred_ids = priority_map.get(procurement_key, [])
    if not preferred_ids:
        # Fall back to global substitution index
        global_index = catalog_data.get("global_substitution_index", {})
        fallbacks = global_index.get(procurement_key, [])
        preferred_ids = [f["supplier_id"] for f in sorted(fallbacks, key=lambda x: x.get("priority", 99))]

    region_lower = region.lower()

    def _score_supplier(sup_id: str) -> float:
        if sup_id in blacklisted_ids:
            return -1.0
        perf = perf_index.get(sup_id, {})
        on_time = perf.get("on_time_delivery_rate", 0.5)
        quality = perf.get("quality_pass_rate", 0.5)
        price_stab = perf.get("price_stability_score", 0.5)
        resp = resp_scores.get(perf.get("urgent_order_responsiveness", "medium"), 0.55)

        if is_urgent:
            return on_time * 0.25 + quality * 0.25 + price_stab * 0.0 + resp * 0.50
        return (on_time * weights.get("on_time_delivery", 0.35)
                + quality * weights.get("quality_pass_rate", 0.35)
                + price_stab * weights.get("price_stability", 0.15)
                + resp * weights.get("urgent_responsiveness", 0.15))

    best_supplier: Optional[Dict] = None
    best_product: Optional[Dict] = None
    best_score = -1.0

    for sup_id in preferred_ids:
        if sup_id in blacklisted_ids:
            continue
        cat = catalog_index.get(sup_id)
        if not cat:
            continue

        # Region filter — prefer local supplier
        sup_regions = [r.lower() for r in cat.get("countries_served", [])]
        if region_lower and not any(region_lower in r for r in sup_regions):
            continue

        # Halal filter
        if require_halal and not cat.get("halal_certified", False):
            continue

        # Find a matching product
        matching_product = None
        for prod in cat.get("products", []):
            if prod.get("procurement_key") == procurement_key:
                if require_halal and prod.get("halal") is False:
                    continue
                matching_product = prod
                break

        if not matching_product:
            continue

        score = _score_supplier(sup_id)
        if score > best_score:
            best_score = score
            best_supplier = cat
            best_product = matching_product

    if not best_supplier or not best_product:
        return {
            "procurement_key": procurement_key,
            "status": "no_vendor_found",
            "require_halal": require_halal,
            "notes": "No qualifying vendor found. Manual sourcing required.",
        }

    # Calculate order quantity (round up to MOQ increments)
    unit_kg = float(best_product.get("unit_kg", 1.0))
    moq = float(best_product.get("moq", 1))
    increment = float(best_product.get("order_increment", 1))
    units_needed = qty_needed / unit_kg
    units_ordered = max(moq, math.ceil(units_needed / increment) * increment)

    # Estimate cost (use first available price field)
    unit_price = (best_product.get("price_per_kg_php")
                  or best_product.get("price_per_kg_myr")
                  or best_product.get("price_per_kg_sgd")
                  or best_product.get("price_per_l_php")
                  or best_product.get("price_per_l_sgd")
                  or 0)

    total_cost = round(float(unit_price) * units_ordered * unit_kg, 2) if unit_price else None

    return {
        "procurement_key": procurement_key,
        "status": "assigned",
        "supplier_id": best_supplier["supplier_id"],
        "supplier_name": best_supplier["name"],
        "sku": best_product["sku"],
        "product_name": best_product["name"],
        "qty_needed_kg_or_l": round(qty_needed, 3),
        "units_to_order": units_ordered,
        "unit_size_kg": unit_kg,
        "total_ordered_kg_or_l": round(units_ordered * unit_kg, 3),
        "unit_price": unit_price,
        "estimated_cost": total_cost,
        "currency": _infer_currency(best_product),
        "lead_days": best_product.get("urgent_lead_hours" if is_urgent else "lead_days"),
        "cold_chain": best_product.get("cold_chain", "ambient"),
        "halal_certified": best_supplier.get("halal_certified", False),
        "vendor_score": round(best_score, 3),
        "is_urgent": is_urgent,
        "notes": best_supplier.get("notes", ""),
    }


def _infer_currency(product: Dict) -> str:
    if "price_php" in product or "price_per_kg_php" in product:
        return "PHP"
    if "price_myr" in product or "price_per_kg_myr" in product:
        return "MYR"
    if "price_sgd" in product or "price_per_kg_sgd" in product:
        return "SGD"
    return "LOCAL"


# ── Approval tier check ───────────────────────────────────────────────────────

def check_approval_tier(
    total_cost: float,
    currency: str,
    is_urgent: bool,
    kb: YAMLKBSearch,
) -> Dict[str, Any]:
    """
    Returns the required approval tier for the total PO value.
    """
    sop_data = kb.get("inventory/procurement_sop")
    thresholds_list: List[Dict] = []
    for proc in sop_data.get("procedures", []):
        if proc.get("sop_id") == "SOP-PROC-002":
            thresholds_list = proc.get("thresholds", [])
            break

    key = f"max_{currency.lower()}"
    min_key = f"min_{currency.lower()}"

    approval_level = "Self-Approval"
    approver = "Procurement Lead"

    for tier in sorted(thresholds_list, key=lambda t: t.get(key, float("inf"))):
        max_val = tier.get(key)
        min_val = tier.get(min_key)
        if max_val is not None and total_cost <= max_val:
            approval_level = tier.get("level", approval_level)
            approver = tier.get("approver", approver)
            break
        if min_val is not None and total_cost >= min_val:
            approval_level = tier.get("level", approval_level)
            approver = tier.get("approver", approver)

    if is_urgent:
        # Urgent orders escalate one level
        escalation_map = {
            "Self-Approval": "Manager Approval",
            "Manager Approval": "Director Approval",
            "Director Approval": "Executive Approval",
        }
        approval_level = escalation_map.get(approval_level, approval_level)
        approver_map = {
            "Manager Approval": "Operations Manager",
            "Director Approval": "Director of Operations",
            "Executive Approval": "CEO or CFO",
        }
        approver = approver_map.get(approval_level, approver)

    return {
        "approval_level": approval_level,
        "approver": approver,
        "total_cost": total_cost,
        "currency": currency,
        "is_urgent": is_urgent,
    }


# ── Full pipeline ─────────────────────────────────────────────────────────────

def build_procurement_plan(
    menu_items: List[str],
    guest_count: int,
    current_stock: Dict[str, float],
    event_type: str,
    service_style: str,
    require_halal: bool,
    region: str,
    event_date: str,
    kb: YAMLKBSearch,
    is_urgent: bool = False,
) -> Dict[str, Any]:
    """
    Full 8-step procurement planning pipeline.

    Returns a comprehensive procurement plan dict with:
      - ingredient_breakdown: per-key raw->buffered quantities
      - vendor_assignments: best supplier per ingredient
      - seasonal_warnings: availability risk flags
      - shortages_after_stock: what still needs ordering
      - approval_requirement: PO approval tier
      - kb_sources: traceability list
    """
    kb_sources: List[str] = []

    # Step 1: Translate menu to raw ingredients
    ingredients, unmatched = build_ingredient_list(menu_items, guest_count, kb)
    kb_sources.append(f"inventory/ingredient_recipe_map -> {len(ingredients)} ingredients from {len(menu_items)} dishes")

    # Step 2: Apply waste buffers
    ingredients = apply_waste_buffers(ingredients, event_type, service_style, kb)
    kb_sources.append(f"inventory/spoilage_waste -> waste buffers applied for {event_type}/{service_style}")

    # Step 3: Subtract current stock
    procurement_needed: Dict[str, float] = {}
    stock_offsets: Dict[str, float] = {}
    for p_key, entry in ingredients.items():
        buffered = entry.get("qty_with_buffer", entry["qty"])
        on_hand = current_stock.get(p_key, 0.0)
        net = max(0.0, buffered - on_hand)
        procurement_needed[p_key] = round(net, 4)
        stock_offsets[p_key] = round(min(on_hand, buffered), 4)

    # Step 4: Seasonal availability check
    seasonal_warnings = check_seasonal_availability(ingredients, region, event_date, kb)
    if seasonal_warnings:
        kb_sources.append(f"shared/seasonal_availability -> {len(seasonal_warnings)} warning(s)")

    # Step 5 + 6: Vendor selection + approval check
    vendor_assignments: List[Dict[str, Any]] = []
    total_cost_estimate = 0.0
    primary_currency = "PHP"

    for p_key, net_qty in procurement_needed.items():
        if net_qty <= 0:
            continue
        entry = ingredients[p_key]
        assignment = select_vendor(
            procurement_key=p_key,
            qty_needed=net_qty,
            unit=entry.get("unit", "kg"),
            require_halal=require_halal,
            region=region,
            is_urgent=is_urgent,
            kb=kb,
        )
        vendor_assignments.append(assignment)
        if assignment.get("status") == "assigned" and assignment.get("estimated_cost"):
            total_cost_estimate += assignment["estimated_cost"]
            primary_currency = assignment.get("currency", primary_currency)
        kb_sources.append(
            f"inventory/supplier_catalog + vendor_performance -> "
            f"{p_key} -> {assignment.get('supplier_name', 'unassigned')} "
            f"(score: {assignment.get('vendor_score', 'N/A')})"
        )

    # Step 7: Approval tier
    approval = check_approval_tier(total_cost_estimate, primary_currency, is_urgent, kb)
    kb_sources.append(f"inventory/procurement_sop -> approval: {approval['approval_level']} ({approval['approver']})")

    shortages = [v for v in vendor_assignments if v.get("status") == "no_vendor_found"]
    assigned = [v for v in vendor_assignments if v.get("status") == "assigned"]

    return {
        "menu_items": menu_items,
        "guest_count": guest_count,
        "unmatched_dishes": unmatched,
        "ingredient_breakdown": {
            p_key: {
                "qty_raw_kg_or_l": round(entry.get("qty_raw", entry["qty"]), 4),
                "qty_buffered_kg_or_l": round(entry.get("qty_with_buffer", entry["qty"]), 4),
                "qty_on_hand": stock_offsets.get(p_key, 0.0),
                "qty_to_procure": procurement_needed.get(p_key, 0.0),
                "unit": entry.get("unit", "kg"),
                "cold_chain": entry.get("cold_chain", "ambient"),
                "buffer_reason": entry.get("buffer_reason", ""),
                "from_dishes": entry.get("dishes", []),
            }
            for p_key, entry in ingredients.items()
        },
        "vendor_assignments": assigned,
        "vendor_assignment_failures": shortages,
        "seasonal_warnings": seasonal_warnings,
        "total_cost_estimate": round(total_cost_estimate, 2),
        "currency": primary_currency,
        "approval_requirement": approval,
        "kb_sources": kb_sources,
        "is_urgent": is_urgent,
        "require_halal": require_halal,
    }
