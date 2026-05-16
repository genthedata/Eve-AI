from abc import ABC, abstractmethod
from typing import Any, Dict, List


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        Multi-turn chat. Default implementation flattens history to a single prompt.
        Providers that support native multi-turn (Ollama /api/chat, OpenAI /chat/completions)
        should override this for better context handling.
        """
        system = ""
        parts: List[str] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                system = content
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            else:
                parts.append(f"User: {content}")
        prompt = "\n\n".join(parts)
        return self.generate(prompt, system_prompt=system)
