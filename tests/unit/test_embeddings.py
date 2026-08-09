from unittest.mock import patch

from app.services.embeddings import default_embedding_function


def test_default_embedding_function_builds_sentence_transformer_ef():
    with patch(
        "app.services.embeddings.embedding_functions.SentenceTransformerEmbeddingFunction"
    ) as ef_cls:
        default_embedding_function("all-MiniLM-L6-v2")

    ef_cls.assert_called_once_with(model_name="all-MiniLM-L6-v2")
