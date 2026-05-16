"""
Azure AI Foundry project client — PLACEHOLDER.

Env:
  AZURE_AI_FOUNDRY_PROJECT_ENDPOINT
  AZURE_AI_FOUNDRY_API_KEY  (or DefaultAzureCredential)
  AZURE_AI_FOUNDRY_DEPLOYMENT_ORCH
  AZURE_AI_FOUNDRY_DEPLOYMENT_SPECIALIST

Future:
  from azure.ai.projects import AIProjectClient
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


class AzureAIFoundryClientPlaceholder:
    """Stub Foundry client; returns None for all generate() calls."""

    def __init__(self) -> None:
        self.project_endpoint = os.getenv("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT", "").strip()
        self.deployment_orch = os.getenv("AZURE_AI_FOUNDRY_DEPLOYMENT_ORCH", "gpt-4o")
        self.deployment_specialist = os.getenv(
            "AZURE_AI_FOUNDRY_DEPLOYMENT_SPECIALIST", "gpt-4o-mini"
        )

    def is_configured(self) -> bool:
        return bool(self.project_endpoint)

    def generate(
        self,
        prompt: str,
        *,
        role: str = "specialist",
        system_prompt: Optional[str] = None,
    ) -> Optional[str]:
        """
        PLACEHOLDER: route to Foundry chat completion for `role` deployment.

        Returns None — callers should fall back to existing LLMProvider.
        """
        _ = (prompt, role, system_prompt)
        # TODO(Foundry): AIProjectClient(...).agents.get_agent(...).run(...)
        return None

    def metadata(self) -> Dict[str, Any]:
        return {
            "service": "azure_ai_foundry",
            "status": "placeholder",
            "project_endpoint": self.project_endpoint or "(not set)",
            "deployments": {
                "orchestrator": self.deployment_orch,
                "specialist": self.deployment_specialist,
            },
        }
