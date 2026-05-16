"""
Eve Cater's AI — Microsoft platform integration layer (placeholders).

Switchable orchestration backends and Azure service hooks. Default runtime is
unchanged (native DAG). Set env vars in .env to declare future platform targets.

See docs/microsoft-agent-framework-architecture.md for the target design.
"""

from app.platform.config import (
    OrchestrationBackend,
    get_orchestration_backend,
    platform_metadata,
    platform_status_banner,
    use_azure_ai_foundry,
    use_azure_ai_search,
    use_ms_agent_framework,
)

__all__ = [
    "OrchestrationBackend",
    "get_orchestration_backend",
    "platform_metadata",
    "platform_status_banner",
    "use_azure_ai_foundry",
    "use_azure_ai_search",
    "use_ms_agent_framework",
]
