from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Iterable, List


DEFAULT_EMBEDDING_PROVIDER = os.getenv("RAG_EMBEDDING_PROVIDER", "local")
DEFAULT_OPENAI_EMBEDDING_MODEL = os.getenv(
    "RAG_OPENAI_EMBEDDING_MODEL",
    "text-embedding-3-small",
)


class LocalHashEmbeddingFunction:
    """
    API 키 없이도 동작하는 로컬 해시 기반 임베딩 함수.

    ChromaDB 버전과 우리 retriever 코드 양쪽에서 모두 쓸 수 있도록
    __call__, embed_documents, embed_query를 전부 제공한다.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    def name(self) -> str:
        return f"local-hash-embedding-{self.dim}"

    def _tokenize(self, text: str) -> list[str]:
        text = str(text).lower()
        return re.findall(r"[가-힣a-zA-Z0-9]+", text)

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = self._tokenize(text)

        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % self.dim
            sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector

        return [v / norm for v in vector]

    def __call__(self, input: Iterable[str]) -> List[List[float]]:
        return [self._embed_one(text) for text in input]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


def get_embedding_function():
    """
    ChromaDB에 전달할 embedding function 반환.

    기본값은 local이라 OpenAI API 키 없이도 실행된다.
    OpenAI 임베딩을 쓰려면:
      RAG_EMBEDDING_PROVIDER=openai
      OPENAI_API_KEY=...
    """
    provider = DEFAULT_EMBEDDING_PROVIDER.lower()

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "RAG_EMBEDDING_PROVIDER=openai 이지만 OPENAI_API_KEY가 없습니다."
            )

        from chromadb.utils import embedding_functions

        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name=DEFAULT_OPENAI_EMBEDDING_MODEL,
        )

    return LocalHashEmbeddingFunction()