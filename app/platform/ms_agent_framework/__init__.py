"""
Microsoft Agent Framework integration — PLACEHOLDER (~50% design surfaced).

Target SDK (when implemented):
  pip install agent-framework  # Microsoft Agent Framework

This package does NOT import the real SDK today. It documents the swap-in
points and delegates execution to the native DAG until MAF workers are wired.
"""

from app.platform.ms_agent_framework.orchestrator_placeholder import (
    MSAgentFrameworkOrchestratorPlaceholder,
)
from app.platform.ms_agent_framework.agent_registry_placeholder import (
    MAF_SPECIALIST_AGENTS,
    register_specialist_agents_placeholder,
)

__all__ = [
    "MSAgentFrameworkOrchestratorPlaceholder",
    "MAF_SPECIALIST_AGENTS",
    "register_specialist_agents_placeholder",
]
