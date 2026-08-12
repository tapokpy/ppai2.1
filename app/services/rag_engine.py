import uuid
from typing import Any

import chromadb
from chromadb import ClientAPI
from chromadb.api.types import EmbeddingFunction


class RAGEngine:
    def __init__(
        self,
        persist_dir: str,
        score_threshold: float,
        collection_name: str = "knowledge_base",
        embedding_function: EmbeddingFunction | None = None,
        client: ClientAPI | None = None,
    ):
        self._threshold = score_threshold
        self._client = client or chromadb.PersistentClient(path=persist_dir)

        kwargs: dict[str, Any] = {"metadata": {"hnsw:space": "cosine"}}
        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function

        self._collection = self._client.get_or_create_collection(name=collection_name, **kwargs)

    def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        ids = ids or [str(uuid.uuid4()) for _ in texts]
        self._collection.add(documents=texts, metadatas=metadatas, ids=ids)

    def upsert_documents(
        self,
        texts: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Like add_documents, but overwrites existing entries with matching
        ids instead of erroring. Used for idempotent re-ingestion (e.g. the
        project's own docs on every bot startup) where callers pass stable,
        deterministic ids rather than random ones."""
        ids = ids or [str(uuid.uuid4()) for _ in texts]
        self._collection.upsert(documents=texts, metadatas=metadatas, ids=ids)

    def query(self, query_text: str, top_k: int = 5) -> dict:
        results = self._collection.query(query_texts=[query_text], n_results=top_k)

        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []
        scores = [1 - d for d in distances]

        # Hybrid boost: pure embedding similarity ranks short, proper-noun
        # queries (company/product names) surprisingly poorly against long
        # chunks with this embedding model, even when the chunk contains the
        # term verbatim (observed live: the chunk titled with the project's
        # own name scored below chunks about unrelated setup instructions).
        # If the query appears literally in a retrieved chunk, trust that
        # over the embedding score.
        query_lower = query_text.strip().lower()
        if query_lower:
            scores = [
                max(score, 0.9) if query_lower in doc.lower() else score
                for score, doc in zip(scores, documents)
            ]

        max_score = max(scores) if scores else 0.0

        return {
            "found": max_score >= self._threshold,
            "max_score": max_score,
            "documents": documents,
            "metadatas": metadatas,
            "scores": scores,
        }
