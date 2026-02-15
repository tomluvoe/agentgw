"""Tests for the FastAPI web application."""

import pytest
from fastapi.testclient import TestClient

from agentgw.core.config import Settings, LLMConfig, AgentConfig, StorageConfig
from agentgw.core.service import AgentService
from agentgw.interfaces.web.app import create_app


@pytest.fixture
def web_client(tmp_dir):
    """Create a test client with isolated storage, using context manager for lifespan."""
    settings = Settings(
        llm=LLMConfig(provider="openai", model="test-model"),
        agent=AgentConfig(),
        storage=StorageConfig(
            sqlite_path=str(tmp_dir / "test.db"),
            chroma_path=str(tmp_dir / "chroma"),
            log_dir=str(tmp_dir / "logs"),
        ),
        skills_dir="skills",
        openai_api_key="test-key",
    )
    svc = AgentService(settings=settings)
    app = create_app(service=svc)
    with TestClient(app) as client:
        yield client


class TestWebRoutes:
    def test_index_page(self, web_client):
        resp = web_client.get("/")
        assert resp.status_code == 200
        assert "agentgw" in resp.text
        assert "general_assistant" in resp.text

    def test_chat_page(self, web_client):
        resp = web_client.get("/chat/general_assistant")
        assert resp.status_code == 200
        assert "general_assistant" in resp.text

    def test_chat_page_404(self, web_client):
        resp = web_client.get("/chat/nonexistent_skill")
        assert resp.status_code == 404

    def test_ingest_page(self, web_client):
        resp = web_client.get("/ingest")
        assert resp.status_code == 200
        assert "Knowledge Base" in resp.text

    def test_api_skills(self, web_client):
        resp = web_client.get("/api/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        names = [s["name"] for s in data]
        assert "general_assistant" in names

    def test_api_sessions_empty(self, web_client):
        resp = web_client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_api_ingest(self, web_client):
        resp = web_client.post("/api/ingest", json={
            "text": "This is a test document about Python programming.",
            "source": "test.txt",
            "tags": ["python", "test"],
            "collection": "default",
        })
        assert resp.status_code == 200, f"Body: {resp.text}"
        data = resp.json()
        assert data["status"] == "ok"
        assert data["chunks_created"] >= 1
