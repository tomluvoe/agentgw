"""CLI client that connects to agentgw daemon via HTTP."""

from __future__ import annotations

import httpx
import json
from typing import AsyncIterator


class AgentGWClient:
    """HTTP client for agentgw daemon."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080", api_key: str | None = None):
        self._base_url = base_url.rstrip("/")
        self._headers = {}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    async def chat(self, skill_name: str, message: str, session_id: str | None = None) -> AsyncIterator[str]:
        """Stream chat response via SSE."""
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json={
                    "skill_name": skill_name,
                    "message": message,
                    "session_id": session_id,
                },
                headers=self._headers,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])  # Skip "data: " prefix
                        if "text" in data:
                            yield data["text"]
                    except json.JSONDecodeError:
                        # Skip malformed JSON
                        pass

    async def run(self, skill_name: str, message: str) -> str:
        """Single-shot execution."""
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self._base_url}/api/run",
                json={"skill_name": skill_name, "message": message},
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()["result"]

    async def list_skills(self) -> list[dict]:
        """List available skills."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self._base_url}/api/skills", headers=self._headers)
            response.raise_for_status()
            return response.json()

    async def ingest(
        self,
        text: str,
        source: str,
        skills: list[str] | None = None,
        tags: list[str] | None = None,
        collection: str = "default",
    ) -> dict:
        """Ingest document."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/api/ingest",
                json={
                    "text": text,
                    "source": source,
                    "skills": skills or [],
                    "tags": tags or [],
                    "collection": collection,
                },
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    async def list_sessions(self, skill_name: str | None = None) -> list[dict]:
        """List conversation sessions."""
        async with httpx.AsyncClient() as client:
            params = {}
            if skill_name:
                params["skill_name"] = skill_name

            response = await client.get(
                f"{self._base_url}/api/sessions",
                params=params,
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_history(self, session_id: str) -> list[dict]:
        """Get session conversation history."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._base_url}/api/sessions/{session_id}/history",
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    async def list_documents(
        self,
        collection: str = "default",
        skill_name: str | None = None,
        tags: list[str] | None = None,
    ) -> list[dict]:
        """List ingested documents."""
        async with httpx.AsyncClient() as client:
            params = {"collection": collection}
            if skill_name:
                params["skill_name"] = skill_name
            if tags:
                params["tags"] = ",".join(tags)

            response = await client.get(
                f"{self._base_url}/api/documents",
                params=params,
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    async def delete_documents(
        self,
        source_pattern: str | None = None,
        collection: str = "default",
        skill_name: str | None = None,
    ) -> dict:
        """Delete documents matching criteria."""
        async with httpx.AsyncClient() as client:
            params = {"collection": collection}
            if source_pattern:
                params["source_pattern"] = source_pattern
            if skill_name:
                params["skill_name"] = skill_name

            response = await client.delete(
                f"{self._base_url}/api/documents",
                params=params,
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    async def daemon_status(self) -> dict:
        """Get daemon status."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self._base_url}/daemon/status")
            response.raise_for_status()
            return response.json()

    async def health(self) -> dict:
        """Check health status."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self._base_url}/health")
            response.raise_for_status()
            return response.json()
