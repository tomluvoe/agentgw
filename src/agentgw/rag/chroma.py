"""ChromaDB wrapper for RAG storage and retrieval."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import chromadb

from agentgw.rag.ingestion import chunk_text

logger = logging.getLogger(__name__)


@dataclass
class RAGResult:
    """A single RAG search result."""

    text: str
    metadata: dict
    distance: float
    id: str


class RAGStore:
    """ChromaDB-backed RAG storage with tag-based filtering."""

    def __init__(self, persist_dir: Path):
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        logger.info("ChromaDB initialized at %s", persist_dir)

    def _get_collection(self, name: str = "default"):
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    async def ingest(
        self,
        text: str,
        metadata: dict | None = None,
        collection: str = "default",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ) -> list[str]:
        """Ingest text into the store, chunking it first.

        Args:
            text: The text to ingest.
            metadata: Metadata to attach (source, tags, etc.).
            collection: Collection name.
            chunk_size: Characters per chunk.
            chunk_overlap: Overlap between chunks.

        Returns:
            List of chunk IDs created.
        """
        chunks = chunk_text(text, chunk_size, chunk_overlap)
        if not chunks:
            return []

        col = self._get_collection(collection)
        ids = [str(uuid.uuid4()) for _ in chunks]
        meta = metadata or {}

        # ChromaDB metadata values must be str, int, float, or bool.
        # Convert tags list to a comma-separated string.
        doc_metadatas = []
        for i, _chunk in enumerate(chunks):
            m = {
                "source": str(meta.get("source", "unknown")),
                "tags": ",".join(meta.get("tags", [])),
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            doc_metadatas.append(m)

        col.add(documents=chunks, metadatas=doc_metadatas, ids=ids)
        logger.info("Ingested %d chunks into collection '%s'", len(chunks), collection)
        return ids

    async def search(
        self,
        query: str,
        collection: str = "default",
        top_k: int = 5,
        tags: list[str] | None = None,
    ) -> list[dict]:
        """Search for relevant documents.

        Args:
            query: Natural language search query.
            collection: Collection to search.
            top_k: Number of results.
            tags: Filter by tags (any match).

        Returns:
            List of result dicts with text, metadata, distance.
        """
        col = self._get_collection(collection)

        where = None
        if tags:
            # Match documents that contain any of the specified tags
            if len(tags) == 1:
                where = {"tags": {"$contains": tags[0]}}
            else:
                where = {"$or": [{"tags": {"$contains": t}} for t in tags]}

        try:
            results = col.query(
                query_texts=[query],
                n_results=min(top_k, col.count() or top_k),
                where=where,
            )
        except Exception as e:
            logger.warning("RAG search failed: %s", e)
            return []

        if not results or not results["documents"] or not results["documents"][0]:
            return []

        output = []
        for i, doc in enumerate(results["documents"][0]):
            output.append({
                "text": doc,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0.0,
                "id": results["ids"][0][i] if results["ids"] else "",
            })
        return output

    async def delete(self, ids: list[str], collection: str = "default") -> None:
        """Delete documents by ID."""
        col = self._get_collection(collection)
        col.delete(ids=ids)
