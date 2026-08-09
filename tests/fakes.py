import hashlib


class FakeEmbeddingFunction:
    """Deterministic character-trigram hashing embedding.

    Avoids downloading real models in tests while still giving morphologically
    related Russian words (e.g. "модуль"/"модуля") meaningful cosine overlap.
    """

    def __init__(self, dim: int = 128, ngram: int = 3):
        self._dim = dim
        self._ngram = ngram

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        normalized = text.lower()
        grams = [
            normalized[i : i + self._ngram]
            for i in range(max(len(normalized) - self._ngram + 1, 1))
        ]
        for gram in grams:
            idx = int(hashlib.sha256(gram.encode()).hexdigest(), 16) % self._dim
            vector[idx] += 1.0

        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0:
            return vector
        return [v / norm for v in vector]
