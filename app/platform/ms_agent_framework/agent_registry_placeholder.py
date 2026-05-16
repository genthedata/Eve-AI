"""
Microsoft Agent Framework — specialist agent registry placeholder.

Maps each in-repo specialist to a future MAF Agent definition (name, tools, instructions).
"""

from __future__ import annotations

from typing import Any, Dict, List

# Mirror app/orchestrator.py DAG order
MAF_SPECIALIST_AGENTS: List[Dict[str, str]] = [
    {"maf_id": "customer_agent", "module": "app.agents.customer_agent", "step": "intake"},
    {"maf_id": "menu_agent", "module": "app.agents.menu_agent", "step": "menu"},
    {"maf_id": "inventory_agent", "module": "app.agents.inventory_agent", "step": "inventory"},
    {"maf_id": "logistics_agent", "module": "app.agents.logistics_agent", "step": "logistics"},
    {"maf_id": "pricing_agent", "module": "app.agents.pricing_agent", "step": "pricing"},
    {"maf_id": "monitoring_agent", "module": "app.agents.monitoring_agent", "step": "monitoring"},
]


def register_specialist_agents_placeholder() -> Dict[str, Any]:
    """
    PLACEHOLDER: register MAF Agent instances with tools from ToolRegistry.

    Future sketch:
        for spec in MAF_SPECIALIST_AGENTS:
            agents[spec["maf_id"]] = Agent(
                name=spec["maf_id"],
                instructions=load_system_prompt(spec["maf_id"]),
                tools=tool_registry.maf_tools_for(spec["maf_id"]),
            )
    """
    return {spec["maf_id"]: {"status": "placeholder", **spec} for spec in MAF_SPECIALIST_AGENTS}
