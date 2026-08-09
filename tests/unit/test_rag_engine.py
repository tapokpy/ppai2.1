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


def test_query_empty_collection_returns_not_found(rag_engine):
    result = rag_engine.query("любой вопрос")

    assert result["found"] is False
    assert result["max_score"] == 0.0
    assert result["documents"] == []
