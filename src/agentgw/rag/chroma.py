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
            metadata: Metadata to attach (source, skills, tags, etc.).
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
        # Convert skills list to a comma-separated string.
        # Empty skills list = available to all agents.
        doc_metadatas = []
        for i, _chunk in enumerate(chunks):
            m = {
                "source": str(meta.get("source", "unknown")),
                "skills": ",".join(meta.get("skills", [])),
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
        skills: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[dict]:
        """Search for relevant documents.

        Args:
            query: Natural language search query.
            collection: Collection to search.
            top_k: Number of results.
            skills: Filter by skill names. Documents with empty skills field match all.
            tags: Filter by tags (backward compatibility, any match).

        Returns:
            List of result dicts with text, metadata, distance.
        """
        col = self._get_collection(collection)

        # Get more results than requested to account for post-filtering
        # If filtering is active, fetch 3x to ensure we have enough after filtering
        fetch_count = top_k * 3 if (skills or tags) else top_k

        try:
            results = col.query(
                query_texts=[query],
                n_results=min(fetch_count, col.count() or fetch_count),
            )
        except Exception as e:
            logger.warning("RAG search failed: %s", e)
            return []

        if not results or not results["documents"] or not results["documents"][0]:
            return []

        # Post-filter results in Python for better control
        output = []
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}

            # Skill-based filtering
            if skills:
                doc_skills = metadata.get("skills", "")
                # Empty skills = available to all
                if doc_skills:
                    doc_skill_list = [s.strip() for s in doc_skills.split(",") if s.strip()]
                    # Check if any requested skill is in the document's skill list
                    if not any(skill in doc_skill_list for skill in skills):
                        continue  # Skip this document
                # If doc_skills is empty, it matches all skills (don't skip)

            # Tag-based filtering
            if tags:
                doc_tags = metadata.get("tags", "")
                if doc_tags:
                    doc_tag_list = [t.strip() for t in doc_tags.split(",") if t.strip()]
                    # Check if any requested tag is in the document's tag list
                    if not any(tag in doc_tag_list for tag in tags):
                        continue  # Skip this document
                else:
                    # Document has no tags, doesn't match tag filter
                    continue

            output.append({
                "text": doc,
                "metadata": metadata,
                "distance": results["distances"][0][i] if results["distances"] else 0.0,
                "id": results["ids"][0][i] if results["ids"] else "",
            })

            # Stop when we have enough results
            if len(output) >= top_k:
                break

        return output[:top_k]

    async def list_documents(
        self,
        collection: str = "default",
        skills: list[str] | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """List ingested documents with metadata.

        Args:
            collection: Collection to list from.
            skills: Filter by skill names.
            source: Filter by source name (substring match).
            limit: Maximum number of documents to return.

        Returns:
            List of document dicts with id, text, metadata.
        """
        col = self._get_collection(collection)

        try:
            # Get all documents (or up to limit)
            results = col.get(limit=limit, include=["documents", "metadatas"])
        except Exception as e:
            logger.warning("Failed to list documents: %s", e)
            return []

        if not results or not results.get("ids"):
            return []

        # Build output with filtering
        output = []
        for i, doc_id in enumerate(results["ids"]):
            metadata = results["metadatas"][i] if results.get("metadatas") else {}
            text = results["documents"][i] if results.get("documents") else ""

            # Filter by skills
            if skills:
                doc_skills = metadata.get("skills", "")
                if doc_skills:
                    doc_skill_list = [s.strip() for s in doc_skills.split(",") if s.strip()]
                    if not any(skill in doc_skill_list for skill in skills):
                        continue

            # Filter by source
            if source:
                doc_source = metadata.get("source", "")
                if source.lower() not in doc_source.lower():
                    continue

            output.append({
                "id": doc_id,
                "text": text[:200] + "..." if len(text) > 200 else text,
                "full_text": text,
                "metadata": metadata,
            })

        return output

    async def delete(self, ids: list[str], collection: str = "default") -> None:
        """Delete documents by ID."""
        col = self._get_collection(collection)
        col.delete(ids=ids)
        logger.info("Deleted %d documents from collection '%s'", len(ids), collection)

    async def delete_by_source(self, source: str, collection: str = "default") -> int:
        """Delete all documents from a specific source.

        Args:
            source: Source identifier to delete.
            collection: Collection to delete from.

        Returns:
            Number of documents deleted.
        """
        col = self._get_collection(collection)

        try:
            # Find all docs with this source
            results = col.get(where={"source": source}, include=["metadatas"])
            if not results or not results.get("ids"):
                return 0

            doc_ids = results["ids"]
            col.delete(ids=doc_ids)
            logger.info("Deleted %d documents with source '%s'", len(doc_ids), source)
            return len(doc_ids)
        except Exception as e:
            logger.warning("Failed to delete by source: %s", e)
            return 0
