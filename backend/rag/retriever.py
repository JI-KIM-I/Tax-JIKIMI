"""RAG 검색기.

1순위: ChromaDB 벡터 검색
2순위: 벡터DB가 없거나 라이브러리/API 키 문제가 있으면 txt 직접 키워드 검색 fallback

이렇게 해두면 팀원 PC에서 아직 인덱스를 안 만들었거나 OPENAI_API_KEY가 없어도
/api/search, /api/chat이 완전히 죽지 않고 데모 가능한 답변을 반환합니다.
"""
from __future__ import annotations

import math
import os
import re
import time
from pathlib import Path

from .embedding import get_embedding_function
from .loader import DocumentChunk, load_documents

BASE_DIR = Path(__file__).resolve().parent
SOURCES_DIR = BASE_DIR / "sources"
DB_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "tax_knowledge"


def _tokens(text: str) -> list[str]:
    text = (text or "").lower()
    return re.findall(r"[가-힣]{2,}|[a-zA-Z0-9]{2,}", text)


def _keyword_score(query: str, text: str) -> float:
    q_tokens = _tokens(query)
    if not q_tokens:
        return 0.0
    text_l = (text or "").lower()
    score = 0.0
    for tok in q_tokens:
        count = text_l.count(tok)
        if count:
            score += 1.0 + math.log(count + 1)
    return score / len(q_tokens)


def fallback_keyword_search(query: str, top_k: int = 10) -> list[dict]:
    chunks = load_documents(SOURCES_DIR)
    scored: list[tuple[float, DocumentChunk]] = []
    for chunk in chunks:
        score = _keyword_score(query, chunk.combined_text)
        if score > 0:
            scored.append((score, chunk))

    # 질의 토큰이 하나도 안 걸릴 때는 앞 문서라도 보여줘서 챗봇이 근거를 갖게 합니다.
    if not scored:
        scored = [(0.0, c) for c in chunks[:top_k]]

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, chunk in scored[:top_k]:
        results.append(
            {
                "id": chunk.id,
                "title": chunk.title,
                "content": chunk.content,
                "text": chunk.content,
                "category": chunk.category,
                "source": chunk.source,
                "date": chunk.date,
                "score": round(float(score), 4),
                "distance": None,
                "retrieval_method": "keyword_fallback",
            }
        )
    return results


def chroma_search(query: str, top_k: int = 10) -> list[dict]:
    import chromadb

    client = chromadb.PersistentClient(path=str(DB_DIR))
    collection = client.get_collection(
        COLLECTION_NAME,
        embedding_function=get_embedding_function(),
    )

    result = collection.query(query_texts=[query], n_results=top_k)
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    ids = result.get("ids", [[]])[0]

    results = []
    for doc_id, doc, meta, dist in zip(ids, documents, metadatas, distances):
        # Chroma distance는 작을수록 유사합니다. UI용 score는 대략 높을수록 좋게 변환.
        score = 1 / (1 + float(dist)) if dist is not None else 0.0
        results.append(
            {
                "id": doc_id,
                "title": meta.get("title", ""),
                "content": doc,
                "text": doc,
                "category": meta.get("category", ""),
                "source": meta.get("source", ""),
                "date": meta.get("date", ""),
                "score": round(score, 4),
                "distance": dist,
                "retrieval_method": "chroma",
            }
        )
    return results


def search_documents(query: str, top_k: int = 10) -> tuple[list[dict], dict]:
    started = time.perf_counter()
    method = "chroma"
    try:
        if DB_DIR.exists():
            results = chroma_search(query, top_k=top_k)
        else:
            method = "keyword_fallback"
            results = fallback_keyword_search(query, top_k=top_k)
    except Exception as exc:
        method = "keyword_fallback"
        results = fallback_keyword_search(query, top_k=top_k)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return results, {
            "method": method,
            "latency_ms": elapsed_ms,
            "hit_count": len(results),
            "warning": f"Chroma 검색 실패로 fallback 검색을 사용했습니다: {exc}",
        }

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return results, {
        "method": method,
        "latency_ms": elapsed_ms,
        "hit_count": len(results),
        "warning": None,
    }
