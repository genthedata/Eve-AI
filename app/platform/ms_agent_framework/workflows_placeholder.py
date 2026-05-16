"""
Microsoft Agent Framework — workflow / handoff graph placeholder.

Target: sequential workflow matching the current fixed DAG (decompose_plan).
Optional future: parallel fan-out for inventory simulation + menu trends.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_catering_workflow_placeholder(thread_id: str) -> Dict[str, Any]:
    """
    Returns a serialisable workflow spec (not executed by MAF yet).

    PLACEHOLDER graph — mirrors OrchestratorAgent.decompose_plan().
    """
    steps: List[Dict[str, str]] = [
        {"id": "intake", "agent": "customer_agent", "handoff_to": "menu_agent"},
        {"id": "menu", "agent": "menu_agent", "handoff_to": "inventory_agent"},
        {"id": "inventory", "agent": "inventory_agent", "handoff_to": "logistics_agent"},
        {"id": "logistics", "agent": "logistics_agent", "handoff_to": "pricing_agent"},
        {"id": "pricing", "agent": "pricing_agent", "handoff_to": "monitoring_agent"},
        {"id": "monitoring", "agent": "monitoring_agent", "handoff_to": "orchestrator"},
    ]
    return {
        "workflow_id": "eve_cater_catering_dag_v1",
        "thread_id": thread_id,
        "engine": "microsoft_agent_framework_placeholder",
        "steps": steps,
        "termination": "monitoring_agent → orchestrator [execution_review]",
    }
