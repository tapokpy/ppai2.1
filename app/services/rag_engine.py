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

    def query(self, query_text: str, top_k: int = 5) -> dict:
        results = self._collection.query(query_texts=[query_text], n_results=top_k)

        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []
        scores = [1 - d for d in distances]

        max_score = max(scores) if scores else 0.0

        return {
            "found": max_score >= self._threshold,
            "max_score": max_score,
            "documents": documents,
            "metadatas": metadatas,
            "scores": scores,
        }
