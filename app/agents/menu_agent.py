"""
MenuPlanningAgent — 8-step KB-driven menu composition pipeline.

Step 1: Dietary & allergen rules   → establish hard constraints
Step 2: Recipe library filter      → filter dishes by cuisine/dietary/service/scale
Step 3: Cuisine trends & balance   → rank and balance into a coherent menu
Step 4: Portion & yield validation → validate quantities; flag imbalances
Step 5: Seasonal availability      → flag out-of-season ingredients; suggest substitutions
Step 6: Equipment capability       → validate executability at venue
Step 7: Past menu performance      → score proposed menu against historical outcomes
Step 8: Output                     → ranked menu options + ingredient brief + cost basis

Platform: swappable to Microsoft Agent Framework worker (placeholder) — app.agents.platform_bridge
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.agents.llm_mixin import LLMReasoningMixin
from app.providers.base import LLMProvider
from app.tools.kb_yaml import YAMLKBSearch
from app.tools.recipe_catalogue import RecipeCatalogueTool


class MenuPlanningAgent(LLMReasoningMixin):
    def __init__(
        self,
        recipe_catalogue: RecipeCatalogueTool,
        provider: Optional[LLMProvider] = None,
        kb: Optional[YAMLKBSearch] = None,
    ) -> None:
        self._recipes = recipe_catalogue
        self._kb = kb or YAMLKBSearch()
        self.set_provider(provider)

    # ── Public entry point ─────────────────────────────────────────────────────

    def process(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produce a complete menu plan from a structured customer brief.

        Expected keys in customer_data:
            guest_count         int
            dietary_constraints list[str]   e.g. ['halal', 'nut_free']
            event_type          str         e.g. 'malay_wedding', 'corporate_gala'
            service_style       str         e.g. 'buffet', 'plated_5_course'
            cuisine             str|None    e.g. 'malay', 'pan_asian'
            venue_type          str|None    e.g. 'indoor_ballroom_no_gas'
            event_date          str|None    ISO date or 'YYYY-MM-DD'
            region              str|None    e.g. 'Malaysia', 'Philippines'
            budget_per_head_myr float|None
        """
        guest_count = int(customer_data.get("guest_count", 100))
        dietary = [d.lower() for d in customer_data.get("dietary_constraints", [])]
        event_type = customer_data.get("event_type", "default")
        service_style = customer_data.get("service_style", "buffet")
        cuisine = customer_data.get("cuisine", "")
        venue_type = customer_data.get("venue_type", "outdoor_tent_partial")
        event_date = customer_data.get("event_date", "")
        region = customer_data.get("region", "Malaysia")
        budget_per_head = customer_data.get("budget_per_head_myr")

        kb_sources: List[str] = []

        # ── Step 1: Dietary constraints ───────────────────────────────────────
        constraints = self._step1_dietary_constraints(dietary, event_type, kb_sources)

        # ── Step 2: Recipe library filter ─────────────────────────────────────
        filtered_dishes = self._step2_filter_recipes(
            dietary, event_type, service_style, cuisine, guest_count, kb_sources
        )

        # ── Step 3: Cuisine trends + menu balance ─────────────────────────────
        menu_plan = self._step3_cuisine_trends_balance(
            event_type, service_style, filtered_dishes, kb_sources
        )

        # ── Step 4: Portion & yield validation ───────────────────────────────
        yield_data = self._step4_portion_validation(
            menu_plan["selected_dishes"], guest_count, event_type, service_style, kb_sources
        )

        # ── Step 5: Seasonal availability ─────────────────────────────────────
        event_month = self._parse_month(event_date)
        seasonal_warnings = self._step5_seasonal_check(
            menu_plan["selected_dishes"], event_month, region, kb_sources
        )

        # ── Step 6: Equipment capability ──────────────────────────────────────
        equipment_result = self._step6_equipment_check(
            menu_plan["selected_dishes"], venue_type, guest_count, kb_sources
        )

        # ── Step 7: Past performance scoring ──────────────────────────────────
        performance = self._step7_performance_score(
            menu_plan["selected_dishes"], event_type, kb_sources
        )

        # ── Step 8: Assemble output ────────────────────────────────────────────
        result = self._assemble_output(
            customer_data=customer_data,
            guest_count=guest_count,
            dietary=dietary,
            event_type=event_type,
            service_style=service_style,
            constraints=constraints,
            menu_plan=menu_plan,
            yield_data=yield_data,
            seasonal_warnings=seasonal_warnings,
            equipment_result=equipment_result,
            performance=performance,
            budget_per_head=budget_per_head,
            kb_sources=kb_sources,
        )

        # ── LLM reasoning ─────────────────────────────────────────────────────
        reasoning = self.reason(
            prompt=self._build_reasoning_prompt(result, customer_data),
            system_prompt=(
                "You are the Menu Planning Agent for a professional catering company in Southeast Asia. "
                "You produce concise, expert menu recommendations grounded in cultural context, "
                "dietary compliance, and operational feasibility. Be direct and practical."
            ),
        )
        if reasoning:
            result["reasoning"] = reasoning

        return result

    # ── Step 1 ─────────────────────────────────────────────────────────────────

    def _step1_dietary_constraints(
        self, dietary: List[str], event_type: str, kb_sources: List[str]
    ) -> Dict[str, Any]:
        """Query dietary & allergen rules to establish hard constraints."""
        forbidden: List[str] = []
        must_include: List[str] = []
        allergen_flags: List[str] = []
        critical_allergens: List[str] = []
        substitution_hints: List[str] = []

        if not dietary:
            return {
                "forbidden": forbidden,
                "must_include": must_include,
                "allergen_flags": allergen_flags,
                "critical_allergens": critical_allergens,
                "substitution_hints": substitution_hints,
            }

        kb_data = self._kb.get("customer/dietary_restrictions")
        profiles = kb_data.get("profiles", []) if isinstance(kb_data, dict) else []

        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            pid = str(profile.get("id", "")).lower()
            if pid not in dietary:
                continue

            kb_sources.append(f"customer/dietary_restrictions -> {pid}")
            forbidden.extend(profile.get("forbidden", []))

            # Kitchen constraints → must_include / notes
            for constraint in profile.get("kitchen_prep_constraints", []):
                must_include.append(f"[{pid}] {constraint}")

            # Cross-contamination risks
            for risk in profile.get("cross_contamination_risks", []):
                allergen_flags.append(f"[{pid}] CROSS-CONTAMINATION RISK: {risk}")

            # Substitution hints
            subs = profile.get("common_substitutions", [])
            if isinstance(subs, list):
                substitution_hints.extend(subs)

        # Critical allergens
        allergen_data = kb_data.get("allergen_severity", []) if isinstance(kb_data, dict) else []
        _critical_allergen_map = {
            "nut_free": ["peanuts", "tree nuts"],
            "gluten_free": ["gluten", "wheat", "barley"],
            "shellfish_free": ["shellfish", "shrimp", "prawn"],
        }
        candidate_allergens = set()
        for d in dietary:
            for mapped in _critical_allergen_map.get(d, []):
                candidate_allergens.add(mapped)

        for entry in allergen_data:
            if not isinstance(entry, dict):
                continue
            allergen_name = str(entry.get("allergen", "")).lower()
            severity = str(entry.get("severity", "")).lower()
            if severity == "critical" and any(a in allergen_name for a in candidate_allergens):
                critical_allergens.append(
                    f"CRITICAL ALLERGEN: {entry.get('allergen')} — "
                    f"{entry.get('response', 'Remove from menu')}"
                )

        # Normalise forbidden items to strings (YAML may yield dicts or strings)
        forbidden_strs = list(dict.fromkeys(
            str(f) if not isinstance(f, str) else f for f in forbidden
        ))

        return {
            "forbidden": forbidden_strs,
            "must_include": must_include,
            "allergen_flags": allergen_flags,
            "critical_allergens": critical_allergens,
            "substitution_hints": substitution_hints,
        }

    # ── Step 2 ─────────────────────────────────────────────────────────────────

    def _step2_filter_recipes(
        self,
        dietary: List[str],
        event_type: str,
        service_style: str,
        cuisine: str,
        guest_count: int,
        kb_sources: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Filter recipe library by: dietary flags, occasion, service style,
        cuisine preference, and scale performance vs guest count.
        """
        kb_data = self._kb.get("menu/recipe_library")
        if not isinstance(kb_data, dict):
            return []

        recipes = kb_data.get("recipes", [])
        if not recipes:
            return []

        # Use dietary filter index for fast initial pass
        dietary_index = kb_data.get("dietary_filter_index", {})
        cuisine_index = kb_data.get("cuisine_index", {})
        occasion_index = kb_data.get("occasion_index", {})

        # Build candidate set from dietary index
        if dietary:
            candidate_dishes: Optional[set] = None
            for d in dietary:
                index_key = d.replace("-", "_")
                allowed = set(dietary_index.get(index_key, dietary_index.get(d, [])))
                if not allowed:
                    continue
                candidate_dishes = allowed if candidate_dishes is None else candidate_dishes & allowed
            # If every constraint was unrecognised (e.g. "none", "vegetarian-option",
            # "seafood-allergy-table-3"), treat as no dietary filter rather than
            # rejecting everything.
            if candidate_dishes is None:
                candidate_dishes = None   # all dishes allowed
        else:
            candidate_dishes = None  # No filter — all dishes allowed

        # Cuisine filter — soft preference: restrict only if it leaves enough dishes (>=4)
        if cuisine:
            cuisine_dishes = set()
            for c_key, dish_list in cuisine_index.items():
                if cuisine.lower() in c_key.lower() or c_key.lower() in cuisine.lower():
                    cuisine_dishes.update(dish_list)
            if cuisine_dishes:
                combined = (
                    cuisine_dishes if candidate_dishes is None
                    else candidate_dishes & cuisine_dishes
                )
                # Only apply strict cuisine filter if it leaves at least 4 dishes
                if len(combined) >= 4:
                    candidate_dishes = combined
                # Otherwise treat cuisine as boost via occasion_index only

        # Occasion filter bonus (soft filter — we boost, don't exclude)
        occasion_dishes: set = set()
        for occ_key, dish_list in occasion_index.items():
            if event_type.lower().replace(" ", "_") in occ_key.lower():
                occasion_dishes.update(dish_list)

        # Now filter individual recipes from the full recipe list
        filtered: List[Dict[str, Any]] = []
        for recipe in recipes:
            if not isinstance(recipe, dict):
                continue
            name = recipe.get("dish_name", "")

            # Hard dietary filter
            if candidate_dishes is not None and name not in candidate_dishes:
                continue

            # Service style filter
            compat = recipe.get("service_style_compatibility", [])
            if compat and service_style not in compat and "any" not in compat:
                # Check partial match (e.g. 'buffet' in 'semi_buffet')
                if not any(service_style in s or s in service_style for s in compat):
                    continue

            # Scale filter — skip 'poor' scale for large events
            scale = recipe.get("scale_performance", "good")
            if guest_count > 150 and scale == "poor":
                continue

            # Score boost if in occasion index
            recipe["_occasion_boost"] = 1 if name in occasion_dishes else 0
            filtered.append(recipe)

        if filtered:
            kb_sources.append(
                f"menu/recipe_library -> {len(filtered)} dishes matched "
                f"({dietary}, {event_type}, {service_style})"
            )

        return filtered

    # ── Step 3 ─────────────────────────────────────────────────────────────────

    def _step3_cuisine_trends_balance(
        self,
        event_type: str,
        service_style: str,
        filtered_dishes: List[Dict[str, Any]],
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """
        Use menu balance templates and cuisine trends to select and rank
        a coherent set of dishes.
        """
        kb_data = self._kb.get("menu/cuisine_trends")
        templates = kb_data.get("menu_balance_templates", []) if isinstance(kb_data, dict) else []
        trends = kb_data.get("current_trends", []) if isinstance(kb_data, dict) else []
        quality_signals = kb_data.get("quality_signals", {}) if isinstance(kb_data, dict) else {}
        pairing_rules = kb_data.get("flavour_pairing_rules", []) if isinstance(kb_data, dict) else []

        # Match template
        matched_template: Optional[Dict] = None
        for tpl in templates:
            if not isinstance(tpl, dict):
                continue
            tpl_event = tpl.get("event_type", "")
            tpl_style = tpl.get("service_style", "")
            if (event_type.lower().replace(" ", "_") in tpl_event.lower().replace(" ", "_")
                    or tpl_event.lower() in event_type.lower()):
                if tpl_style in service_style or service_style in tpl_style or not tpl_style:
                    matched_template = tpl
                    break

        if matched_template:
            kb_sources.append(
                f"menu/cuisine_trends -> template {matched_template.get('template_id','')}"
            )

        # Relevant trends
        matched_trends: List[str] = []
        for trend in trends:
            if not isinstance(trend, dict):
                continue
            applies_to = trend.get("applicable_event_types", trend.get("event_types", []))
            if any(event_type.lower() in str(e).lower() for e in applies_to) or "any" in applies_to:
                matched_trends.append(trend.get("name", ""))
                kb_sources.append(f"menu/cuisine_trends -> trend: {trend.get('name', '')}")
                if len(matched_trends) >= 2:
                    break

        # Relevant pairing rules
        relevant_pairings: List[str] = []
        for rule in pairing_rules:
            if not isinstance(rule, dict):
                continue
            relevant_pairings.append(rule.get("principle", ""))

        # Group dishes by category AND by subcategory for finer slot matching
        by_category: Dict[str, List[Dict]] = {}
        by_subcategory: Dict[str, List[Dict]] = {}
        for dish in filtered_dishes:
            cat = dish.get("category", "other")
            subcat = dish.get("subcategory", "")
            by_category.setdefault(cat, []).append(dish)
            if subcat:
                by_subcategory.setdefault(subcat, []).append(dish)

        # Sort each category: occasion-boosted dishes first, then by skill level descending
        # (more skilled dishes preferred for quality events)
        for cat in by_category:
            by_category[cat].sort(
                key=lambda d: (d.get("_occasion_boost", 0), d.get("skill_level", 3)),
                reverse=True,
            )
        for scat in by_subcategory:
            by_subcategory[scat].sort(
                key=lambda d: (d.get("_occasion_boost", 0), d.get("skill_level", 3)),
                reverse=True,
            )

        # Select dishes from template structure, or fall back to category-based selection
        selected_dishes: List[str] = []
        must_include_from_template: List[str] = []
        structure_notes: Dict[str, int] = {}

        if matched_template:
            structure = matched_template.get("structure", {})
            structure_notes = {k: v for k, v in structure.items() if isinstance(v, int)}
            must_include_from_template = matched_template.get("must_include", [])

            # Category slot filling — map template slot names → dish categories/subcategories
            # Each entry maps slot_name → list of (category, subcategory_filter) tuples
            category_slot_map: Dict[str, List[str]] = {
                "protein_mains":     ["main"],
                "protein_main":      ["main"],
                "rice_or_staple":    ["staple"],
                "rice_or_noodle":    ["staple"],
                "vegetable_sides":   ["side"],
                "vegetable_side":    ["side"],
                "appetizers":        ["appetizer"],
                "appetizer":         ["appetizer"],
                "amuse_bouche":      ["appetizer"],
                "cold_platter":      ["appetizer"],
                "desserts":          ["dessert"],
                "dessert":           ["dessert"],
                "dessert_warm":      ["dessert"],
                "dessert_cold":      ["dessert"],
                "soup":              ["soup"],          # subcategory lookup first
                "noodle_or_rice":    ["staple"],
                "vegetarian_main":   ["main"],
                "poultry":           ["main"],
                "red_meat":          ["main"],
                "seafood":           ["main"],
                "finger_sandwiches": ["appetizer"],
                "scones":            ["dessert"],
                "pastries_petits_fours": ["dessert"],
                "cakes":             ["dessert"],
            }

            already_selected: set = set()

            for slot_name, slot_count in structure_notes.items():
                cats = category_slot_map.get(slot_name, [slot_name.replace("_", " ")])
                candidates: List[Dict] = []

                # Soup slot: prefer subcategory 'soup' over generic side
                if slot_name == "soup":
                    candidates = list(by_subcategory.get("soup", []))
                    if not candidates:
                        candidates = [
                            d for d in by_category.get("side", [])
                            if "soup" in d.get("subcategory", "").lower()
                            or "soup" in d.get("dish_name", "").lower()
                        ]
                else:
                    for cat in cats:
                        # Try exact category match first
                        for dish in by_category.get(cat, []):
                            if dish not in candidates:
                                candidates.append(dish)
                        # For main dishes, also check if subcategory matches slot
                        if slot_name in {"poultry", "red_meat", "seafood"}:
                            for dish in by_subcategory.get(slot_name, []):
                                if dish not in candidates:
                                    candidates.insert(0, dish)

                added = 0
                for candidate in candidates:
                    name = candidate.get("dish_name", "")
                    if name and name not in already_selected and added < slot_count:
                        selected_dishes.append(name)
                        already_selected.add(name)
                        added += 1

        else:
            # No template match — pick top-scoring dishes across categories
            already_selected = set()
            for cat in ["appetizer", "main", "staple", "side", "dessert"]:
                dishes_in_cat = by_category.get(cat, [])
                for d in dishes_in_cat[:2]:
                    name = d.get("dish_name", "")
                    if name and name not in already_selected:
                        selected_dishes.append(name)
                        already_selected.add(name)

        # Ensure must-include dishes are present (handle 'A or B' logic)
        available_names = {d.get("dish_name") for d in filtered_dishes}
        for mi in must_include_from_template:
            parts = [p.strip() for p in str(mi).split(" or ")]
            already_in = any(p in already_selected for p in parts)
            if not already_in:
                for p in parts:
                    if p in available_names:
                        selected_dishes.insert(0, p)
                        already_selected.add(p)
                        break

        return {
            "selected_dishes": list(dict.fromkeys(selected_dishes)),  # preserve order, de-dup
            "template_used": matched_template.get("template_id") if matched_template else None,
            "template_quality_notes": matched_template.get("quality_notes") if matched_template else None,
            "relevant_trends": matched_trends,
            "pairing_principles": relevant_pairings[:3],
            "structure_target": structure_notes,
            "amateurism_flags": quality_signals.get("amateurism_red_flags", []),
        }

    # ── Step 4 ─────────────────────────────────────────────────────────────────

    def _step4_portion_validation(
        self,
        selected_dishes: List[str],
        guest_count: int,
        event_type: str,
        service_style: str,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """
        Validate quantities using empirical consumption data.
        Returns adjusted quantity multipliers and flags.
        """
        kb_data = self._kb.get("menu/portion_yield")
        if not isinstance(kb_data, dict):
            return {"adjustments": [], "warnings": []}

        consumption_rates = kb_data.get("consumption_rates", [])
        event_buffers = kb_data.get("event_waste_buffers", {})
        dish_notes = kb_data.get("dish_yield_notes", [])

        adjustments: List[Dict] = []
        warnings: List[str] = []

        # Map event_type to consumption event key
        event_key = self._map_event_key(event_type, service_style)
        waste_buffer = event_buffers.get(
            event_type.replace(" ", "_").replace("-", "_"),
            event_buffers.get("default", 1.10),
        )

        for rate_entry in consumption_rates:
            if not isinstance(rate_entry, dict):
                continue
            category = rate_entry.get("category", "")
            by_event = rate_entry.get("by_event_type", {})
            rate = by_event.get(event_key, rate_entry.get("baseline_rate", 1.0))
            notes = rate_entry.get("notes", "")

            if rate < 0.75:
                warnings.append(
                    f"{category}: Only {int(rate*100)}% consumed at {event_key} events. "
                    f"Reduce order by {int((1-rate)*100)}%."
                )
            elif rate > 1.0:
                warnings.append(
                    f"{category}: {int(rate*100)}% consumption (runs out). "
                    f"Order {int((rate-1)*100)}% extra."
                )

            adjustments.append({
                "category": category,
                "consumption_rate": rate,
                "waste_buffer": waste_buffer,
                "effective_multiplier": round(rate * waste_buffer, 2),
                "notes": notes[:120] if notes else "",
            })

        # Dish-specific yield notes for selected dishes
        dish_yield_flags: List[str] = []
        for note in dish_notes:
            if not isinstance(note, dict):
                continue
            if note.get("dish") in selected_dishes:
                flag_text = note.get("notes", "")
                if flag_text:
                    dish_yield_flags.append(f"{note['dish']}: {flag_text}")

        if adjustments:
            kb_sources.append(f"menu/portion_yield -> {event_key} consumption rates")

        return {
            "adjustments": adjustments,
            "warnings": warnings,
            "dish_yield_flags": dish_yield_flags,
            "waste_buffer_applied": waste_buffer,
        }

    # ── Step 5 ─────────────────────────────────────────────────────────────────

    def _step5_seasonal_check(
        self,
        selected_dishes: List[str],
        event_month: Optional[str],
        region: str,
        kb_sources: List[str],
    ) -> List[str]:
        """
        Check seasonal ingredient availability for selected dishes.
        Returns list of warnings and substitution suggestions.
        """
        if not event_month:
            return []

        kb_data = self._kb.get("shared/seasonal_availability")
        if not isinstance(kb_data, dict):
            return []

        calendar = kb_data.get("calendar", [])
        warnings: List[str] = []

        # Map dish names to seasonal ingredients from recipe library
        recipe_kb = self._kb.get("menu/recipe_library")
        dish_seasonal_map: Dict[str, str] = {}
        if isinstance(recipe_kb, dict):
            for recipe in recipe_kb.get("recipes", []):
                if not isinstance(recipe, dict):
                    continue
                si = recipe.get("seasonal_ingredient")
                if si and si != "null":
                    dish_seasonal_map[recipe.get("dish_name", "")] = str(si)

        # Check each calendar entry
        for entry in calendar:
            if not isinstance(entry, dict):
                continue
            ingredient = entry.get("ingredient", "")
            off_peak = entry.get("off_peak_months", [])
            entry_region = entry.get("region", "")

            # Region match (loose)
            if isinstance(entry_region, list):
                region_match = any(region.lower() in r.lower() for r in entry_region)
            else:
                region_match = region.lower() in str(entry_region).lower()

            if not region_match:
                continue

            if event_month in off_peak:
                # Check if any selected dish uses this seasonal ingredient
                affected = [
                    dish for dish, si in dish_seasonal_map.items()
                    if dish in selected_dishes and ingredient.lower() in si.lower()
                ]
                sub = entry.get("substitute", "")
                notes = entry.get("notes", "")
                if affected:
                    warning = (
                        f"SEASONAL WARNING: {ingredient} is off-peak in {event_month} "
                        f"({region}). Affects: {', '.join(affected)}."
                    )
                    if sub:
                        warning += f" Suggested substitute: {sub}."
                    elif notes:
                        # Extract substitute suggestion from notes
                        warning += f" Note: {str(notes)[:120]}"
                    warnings.append(warning)

        if warnings:
            kb_sources.append(f"shared/seasonal_availability -> {event_month} check ({region})")

        return warnings

    # ── Step 6 ─────────────────────────────────────────────────────────────────

    def _step6_equipment_check(
        self,
        selected_dishes: List[str],
        venue_type: str,
        guest_count: int,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """
        Validate that all selected dishes can be executed at the venue.
        Returns a list of equipment conflicts and suggested alternatives.
        """
        kb_data = self._kb.get("menu/equipment_capability")
        if not isinstance(kb_data, dict):
            return {"conflicts": [], "warnings": [], "recommendations": []}

        venue_constraints = kb_data.get("venue_constraints", [])
        dish_equipment = kb_data.get("dish_equipment_requirements", {})
        owned_equipment = kb_data.get("owned_equipment", [])
        capacity_rules = kb_data.get("capacity_rules", [])

        # Find venue constraint profile
        venue_profile: Optional[Dict] = None
        for vc in venue_constraints:
            if not isinstance(vc, dict):
                continue
            vtype = vc.get("venue_type", "")
            if venue_type.lower().replace(" ", "_") in vtype.lower().replace(" ", "_"):
                venue_profile = vc
                break

        conflicts: List[str] = []
        warnings: List[str] = []
        recommendations: List[str] = []

        if venue_profile:
            kb_sources.append(f"menu/equipment_capability -> venue: {venue_profile.get('venue_type')}")
            prohibited = venue_profile.get("prohibited_techniques", [])
            dishes_to_avoid = venue_profile.get("dishes_to_avoid", [])
            venue_rec = venue_profile.get("recommended_menu_style", "")
            if venue_rec:
                recommendations.append(f"Venue style: {venue_rec}")

            # Check dishes against prohibited techniques
            for dish in selected_dishes:
                required_equip_ids = dish_equipment.get(dish, [])
                if dish in dishes_to_avoid:
                    conflicts.append(
                        f"EQUIPMENT CONFLICT: '{dish}' not executable at {venue_type}. "
                        f"Remove from menu or adjust to pre-cooked transport."
                    )
                    continue
                # Check technique requirement
                for eq_id in required_equip_ids:
                    # Find equipment and its technique
                    for eq in owned_equipment:
                        if not isinstance(eq, dict):
                            continue
                        if eq.get("equipment_id") == eq_id:
                            techniques = eq.get("techniques", [])
                            for tech in techniques:
                                if tech in prohibited:
                                    conflicts.append(
                                        f"EQUIPMENT CONFLICT: '{dish}' requires {tech} "
                                        f"({eq_id}) which is prohibited at {venue_type}."
                                    )
                                    break

        # Capacity rule checks — only flag dishes specifically called out in the rule
        _capacity_rule_dish_targets = {
            "CAP-001": {"Spring Rolls (Fried)", "Lechon Kawali"},
            "CAP-002": {"Chicken Satay", "Beef Satay", "Chicken Satay (mini)"},
            "CAP-003": {"Nasi Goreng", "Pad Thai (Chicken)", "Pad Thai (Tofu)"},
            "CAP-004": {"Chocolate Lava Cake"},
        }
        for rule in capacity_rules:
            if not isinstance(rule, dict):
                continue
            rule_id = rule.get("rule_id", "")
            trigger = rule.get("trigger_pax_threshold", 9999)
            desc = rule.get("description", "")
            target_dishes = _capacity_rule_dish_targets.get(rule_id, set())
            # Only flag dishes explicitly targeted by this capacity rule
            affected_dishes = [d for d in selected_dishes if d in target_dishes]
            if affected_dishes and guest_count > trigger:
                warnings.append(
                    f"CAPACITY WARNING ({rule_id}): {desc.strip()} "
                    f"Affected: {', '.join(affected_dishes)}."
                )

        return {
            "conflicts": conflicts,
            "warnings": warnings,
            "recommendations": recommendations,
            "venue_profile_matched": venue_profile.get("venue_type") if venue_profile else None,
        }

    # ── Step 7 ─────────────────────────────────────────────────────────────────

    def _step7_performance_score(
        self,
        selected_dishes: List[str],
        event_type: str,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """
        Score the proposed menu against historical performance records.
        Returns an overall menu confidence score and dish-level flags.
        """
        kb_data = self._kb.get("menu/menu_performance")
        if not isinstance(kb_data, dict):
            return {"confidence_score": 0.0, "dish_flags": [], "proven_combo_match": None}

        dish_summary = kb_data.get("dish_performance_summary", [])
        proven_combos = kb_data.get("proven_menu_combinations", [])

        # Dish-level scoring
        dish_flags: List[Dict] = []
        dish_scores: List[float] = []
        for ds in dish_summary:
            if not isinstance(ds, dict):
                continue
            if ds.get("dish") in selected_dishes:
                score = float(ds.get("avg_score", 0))
                dish_scores.append(score)
                always_hit = ds.get("always_a_hit", False)
                caveat = ds.get("caveat", "")
                notes = ds.get("notes", "")
                flag: Dict[str, Any] = {
                    "dish": ds.get("dish"),
                    "avg_score": score,
                    "always_a_hit": always_hit,
                }
                if caveat:
                    flag["caveat"] = caveat
                if notes and not always_hit:
                    flag["warning"] = notes
                dish_flags.append(flag)

        overall_score = round(sum(dish_scores) / len(dish_scores), 2) if dish_scores else 0.0

        # Check for proven combo match
        matched_combo: Optional[Dict] = None
        for combo in proven_combos:
            if not isinstance(combo, dict):
                continue
            combo_event = combo.get("event_type", "")
            if event_type.lower().replace(" ", "_") in combo_event.lower().replace(" ", "_"):
                combo_dishes = combo.get("dishes", [])
                overlap = [d for d in combo_dishes if d in selected_dishes]
                if len(overlap) >= 2:
                    matched_combo = {
                        "combo_id": combo.get("combo_id"),
                        "label": combo.get("label"),
                        "overlap_dishes": overlap,
                        "avg_satisfaction": combo.get("avg_satisfaction"),
                        "notes": combo.get("notes"),
                    }
                    break

        if dish_flags or matched_combo:
            kb_sources.append(f"menu/menu_performance -> {len(dish_flags)} dishes scored")
        if matched_combo:
            kb_sources.append(f"menu/menu_performance -> proven combo: {matched_combo['combo_id']}")

        return {
            "confidence_score": overall_score,
            "dish_flags": dish_flags,
            "proven_combo_match": matched_combo,
        }

    # ── Step 8 ─────────────────────────────────────────────────────────────────

    def _assemble_output(
        self,
        customer_data: Dict[str, Any],
        guest_count: int,
        dietary: List[str],
        event_type: str,
        service_style: str,
        constraints: Dict,
        menu_plan: Dict,
        yield_data: Dict,
        seasonal_warnings: List[str],
        equipment_result: Dict,
        performance: Dict,
        budget_per_head: Optional[float],
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        """Compose the final structured output."""

        selected = menu_plan.get("selected_dishes", [])

        # Collect all warnings/flags
        all_warnings: List[str] = []
        all_warnings.extend(constraints.get("allergen_flags", []))
        all_warnings.extend(constraints.get("critical_allergens", []))
        all_warnings.extend(yield_data.get("warnings", []))
        all_warnings.extend(seasonal_warnings)
        all_warnings.extend(equipment_result.get("conflicts", []))
        all_warnings.extend(equipment_result.get("warnings", []))

        # Ingredient brief (for inventory agent)
        ingredient_brief = {
            "menu_items": selected,
            "guest_count": guest_count,
            "event_type": event_type,
            "service_style": service_style,
            "dietary_constraints": dietary,
            "waste_buffer": yield_data.get("waste_buffer_applied", 1.10),
        }

        # Cost basis estimate (for pricing agent)
        cost_basis: Dict[str, Any] = {}
        if budget_per_head:
            food_cost_pct = 0.35  # industry standard 35% food cost
            estimated_food_cost = budget_per_head * food_cost_pct
            cost_basis = {
                "budget_per_head_myr": budget_per_head,
                "estimated_food_cost_per_head_myr": round(estimated_food_cost, 2),
                "dishes_count": len(selected),
                "cost_per_dish_target_myr": (
                    round(estimated_food_cost / len(selected), 2) if selected else 0
                ),
            }

        result: Dict[str, Any] = {
            # Primary outputs
            "menu_items": selected,
            "guest_count": guest_count,
            "event_type": event_type,
            "service_style": service_style,
            "dietary_constraints": dietary,

            # Step 1
            "hard_constraints": constraints.get("forbidden", []),
            "substitution_hints": constraints.get("substitution_hints", []),

            # Step 3
            "template_used": menu_plan.get("template_used"),
            "template_quality_notes": menu_plan.get("template_quality_notes"),
            "relevant_trends": menu_plan.get("relevant_trends", []),
            "flavour_pairing_principles": menu_plan.get("pairing_principles", []),

            # Step 4
            "portion_yield_adjustments": yield_data.get("adjustments", []),
            "portion_warnings": yield_data.get("warnings", []),
            "dish_yield_flags": yield_data.get("dish_yield_flags", []),
            "waste_buffer": yield_data.get("waste_buffer_applied", 1.10),

            # Step 5
            "seasonal_warnings": seasonal_warnings,

            # Step 6
            "equipment_conflicts": equipment_result.get("conflicts", []),
            "equipment_warnings": equipment_result.get("warnings", []),
            "venue_recommendations": equipment_result.get("recommendations", []),

            # Step 7
            "performance_confidence_score": performance.get("confidence_score", 0.0),
            "dish_performance_flags": performance.get("dish_flags", []),
            "proven_combo_match": performance.get("proven_combo_match"),

            # Combined summary
            "all_warnings": all_warnings,
            "is_executable": len(equipment_result.get("conflicts", [])) == 0,

            # Downstream agent briefs
            "ingredient_brief_for_inventory": ingredient_brief,
            "cost_basis_for_pricing": cost_basis,

            # Traceability
            "kb_sources": list(dict.fromkeys(kb_sources)),
        }

        return result

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _map_event_key(self, event_type: str, service_style: str) -> str:
        """Map event_type + service_style to portion_yield consumption key."""
        et = event_type.lower().replace(" ", "_").replace("-", "_")
        ss = service_style.lower().replace(" ", "_").replace("-", "_")

        mapping = {
            "malay_wedding": "malay_wedding_buffet",
            "chinese_banquet": "chinese_banquet_plated",
            "corporate_gala": "corporate_gala_plated",
            "corporate_gala_dinner": "corporate_gala_plated",
            "corporate_lunch": "corporate_lunch_buffet",
            "birthday": "birthday_buffet",
            "birthday_party": "birthday_buffet",
            "high_tea": "high_tea",
            "food_festival": "festival_food_stall",
            "product_launch": "corporate_lunch_buffet",
        }

        for key, mapped in mapping.items():
            if key in et:
                if "plated" in ss and "plated" not in mapped:
                    return mapped.replace("buffet", "plated")
                return mapped

        return "corporate_lunch_buffet"

    @staticmethod
    def _parse_month(event_date: str) -> Optional[str]:
        """Extract month name from an ISO date string."""
        if not event_date:
            return None
        try:
            dt = datetime.strptime(event_date[:10], "%Y-%m-%d")
            return dt.strftime("%B")  # e.g. 'December'
        except (ValueError, TypeError):
            return None

    def _build_reasoning_prompt(
        self, result: Dict[str, Any], customer_data: Dict[str, Any]
    ) -> str:
        selected = result.get("menu_items", [])
        event_type = result.get("event_type", "")
        dietary = result.get("dietary_constraints", [])
        score = result.get("performance_confidence_score", 0.0)
        warnings = result.get("all_warnings", [])
        trends = result.get("relevant_trends", [])
        combo = result.get("proven_combo_match")

        prompt_parts = [
            f"Event: {event_type}, {result.get('guest_count')} guests, "
            f"service: {result.get('service_style')}.",
            f"Dietary requirements: {dietary or 'None'}.  ",
            f"Proposed menu ({len(selected)} dishes): {', '.join(selected[:8])}"
            + (f" (+ {len(selected)-8} more)" if len(selected) > 8 else "") + ".",
        ]
        if score > 0:
            prompt_parts.append(f"Historical performance score: {score}/5.")
        if combo:
            prompt_parts.append(
                f"Matches proven combo '{combo.get('label')}' "
                f"(avg satisfaction {combo.get('avg_satisfaction')})."
            )
        if trends:
            prompt_parts.append(f"Relevant trends: {', '.join(trends)}.")
        if warnings:
            prompt_parts.append(f"Active warnings ({len(warnings)}): {warnings[0]}.")

        prompt_parts.append(
            "In 3-4 sentences: explain why this menu fits the brief, "
            "call out any cultural or operational risks, and suggest one upgrade to elevate it."
        )
        return " ".join(prompt_parts)
