# Platform: swappable to Microsoft Agent Framework worker (placeholder) — app.agents.platform_bridge

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.agents.llm_mixin import LLMReasoningMixin
from app.providers.base import LLMProvider
from app.tools.kb_yaml import YAMLKBSearch
from app.tools.scheduler_api import SchedulerAPITool


class LogisticsPlanningAgent(LLMReasoningMixin):
    """
    8-step logistics planning pipeline:
      Step 1  — Venue profile: access constraints, kitchen, setup window
      Step 2  — Runsheet: load base timeline for event type
      Step 3  — Staffing: assign roles, check certifications, build schedule
      Step 4  — Routes & transport: departure times, vehicle assignment, cold chain
      Step 5  — Equipment: confirm availability, assign to vehicles, detect double-bookings
      Step 6  — Food safety: cold chain design, holding plan, outdoor rules
      Step 7  — Compliance: permits, licences, insurance, certification checks
      Step 8  — Execution logs: retrieve past events at venue, apply learned lessons
    """

    def __init__(
        self,
        scheduler: SchedulerAPITool,
        provider: Optional[LLMProvider] = None,
        kb: Optional[YAMLKBSearch] = None,
    ) -> None:
        self._scheduler = scheduler
        self._kb = kb or YAMLKBSearch()
        self.set_provider(provider)

    # ── Public entry point ────────────────────────────────────────────────

    def process(
        self,
        customer_data: Dict[str, Any],
        inventory_data: Dict[str, Any],
        menu_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        guest_count: int = int(customer_data.get("guest_count", 0))
        event_date: str = customer_data.get("event_date", "")
        event_type: str = customer_data.get("event_type", "")
        location: str = customer_data.get("location", "")
        service_style: str = customer_data.get("service_style", "buffet")
        venue_name: str = customer_data.get("venue", location)
        is_outdoor: bool = customer_data.get("outdoor_event", False)
        country: str = customer_data.get("country", "Malaysia")
        # "menu_items" is the key MenuPlanningAgent outputs; fall back to "menu_plan" for compat
        menu_items: List[str] = (
            menu_data.get("menu_items", menu_data.get("menu_plan", [])) if menu_data else []
        )
        # Also accept menu items echoed through inventory_data
        if not menu_items:
            menu_items = inventory_data.get("menu_items", [])

        kb_sources: List[str] = []
        flags: List[str] = []
        equipment_gaps: List[str] = []

        # ── Step 1: Venue profile ─────────────────────────────────────────
        venue_profile = self._step1_venue_profile(venue_name, location, country, kb_sources, flags)

        # ── Step 2: Runsheet template ─────────────────────────────────────
        runsheet = self._step2_runsheet(event_type, service_style, guest_count, venue_profile, kb_sources)

        # ── Step 3: Staffing plan ─────────────────────────────────────────
        staffing_plan = self._step3_staffing(service_style, guest_count, event_date, kb_sources, flags)

        # ── Step 4: Routes & transport ────────────────────────────────────
        transport_plan = self._step4_routes(location, country, event_type, service_style,
                                            guest_count, menu_items, kb_sources, flags)

        # ── Step 5: Equipment ─────────────────────────────────────────────
        equipment_plan = self._step5_equipment(service_style, guest_count, menu_items,
                                               venue_profile, kb_sources, equipment_gaps, flags)

        # ── Step 6: Food safety ───────────────────────────────────────────
        food_safety_plan = self._step6_food_safety(service_style, guest_count, is_outdoor,
                                                   menu_items, transport_plan, kb_sources, flags)

        # ── Step 7: Compliance ────────────────────────────────────────────
        compliance_plan = self._step7_compliance(country, event_type, is_outdoor, guest_count,
                                                 venue_profile, kb_sources, flags)

        # ── Step 8: Execution logs / past learnings ───────────────────────
        past_learnings = self._step8_execution_logs(venue_name, event_type, kb_sources)

        # ── Assemble output ───────────────────────────────────────────────
        return self._assemble_output(
            customer_data=customer_data,
            venue_profile=venue_profile,
            runsheet=runsheet,
            staffing_plan=staffing_plan,
            transport_plan=transport_plan,
            equipment_plan=equipment_plan,
            food_safety_plan=food_safety_plan,
            compliance_plan=compliance_plan,
            past_learnings=past_learnings,
            equipment_gaps=equipment_gaps,
            flags=flags,
            kb_sources=kb_sources,
        )

    # ── Step implementations ──────────────────────────────────────────────

    def _step1_venue_profile(
        self,
        venue_name: str,
        location: str,
        country: str,
        kb_sources: List[str],
        flags: List[str],
    ) -> Dict[str, Any]:
        query = f"{venue_name} {location} {country}".strip()
        hits = self._kb.search(
            "logistics/venue_profiles",
            query,
            collection_key="venues",
            top_k=1,
        )
        if hits and isinstance(hits[0], dict):
            v = hits[0]
            kb_sources.append(f"logistics/venue_profiles -> {v.get('name', venue_name)}")

            access = v.get("access", {})
            kitchen = v.get("kitchen", {})
            setup = v.get("setup", {})
            constraints = v.get("constraints", {})

            # Surface learned constraints as flags for the plan
            for lc in constraints.get("learned_constraints", []):
                flags.append(f"[VENUE CONSTRAINT] {lc}")

            return {
                "venue_id": v.get("venue_id"),
                "name": v.get("name"),
                "city": v.get("city"),
                "country": v.get("country"),
                "gps": v.get("gps", {}),
                "capacity_guests": v.get("capacity_guests"),
                "indoor_outdoor": v.get("indoor_outdoor"),
                "halal_only_venue": v.get("halal_only_venue", False),
                "access": {
                    "loading_dock": access.get("loading_dock"),
                    "loading_dock_hours": access.get("loading_dock_hours"),
                    "loading_dock_clearance_m": access.get("loading_dock_clearance_m"),
                    "max_vehicle_height_m": access.get("max_vehicle_height_m"),
                    "service_lift": access.get("service_lift"),
                    "stairs_only": access.get("stairs_only_backup", False),
                    "parking_staff": access.get("parking_staff_vehicles"),
                },
                "kitchen": {
                    "kitchen_available": kitchen.get("kitchen_available"),
                    "kitchen_type": kitchen.get("kitchen_type"),
                    "gas_available": kitchen.get("gas_available"),
                    "electricity_amperage": kitchen.get("electricity_amperage"),
                    "cold_storage": kitchen.get("cold_storage"),
                    "prep_space_sqm": kitchen.get("prep_space_sqm"),
                },
                "setup": {
                    "earliest_access_time": setup.get("earliest_access_time"),
                    "setup_window_hours": setup.get("setup_window_hours"),
                    "teardown_by": setup.get("teardown_by"),
                    "noise_curfew": setup.get("noise_curfew"),
                    "outdoor_setup_allowed": setup.get("outdoor_setup_allowed"),
                },
                "equipment_restrictions": constraints.get("equipment_restrictions", []),
                "learned_constraints": constraints.get("learned_constraints", []),
                "venue_manager": v.get("venue_manager", {}),
            }

        # Fallback if no venue found in KB
        kb_sources.append(f"logistics/venue_profiles -> [no match for '{venue_name}']")
        flags.append(f"[VENUE WARNING] Venue '{venue_name}' not in KB. Site visit required before event.")
        return {"name": venue_name, "city": location, "country": country,
                "indoor_outdoor": "unknown", "access": {}, "kitchen": {}, "setup": {},
                "equipment_restrictions": [], "learned_constraints": []}

    def _step2_runsheet(
        self,
        event_type: str,
        service_style: str,
        guest_count: int,
        venue_profile: Dict[str, Any],
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        query = f"{event_type} {service_style} runsheet timeline"
        hits = self._kb.search(
            "logistics/runsheet_templates",
            query,
            collection_key="runsheet_templates",
            top_k=2,
        )

        # Select best matching template
        template: Optional[Dict[str, Any]] = None
        for hit in hits:
            if isinstance(hit, dict):
                et = hit.get("event_type", "").replace("_", " ").lower()
                ss = hit.get("service_style", "").lower()
                if event_type.lower().replace("_", " ") in et or ss in service_style.lower():
                    template = hit
                    break
        if template is None and hits and isinstance(hits[0], dict):
            template = hits[0]

        if not template:
            return {"template": "generic", "milestones": [], "notes": "No matching runsheet template found."}

        kb_sources.append(f"logistics/runsheet_templates -> {template.get('template_id', 'unknown')}")

        # Apply adaptation rules
        adaptation_hits = self._kb.search(
            "logistics/runsheet_templates",
            "adaptation rules adjustment",
            collection_key="adaptation_rules",
            top_k=5,
        )
        adaptations: List[str] = []
        access = venue_profile.get("access", {})
        kitchen = venue_profile.get("kitchen", {})

        if not kitchen.get("kitchen_available", True):
            adaptations.append("No kitchen at venue: add 60min to all pre-service milestones.")
        if access.get("stairs_only", False):
            adaptations.append("Stairs only (no service lift): add 30min to setup start; assign 2 extra setup crew.")
        if guest_count > (template.get("typical_guest_count_range", [0, 9999])[1] * 1.5):
            adaptations.append(f"Guest count {guest_count} is >50% above template range. Scale kitchen +1 line cook per 50 extra guests.")

        return {
            "template_id": template.get("template_id"),
            "event_type": template.get("event_type"),
            "service_style": template.get("service_style"),
            "milestones": [
                {
                    "time_offset_min": m.get("time_offset_min"),
                    "milestone": m.get("milestone"),
                    "critical_path": m.get("critical_path", False),
                    "responsible": m.get("responsible", "team"),
                }
                for m in template.get("milestones", [])
                if isinstance(m, dict)
            ],
            "buffer_times": template.get("buffer_times", {}),
            "notes": template.get("notes", ""),
            "adaptations_applied": adaptations,
        }

    def _step3_staffing(
        self,
        service_style: str,
        guest_count: int,
        event_date: str,
        kb_sources: List[str],
        flags: List[str],
    ) -> Dict[str, Any]:
        model_query = f"staffing model {service_style} {guest_count} pax"
        model_hits = self._kb.search(
            "logistics/staff_scheduling",
            model_query,
            collection_key="staffing_models",
            top_k=3,
        )

        # Find best matching staffing model
        selected_model: Optional[Dict[str, Any]] = None
        for hit in model_hits:
            if not isinstance(hit, dict):
                continue
            pax_range = hit.get("pax_range", [0, 9999])
            ss = hit.get("service_style", "").lower()
            lo = int(pax_range[0]) if len(pax_range) > 0 else 0
            hi = int(pax_range[1]) if len(pax_range) > 1 else 9999
            if lo <= guest_count <= hi and ss in service_style.lower():
                selected_model = hit
                break
        if selected_model is None and model_hits and isinstance(model_hits[0], dict):
            selected_model = model_hits[0]

        model_info: Dict[str, Any] = {}
        if selected_model:
            kb_sources.append(f"logistics/staff_scheduling -> {selected_model.get('name', 'staffing_model')}")
            model_info = {
                "model_id": selected_model.get("model_id"),
                "model_name": selected_model.get("name"),
                "total_staff": selected_model.get("total_staff"),
                "required_roles": selected_model.get("required_staff", []),
            }

        # Check staff availability (scan named roster for expiring certs)
        roster_hits = self._kb.search(
            "logistics/staff_scheduling",
            "staff roster certifications expiry",
            collection_key="staff_roster",
            top_k=10,
        )
        cert_warnings: List[str] = []
        for staff in roster_hits:
            if not isinstance(staff, dict):
                continue
            for cert in staff.get("certifications", []):
                if isinstance(cert, dict) and cert.get("status", "").startswith("EXPIR"):
                    cert_warnings.append(
                        f"CERT WARNING: {staff.get('name')} — {cert.get('cert')} {cert.get('status')}"
                    )
        for w in cert_warnings:
            flags.append(f"[CERTIFICATION] {w}")

        # Check availability rules
        avail_hits = self._kb.search(
            "logistics/staff_scheduling",
            "availability booking lead time peak season",
            collection_key="availability_rules",
            top_k=3,
        )
        avail_notes: List[str] = [
            h if isinstance(h, str) else h.get("description", "")
            for h in avail_hits
            if h
        ]

        return {
            "staffing_model": model_info,
            "certification_warnings": cert_warnings,
            "availability_notes": avail_notes[:3],
        }

    def _step4_routes(
        self,
        location: str,
        country: str,
        event_type: str,
        service_style: str,
        guest_count: int,
        menu_items: List[str],
        kb_sources: List[str],
        flags: List[str],
    ) -> Dict[str, Any]:
        country_key = "malaysia" if "malay" in country.lower() else "philippines" if "phil" in country.lower() else "malaysia"
        route_query = f"{location} {country} route travel"
        route_hits = self._kb.search(
            "logistics/route_transport",
            route_query,
            collection_key=f"routes_{country_key}",
            top_k=2,
        )

        route_info: Dict[str, Any] = {}
        if route_hits and isinstance(route_hits[0], dict):
            r = route_hits[0]
            kb_sources.append(f"logistics/route_transport -> {r.get('route_id', 'route')}")
            route_info = {
                "route_id": r.get("route_id"),
                "distance_km": r.get("distance_km"),
                "travel_normal_min": r.get("travel_time_normal_min"),
                "travel_peak_pm_min": r.get("travel_time_peak_pm_min"),
                "toll_costs": r.get("toll_costs_myr") or r.get("toll_costs_php"),
                "recommended_departure": r.get("recommended_departure_for_7pm_event"),
                "pinch_points": r.get("peak_pinch_points", []),
                "vehicle_restrictions": r.get("vehicle_restrictions", []),
                "notes": r.get("notes", ""),
            }
            if r.get("vehicle_restrictions"):
                flags.append(f"[TRANSPORT] Vehicle restrictions on route: {r.get('vehicle_restrictions')}")

        # Determine if cold chain vehicle is needed
        cold_chain_needed = self._needs_cold_chain(menu_items, service_style)
        vehicle_hits = self._kb.search(
            "logistics/route_transport",
            "vehicle fleet refrigerated van lorry cargo",
            collection_key="vehicle_fleet",
            top_k=3,
        )
        vehicles_assigned: List[Dict[str, Any]] = []
        needs_lorry = guest_count > 200

        # Determine delivery schedule
        ds_hits = self._kb.search(
            "logistics/route_transport",
            "delivery schedule departure cold chain hot boxes",
            collection_key="delivery_scheduling",
            top_k=4,
        )
        schedule_steps = [
            {
                "rule_id": ds.get("rule_id"),
                "name": ds.get("name"),
                "timing": ds.get("timing"),
                "vehicle": ds.get("vehicle"),
                "carries": ds.get("carries", []),
            }
            for ds in ds_hits if isinstance(ds, dict)
        ]

        for vh in vehicle_hits:
            if not isinstance(vh, dict):
                continue
            vtype = vh.get("type", "")
            if "refrigerated" in vtype and cold_chain_needed:
                vehicles_assigned.append({"vehicle": vh.get("description"), "role": "cold_chain"})
            elif "lorry" in vtype and needs_lorry:
                vehicles_assigned.append({"vehicle": vh.get("description"), "role": "furniture_and_heavy_equipment"})
            elif "cargo" in vtype:
                vehicles_assigned.append({"vehicle": vh.get("description"), "role": "cooking_equipment_and_dry_goods"})

        if cold_chain_needed and not any(v["role"] == "cold_chain" for v in vehicles_assigned):
            flags.append("[TRANSPORT] Cold chain menu items detected but refrigerated van not confirmed — check availability.")

        return {
            "route": route_info,
            "cold_chain_required": cold_chain_needed,
            "vehicles_assigned": vehicles_assigned,
            "delivery_schedule": schedule_steps,
        }

    def _step5_equipment(
        self,
        service_style: str,
        guest_count: int,
        menu_items: List[str],
        venue_profile: Dict[str, Any],
        kb_sources: List[str],
        equipment_gaps: List[str],
        flags: List[str],
    ) -> Dict[str, Any]:
        equip_query = f"{service_style} buffet chafing rice cooker hot box"
        owned_hits = self._kb.search(
            "logistics/equipment_inventory",
            equip_query,
            collection_key="owned_equipment",
            top_k=8,
        )
        venue_restrictions = venue_profile.get("equipment_restrictions", [])

        # Estimate quantities needed
        chafing_needed = max(8, guest_count // 25)
        hot_boxes_needed = max(4, guest_count // 50)
        rice_cookers_needed = max(2, guest_count // 75)

        checklist: List[Dict[str, Any]] = []
        for eq in owned_hits:
            if not isinstance(eq, dict):
                continue
            name = eq.get("name", "")
            qty = int(eq.get("quantity", 0))
            dims = eq.get("dimensions_cm", {})
            restriction_blocked = any(
                r.lower() in name.lower()
                for r in venue_restrictions
            )
            kb_sources.append(f"logistics/equipment_inventory -> {name}")
            checklist.append({
                "equipment_id": eq.get("equipment_id"),
                "name": name,
                "qty_available": qty,
                "dimensions_cm": dims,
                "weight_kg": eq.get("weight_kg"),
                "vehicle_preference": eq.get("vehicle_preference"),
                "setup_sequence_priority": eq.get("setup_sequence_priority"),
                "setup_time_min": eq.get("setup_time_min_per_unit") or eq.get("setup_time_min"),
                "restriction_blocked": restriction_blocked,
            })

        # Check for gaps
        chafing_available = sum(
            int(e.get("qty_available", 0))
            for e in checklist
            if e and "chafing" in e.get("name", "").lower()
        )
        if chafing_needed > chafing_available:
            gap = f"Chafing dishes: need {chafing_needed}, have {chafing_available}. Rent {chafing_needed - chafing_available} extra."
            equipment_gaps.append(gap)
            flags.append(f"[EQUIPMENT GAP] {gap}")

        hot_box_available = sum(
            int(e.get("qty_available", 0))
            for e in checklist
            if e and "hot box" in e.get("name", "").lower()
        )
        if hot_boxes_needed > hot_box_available:
            gap = f"Hot boxes: need {hot_boxes_needed}, have {hot_box_available}."
            equipment_gaps.append(gap)
            flags.append(f"[EQUIPMENT GAP] {gap}")

        # Check double-booking rules
        db_hits = self._kb.search(
            "logistics/equipment_inventory",
            "double booking same day conflict",
            collection_key="double_booking_rules",
            top_k=3,
        )
        double_booking_rules = [r if isinstance(r, str) else str(r) for r in db_hits if r]

        # Load vehicle loading plan
        plan_query = f"buffet {guest_count} pax loading plan"
        plan_hits = self._kb.search(
            "logistics/equipment_inventory",
            plan_query,
            collection_key="vehicle_loading_plans",
            top_k=2,
        )
        loading_plan: Optional[Dict[str, Any]] = None
        for ph in plan_hits:
            if isinstance(ph, dict):
                pax_in_desc = ph.get("for", "")
                loading_plan = {"plan_id": ph.get("plan_id"), "description": pax_in_desc,
                                "vehicles": ph.get("vehicles_required", [])}
                break

        return {
            "equipment_checklist": checklist[:8],
            "quantities_needed": {
                "chafing_dishes": chafing_needed,
                "hot_boxes": hot_boxes_needed,
                "rice_cookers": rice_cookers_needed,
            },
            "equipment_gaps": equipment_gaps,
            "loading_plan": loading_plan,
            "double_booking_rules": double_booking_rules[:3],
        }

    def _step6_food_safety(
        self,
        service_style: str,
        guest_count: int,
        is_outdoor: bool,
        menu_items: List[str],
        transport_plan: Dict[str, Any],
        kb_sources: List[str],
        flags: List[str],
    ) -> Dict[str, Any]:
        temp_hits = self._kb.search(
            "logistics/food_safety",
            "temperature holding hot food chilled cold chain",
            collection_key="temperature_requirements",
            top_k=4,
        )
        danger_hits = self._kb.search(
            "logistics/food_safety",
            "danger zone two hour rule",
            collection_key="danger_zone_rules",
            top_k=1,
        )
        cold_box_hits = self._kb.search(
            "logistics/food_safety",
            "ice cold box quantity ice sourcing",
            collection_key="cold_chain_planning",
            top_k=1,
        )
        outdoor_hits: List[Any] = []
        if is_outdoor:
            outdoor_hits = self._kb.search(
                "logistics/food_safety",
                "outdoor event insects cover canopy",
                collection_key="outdoor_event_special_rules",
                top_k=5,
            )
            flags.append("[FOOD SAFETY] Outdoor event: all food must be covered. Increase ice stock by 30%.")

        kb_sources.append("logistics/food_safety -> temperature_requirements")

        # Determine cold box quantity
        # Ice box lookup: derive directly from guest count (KB values)
        if guest_count <= 100:
            ice_boxes_required, ice_kg_required = 2, 30
        elif guest_count <= 300:
            ice_boxes_required, ice_kg_required = 4, 60
        elif guest_count <= 600:
            ice_boxes_required, ice_kg_required = 6, 100
        else:
            ice_boxes_required, ice_kg_required = 8, 150

        if is_outdoor:
            ice_kg_required = int(ice_kg_required * 1.3)

        # Loading sequence from cold chain planning KB
        cold_box_data = cold_box_hits[0] if cold_box_hits and isinstance(cold_box_hits[0], dict) else {}
        loading_seq_data = cold_box_data.get("loading_sequence", {})
        loading_sequence = [
            f"{k}: {v}" for k, v in loading_seq_data.items()
        ] if isinstance(loading_seq_data, dict) else []

        # Key temperature rules summary
        temp_rules: List[Dict[str, Any]] = []
        for t in temp_hits:
            if isinstance(t, dict):
                temp_rules.append({
                    "category": t.get("category"),
                    "min_temp_c": t.get("minimum_holding_temp_c"),
                    "max_temp_c": t.get("maximum_holding_temp_c"),
                    "transport_method": t.get("transport_method"),
                })

        danger_rule = danger_hits[0] if danger_hits and isinstance(danger_hits[0], dict) else {}

        return {
            "temperature_rules": temp_rules,
            "danger_zone_two_hour_rule": danger_rule.get("two_hour_rule", "Food must not spend >2h between 4-60°C."),
            "cold_chain": {
                "ice_boxes_required": ice_boxes_required,
                "ice_kg_required": ice_kg_required,
                "cold_chain_needed": transport_plan.get("cold_chain_required", True),
                "loading_sequence": loading_sequence,
            },
            "outdoor_rules": [r if isinstance(r, str) else str(r) for r in outdoor_hits[:5]],
        }

    def _step7_compliance(
        self,
        country: str,
        event_type: str,
        is_outdoor: bool,
        guest_count: int,
        venue_profile: Dict[str, Any],
        kb_sources: List[str],
        flags: List[str],
    ) -> Dict[str, Any]:
        query = f"{country} {event_type} permit licence compliance outdoor"
        permit_hits = self._kb.search(
            "logistics/compliance_permits",
            query,
            collection_key="temporary_permits",
            top_k=4,
        )
        licence_hits = self._kb.search(
            "logistics/compliance_permits",
            f"{country} business licence halal",
            collection_key="business_licences",
            top_k=2,
        )
        trigger_hits = self._kb.search(
            "logistics/compliance_permits",
            "compliance check trigger outdoor alcohol halal staff cert",
            collection_key="compliance_check_triggers",
            top_k=6,
        )
        kb_sources.append("logistics/compliance_permits -> compliance_check_triggers")

        required_permits: List[Dict[str, Any]] = []
        compliance_flags: List[str] = []

        for permit in permit_hits:
            if not isinstance(permit, dict):
                continue
            when_req = permit.get("when_required", [])
            is_relevant = False
            if is_outdoor and (
                isinstance(when_req, list) and any("outdoor" in str(w).lower() for w in when_req)
                or isinstance(when_req, str) and "outdoor" in when_req.lower()
            ):
                is_relevant = True
            if isinstance(when_req, str) and "outdoor" in when_req.lower() and is_outdoor:
                is_relevant = True
            if guest_count >= 200 and "200" in str(when_req):
                is_relevant = True
            if is_relevant:
                lead = permit.get("lead_time_days", 0)
                required_permits.append({
                    "permit_id": permit.get("permit_id"),
                    "type": permit.get("type"),
                    "authority": permit.get("authority"),
                    "lead_time_days": lead,
                    "notes": permit.get("notes", ""),
                })
                if lead >= 14:
                    compliance_flags.append(
                        f"[COMPLIANCE] '{permit.get('type')}' requires {lead}-day notice to {permit.get('authority')}. Apply now."
                    )

        if venue_profile.get("halal_only_venue"):
            compliance_flags.append("[COMPLIANCE] Halal-only venue: verify JAKIM certificate is current and bring physical copy.")

        # Check trigger rules
        triggered_checks: List[str] = []
        for t in trigger_hits:
            if not isinstance(t, dict):
                continue
            trigger = t.get("trigger", "")
            if is_outdoor and "outdoor" in trigger.lower():
                triggered_checks.append(trigger)
            if guest_count >= 500 and "500" in trigger:
                triggered_checks.append(trigger)
            if venue_profile.get("halal_only_venue") and "halal" in trigger.lower():
                triggered_checks.append(trigger)
            if "staff certification" in trigger.lower():
                triggered_checks.append(trigger)

        for f in compliance_flags:
            flags.append(f)

        licences_active: List[Dict[str, Any]] = [
            {
                "licence_id": lic.get("licence_id"),
                "type": lic.get("type"),
                "authority": lic.get("authority"),
                "expiry_date": lic.get("expiry_date"),
                "current_status": lic.get("current_status"),
                "alert": lic.get("alert"),
            }
            for lic in licence_hits if isinstance(lic, dict)
        ]

        return {
            "required_permits": required_permits,
            "active_licences": licences_active,
            "triggered_checks": triggered_checks,
            "compliance_flags": compliance_flags,
        }

    def _step8_execution_logs(
        self,
        venue_name: str,
        event_type: str,
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        log_query = f"{venue_name} {event_type}"
        log_hits = self._kb.search(
            "logistics/execution_logs",
            log_query,
            collection_key="execution_logs",
            top_k=3,
        )
        # Also retrieve aggregated learnings
        agg_hits = self._kb.search(
            "logistics/execution_logs",
            f"common risk pattern {event_type}",
            collection_key="aggregate_learnings",
            top_k=1,
        )

        past_events: List[Dict[str, Any]] = []
        all_lessons: List[str] = []
        all_watch_points: List[str] = []

        for log in log_hits:
            if not isinstance(log, dict):
                continue
            if log.get("venue_name") and venue_name.lower() in log.get("venue_name", "").lower():
                kb_sources.append(f"logistics/execution_logs -> {log.get('log_id')}")
            past_events.append({
                "log_id": log.get("log_id"),
                "event_type": log.get("event_type"),
                "event_date": log.get("event_date"),
                "venue_name": log.get("venue_name"),
                "guest_count_actual": log.get("guest_count_actual"),
                "outcome": log.get("outcome"),
                "score": log.get("overall_score"),
                "what_to_do_differently": log.get("what_to_do_differently", []),
                "venue_learnings": log.get("venue_specific_learnings", []),
            })
            all_lessons.extend(log.get("what_to_do_differently", []))
            all_watch_points.extend(log.get("venue_specific_learnings", []))

        # Retrieve common risk patterns
        risk_patterns: List[str] = []
        if agg_hits and isinstance(agg_hits[0], dict):
            patterns = agg_hits[0].get("common_risk_patterns", [])
            for p in patterns:
                if isinstance(p, dict):
                    risk_patterns.append(
                        f"{p.get('pattern')}: {p.get('mitigation')}"
                    )

        return {
            "past_events_found": len(past_events),
            "past_events": past_events[:3],
            "lessons_from_history": list(dict.fromkeys(all_lessons))[:8],
            "venue_watch_points": list(dict.fromkeys(all_watch_points))[:6],
            "common_risk_patterns": risk_patterns[:4],
        }

    # ── Assemble final output ─────────────────────────────────────────────

    def _assemble_output(
        self,
        customer_data: Dict[str, Any],
        venue_profile: Dict[str, Any],
        runsheet: Dict[str, Any],
        staffing_plan: Dict[str, Any],
        transport_plan: Dict[str, Any],
        equipment_plan: Dict[str, Any],
        food_safety_plan: Dict[str, Any],
        compliance_plan: Dict[str, Any],
        past_learnings: Dict[str, Any],
        equipment_gaps: List[str],
        flags: List[str],
        kb_sources: List[str],
    ) -> Dict[str, Any]:
        # Use scheduler for base timeline/resource allocation
        guest_count = int(customer_data.get("guest_count", 0))
        event_date = customer_data.get("event_date", "")

        resources = self._scheduler.allocate_resources(guest_count)
        timeline = self._scheduler.build_timeline(event_date)

        staffing_model = staffing_plan.get("staffing_model", {})
        required_roles = staffing_model.get("required_roles", [])

        # Transport manifest: what's in which vehicle
        transport_manifest: List[Dict[str, Any]] = []
        for v in transport_plan.get("vehicles_assigned", []):
            transport_manifest.append({
                "vehicle": v.get("vehicle"),
                "role": v.get("role"),
            })

        # Compliance checklist
        compliance_checklist: List[str] = []
        for permit in compliance_plan.get("required_permits", []):
            compliance_checklist.append(
                f"[ ] Obtain '{permit.get('type')}' from {permit.get('authority')} "
                f"(lead time: {permit.get('lead_time_days')} days)"
            )
        for cf in compliance_plan.get("compliance_flags", []):
            compliance_checklist.append(f"[ ] {cf}")
        for w in staffing_plan.get("certification_warnings", []):
            compliance_checklist.append(f"[ ] {w}")

        # Generate LLM reasoning
        context_summary = (
            f"Event: {customer_data.get('event_type')} at {venue_profile.get('name', customer_data.get('venue', ''))}, "
            f"{guest_count} guests, {customer_data.get('service_style', 'buffet')} service.\n"
            f"Venue access: loading_dock={venue_profile.get('access', {}).get('loading_dock')}, "
            f"stairs_only={venue_profile.get('access', {}).get('stairs_only', False)}.\n"
            f"Transport: {len(transport_plan.get('vehicles_assigned', []))} vehicles. "
            f"Cold chain needed: {transport_plan.get('cold_chain_required')}.\n"
            f"Staffing: {staffing_model.get('total_staff', 'TBD')} staff required.\n"
            f"Equipment gaps: {equipment_gaps or 'none'}.\n"
            f"Compliance flags: {len(compliance_plan.get('compliance_flags', []))} items.\n"
            f"Flags from past events: {past_learnings.get('lessons_from_history', [])[:3]}.\n"
            "In 2-3 sentences, identify the top logistics risks and recommended actions."
        )

        reasoning = self.reason(
            prompt=context_summary,
            system_prompt=(
                "You are the Logistics Planning Agent for a catering company. "
                "Focus on execution reliability, on-time delivery, and operational safety. "
                "Be specific and practical."
            ),
        )

        result: Dict[str, Any] = {
            "logistics_plan": {
                "venue_profile": venue_profile,
                "runsheet": runsheet,
                "staffing_schedule": {
                    "model": staffing_model.get("name", ""),
                    "total_staff": staffing_model.get("total_staff"),
                    "required_roles": required_roles,
                    "certification_warnings": staffing_plan.get("certification_warnings", []),
                    "availability_notes": staffing_plan.get("availability_notes", []),
                },
                "transport_manifest": transport_manifest,
                "vehicles_needed": len(transport_plan.get("vehicles_assigned", [])),
                "cold_chain_required": transport_plan.get("cold_chain_required", False),
                "delivery_schedule": transport_plan.get("delivery_schedule", []),
                "equipment_plan": {
                    "checklist": equipment_plan.get("equipment_checklist", []),
                    "quantities_needed": equipment_plan.get("quantities_needed", {}),
                    "loading_plan": equipment_plan.get("loading_plan"),
                    "double_booking_rules": equipment_plan.get("double_booking_rules", []),
                },
                "food_safety_plan": food_safety_plan,
                "compliance_checklist": compliance_checklist,
                "past_learnings": past_learnings,
            },
            "menu_items": list(set(
                [str(it) for it in (equipment_plan.get("menu_items_used") or []) or []]
            )),
            "equipment_gaps_for_inventory": equipment_gaps,
            "flags": flags,
            "kb_sources": list(dict.fromkeys(kb_sources)),
            # Scheduler baseline (retained for orchestrator compatibility)
            "timeline": timeline,
            "resource_allocation": resources,
        }

        if reasoning:
            result["reasoning"] = reasoning

        return result

    # ── Helpers ───────────────────────────────────────────────────────────

    def _needs_cold_chain(self, menu_items: List[str], service_style: str) -> bool:
        cold_triggers = [
            "chicken", "beef", "lamb", "seafood", "fish", "prawn", "pork",
            "rendang", "satay", "cream", "cheese", "dairy", "panna cotta",
            "mousse", "ice cream", "jelly", "custard", "mayo", "salad",
        ]
        menu_str = " ".join(menu_items).lower()
        return any(t in menu_str for t in cold_triggers) or service_style == "plated"
