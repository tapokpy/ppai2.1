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
    )


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
