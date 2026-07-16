from __future__ import annotations

import os
import time
from typing import Any

import chromadb

from rag.embedding import get_embedding_function
from rag.loader import DocumentLoader


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_DIR = os.path.join(BASE_DIR, "sources")
CHROMA_DB_DIR = os.path.join(BASE_DIR, "chroma_db")
COLLECTION_NAME = "tax_knowledge"


class RAGRetriever:
    def __init__(self):
        self.embedding_function = get_embedding_function()
        self.loader = DocumentLoader(SOURCES_DIR)

    def _fallback_search(self, query: str, top_k: int = 10, warning: str | None = None) -> dict:
        started = time.time()
        docs = self.loader.load_documents()

        query_terms = set(str(query).lower().split())
        scored = []

        for doc in docs:
            text = f"{doc.title} {doc.category} {doc.content}".lower()
            score = 0
            for term in query_terms:
                if term and term in text:
                    score += 1

            # 한국어 문장이 공백 기준으로 잘 안 잘릴 수 있어서 핵심 키워드 보정
            bonus_keywords = [
                "연금", "분할", "일시금", "세율", "금융소득",
                "종합과세", "ISA", "IRP", "연금저축"
            ]
            for kw in bonus_keywords:
                if kw in query and kw in text:
                    score += 2

            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []

        for score, doc in scored[:top_k]:
            results.append({
                "id": doc.doc_id,
                "title": doc.title,
                "content": doc.content,
                "text": doc.content,
                "category": doc.category,
                "source": doc.source,
                "date": doc.date,
                "score": score,
                "distance": None,
                "retrieval_method": "keyword_fallback",
            })

        return {
            "query": query,
            "top_k": top_k,
            "results": results,
            "meta": {
                "method": "keyword_fallback",
                "latency_ms": round((time.time() - started) * 1000, 2),
                "hit_count": len(results),
                "warning": warning,
            },
        }

    def search(self, query: str, top_k: int = 10) -> dict:
        started = time.time()

        try:
            client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
            collection = client.get_collection(
                COLLECTION_NAME,
                embedding_function=self.embedding_function,
            )

            # 핵심 수정:
            # Chroma query_texts가 embedding function 버전에 따라 깨질 수 있어서,
            # 우리가 직접 query embedding을 만든 뒤 query_embeddings로 검색한다.
            query_embedding = self.embedding_function.embed_query(query)

            raw = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

            ids = raw.get("ids", [[]])[0]
            documents = raw.get("documents", [[]])[0]
            metadatas = raw.get("metadatas", [[]])[0]
            distances = raw.get("distances", [[]])[0]

            results = []
            for doc_id, content, metadata, distance in zip(
                ids, documents, metadatas, distances
            ):
                metadata = metadata or {}
                results.append({
                    "id": doc_id,
                    "title": metadata.get("title", ""),
                    "content": content,
                    "text": content,
                    "category": metadata.get("category", ""),
                    "source": metadata.get("source", ""),
                    "date": metadata.get("date", ""),
                    "score": None,
                    "distance": distance,
                    "retrieval_method": "chroma",
                })

            return {
                "query": query,
                "top_k": top_k,
                "results": results,
                "meta": {
                    "method": "chroma",
                    "latency_ms": round((time.time() - started) * 1000, 2),
                    "hit_count": len(results),
                    "warning": None,
                },
            }

        except Exception as e:
            return self._fallback_search(
                query=query,
                top_k=top_k,
                warning=f"Chroma 검색 실패로 fallback 검색을 사용했습니다: {e}",
            )