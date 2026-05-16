"""
Microsoft Agent Framework — orchestrator placeholder.

Future: replace OrchestratorAgent.run() with MAF Workflow / Agent team:
  - ThreadStore keyed by thread_id (maps to CateringPlanContext)
  - Handoff: customer → menu → inventory → logistics → pricing → monitoring
  - Tools bound via ToolRegistry → MAF FunctionTool definitions

Today: runs native_runner (deterministic DAG) and annotates the response.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from app.platform.config import platform_metadata
from app.platform.ms_agent_framework.agent_registry_placeholder import (
    register_specialist_agents_placeholder,
)
from app.platform.ms_agent_framework.workflows_placeholder import (
    build_catering_workflow_placeholder,
)


class MSAgentFrameworkOrchestratorPlaceholder:
    """~50% MAF surface: registry + workflow spec exist; execution = native DAG."""

    def is_available(self) -> bool:
        # TODO(MAF): return True when `agent-framework` is installed and configured
        return False

    def run(
        self,
        request_payload: Dict[str, Any],
        thread_id: str,
        *,
        native_runner: Callable[[Dict[str, Any], str], Dict[str, Any]],
    ) -> Dict[str, Any]:
        _ = build_catering_workflow_placeholder(thread_id)
        _agents = register_specialist_agents_placeholder()

        # PLACEHOLDER: when MAF is available, execute workflow here instead of fallback.
        # from agent_framework import ...  # noqa: F401 — future import
        result = native_runner(request_payload, thread_id)

        meta = platform_metadata()
        meta["ms_agent_framework"]["workflow"] = "catering_dag_v1_placeholder"
        meta["ms_agent_framework"]["registered_agents"] = list(_agents.keys())
        meta["ms_agent_framework"]["executed_via"] = "native_dag_fallback"
        result["platform"] = meta
        result["ms_agent_framework_notice"] = (
            "USE_MS_AGENT_FRAMEWORK=true — MAF orchestration is a placeholder. "
            "Pipeline ran via native DAG. See docs/microsoft-agent-framework-architecture.md."
        )
        return result
