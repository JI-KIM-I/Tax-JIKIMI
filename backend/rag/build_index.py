"""세금지킴이 RAG - ChromaDB 벡터DB 구축 스크립트.

위치:
    backend/rag/build_index.py

실행:
    cd backend
    python rag/build_index.py

동작:
    1. rag/sources/*.txt 파일 로드
    2. 문단 단위 chunk 분리
    3. ChromaDB에 저장

환경변수:
    RAG_EMBEDDING_PROVIDER=local   # 기본값, API 키 없이 동작
    RAG_EMBEDDING_PROVIDER=openai  # OPENAI_API_KEY 필요
"""
from __future__ import annotations

from pathlib import Path
import sys

# backend/에서 실행하든 backend/rag에서 실행하든 import 되게 처리
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import chromadb

from rag.embedding import get_embedding_function
from rag.loader import load_documents

SOURCES_DIR = CURRENT_DIR / "sources"
DB_DIR = CURRENT_DIR / "chroma_db"
COLLECTION_NAME = "tax_knowledge"


def build_index() -> None:
    chunks = load_documents(SOURCES_DIR)
    if not chunks:
        raise RuntimeError("인덱싱할 문서 조각이 없습니다.")

    print(f"총 {len(chunks)}개 문서 조각을 ChromaDB에 저장합니다.")

    client = chromadb.PersistentClient(path=str(DB_DIR))

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        metadata={"description": "절세지킴이 세금 지식 베이스"},
    )

    collection.add(
        ids=[c.id for c in chunks],
        documents=[c.combined_text for c in chunks],
        metadatas=[c.metadata() for c in chunks],
    )

    print(f"완료: {collection.count()}개 chunk 저장")
    print(f"DB 위치: {DB_DIR}")
    print("서버 실행: uvicorn main:app --reload")


if __name__ == "__main__":
    build_index()
