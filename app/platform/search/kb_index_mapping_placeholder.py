"""
YAML KB path → Azure AI Search index field mapping (placeholder).

Used when syncing app/tools/data/kb/**/*.yaml into eve-cater-kb index.
"""

from __future__ import annotations

from typing import Dict, List

# agent_scope / kb_path prefix → index filter facet
KB_INDEX_FIELD_MAP: Dict[str, List[str]] = {
    "customer": ["customer/event_profiles", "customer/dietary_restrictions", "customer/cultural_norms"],
    "menu": ["menu/recipe_library", "menu/cuisine_trends", "menu/portion_yield"],
    "inventory": ["inventory/supplier_catalog", "inventory/procurement_sop"],
    "logistics": ["logistics/venue_profiles", "logistics/staff_scheduling"],
    "pricing": ["pricing/cost_of_goods", "pricing/market_benchmarks"],
    "shared": ["shared/seasonal_availability", "shared/competitor_pricing"],
}
