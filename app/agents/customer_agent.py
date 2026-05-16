"""
Customer Interaction Agent

Converts vague human intent into a structured event brief.
The brief is used by all downstream agents (menu, inventory, logistics, pricing).

Pipeline:
  1. Validate and normalise raw input fields
  2. Load event profile template -> pre-fill defaults, surface clarifying questions
  3. Auto-flag dietary & allergen constraints -> pass constraints downstream
  4. Load cultural norms -> add cultural operational flags
  5. Look up returning client CRM record -> apply preferences and VIP flags
  6. Match budget + guest count to service package
  7. Check venue compatibility
  8. Surface relevant FAQ/policy snippets for any policy-related fields
  9. Assemble structured brief + kb_sources traceability

Platform: swappable to Microsoft Agent Framework worker (placeholder) — app.agents.platform_bridge
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.tools.currency import all_iso_codes
from app.tools.kb_yaml import YAMLKBSearch


class CustomerInteractionAgent:
    required_fields = [
        "event_type",
        "guest_count",
        "dietary_constraints",
        "budget",
        "location",
        "event_date",
        "service_style",
    ]

    def __init__(self, kb: Optional[YAMLKBSearch] = None) -> None:
        self._kb = kb or YAMLKBSearch()

    # ── Public entry point ────────────────────────────────────────────────────

    def process(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        missing = [k for k in self.required_fields if k not in raw_input]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        raw_currency = str(raw_input.get("currency", "PHP")).upper().strip()
        valid_currencies = all_iso_codes()
        currency = raw_currency if raw_currency in valid_currencies else "PHP"

        event_type = str(raw_input["event_type"]).lower().strip()
        dietary = [str(d) for d in raw_input.get("dietary_constraints", [])]
        guest_count = int(raw_input["guest_count"])
        budget = float(raw_input["budget"])
        location = str(raw_input["location"])
        event_date = str(raw_input["event_date"])
        service_style = str(raw_input["service_style"])

        kb_sources: List[str] = []

        # ── Step 1: Base result ───────────────────────────────────────────────
        result: Dict[str, Any] = {
            "event_type": event_type,
            "guest_count": guest_count,
            "dietary_constraints": dietary,
            "budget": budget,
            "currency": currency,
            "budget_per_head": round(budget / max(guest_count, 1), 2),
            "location": location,
            "event_date": event_date,
            "service_style": service_style,
        }

        # ── Step 2: Event profile template ────────────────────────────────────
        self._apply_event_profile(result, event_type, kb_sources)

        # ── Step 3: Dietary & allergen flags ──────────────────────────────────
        self._apply_dietary_flags(result, dietary, kb_sources)

        # ── Step 4: Cultural norms ────────────────────────────────────────────
        self._apply_cultural_norms(result, event_type, dietary, kb_sources)

        # ── Step 5: Returning client CRM ─────────────────────────────────────
        client_id = raw_input.get("client_id")
        client_email = raw_input.get("client_email")
        if client_id or client_email:
            self._apply_crm_data(result, client_id, client_email, kb_sources)

        # ── Step 6: Service package matching ─────────────────────────────────
        self._apply_package_match(result, guest_count, budget, service_style, event_type, kb_sources)

        # ── Step 7: Venue compatibility ───────────────────────────────────────
        venue_name = raw_input.get("venue")
        if venue_name:
            self._apply_venue_check(result, venue_name, kb_sources)

        # ── Step 8: FAQ / policy snippets ────────────────────────────────────
        self._apply_policy_flags(result, raw_input, kb_sources)

        result["kb_sources"] = kb_sources
        return result

    # ── Step 2 ────────────────────────────────────────────────────────────────

    def _apply_event_profile(
        self, result: Dict, event_type: str, kb_sources: List[str]
    ) -> None:
        templates = self._kb.get("customer/event_profiles").get("templates", [])
        # Match by event_id or label
        match = None
        for t in templates:
            if (event_type in str(t.get("event_id", "")).lower()
                    or event_type in str(t.get("label", "")).lower()
                    or event_type in str(t.get("category", "")).lower()):
                match = t
                break

        if match:
            result["event_profile"] = {
                "label": match.get("label"),
                "service_style_default": match.get("service_style"),
                "typical_duration_h": match.get("typical_duration_h"),
                "guest_count_range": match.get("guest_count_range"),
                "budget_band_per_head_myr": match.get("budget_band_per_head_myr"),
                "menu_anchors": match.get("menu_anchors", []),
                "common_addons": match.get("common_addons", []),
                "clarifying_questions": match.get("clarifying_questions", []),
                "watch_outs": match.get("watch_outs", []),
            }
            # Merge cultural defaults into dietary_constraints if not already there
            cultural_defaults = match.get("cultural_defaults", [])
            if cultural_defaults:
                result["event_cultural_defaults"] = cultural_defaults
            # Merge downstream flags (may be dict or list-of-dicts from YAML)
            flags = match.get("flags_to_pass", {})
            if isinstance(flags, dict):
                for agent, val in flags.items():
                    result.setdefault("downstream_flags", {})[agent] = val
            elif isinstance(flags, list):
                for item in flags:
                    if isinstance(item, dict):
                        for agent, val in item.items():
                            result.setdefault("downstream_flags", {})[agent] = val
            kb_sources.append(
                f"customer/event_profiles -> {match.get('event_id', event_type)}: "
                f"{len(match.get('clarifying_questions', []))} clarifying questions loaded"
            )
        else:
            kb_sources.append(f"customer/event_profiles -> no template found for '{event_type}'")

    # ── Step 3 ────────────────────────────────────────────────────────────────

    def _apply_dietary_flags(
        self, result: Dict, dietary: List[str], kb_sources: List[str]
    ) -> None:
        dr_data = self._kb.get("customer/dietary_restrictions")
        profiles: List[Dict] = dr_data.get("profiles", [])
        severity_list: List[Dict] = dr_data.get("allergen_severity", [])
        combined: List[Dict] = dr_data.get("combined_profiles", [])

        dietary_lower = [d.lower() for d in dietary]
        constraint_flags: List[str] = []
        allergen_critical: List[str] = []
        downstream_flags: Dict[str, Any] = result.setdefault("downstream_flags", {})
        cross_contamination_risks: List[str] = []
        prep_constraints: List[str] = []
        auto_flags: List[str] = []

        # Match each declared dietary constraint to a profile
        matched_profile_ids: List[str] = []
        for profile in profiles:
            pid = profile.get("id", "").lower()
            label = profile.get("label", "").lower()
            if any(pid in d or label in d or d in pid for d in dietary_lower):
                matched_profile_ids.append(pid)
                constraint_flags.append(profile.get("label", pid))
                cross_contamination_risks.extend(profile.get("cross_contamination_risks", []))
                prep_constraints.extend(profile.get("kitchen_prep_constraints", []))
                # Merge downstream flags (dict or list-of-dicts)
                flags_raw = profile.get("flags_to_pass", {})
                flag_items: List[tuple] = []
                if isinstance(flags_raw, dict):
                    flag_items = list(flags_raw.items())
                elif isinstance(flags_raw, list):
                    for item in flags_raw:
                        if isinstance(item, dict):
                            flag_items.extend(item.items())
                for agent_key, flag_str in flag_items:
                    downstream_flags.setdefault(agent_key, [])
                    if isinstance(downstream_flags[agent_key], list):
                        downstream_flags[agent_key].append(flag_str)
                    else:
                        downstream_flags[agent_key] = [downstream_flags[agent_key], flag_str]

        # Check combined profiles for auto-flag
        for combo in combined:
            components = combo.get("components", [])
            if all(c in matched_profile_ids for c in components):
                auto_flags.append(combo.get("auto_flag", ""))
                auto_flags.extend(combo.get("additional_constraints", []))
                kb_sources.append(
                    f"customer/dietary_restrictions -> combined profile: {combo.get('combo_id')}"
                )

        # Map dietary profile IDs to their implicit allergens for severity check
        _profile_to_allergen = {
            "nut_free": ["peanuts", "tree_nuts"],
            "halal": [],
            "gluten_free": ["gluten_wheat"],
            "kosher": ["shellfish"],
        }
        allergen_candidates = list(dietary_lower)
        for pid in matched_profile_ids:
            allergen_candidates.extend(_profile_to_allergen.get(pid, []))

        for candidate in allergen_candidates:
            for sev in severity_list:
                allergen_key = str(sev.get("allergen", "")).lower()
                if candidate in allergen_key or allergen_key in candidate:
                    if sev.get("severity") == "critical" and candidate not in allergen_critical:
                        allergen_critical.append(sev.get("allergen", candidate))

        if matched_profile_ids:
            result["dietary_flags"] = constraint_flags
            result["dietary_profile_ids"] = matched_profile_ids
            kb_sources.append(
                f"customer/dietary_restrictions -> matched: {', '.join(matched_profile_ids)}"
            )
        if cross_contamination_risks:
            result["cross_contamination_risks"] = list(set(cross_contamination_risks))
        if prep_constraints:
            result["kitchen_prep_constraints"] = list(set(prep_constraints))
        if allergen_critical:
            result["critical_allergens"] = allergen_critical
            result["allergen_action_required"] = (
                "CRITICAL allergen(s) declared. "
                "Full kitchen allergen protocol must be activated. "
                "Written declaration from kitchen lead required."
            )
        if auto_flags:
            result["dietary_auto_flags"] = [f for f in auto_flags if f]

    # ── Step 4 ────────────────────────────────────────────────────────────────

    def _apply_cultural_norms(
        self,
        result: Dict,
        event_type: str,
        dietary: List[str],
        kb_sources: List[str],
    ) -> None:
        cn_data = self._kb.get("customer/cultural_norms")
        communities: List[Dict] = cn_data.get("communities", [])

        dietary_lower = [d.lower() for d in dietary]
        event_lower = event_type.lower()
        matched_communities: List[str] = []
        cultural_flags: List[Dict] = []

        for community in communities:
            cid = community.get("community_id", "")
            applies = [str(a).lower() for a in community.get("applies_to_event_types", [])]

            # Match by event type or dietary constraint (halal -> muslim, etc.)
            matches_event = any(event_lower in a or a in event_lower for a in applies)
            matches_dietary = (
                ("halal" in dietary_lower and "muslim" in cid)
                or ("vegetarian" in dietary_lower and "indian" in cid)
                or ("kosher" in dietary_lower and "jewish" in cid)
            )
            is_mixed = cid == "mixed_sea_event" and len(dietary_lower) > 1

            if matches_event or matches_dietary or is_mixed:
                matched_communities.append(cid)
                flags: Dict[str, Any] = {
                    "community": community.get("label"),
                    "clarifying_questions": community.get("clarifying_questions", []),
                    "operational_notes": [],
                    "taboos": community.get("taboos", []),
                }
                # Prayer schedule — may be dict or list-of-dicts
                prayer_raw = community.get("prayer_scheduling")
                if prayer_raw:
                    flags["prayer_break_required"] = True
                    # Normalise to dict
                    prayer: Dict = {}
                    if isinstance(prayer_raw, dict):
                        prayer = prayer_raw
                    elif isinstance(prayer_raw, list):
                        for item in prayer_raw:
                            if isinstance(item, dict):
                                prayer.update(item)
                    windows = prayer.get("prayer_windows", [])
                    if windows:
                        flags["prayer_windows"] = [
                            f"{p.get('name','?')} (~{p.get('approximate_time','?')}, "
                            f"{p.get('duration_min','?')}min)"
                            for p in windows if isinstance(p, dict)
                        ]
                # Banana leaf
                if community.get("service_rituals", {}).get("banana_leaf_service"):
                    flags["banana_leaf_service"] = True
                # Downstream flags — may be dict or list-of-dicts
                downstream_raw = community.get("flags_to_pass", {})
                downstream_items: List[tuple] = []
                if isinstance(downstream_raw, dict):
                    downstream_items = list(downstream_raw.items())
                elif isinstance(downstream_raw, list):
                    for item in downstream_raw:
                        if isinstance(item, dict):
                            downstream_items.extend(item.items())
                for agent_key, flag in downstream_items:
                    bucket = result.setdefault("downstream_flags", {})
                    existing = bucket.get(agent_key)
                    if existing is None:
                        bucket[agent_key] = flag
                    elif isinstance(existing, list):
                        existing.append(flag)
                    else:
                        bucket[agent_key] = [existing, flag]

                cultural_flags.append(flags)

        if cultural_flags:
            result["cultural_flags"] = cultural_flags
            result["cultural_communities_matched"] = matched_communities
            kb_sources.append(
                f"customer/cultural_norms -> matched: {', '.join(matched_communities)}"
            )

    # ── Step 5 ────────────────────────────────────────────────────────────────

    def _apply_crm_data(
        self,
        result: Dict,
        client_id: Optional[str],
        client_email: Optional[str],
        kb_sources: List[str],
    ) -> None:
        crm_data = self._kb.get("customer/interaction_history")
        clients: List[Dict] = crm_data.get("clients", [])
        vip_flags: List[Dict] = crm_data.get("vip_flags", [])
        escalation_triggers: List[Dict] = crm_data.get("escalation_triggers", [])

        match = None
        for client in clients:
            if client_id and client.get("client_id") == client_id:
                match = client
                break
            if client_email and client.get("email", "").lower() == client_email.lower():
                match = client
                break

        if not match:
            return

        result["client_profile"] = {
            "client_id": match.get("client_id"),
            "name": match.get("name"),
            "vip_tier": match.get("vip_tier"),
            "payment_reliability": match.get("payment_reliability"),
            "lifetime_spend": f"{match.get('currency','MYR')} {match.get('lifetime_spend_myr', 0):,}",
            "language_preference": match.get("language_preference"),
            "recurring_preferences": match.get("recurring_preferences", []),
            "agent_notes": match.get("agent_notes", ""),
        }

        # VIP escalation flag
        vip = next((v for v in vip_flags if v.get("client_id") == match.get("client_id")), None)
        if vip:
            result["vip_action"] = vip.get("action")
            result["vip_tier"] = vip.get("tier")

        # Payment risk flag
        if match.get("payment_reliability") in ("fair", "poor"):
            result["payment_risk_flag"] = (
                f"Client {match.get('name')} has {match.get('payment_reliability')} payment history. "
                "Require 50% prepayment before confirming booking."
            )

        # Complaint history
        complaints = match.get("complaint_log", [])
        if complaints:
            unresolved = [c for c in complaints if not c.get("resolved")]
            result["complaint_history_summary"] = {
                "total": len(complaints),
                "unresolved": len(unresolved),
                "last_issue": complaints[-1].get("issue", "") if complaints else "",
            }

        kb_sources.append(
            f"customer/interaction_history -> {match.get('client_id')} ({match.get('vip_tier')} tier, "
            f"{len(match.get('recurring_preferences', []))} preferences loaded)"
        )

    # ── Step 6 ────────────────────────────────────────────────────────────────

    def _apply_package_match(
        self,
        result: Dict,
        guest_count: int,
        budget: float,
        service_style: str,
        event_type: str,
        kb_sources: List[str],
    ) -> None:
        pkg_data = self._kb.get("customer/service_packages")
        packages: List[Dict] = pkg_data.get("packages", [])
        rules: List[Dict] = pkg_data.get("package_matching_rules", [])
        addons: List[Dict] = pkg_data.get("addons", [])

        budget_per_head = result.get("budget_per_head", budget / max(guest_count, 1))

        # Simple scoring: find best package by guest count + budget
        best_pkg = None
        for pkg in packages:
            try:
                min_g = int(pkg.get("min_guests", 0))
                max_g = int(pkg.get("max_guests", 99999))
            except (ValueError, TypeError):
                min_g, max_g = 0, 99999
            # Use MYR as reference; if PHP, divide by ~25 to estimate MYR equiv
            budget_myr = budget_per_head
            # Very rough: if location suggests PHP, convert
            location = str(result.get("location", "")).lower()
            if "philippines" in location or result.get("currency") == "PHP":
                budget_myr = budget_per_head / 25.0
            elif "singapore" in location or result.get("currency") == "SGD":
                budget_myr = budget_per_head * 3.5

            pkg_max_myr = pkg.get("pricing_myr_per_head", {})
            if isinstance(pkg_max_myr, dict):
                pkg_price = float(pkg_max_myr.get("standard", 999))
            else:
                pkg_price = float(pkg_max_myr)

            if min_g <= guest_count <= max_g and budget_myr >= pkg_price * 0.8:
                # Accept if budget is within 20% of package price
                best_pkg = pkg

        if best_pkg:
            pricing_info = best_pkg.get("pricing_myr_per_head", {})
            result["recommended_package"] = {
                "package_id": best_pkg.get("package_id"),
                "name": best_pkg.get("name"),
                "tier": best_pkg.get("tier"),
                "included_dishes": best_pkg.get("included_dishes"),
                "service_style": best_pkg.get("service_style"),
                "price_per_head_myr": (
                    pricing_info.get("standard") if isinstance(pricing_info, dict)
                    else pricing_info
                ),
                "minimum_spend_myr": best_pkg.get("minimum_spend_myr"),
                "upgrade_options": best_pkg.get("upgrade_options", []),
            }
            kb_sources.append(
                f"customer/service_packages -> matched: {best_pkg.get('package_id')} "
                f"({best_pkg.get('name')}, {guest_count} pax)"
            )
        else:
            result["recommended_package"] = {
                "package_id": "PKG-BESPOKE",
                "name": "Bespoke / Custom Quote",
                "note": "No standard package matches; bespoke quote required.",
            }
            kb_sources.append("customer/service_packages -> no standard match; bespoke required")

        # Suggest relevant add-ons based on event type
        event_lower = event_type.lower()
        relevant_addons = [
            a.get("name") for a in addons
            if ("wedding" in event_lower and "satay" in str(a.get("name", "")).lower())
            or ("gala" in event_lower and "bar" in str(a.get("id", "")).lower())
            or ("birthday" in event_lower and "dessert" in str(a.get("name", "")).lower())
        ]
        if relevant_addons:
            result["suggested_addons"] = relevant_addons

    # ── Step 7 ────────────────────────────────────────────────────────────────

    def _apply_venue_check(
        self, result: Dict, venue_name: str, kb_sources: List[str]
    ) -> None:
        venue_data = self._kb.get("shared/venue_index")
        venues: List[Dict] = venue_data.get("venues", [])

        venue_lower = venue_name.lower()
        match = None
        for v in venues:
            if (venue_lower in str(v.get("name", "")).lower()
                    or str(v.get("name", "")).lower() in venue_lower):
                match = v
                break

        if match:
            status = match.get("status", "unknown")
            result["venue_check"] = {
                "venue_id": match.get("venue_id"),
                "name": match.get("name"),
                "status": status,
                "outside_catering_allowed": match.get("outside_catering_allowed"),
                "kitchen_available": match.get("kitchen_available"),
                "halal_only": match.get("halal_only_venue", False),
                "access_constraints": match.get("access_constraints", []),
                "notes": match.get("notes", ""),
            }
            if status == "not_compatible":
                result["venue_warning"] = (
                    f"VENUE ALERT: {match['name']} does not permit outside catering. "
                    "Client must be notified to change venue or confirm venue policy."
                )
            kb_sources.append(
                f"shared/venue_index -> {match.get('venue_id')}: status={status}"
            )
        else:
            result["venue_check"] = {
                "name": venue_name,
                "status": "unknown",
                "notes": "Venue not in our database. Logistics agent to conduct site assessment.",
            }
            kb_sources.append(f"shared/venue_index -> venue unknown: '{venue_name}'")

    # ── Step 8 ────────────────────────────────────────────────────────────────

    def _apply_policy_flags(
        self, result: Dict, raw_input: Dict, kb_sources: List[str]
    ) -> None:
        faq_data = self._kb.get("customer/faq_policies")
        deposit = {}
        cancel = {}
        headcount = {}
        for pol in faq_data.get("deposit_and_payment", []):
            if pol.get("policy_id") == "POL-PAY-001":
                deposit = pol
        for pol in faq_data.get("cancellation_policy", []):
            if pol.get("policy_id") == "POL-CANCEL-001":
                cancel = pol
        for pol in faq_data.get("headcount_and_changes", []):
            if pol.get("policy_id") == "POL-HEAD-001":
                headcount = pol

        if deposit or cancel or headcount:
            result["booking_policies"] = {
                "deposit_required_pct": deposit.get("details", {}).get("deposit_pct"),
                "deposit_due": deposit.get("details", {}).get("due"),
                "balance_due_days_before_event": (
                    headcount.get("details", {}).get("deadline_days_before_event")
                ),
                "headcount_final_deadline_days": (
                    headcount.get("details", {}).get("deadline_days_before_event")
                ),
                "cancellation_summary": cancel.get("summary"),
            }
            kb_sources.append(
                "customer/faq_policies -> deposit + cancellation + headcount policies loaded"
            )

        # Dietary liability flag if no allergens declared
        if not result.get("critical_allergens") and result.get("dietary_constraints"):
            faq_diet = faq_data.get("dietary_liability", [])
            for pol in faq_diet:
                if pol.get("policy_id") == "POL-DIET-001":
                    result["dietary_declaration_reminder"] = pol.get("exact_answer", "")
                    break
