"""
Ollama local model provider.
Env: MODEL_ENDPOINT (default http://localhost:11434), MODEL_NAME (default llama3.1)
Run ollama first: ollama pull llama3.1
"""

from __future__ import annotations

import os

import requests

from app.providers.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        self._endpoint = os.getenv("MODEL_ENDPOINT", "http://localhost:11434").rstrip("/")
        self._model = os.getenv("MODEL_NAME", "llama3.1").strip()

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}".strip() if system_prompt else prompt
        resp = requests.post(
            f"{self._endpoint}/api/generate",
            json={"model": self._model, "prompt": full_prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return str(resp.json().get("response", "")).strip()

    def chat(self, messages):
        """Use Ollama /api/chat for native multi-turn conversation."""
        resp = requests.post(
            f"{self._endpoint}/api/chat",
            json={"model": self._model, "messages": messages, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return str(resp.json().get("message", {}).get("content", "")).strip()

    def stream_chat(self, messages):
        """Stream tokens from Ollama — yields string chunks as they arrive."""
        import json as _json
        resp = requests.post(
            f"{self._endpoint}/api/chat",
            json={"model": self._model, "messages": messages, "stream": True},
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                data = _json.loads(line)
            except Exception:
                continue
            token = data.get("message", {}).get("content", "")
            if token:
                yield token
            if data.get("done"):
                break
