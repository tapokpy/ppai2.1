from chromadb.utils import embedding_functions
from chromadb.api.types import EmbeddingFunction


def default_embedding_function(model_name: str) -> EmbeddingFunction:
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
