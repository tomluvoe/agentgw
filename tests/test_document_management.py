"""Tests for document management (list, delete)."""

from __future__ import annotations

import pytest

from agentgw.rag.chroma import RAGStore


@pytest.fixture
async def rag_store(tmp_path):
    """Create a temporary RAG store with some documents."""
    store = RAGStore(tmp_path / "chroma")

    # Ingest test documents
    await store.ingest(
        text="Python programming guide for beginners.",
        metadata={"source": "python-guide.md", "skills": ["code_assistant"], "tags": ["python"]},
    )
    await store.ingest(
        text="Company HR policies and procedures.",
        metadata={"source": "hr-policies.pdf", "skills": ["hr_assistant"], "tags": ["hr"]},
    )
    await store.ingest(
        text="General company overview and history.",
        metadata={"source": "company-overview.md", "skills": [], "tags": ["general"]},
    )

    yield store


class TestDocumentManagement:
    """Test document listing and deletion."""

    async def test_list_all_documents(self, rag_store):
        """List all documents without filters."""
        docs = await rag_store.list_documents()
        assert len(docs) == 3
        assert all("id" in doc for doc in docs)
        assert all("metadata" in doc for doc in docs)
        assert all("text" in doc for doc in docs)

    async def test_list_by_skill(self, rag_store):
        """Filter documents by skill (includes docs available to all)."""
        docs = await rag_store.list_documents(skills=["code_assistant"])
        # Should include code_assistant doc + docs available to all
        assert len(docs) == 2
        sources = [d["metadata"]["source"] for d in docs]
        assert "python-guide.md" in sources
        assert "company-overview.md" in sources  # Available to all

    async def test_list_by_source(self, rag_store):
        """Filter documents by source substring."""
        docs = await rag_store.list_documents(source="hr-policies")
        assert len(docs) == 1
        assert docs[0]["metadata"]["source"] == "hr-policies.pdf"

    async def test_list_with_limit(self, rag_store):
        """Limit number of results."""
        docs = await rag_store.list_documents(limit=2)
        assert len(docs) == 2

    async def test_list_empty_skills_included(self, rag_store):
        """Documents with empty skills should show up when no filter."""
        docs = await rag_store.list_documents()
        empty_skill_docs = [d for d in docs if d["metadata"]["skills"] == ""]
        assert len(empty_skill_docs) == 1
        assert "company-overview" in empty_skill_docs[0]["metadata"]["source"]

    async def test_delete_by_ids(self, rag_store):
        """Delete specific documents by ID."""
        # Get all docs
        docs = await rag_store.list_documents()
        initial_count = len(docs)
        assert initial_count == 3

        # Delete one
        doc_id = docs[0]["id"]
        await rag_store.delete([doc_id])

        # Verify deletion
        remaining = await rag_store.list_documents()
        assert len(remaining) == initial_count - 1
        assert not any(d["id"] == doc_id for d in remaining)

    async def test_delete_by_source(self, rag_store):
        """Delete all chunks from a source."""
        # Delete by source
        deleted_count = await rag_store.delete_by_source("python-guide.md")
        assert deleted_count == 1

        # Verify deletion
        docs = await rag_store.list_documents()
        assert len(docs) == 2
        assert not any("python-guide" in d["metadata"]["source"] for d in docs)

    async def test_delete_nonexistent_source(self, rag_store):
        """Deleting non-existent source returns 0."""
        deleted_count = await rag_store.delete_by_source("nonexistent.txt")
        assert deleted_count == 0

    async def test_delete_multiple_ids(self, rag_store):
        """Delete multiple documents at once."""
        docs = await rag_store.list_documents()
        ids_to_delete = [docs[0]["id"], docs[1]["id"]]

        await rag_store.delete(ids_to_delete)

        remaining = await rag_store.list_documents()
        assert len(remaining) == 1

    async def test_list_shows_preview_text(self, rag_store):
        """Listed documents include preview text."""
        docs = await rag_store.list_documents()
        for doc in docs:
            assert "text" in doc
            # Preview is truncated
            if len(doc["full_text"]) > 200:
                assert doc["text"].endswith("...")
            # Full text is available
            assert "full_text" in doc
            assert len(doc["full_text"]) > 0

    async def test_list_includes_chunk_metadata(self, rag_store):
        """Documents include chunk index and total chunks."""
        # Ingest a multi-chunk document
        await rag_store.ingest(
            text="A" * 1000,  # Long text that will be chunked
            metadata={"source": "long-doc.txt", "skills": [], "tags": []},
            chunk_size=200,
        )

        docs = await rag_store.list_documents(source="long-doc")
        assert len(docs) > 1  # Multiple chunks

        # Check metadata
        for doc in docs:
            assert "chunk_index" in doc["metadata"]
            assert "total_chunks" in doc["metadata"]
