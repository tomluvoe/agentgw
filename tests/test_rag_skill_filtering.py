"""Tests for RAG skill-based filtering."""

from __future__ import annotations

import pytest

from agentgw.rag.chroma import RAGStore


@pytest.fixture
async def rag_store(tmp_path):
    """Create a temporary RAG store."""
    store = RAGStore(tmp_path / "chroma")
    yield store


class TestRAGSkillFiltering:
    """Test skill-based document filtering in RAG."""

    async def test_ingest_with_skills(self, rag_store):
        """Documents can be ingested with specific skill names."""
        chunk_ids = await rag_store.ingest(
            text="This is about Python programming.",
            metadata={"source": "test.txt", "skills": ["code_assistant"], "tags": []},
        )
        assert len(chunk_ids) == 1

    async def test_ingest_available_to_all(self, rag_store):
        """Documents with empty skills list are available to all."""
        chunk_ids = await rag_store.ingest(
            text="This is general knowledge.",
            metadata={"source": "general.txt", "skills": [], "tags": []},
        )
        assert len(chunk_ids) == 1

    async def test_search_filters_by_skill(self, rag_store):
        """Search filters documents by skill name."""
        # Ingest docs with different skills
        await rag_store.ingest(
            text="Python code examples and best practices.",
            metadata={"source": "python.txt", "skills": ["code_assistant"], "tags": []},
        )
        await rag_store.ingest(
            text="Meeting notes from the quarterly review.",
            metadata={"source": "meeting.txt", "skills": ["meeting_assistant"], "tags": []},
        )

        # Search with skill filter
        results = await rag_store.search(
            query="code",
            skills=["code_assistant"],
            top_k=5,
        )
        assert len(results) == 1
        assert "Python" in results[0]["text"]

    async def test_search_empty_skills_matches_all(self, rag_store):
        """Documents with empty skills field match any search."""
        # Ingest one with specific skill, one available to all
        await rag_store.ingest(
            text="Python programming guide.",
            metadata={"source": "python.txt", "skills": ["code_assistant"], "tags": []},
        )
        await rag_store.ingest(
            text="General knowledge base article.",
            metadata={"source": "general.txt", "skills": [], "tags": []},
        )

        # Search with skill filter should match both
        results = await rag_store.search(
            query="programming knowledge",
            skills=["code_assistant"],
            top_k=5,
        )
        # Should get the skill-specific doc AND the all-skills doc
        assert len(results) == 2

    async def test_search_multiple_skills(self, rag_store):
        """Search can filter by multiple skills."""
        await rag_store.ingest(
            text="Python code examples.",
            metadata={"source": "python.txt", "skills": ["code_assistant"], "tags": []},
        )
        await rag_store.ingest(
            text="Meeting notes.",
            metadata={"source": "meeting.txt", "skills": ["meeting_assistant"], "tags": []},
        )
        await rag_store.ingest(
            text="General tips.",
            metadata={"source": "general.txt", "skills": [], "tags": []},
        )

        # Search with multiple skill filters
        results = await rag_store.search(
            query="text",
            skills=["code_assistant", "meeting_assistant"],
            top_k=10,
        )
        # Should match all three (two specific + one available to all)
        assert len(results) == 3

    async def test_search_skill_and_tag_combined(self, rag_store):
        """Search can filter by both skills and tags."""
        await rag_store.ingest(
            text="Python code for data processing.",
            metadata={"source": "python.txt", "skills": ["code_assistant"], "tags": ["data"]},
        )
        await rag_store.ingest(
            text="Python code for web development.",
            metadata={"source": "web.txt", "skills": ["code_assistant"], "tags": ["web"]},
        )
        await rag_store.ingest(
            text="Meeting about data strategy.",
            metadata={"source": "meeting.txt", "skills": ["meeting_assistant"], "tags": ["data"]},
        )

        # Filter by skill AND tag
        results = await rag_store.search(
            query="data",
            skills=["code_assistant"],
            tags=["data"],
            top_k=10,
        )
        # Should only match the code_assistant doc with "data" tag
        assert len(results) == 1
        assert "processing" in results[0]["text"]

    async def test_search_no_filters(self, rag_store):
        """Search without filters returns all matching documents."""
        await rag_store.ingest(
            text="Python code.",
            metadata={"source": "python.txt", "skills": ["code_assistant"], "tags": []},
        )
        await rag_store.ingest(
            text="Meeting notes.",
            metadata={"source": "meeting.txt", "skills": ["meeting_assistant"], "tags": []},
        )

        # No filters = all docs
        results = await rag_store.search(
            query="code notes",
            top_k=10,
        )
        assert len(results) == 2

    async def test_backward_compatibility_tags_only(self, rag_store):
        """Ensure backward compatibility with tag-only filtering."""
        await rag_store.ingest(
            text="Python tutorial.",
            metadata={"source": "tutorial.txt", "skills": [], "tags": ["tutorial", "python"]},
        )
        await rag_store.ingest(
            text="Python reference.",
            metadata={"source": "reference.txt", "skills": [], "tags": ["reference", "python"]},
        )

        # Filter by tags only (no skills filter)
        results = await rag_store.search(
            query="python",
            tags=["tutorial"],
            top_k=5,
        )
        assert len(results) == 1
        assert "tutorial" in results[0]["text"]
