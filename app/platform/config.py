"""
Platform configuration — orchestration backend and Azure service toggles.

ORCHESTRATION_BACKEND (optional explicit override):
  native_dag          — default; in-process OrchestratorAgent DAG
  autogen             — Microsoft AutoGen group-chat (USE_AUTOGEN=true)
  ms_agent_framework  — Microsoft Agent Framework (placeholder; falls back to DAG)

When unset, priority is: ms_agent_framework > autogen > native_dag
(based on USE_MS_AGENT_FRAMEWORK / USE_AUTOGEN flags).
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict


class OrchestrationBackend(str, Enum):
    NATIVE_DAG = "native_dag"
    AUTOGEN = "autogen"
    MS_AGENT_FRAMEWORK = "ms_agent_framework"


def _truthy(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes")


def use_ms_agent_framework() -> bool:
    return _truthy("USE_MS_AGENT_FRAMEWORK")


def use_autogen() -> bool:
    return _truthy("USE_AUTOGEN")


def use_azure_ai_foundry() -> bool:
    return _truthy("USE_AZURE_AI_FOUNDRY")


def use_azure_ai_search() -> bool:
    return _truthy("USE_AZURE_AI_SEARCH")


def get_orchestration_backend() -> OrchestrationBackend:
    explicit = os.getenv("ORCHESTRATION_BACKEND", "").strip().lower()
    if explicit:
        try:
            return OrchestrationBackend(explicit)
        except ValueError:
            pass
    if use_ms_agent_framework():
        return OrchestrationBackend.MS_AGENT_FRAMEWORK
    if use_autogen():
        return OrchestrationBackend.AUTOGEN
    return OrchestrationBackend.NATIVE_DAG


def platform_metadata() -> Dict[str, Any]:
    """Attach to API responses / final_report without changing business logic."""
    backend = get_orchestration_backend()
    return {
        "orchestration_backend": backend.value,
        "orchestration_backend_label": {
            OrchestrationBackend.NATIVE_DAG: "Native DAG (in-process)",
            OrchestrationBackend.AUTOGEN: "Microsoft AutoGen (optional)",
            OrchestrationBackend.MS_AGENT_FRAMEWORK: "Microsoft Agent Framework (placeholder)",
        }[backend],
        "ms_agent_framework": {
            "enabled": use_ms_agent_framework(),
            "implementation_status": "placeholder_50pct",
            "fallback": "native_dag",
            "module": "app.platform.ms_agent_framework",
        },
        "azure_ai_foundry": {
            "enabled": use_azure_ai_foundry(),
            "implementation_status": "placeholder",
            "project_endpoint": os.getenv("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT", ""),
            "deployment_orchestrator": os.getenv("AZURE_AI_FOUNDRY_DEPLOYMENT_ORCH", ""),
        },
        "azure_ai_search": {
            "enabled": use_azure_ai_search(),
            "implementation_status": "placeholder",
            "endpoint": os.getenv("AZURE_SEARCH_ENDPOINT", ""),
            "index_kb": os.getenv("AZURE_SEARCH_INDEX_KB", "eve-cater-kb"),
        },
        "rag_mode": (
            "azure_ai_search"
            if use_azure_ai_search()
            else "yaml_keyword_rag_lite"
        ),
    }


def platform_status_banner() -> str:
    m = platform_metadata()
    lines = [
        f"Orchestration: {m['orchestration_backend_label']}",
        f"MAF placeholder: {'ON' if m['ms_agent_framework']['enabled'] else 'off'}",
        f"AI Foundry:      {'ON (placeholder)' if m['azure_ai_foundry']['enabled'] else 'off'}",
        f"Azure AI Search: {'ON (placeholder)' if m['azure_ai_search']['enabled'] else 'off'}",
        f"RAG:             {m['rag_mode']}",
    ]
    return " | ".join(lines)
