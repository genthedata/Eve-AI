from typing import Any, Dict


# Base unit costs expressed in PHP.
# The engine scales these to whatever currency the customer chose.
_BASE_INGREDIENT_PER_GUEST_PHP = 180.0
_BASE_LABOR_PER_STAFF_PHP = 1800.0
_BASE_COST_PER_VEHICLE_PHP = 3500.0


class PricingEngineTool:
    """
    Cost rules, markup, and contingency.
    All base costs are stored in PHP; pass php_rate to express results
    in the customer's chosen currency (php_rate = PHP per 1 unit of that currency).
    """

    def __init__(self) -> None:
        self.contingency_rate = 0.08
        self.target_margin = 0.2

    def compute(
        self,
        guest_count: int,
        budget: float,
        kitchen_staff: int,
        delivery_vehicles: int,
        shortage_count: int,
        currency: str = "PHP",
        php_rate: float = 1.0,
    ) -> Dict[str, Any]:
        # Scale base PHP costs to the chosen currency
        ingredient_per_guest = _BASE_INGREDIENT_PER_GUEST_PHP / php_rate
        labor_per_staff = _BASE_LABOR_PER_STAFF_PHP / php_rate
        cost_per_vehicle = _BASE_COST_PER_VEHICLE_PHP / php_rate

        ingredient_cost = guest_count * ingredient_per_guest
        labor_cost = kitchen_staff * labor_per_staff
        logistics_cost = delivery_vehicles * cost_per_vehicle
        subtotal = ingredient_cost + labor_cost + logistics_cost
        contingency = self.contingency_rate * subtotal
        total_cost = subtotal + contingency

        suggested_quote = total_cost * (1 + self.target_margin)
        budget_fit = suggested_quote <= budget
        recommendation = (
            "Within budget. Keep current menu and staffing."
            if budget_fit
            else "Above budget. Reduce premium dishes or adjust staffing and logistics."
        )

        return {
            "currency": currency,
            "cost_breakdown": {
                "ingredient_cost": round(ingredient_cost, 2),
                "labor_cost": round(labor_cost, 2),
                "logistics_cost": round(logistics_cost, 2),
                "contingency": round(contingency, 2),
                "total_cost": round(total_cost, 2),
            },
            "pricing": {
                "target_margin": self.target_margin,
                "suggested_quote": round(suggested_quote, 2),
                "budget": budget,
                "budget_fit": budget_fit,
            },
            "recommendation": recommendation,
            "inventory_shortages_count": shortage_count,
        }
