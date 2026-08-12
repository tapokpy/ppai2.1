import re
import uuid
from typing import Any

import chromadb
from chromadb import ClientAPI
from chromadb.api.types import EmbeddingFunction

# Common short Russian/English question words excluded from the hybrid boost
# below — without this, a generic word like "такое" or "что" could spuriously
# boost unrelated chunks that happen to contain it.
_BOOST_STOPWORDS = {
    "что", "такое", "это", "как", "для", "про", "или", "если", "того",
    "этот", "эта", "эти", "него", "нему", "меня", "тебя", "нас",
    "when", "what", "this", "that", "with", "from", "about", "does",
}

# How many candidates to pull from chromadb before applying the literal-match
# boost and re-ranking, even when the caller asked for a smaller top_k.
_MIN_CANDIDATE_POOL = 20


class RAGEngine:
    def __init__(
        self,
        persist_dir: str,
        score_threshold: float,
        collection_name: str = "knowledge_base",
        embedding_function: EmbeddingFunction | None = None,
        client: ClientAPI | None = None,
        embedding_model_name: str = "",
    ):
        self._threshold = score_threshold
        self._client = client or chromadb.PersistentClient(path=persist_dir)
        self._collection_name = collection_name
        self._embedding_model_name = embedding_model_name

        kwargs: dict[str, Any] = {"metadata": {"hnsw:space": "cosine"}}
        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function

        self._collection = self._client.get_or_create_collection(name=collection_name, **kwargs)

    @property
    def collection_name(self) -> str:
        return self._collection_name

    @property
    def embedding_model_name(self) -> str:
        return self._embedding_model_name

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
        # Retrieve a wider candidate pool than what's ultimately returned.
        # Pure embedding similarity can bury a chunk that literally contains
        # the query term well outside a narrow top_k (observed live: the
        # correct chunk for a proper-noun query ranked 13th of 15 on
        # embedding score alone) — if we only ever asked chromadb for top_k,
        # the literal-match boost below would never even see that chunk to
        # promote it, since it wouldn't be in the candidate set at all.
        candidate_k = max(top_k, _MIN_CANDIDATE_POOL)
        results = self._collection.query(query_texts=[query_text], n_results=candidate_k)

        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []
        scores = [1 - d for d in distances]

        # Hybrid boost: pure embedding similarity ranks short, proper-noun
        # queries (company/product names) surprisingly poorly against long
        # chunks with this embedding model, even when the chunk contains the
        # term verbatim (observed live: the chunk titled with the project's
        # own name scored below chunks about unrelated setup instructions).
        # Matching on the *whole* query string only helps bare-term queries
        # ("ПридПром") — real questions are full sentences ("что такое
        # ПридПром") that never appear verbatim in a chunk, so this checks
        # individual significant words (skipping short/common ones) instead:
        # if any such word from the query appears literally in a retrieved
        # chunk, trust that over the embedding score.
        query_words = [
            w for w in re.findall(r"\w+", query_text.lower(), re.UNICODE)
            if len(w) >= 4 and w not in _BOOST_STOPWORDS
        ]
        if query_words:
            scores = [
                max(score, 0.9) if any(w in doc.lower() for w in query_words) else score
                for score, doc in zip(scores, documents)
            ]

        # Re-rank by the boosted score (not the original embedding order) so
        # a literal-match chunk promoted from deep in the candidate pool
        # actually surfaces within the final top_k slice below.
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        documents = [documents[i] for i in order]
        metadatas = [metadatas[i] for i in order]
        scores = [scores[i] for i in order]

        max_score = max(scores) if scores else 0.0

        return {
            "found": max_score >= self._threshold,
            "max_score": max_score,
            "documents": documents,
            "metadatas": metadatas,
            "scores": scores,
        }

    def get_document_chunks(self, source: str, filename: str | None) -> dict:
        """Live-fetch every chunk belonging to one ingested document, keyed
        by the same (source, filename) metadata written at ingestion time
        (project_docs_ingest.py / documents.py). Chunk text/embeddings are
        never duplicated into Postgres — this is the read path the admin
        "Document"/"Чанкинг"/"Эмбеддинг" screens use instead."""
        where: dict[str, Any] = {"source": source}
        if filename is not None:
            where = {"$and": [{"source": source}, {"filename": filename}]}

        results = self._collection.get(where=where, include=["documents", "metadatas"])

        return {
            "ids": results.get("ids", []),
            "documents": results.get("documents", []),
            "metadatas": results.get("metadatas", []),
        }
