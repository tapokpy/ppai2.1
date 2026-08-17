import uuid
from unittest.mock import MagicMock

import chromadb
import pytest

from app.services.rag_engine import RAGEngine
from tests.fakes import FakeEmbeddingFunction


@pytest.fixture
def rag_engine():
    client = chromadb.EphemeralClient()
    return RAGEngine(
        persist_dir="unused",
        score_threshold=0.5,
        collection_name=f"test-{uuid.uuid4().hex}",
        embedding_function=FakeEmbeddingFunction(),
        client=client,
        embedding_model_name="fake-embedding-model",
    )


def _rag_engine_with_reranker(reranker):
    client = chromadb.EphemeralClient()
    return RAGEngine(
        persist_dir="unused",
        score_threshold=0.5,
        collection_name=f"test-{uuid.uuid4().hex}",
        embedding_function=FakeEmbeddingFunction(),
        client=client,
        embedding_model_name="fake-embedding-model",
        reranker=reranker,
    )


def test_collection_name_and_embedding_model_name_are_exposed(rag_engine):
    assert rag_engine.collection_name.startswith("test-")
    assert rag_engine.embedding_model_name == "fake-embedding-model"


def test_get_document_chunks_returns_only_matching_document(rag_engine):
    rag_engine.add_documents(
        texts=["Чанк 1 про модуль P2.5", "Чанк 2 про модуль P2.5"],
        metadatas=[
            {"source": "project_docs", "filename": "ARCHITECTURE.md", "chunk_index": 0},
            {"source": "project_docs", "filename": "ARCHITECTURE.md", "chunk_index": 1},
        ],
    )
    rag_engine.add_documents(
        texts=["Другой документ"],
        metadatas=[{"source": "project_docs", "filename": "README.md", "chunk_index": 0}],
    )

    result = rag_engine.get_document_chunks("project_docs", "ARCHITECTURE.md")

    assert len(result["documents"]) == 2
    assert all(m["filename"] == "ARCHITECTURE.md" for m in result["metadatas"])


def test_get_document_chunks_returns_empty_for_unknown_document(rag_engine):
    result = rag_engine.get_document_chunks("project_docs", "NOPE.md")

    assert result["documents"] == []
    assert result["ids"] == []


def test_query_finds_relevant_document(rag_engine):
    rag_engine.add_documents(
        texts=["Модуль P2.5 имеет шаг пикселя 2.5мм и яркость 1200 нит"],
        metadatas=[{"source": "catalog"}],
    )

    result = rag_engine.query("Какой шаг пикселя у модуля P2.5?")

    assert result["found"] is True
    assert result["max_score"] >= 0.5
    assert len(result["documents"]) == 1


def test_query_not_found_for_unrelated_text(rag_engine):
    rag_engine.add_documents(texts=["Рецепт борща с говядиной и капустой"])

    result = rag_engine.query("Настройка видеоконтроллера NovaStar TB50")

    assert result["found"] is False


def test_query_boosts_score_when_query_appears_literally_in_chunk(rag_engine):
    # Lots of unrelated filler dilutes the embedding similarity for a short
    # proper-noun query far below the chunk's literal-match relevance —
    # mirrors the real failure observed live (a chunk titled with the
    # project's own name scored 0.31, well below threshold, purely on
    # embedding similarity even though the term was right there in the text).
    noise = "слово " * 200
    rag_engine.add_documents(texts=[f"{noise}ПридПром{noise}"])

    result = rag_engine.query("ПридПром")

    assert result["found"] is True
    assert result["max_score"] >= 0.9


def test_query_does_not_boost_engineering_doc_or_showroom_media_sources(rag_engine):
    # These sources are indexed for cross-search (engineering_rag_ingest.py),
    # not as knowledge-base content — a drawing/video name is exactly the
    # kind of short proper-noun text the boost was built to reward, so
    # without this exclusion an unrelated question sharing a word with a
    # drawing's project_name would get spuriously boosted to score>=0.9 and
    # fed to the LLM as grounding context.
    noise = "слово " * 200
    rag_engine.add_documents(
        texts=[f"{noise}ПридПром{noise}"],
        metadatas=[{"source": "engineering_doc", "doc_id": 1}],
    )

    result = rag_engine.query("ПридПром")

    assert result["max_score"] < 0.9


def test_query_boost_is_case_insensitive(rag_engine):
    noise = "слово " * 200
    rag_engine.add_documents(texts=[f"{noise}ПридПром{noise}"])

    result = rag_engine.query("придпром")

    assert result["found"] is True
    assert result["max_score"] >= 0.9


def test_query_boost_matches_significant_word_in_full_sentence(rag_engine):
    # Real user questions are full sentences ("что такое ПридПром"), not a
    # bare term — the whole sentence never appears verbatim in a chunk, so
    # the boost must match on individual significant words, not the full
    # query string.
    noise = "слово " * 200
    rag_engine.add_documents(texts=[f"{noise}ПридПром{noise}"])

    result = rag_engine.query("что такое ПридПром")

    assert result["found"] is True
    assert result["max_score"] >= 0.9


def test_query_boost_ignores_common_short_words(rag_engine):
    # A generic stopword like "такое" shouldn't spuriously boost an
    # unrelated chunk just because it happens to contain that word.
    noise = "слово " * 200
    rag_engine.add_documents(texts=[f"{noise}такое{noise}"])

    result = rag_engine.query("что такое ПридПром")

    assert result["max_score"] < 0.9


def test_query_widens_candidate_pool_so_buried_literal_match_still_surfaces(rag_engine):
    # Mirrors the real failure this was built to fix: the chunk containing
    # the exact query term ranked 13th of 15 on raw embedding similarity
    # alone (buried under noise), so a naive top_k=5 fetch from chromadb
    # would never even see it for the literal-match boost to act on. The
    # fix must ask chromadb for a wider candidate pool before boosting.
    captured_n_results = {}

    class FakeCollection:
        def query(self, query_texts, n_results):
            captured_n_results["value"] = n_results
            documents = [f"decoy {i} — не содержит нужный термин" for i in range(24)]
            documents.append("шум " * 50 + "ПридПром" + " шум " * 50)
            distances = [0.6 + i * 0.01 for i in range(24)] + [0.99]
            metadatas = [{} for _ in documents]
            return {"documents": [documents], "metadatas": [metadatas], "distances": [distances]}

    rag_engine._collection = FakeCollection()

    result = rag_engine.query("ПридПром", top_k=5)

    assert captured_n_results["value"] >= 20
    assert result["found"] is True
    assert any("ПридПром" in doc for doc in result["documents"])
    assert len(result["documents"]) == 5


def test_query_empty_collection_returns_not_found(rag_engine):
    result = rag_engine.query("любой вопрос")

    assert result["found"] is False
    assert result["max_score"] == 0.0
    assert result["documents"] == []


def test_query_degrades_to_not_found_when_chromadb_raises(rag_engine, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("Cannot return the results in a contigious 2D array. Probably ef or M is too small")

    monkeypatch.setattr(rag_engine._collection, "query", _boom)

    result = rag_engine.query("любой вопрос")

    assert result == {"found": False, "max_score": 0.0, "documents": [], "metadatas": [], "scores": []}


def test_upsert_documents_overwrites_existing_id(rag_engine):
    rag_engine.upsert_documents(
        texts=["Первая версия документа"], metadatas=[{"v": 1}], ids=["doc:1"]
    )
    rag_engine.upsert_documents(
        texts=["Модуль P2.5 имеет шаг пикселя 2.5мм"], metadatas=[{"v": 2}], ids=["doc:1"]
    )

    result = rag_engine.query("Какой шаг пикселя у модуля P2.5?")

    assert result["found"] is True
    assert len(result["documents"]) == 1
    assert result["metadatas"][0]["v"] == 2


def test_upsert_documents_generates_ids_when_not_given(rag_engine):
    rag_engine.upsert_documents(texts=["Документ без явного id"])

    result = rag_engine.query("Документ без явного id")

    assert result["found"] is True


def test_query_reranks_documents_using_cross_encoder_scores():
    # Reranker scores purely by document content (a marker string), so this
    # is robust regardless of what order chromadb's own embedding-similarity
    # ranking happens to return the two documents in.
    def fake_predict(pairs):
        return [1.0 if "ВАЖНО" in doc else 0.0 for _query, doc in pairs]

    reranker = MagicMock()
    reranker.predict.side_effect = fake_predict
    engine = _rag_engine_with_reranker(reranker)
    engine.add_documents(
        texts=[
            "Модуль P2.5 шаг пикселя 2.5мм яркость 1200 нит",
            "ВАЖНО: другой релевантный факт про модуль P2.5",
        ],
    )

    result = engine.query("Какой шаг пикселя у модуля P2.5?")

    assert "ВАЖНО" in result["documents"][0]


def test_query_found_and_max_score_unaffected_by_reranker_scores():
    # The reranker scores everything as irrelevant (0.0) — found/max_score
    # must still come from the hybrid embedding score, not the reranker,
    # since RAG_SCORE_THRESHOLD is tuned against that scale, not a
    # cross-encoder's raw logit.
    reranker = MagicMock()
    reranker.predict.return_value = [0.0]
    engine = _rag_engine_with_reranker(reranker)
    engine.add_documents(texts=["Модуль P2.5 имеет шаг пикселя 2.5мм и яркость 1200 нит"])

    result = engine.query("Какой шаг пикселя у модуля P2.5?")

    assert result["found"] is True
    assert result["max_score"] >= 0.5


def test_query_skips_reranking_when_no_documents_found():
    reranker = MagicMock()
    engine = _rag_engine_with_reranker(reranker)

    result = engine.query("любой вопрос")

    reranker.predict.assert_not_called()
    assert result["found"] is False
