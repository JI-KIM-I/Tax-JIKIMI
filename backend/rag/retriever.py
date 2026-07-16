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

    def _fallback_search(self, query: str, top_k: int = 10, warning: str | None = None) -> dict[str, Any]:
        started = time.time()
        docs = self.loader.load_documents()
        query_text = str(query).lower()
        query_terms = set(query_text.split())
        bonus_keywords = ["연금", "분할", "일시금", "세율", "금융소득", "종합과세", "ISA", "IRP", "연금저축", "절세", "한도"]
        scored = []

        for doc in docs:
            text = f"{doc.title} {doc.category} {doc.content}".lower()
            score = sum(1 for term in query_terms if term and term in text)
            score += sum(2 for kw in bonus_keywords if kw in query_text and kw.lower() in text)
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = [
            {
                "id": doc.doc_id,
                "title": doc.title,
                "content": doc.content,
                "text": doc.text,
                "category": doc.category,
                "source": doc.source,
                "date": doc.date,
                "score": score,
                "distance": None,
                "retrieval_method": "keyword_fallback",
            }
            for score, doc in scored[:top_k]
        ]

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

    def search(self, query: str, top_k: int = 10) -> dict[str, Any]:
        started = time.time()

        try:
            client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
            collection = client.get_collection(COLLECTION_NAME, embedding_function=self.embedding_function)
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
            for doc_id, content, metadata, distance in zip(ids, documents, metadatas, distances):
                metadata = metadata or {}
                results.append(
                    {
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
                    }
                )

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
            return self._fallback_search(query, top_k, f"Chroma 검색 실패로 fallback 검색을 사용했습니다: {e}")


_retriever_instance = None


def get_retriever() -> RAGRetriever:
    global _retriever_instance

    if _retriever_instance is None:
        _retriever_instance = RAGRetriever()

    return _retriever_instance


def search_documents(query: str, top_k: int = 10):
    retriever = get_retriever()
    data = retriever.search(query=query, top_k=top_k)

    results = data.get("results", [])
    meta = data.get("meta", {})

    return results, meta