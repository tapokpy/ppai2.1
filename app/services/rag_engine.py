import re
import uuid
from typing import Any

import chromadb
from chromadb import ClientAPI
from chromadb.api.types import EmbeddingFunction
from loguru import logger

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

# Sources indexed for cross-search (engineering_rag_ingest.py) rather than as
# genuine knowledge-base content — a CAD drawing's project_name or a video
# title is exactly the kind of short, name-like text the literal-match boost
# below was designed to reward, so without this exclusion a completely
# unrelated question that happens to share a 4+-letter word with a drawing's
# name (a project name, a GOST reference, a common noun) would get boosted
# to score>=0.9 and treated as grounding context. They can still surface via
# genuine embedding similarity — just not via the literal-keyword shortcut
# meant for proper-noun knowledge-base queries.
_NO_LITERAL_BOOST_SOURCES = {"engineering_doc", "showroom_media"}


class RAGEngine:
    def __init__(
        self,
        persist_dir: str,
        score_threshold: float,
        collection_name: str = "knowledge_base",
        embedding_function: EmbeddingFunction | None = None,
        client: ClientAPI | None = None,
        embedding_model_name: str = "",
        reranker: Any | None = None,
    ):
        self._threshold = score_threshold
        self._client = client or chromadb.PersistentClient(path=persist_dir)
        self._collection_name = collection_name
        self._embedding_model_name = embedding_model_name
        # Optional CrossEncoder (see app/services/embeddings.py::default_reranker)
        # — only reorders which chunks make the final top_k cut, never
        # touches found/max_score below (a cross-encoder's raw logit isn't
        # on the same 0..1 scale as RAG_SCORE_THRESHOLD, which is already
        # tuned against the embedding-based hybrid score).
        self._reranker = reranker

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
        try:
            results = self._collection.query(query_texts=[query_text], n_results=candidate_k)
        except Exception as exc:
            # chromadb's local HNSW index has occasionally thrown "Cannot
            # return the results in a contigious 2D array" for reasons not
            # fully understood (observed live, not reliably reproducible) —
            # letting that propagate crashes the ENTIRE cascade with no
            # reply to the user at all, instead of just degrading to "no
            # RAG context" and letting local/cloud still answer. A RAG miss
            # is an expected, handled outcome (found=False below); an
            # external index error should degrade the same way, not crash.
            logger.error(f"RAG query failed, degrading to no-context: {exc}")
            return {"found": False, "max_score": 0.0, "documents": [], "metadatas": [], "scores": []}

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
                max(score, 0.9)
                if (meta or {}).get("source") not in _NO_LITERAL_BOOST_SOURCES
                and any(w in doc.lower() for w in query_words)
                else score
                for score, doc, meta in zip(scores, documents, metadatas)
            ]

        # Re-rank by the boosted score (not the original embedding order) so
        # a literal-match chunk promoted from deep in the candidate pool
        # actually surfaces within the final top_k slice below. found/
        # max_score are always derived from THIS hybrid-boosted score, even
        # when a cross-encoder reranker (below) changes which chunks/order
        # actually get returned — a cross-encoder's raw logit isn't on the
        # same 0..1 scale as RAG_SCORE_THRESHOLD, which is already tuned
        # against this hybrid score specifically.
        hybrid_order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        max_score = max((scores[i] for i in hybrid_order), default=0.0)

        if self._reranker is not None and documents:
            # Reranks the same full candidate pool the hybrid boost saw
            # (not just its top_k) — a chunk that's genuinely the best
            # semantic match but scored just under the hybrid cutoff still
            # gets a fair chance here, same rationale as the wide candidate
            # pool above.
            pair_scores = self._reranker.predict([(query_text, doc) for doc in documents])
            final_order = sorted(range(len(documents)), key=lambda i: pair_scores[i], reverse=True)[:top_k]
        else:
            final_order = hybrid_order

        return {
            "found": max_score >= self._threshold,
            "max_score": max_score,
            "documents": [documents[i] for i in final_order],
            "metadatas": [metadatas[i] for i in final_order],
            "scores": [scores[i] for i in final_order],
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
