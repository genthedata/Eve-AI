"""
Unified orchestration entry — routes to native DAG, AutoGen, or MAF placeholder.

Existing code paths call through here when using AgentRouter; native
OrchestratorAgent remains the implementation for DAG and MAF fallback.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from app.platform.config import OrchestrationBackend, get_orchestration_backend, platform_metadata


def run_catering_flow(
    request_payload: Dict[str, Any],
    thread_id: str,
    *,
    native_runner: Callable[[Dict[str, Any], str], Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Run the catering pipeline via the configured backend.

    native_runner: typically AgentRouter._run_deterministic (wraps OrchestratorAgent).
    """
    backend = get_orchestration_backend()

    if backend == OrchestrationBackend.MS_AGENT_FRAMEWORK:
        from app.platform.ms_agent_framework.orchestrator_placeholder import (
            MSAgentFrameworkOrchestratorPlaceholder,
        )

        return MSAgentFrameworkOrchestratorPlaceholder().run(
            request_payload, thread_id, native_runner=native_runner
        )

    if backend == OrchestrationBackend.AUTOGEN:
        from app.runtime.ms_autogen_adapter import MicrosoftAgentFrameworkAdapter

        adapter = MicrosoftAgentFrameworkAdapter()
        if adapter.is_available():
            payload = {**request_payload, "thread_id": thread_id}
            result = adapter.run_multi_agent_flow(payload)
            result.setdefault("platform", platform_metadata())
            return result
        result = native_runner(request_payload, thread_id)
        result["autogen_warning"] = (
            "USE_AUTOGEN / ORCHESTRATION_BACKEND=autogen but autogen-agentchat "
            "is not installed. Ran native DAG. "
            "Install: pip install autogen-agentchat autogen-ext[openai]"
        )
        result.setdefault("platform", platform_metadata())
        return result

    result = native_runner(request_payload, thread_id)
    result.setdefault("platform", platform_metadata())
    return result
