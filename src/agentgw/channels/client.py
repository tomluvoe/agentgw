"""HTTP client for a running agentgw daemon."""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import httpx


class AgentClient:
    def __init__(self, base_url: str, timeout: float = 120.0, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key if api_key is not None else os.environ.get("AGENTGW_API_KEY") or None

    def _headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()

    async def skills(self) -> list[dict[str, str]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/v1/skills", headers=self._headers()
            )
            response.raise_for_status()
            return response.json()

    async def tools(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/v1/tools", headers=self._headers()
            )
            response.raise_for_status()
            return response.json()

    async def sessions(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/v1/sessions", headers=self._headers()
            )
            response.raise_for_status()
            return response.json()["sessions"]

    async def chat(self, message: str, session_id: str | None = None) -> dict[str, str]:
        payload: dict[str, str] = {"message": message}
        if session_id:
            payload["session_id"] = session_id
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat", json=payload, headers=self._headers()
            )
            response.raise_for_status()
            return response.json()

    async def chat_stream(
        self, message: str, session_id: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        payload: dict[str, str] = {"message": message}
        if session_id:
            payload["session_id"] = session_id
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/stream",
                json=payload,
                headers=self._headers(),
            ) as response:
                if response.status_code != 404:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        yield json.loads(raw)
                    return
        data = await self.chat(message, session_id=session_id)
        if data.get("response"):
            yield {"delta": data["response"]}
        yield {"session_id": data["session_id"], "done": True}
