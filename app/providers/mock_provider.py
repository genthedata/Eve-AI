from app.providers.base import LLMProvider


class MockProvider(LLMProvider):
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return (
            "Mock provider response. Replace with Ollama or OpenAI-compatible "
            "provider for real LLM behavior."
        )
