from __future__ import annotations

import sys
from pathlib import Path

import chromadb

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rag.embedding import get_embedding_function
from rag.loader import DocumentLoader

SOURCES_DIR = BASE_DIR / "sources"
DB_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "tax_knowledge"


def build_index() -> None:
    loader = DocumentLoader(SOURCES_DIR)
    documents = loader.load_documents()

    print(f"총 {len(documents)}개 문서 조각(chunk)으로 분리")

    client = chromadb.PersistentClient(path=str(DB_DIR))

    # 예전에는 chroma_db 폴더를 통째로 지우고 다시 만들었는데, OS/동기화 폴더에 따라
    # sqlite 파일 삭제 권한이 없어서 실패할 수 있었습니다. 폴더 대신 컬렉션만 지우고
    # 다시 만들면 같은 결과를 훨씬 안전하게 얻을 수 있습니다.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        COLLECTION_NAME,
        embedding_function=get_embedding_function(),
    )

    collection.add(
        ids=[doc.doc_id for doc in documents],
        documents=[doc.content for doc in documents],
        metadatas=[
            {
                "title": doc.title,
                "category": doc.category,
                "source": doc.source,
                "date": doc.date,
            }
            for doc in documents
        ],
    )

    print(f"'{COLLECTION_NAME}' 컬렉션에 {collection.count()}개 조각 저장 완료")
    print(f"저장 위치: {DB_DIR}")


if __name__ == "__main__":
    build_index()
