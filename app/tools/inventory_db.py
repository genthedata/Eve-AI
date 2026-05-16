from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple


# Granular ingredient keys that demand_planner uses.
# The live stock dict can be seeded with any of these keys.
TRACKED_INGREDIENT_KEYS = [
    "chicken_kg", "beef_kg", "pork_kg", "seafood_fish_kg", "seafood_prawn_kg",
    "tofu_kg", "lentils_kg", "rice_kg", "rice_noodles_kg", "pasta_kg",
    "vegetables_kg", "aromatics_kg", "fresh_herbs_kg", "fruit_kg",
    "mushrooms_kg", "coconut_milk_l", "dairy_cream_l", "cooking_oil_l",
    "soy_sauce_l", "fish_sauce_l", "tamarind_l", "vinegar_l",
    "spice_blend_pack", "peanut_sauce_kg", "laksa_paste_kg",
    "broth_l", "eggs_pcs", "flour_kg", "sugar_kg",
]


class InventoryDBTool:
    """
    Stock and supplier data.
    When SIMULATE_INVENTORY=true, delegates stock levels to InventorySimulator.
    Supplier assignments come from KBSearch.
    """

    def __init__(self) -> None:
        self._base_stock: Dict[str, float] = {
            "rice_kg": 15.0,
            "mixed_vegetables_kg": 8.0,
            "protein_kg": 10.0,
            "fruit_kg": 5.0,
            "seasoning_pack": 3.0,
        }
        self._safety_factor = 1.1
        self._simulation_events: List[str] = []

    def _simulate(self) -> bool:
        return os.getenv("SIMULATE_INVENTORY", "false").strip().lower() in ("1", "true", "yes")

    def get_current_stock(self) -> Dict[str, float]:
        if self._simulate():
            from app.tools.inventory_simulation import InventorySimulator
            sim = InventorySimulator(self._base_stock)
            snapshot = sim.run()
            self._simulation_events = snapshot.events
            return snapshot.stock
        return dict(self._base_stock)

    def get_simulation_events(self) -> List[str]:
        return list(self._simulation_events)

    def get_safety_factor(self) -> float:
        return self._safety_factor

    def compute_ingredients_needed(self, guest_count: int) -> Dict[str, float]:
        sf = self._safety_factor
        return {
            "rice_kg": round((guest_count * 0.12) * sf, 2),
            "mixed_vegetables_kg": round((guest_count * 0.09) * sf, 2),
            "protein_kg": round((guest_count * 0.15) * sf, 2),
            "fruit_kg": round((guest_count * 0.08) * sf, 2),
            "seasoning_pack": round((guest_count * 0.05) * sf, 2),
        }

    def compute_shortages_and_procurement(
        self,
        ingredients: Dict[str, float],
        stock: Optional[Dict[str, float]] = None,
    ) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
        stock = stock if stock is not None else self._base_stock
        shortages: Dict[str, float] = {}
        procurement_list: List[Dict[str, Any]] = []
        for item, needed in ingredients.items():
            available = stock.get(item, 0.0)
            if needed > available:
                shortage = round(needed - available, 2)
                shortages[item] = shortage
                procurement_list.append({"item": item, "qty": shortage, "unit": "kg_or_pack"})
        return shortages, procurement_list

    def get_supplier_assignments(
        self,
        procurement_list: List[Dict[str, Any]],
        require_halal: bool = False,
    ) -> List[Dict[str, Any]]:
        from app.tools.kb_search import KBSearch
        kb = KBSearch()
        return kb.get_procurement_suppliers(procurement_list, require_halal=require_halal)

    def get_granular_stock(self) -> Dict[str, float]:
        """
        Return on-hand quantities for granular procurement keys used by
        demand_planner. Extends the base 5-item stock dict with realistic
        seed values for all tracked ingredient categories.

        In a production system this would query a live warehouse database.
        Here we return a representative snapshot that the agent subtracts from.
        """
        base = self.get_current_stock()
        # Map legacy broad keys to granular ones + add extras
        granular: Dict[str, float] = {
            "chicken_kg":       base.get("protein_kg", 10.0) * 0.5,
            "beef_kg":          base.get("protein_kg", 10.0) * 0.3,
            "pork_kg":          3.0,
            "seafood_fish_kg":  2.0,
            "seafood_prawn_kg": 1.5,
            "tofu_kg":          base.get("protein_kg", 10.0) * 0.2,
            "lentils_kg":       2.0,
            "rice_kg":          base.get("rice_kg", 15.0),
            "rice_noodles_kg":  2.0,
            "pasta_kg":         1.5,
            "vegetables_kg":    base.get("mixed_vegetables_kg", 8.0),
            "aromatics_kg":     1.5,
            "fresh_herbs_kg":   0.5,
            "fruit_kg":         base.get("fruit_kg", 5.0),
            "mushrooms_kg":     1.0,
            "coconut_milk_l":   3.0,
            "dairy_cream_l":    1.0,
            "cooking_oil_l":    5.0,
            "soy_sauce_l":      2.0,
            "fish_sauce_l":     1.0,
            "tamarind_l":       0.5,
            "vinegar_l":        1.5,
            "spice_blend_pack": float(base.get("seasoning_pack", 3.0)) * 0.6,
            "peanut_sauce_kg":  0.5,
            "laksa_paste_kg":   0.2,
            "broth_l":          4.0,
            "eggs_pcs":         24.0,
            "flour_kg":         2.0,
            "sugar_kg":         2.0,
        }
        return {k: round(v, 2) for k, v in granular.items()}

    def compute_ingredients_from_menu(
        self,
        menu_items: List[str],
        guest_count: int,
        event_type: str = "default",
        service_style: str = "buffet",
        require_halal: bool = False,
        region: str = "Philippines",
        event_date: str = "",
        kb: "Any | None" = None,
        is_urgent: bool = False,
    ) -> Dict[str, Any]:
        """
        Use demand_planner to translate a menu + guest count into a full
        procurement plan, subtracting live stock from granular quantities.

        Returns the procurement plan dict from demand_planner.build_procurement_plan().
        Falls back to legacy compute_ingredients_needed() if demand_planner fails.
        """
        try:
            from app.tools.demand_planner import build_procurement_plan
            from app.tools.kb_yaml import YAMLKBSearch
            _kb = kb or YAMLKBSearch()
            stock = self.get_granular_stock()
            return build_procurement_plan(
                menu_items=menu_items,
                guest_count=guest_count,
                current_stock=stock,
                event_type=event_type,
                service_style=service_style,
                require_halal=require_halal,
                region=region,
                event_date=event_date,
                kb=_kb,
                is_urgent=is_urgent,
            )
        except Exception as exc:
            # Graceful fallback to legacy method
            legacy = self.compute_ingredients_needed(guest_count)
            stock = self.get_current_stock()
            shortages, proc_list = self.compute_shortages_and_procurement(legacy, stock)
            return {
                "menu_items": menu_items,
                "guest_count": guest_count,
                "ingredient_breakdown": {k: {"qty_to_procure": v, "unit": "kg"} for k, v in legacy.items()},
                "vendor_assignments": proc_list,
                "vendor_assignment_failures": [],
                "seasonal_warnings": [],
                "total_cost_estimate": 0.0,
                "approval_requirement": {"approval_level": "Unknown", "approver": "Manual"},
                "kb_sources": [f"fallback: demand_planner unavailable ({exc})"],
                "is_urgent": is_urgent,
            }
