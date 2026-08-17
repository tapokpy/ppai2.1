from chromadb.utils import embedding_functions
from chromadb.api.types import EmbeddingFunction
from sentence_transformers import CrossEncoder

# Small (~80MB), CPU-friendly cross-encoder trained on MS MARCO passage
# ranking — same "small local model" tradeoff already made for the
# all-MiniLM-L6-v2 embedding model, just for the rerank step instead of the
# initial retrieval. Loaded once at startup (app/core/dependencies.py), not
# per-query — the model itself is the expensive part, not a single predict()
# call.
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def default_embedding_function(model_name: str) -> EmbeddingFunction:
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)


def default_reranker(model_name: str = DEFAULT_RERANKER_MODEL) -> CrossEncoder:
    return CrossEncoder(model_name)
