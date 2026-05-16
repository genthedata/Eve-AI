"""
Microsoft Azure AI Foundry — placeholder clients.

When USE_AZURE_AI_FOUNDRY=true, model calls can route through Foundry project
deployments instead of raw AZURE_OPENAI_* endpoints.

Not wired to production; see client_placeholder.py.
"""

from app.platform.foundry.client_placeholder import AzureAIFoundryClientPlaceholder
from app.platform.foundry.deployments_placeholder import get_foundry_deployment_map

__all__ = ["AzureAIFoundryClientPlaceholder", "get_foundry_deployment_map"]
