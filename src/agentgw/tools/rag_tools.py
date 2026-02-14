"""RAG tools for searching and ingesting documents."""

from __future__ import annotations

from agentgw.tools.decorator import tool

# These tools delegate to the RAG store, which is injected at runtime
# via the tool context. For now, they use a module-level reference
# that gets set during app initialization.

_rag_store = None


def set_rag_store(store) -> None:
    """Set the RAG store instance for tool use."""
    global _rag_store
    _rag_store = store


@tool()
async def search_documents(
    query: str,
    top_k: int = 5,
    tags: list[str] | None = None,
) -> list[dict]:
    """Search the knowledge base for relevant documents.

    Args:
        query: Natural language search query.
        top_k: Number of results to return.
        tags: Optional tag filters to narrow search scope.
    """
    if _rag_store is None:
        return [{"error": "RAG store not initialized"}]
    return await _rag_store.search(query=query, top_k=top_k, tags=tags)


@tool()
async def ingest_document(
    text: str,
    source: str = "manual",
    tags: list[str] | None = None,
) -> dict:
    """Ingest text into the knowledge base for future retrieval.

    Args:
        text: The text content to ingest.
        source: Source identifier (e.g. filename, URL).
        tags: Tags for categorizing and filtering the document.
    """
    if _rag_store is None:
        return {"error": "RAG store not initialized"}
    chunk_ids = await _rag_store.ingest(
        text=text,
        metadata={"source": source, "tags": tags or []},
    )
    return {"status": "ok", "chunks_created": len(chunk_ids), "ids": chunk_ids}
