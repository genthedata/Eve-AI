"""
Azure OpenAI chat client for orchestrator/specialist roles (GPT-4o / GPT-4o-mini style deployments).

PLATFORM: When USE_AZURE_AI_FOUNDRY=true, prefer app.platform.foundry.AzureAIFoundryClientPlaceholder
(placeholder) which will supersede direct AZURE_OPENAI_* calls via AI Foundry project deployments.

Requires: pip install openai
Env:
  AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY
  AZURE_OPENAI_API_VERSION (default 2024-08-01-preview)
  AZURE_OPENAI_DEPLOYMENT_ORCH (default gpt-4o)
  AZURE_OPENAI_DEPLOYMENT_SPECIALIST (default gpt-4o-mini)
"""

from __future__ import annotations

import os
from typing import Literal, Optional

from app.providers.base import LLMProvider


class AzureOpenAIProvider(LLMProvider):
    def __init__(self, role: Literal["orchestrator", "specialist"] = "specialist") -> None:
        self._role = role
        try:
            from openai import AzureOpenAI  # type: ignore
        except ImportError as e:
            raise RuntimeError("Install openai package: pip install openai") from e

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        if not endpoint or not api_key:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set")

        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview").strip()
        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        if role == "orchestrator":
            self._deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_ORCH", "gpt-4o").strip()
        else:
            self._deployment = os.getenv(
                "AZURE_OPENAI_DEPLOYMENT_SPECIALIST", "gpt-4o-mini"
            ).strip()

    def chat(self, messages):
        """Native multi-turn using Azure OpenAI SDK."""
        resp = self._client.chat.completions.create(
            model=self._deployment,
            messages=messages,
            temperature=0.7,
        )
        return (resp.choices[0].message.content or "").strip()

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(
            model=self._deployment,
            messages=messages,
            temperature=0.2,
        )
        choice = resp.choices[0].message
        return (choice.content or "").strip()
