from __future__ import annotations

import logging

import httpx

from app.core.config import settings

LOGGER = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float | None = None) -> None:
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.timeout = httpx.Timeout(timeout_seconds or settings.ollama_timeout_seconds)

    async def generate(self, model: str, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        content = data.get("message", {}).get("content")
        if not content:
            raise RuntimeError("Ollama returned an empty response")

        LOGGER.info("Ollama response received for model=%s (%d chars)", model, len(content))
        return content
