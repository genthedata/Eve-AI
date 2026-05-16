"""
Per-agent platform hook — PLACEHOLDER metadata only (no behavior change).

Specialist agents may call agent_platform_hint() to attach future MAF/Foundry
context to their output dict under '_platform' when implementing the switch.
"""

from __future__ import annotations

from typing import Any, Dict

from app.platform.config import platform_metadata, use_azure_ai_foundry, use_ms_agent_framework


def agent_platform_hint(agent_name: str) -> Dict[str, Any]:
    """Lightweight metadata for specialist agent responses (optional)."""
    base = platform_metadata()
    return {
        "agent": agent_name,
        "maf_worker_placeholder": use_ms_agent_framework(),
        "foundry_model_route_placeholder": use_azure_ai_foundry(),
        "orchestration_backend": base["orchestration_backend"],
    }
