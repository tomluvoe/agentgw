"""HTTP client for a running agentgw daemon."""

from __future__ import annotations

from typing import Any

import httpx


class AgentClient:
    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()

    async def skills(self) -> list[dict[str, str]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/skills")
            response.raise_for_status()
            return response.json()

    async def tools(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/tools")
            response.raise_for_status()
            return response.json()

    async def sessions(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/sessions")
            response.raise_for_status()
            return response.json()["sessions"]

    async def chat(self, message: str, session_id: str | None = None) -> dict[str, str]:
        payload: dict[str, str] = {"message": message}
        if session_id:
            payload["session_id"] = session_id
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/v1/chat", json=payload)
            response.raise_for_status()
            return response.json()
