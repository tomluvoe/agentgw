"""HTTP client for a running agentgw daemon."""

from __future__ import annotations

import os
from typing import Any

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
