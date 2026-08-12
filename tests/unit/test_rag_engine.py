import uuid

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
