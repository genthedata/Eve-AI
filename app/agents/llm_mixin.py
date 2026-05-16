"""LLM reasoning mixin — shared by all specialist agents."""

from __future__ import annotations

from typing import Optional

from app.providers.base import LLMProvider


class LLMReasoningMixin:
    """
    Mixin that adds optional LLM reasoning capability to any specialist agent.
    When no provider is set (or USE_LLM=false), reason() returns None silently.
    """

    _provider: Optional[LLMProvider] = None

    def set_provider(self, provider: Optional[LLMProvider]) -> None:
        self._provider = provider

    def reason(
        self,
        prompt: str,
        system_prompt: str = "You are a specialist catering agent. Be concise and practical.",
    ) -> Optional[str]:
        """
        Call the LLM provider with the given prompt.
        Returns None if no provider is configured or if the call fails.
        """
        # PLATFORM PLACEHOLDER: Azure AI Foundry deployment route (USE_AZURE_AI_FOUNDRY=true)
        try:
            from app.platform.config import use_azure_ai_foundry

            if use_azure_ai_foundry():
                from app.platform.foundry import AzureAIFoundryClientPlaceholder

                foundry = AzureAIFoundryClientPlaceholder()
                if foundry.is_configured():
                    out = foundry.generate(prompt, system_prompt=system_prompt)
                    if out:
                        return out
        except Exception:
            pass

        if self._provider is None:
            return None
        try:
            return self._provider.generate(prompt, system_prompt=system_prompt)
        except Exception:
            return None
