"""RAG 임베딩 함수.

기본값은 외부 API 없이 동작하는 local 해시 임베딩입니다.
OPENAI_API_KEY가 있고 RAG_EMBEDDING_PROVIDER=openai로 설정하면 OpenAI 임베딩을 사용합니다.

중요:
- build_index.py에서 사용한 provider와 main.py 검색 시 provider가 같아야 합니다.
- 팀 프로젝트 데모 안정성을 위해 기본값은 local입니다.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Iterable, List

EMBEDDING_PROVIDER = os.getenv("RAG_EMBEDDING_PROVIDER", "local").lower().strip()
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def _tokenize_ko_en(text: str) -> list[str]:
    """한국어/영어/숫자 텍스트를 간단히 토큰화합니다.

    전문 형태소 분석기 없이도 동작하게 만든 경량 전처리입니다.
    """
    text = (text or "").lower()
    words = re.findall(r"[가-힣]{2,}|[a-zA-Z0-9]{2,}", text)
    # 한국어는 조사 때문에 문장 전체 매칭이 약해질 수 있어 문자 2-gram도 추가합니다.
    hangul = "".join(re.findall(r"[가-힣]", text))
    bigrams = [hangul[i : i + 2] for i in range(max(0, len(hangul) - 1))]
    return words + bigrams


class LocalHashEmbeddingFunction:
    """ChromaDB에서 사용할 수 있는 deterministic embedding function.

    외부 모델 다운로드나 API 키 없이 문서를 숫자 벡터로 바꿉니다.
    의미 임베딩보다는 약하지만, 한국어 키워드 기반 유사도 검색은 안정적으로 됩니다.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    def name(self) -> str:
        return f"taxjikimi-local-hash-{self.dim}"

    def __call__(self, input: Iterable[str]) -> List[List[float]]:  # Chroma expects "input"
        return [self._embed_one(text) for text in input]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize_ko_en(text):
            digest = hashlib.md5(tok.encode("utf-8")).hexdigest()
            idx = int(digest[:8], 16) % self.dim
            sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


def get_embedding_function():
    """환경변수에 맞는 ChromaDB embedding_function을 반환합니다."""
    provider = os.getenv("RAG_EMBEDDING_PROVIDER", EMBEDDING_PROVIDER).lower().strip()

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "RAG_EMBEDDING_PROVIDER=openai 이지만 OPENAI_API_KEY가 없습니다. "
                "키를 설정하거나 RAG_EMBEDDING_PROVIDER=local로 바꾸세요."
            )
        from chromadb.utils import embedding_functions

        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name=OPENAI_EMBEDDING_MODEL,
        )

    return LocalHashEmbeddingFunction()
