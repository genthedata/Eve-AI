"""
Generic OpenAI-compatible chat completions provider.
Covers: OpenAI, Groq, Together AI, LM Studio, Jan, any /chat/completions endpoint.
Env: MODEL_ENDPOINT, MODEL_API_KEY, MODEL_NAME
"""

from __future__ import annotations

import os

import requests

from app.providers.base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self) -> None:
        self._endpoint = os.getenv("MODEL_ENDPOINT", "https://api.openai.com/v1").rstrip("/")
        self._api_key = os.getenv("MODEL_API_KEY", "").strip()
        self._model = os.getenv("MODEL_NAME", "gpt-4o-mini").strip()

    def chat(self, messages):
        """Native multi-turn using OpenAI /chat/completions."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        resp = requests.post(
            f"{self._endpoint}/chat/completions",
            headers=headers,
            json={"model": self._model, "messages": messages, "temperature": 0.7},
            timeout=60,
        )
        resp.raise_for_status()
        return str(resp.json()["choices"][0]["message"]["content"]).strip()

    def stream_chat(self, messages):
        """Stream tokens via Server-Sent Events."""
        import json as _json
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        resp = requests.post(
            f"{self._endpoint}/chat/completions",
            headers=headers,
            json={"model": self._model, "messages": messages,
                  "temperature": 0.7, "stream": True},
            stream=True,
            timeout=60,
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if text.startswith("data: "):
                text = text[6:]
            if text.strip() == "[DONE]":
                break
            try:
                data = _json.loads(text)
                token = data["choices"][0].get("delta", {}).get("content", "")
                if token:
                    yield token
            except Exception:
                continue

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        resp = requests.post(
            f"{self._endpoint}/chat/completions",
            headers=headers,
            json={"model": self._model, "messages": messages, "temperature": 0.2},
            timeout=60,
        )
        resp.raise_for_status()
        return str(resp.json()["choices"][0]["message"]["content"]).strip()
