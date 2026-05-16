"""Map specialist agents → Foundry model deployments (placeholder)."""

from __future__ import annotations

import os
from typing import Dict


def get_foundry_deployment_map() -> Dict[str, str]:
    orch = os.getenv("AZURE_AI_FOUNDRY_DEPLOYMENT_ORCH", "gpt-4o")
    spec = os.getenv("AZURE_AI_FOUNDRY_DEPLOYMENT_SPECIALIST", "gpt-4o-mini")
    return {
        "orchestrator": orch,
        "customer_agent": spec,
        "menu_agent": spec,
        "inventory_agent": spec,
        "logistics_agent": spec,
        "pricing_agent": spec,
        "monitoring_agent": orch,
    }
