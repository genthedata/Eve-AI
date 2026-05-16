"""
Provider factory.
Set MODEL_PROVIDER to one of: mock | ollama | openai_compatible | azure_openai
"""

from __future__ import annotations

import os

from app.providers.base import LLMProvider


def build_provider() -> LLMProvider:
    prov = os.getenv("MODEL_PROVIDER", "mock").strip().lower()

    if prov == "ollama":
        from app.providers.ollama import OllamaProvider
        return OllamaProvider()

    if prov == "openai_compatible":
        from app.providers.openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider()

    if prov == "azure_openai":
        from app.providers.azure_openai import AzureOpenAIProvider
        return AzureOpenAIProvider(role="specialist")

    from app.providers.mock_provider import MockProvider
    return MockProvider()
