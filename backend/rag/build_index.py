"""
세금지킴이 RAG - 벡터DB(ChromaDB) 구축 스크립트

sources/ 폴더 안의 .txt 문서들을 문단 단위로 쪼개서(chunking)
ChromaDB에 임베딩과 함께 저장합니다.

실행:
    python build_index.py

최초 실행 시 임베딩 모델(약 90MB)을 다운로드하므로 인터넷 연결이 필요합니다.
한 번 다운로드되면 이후에는 캐시된 모델을 사용합니다.
"""

from __future__ import annotations

import os
import re

import chromadb
from chromadb.utils import embedding_functions

SOURCES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources")
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
COLLECTION_NAME = "tax_knowledge"
EMBEDDING_MODEL = "text-embedding-3-small"


def _get_embedding_function():
    """OpenAI 임베딩을 사용합니다 (기본 제공 모델은 영어 위주라 한국어 검색 정확도가 낮습니다).

    /api/chat 답변 생성에도 어차피 OPENAI_API_KEY가 필요하므로, 검색(임베딩)에도
    같은 키로 OpenAI 임베딩을 써서 한국어 의미 검색 정확도를 높입니다.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
            "예: export OPENAI_API_KEY=\"sk-...\" 실행 후 다시 시도해주세요. "
            "(검색 품질을 위해 임베딩도 OpenAI를 사용합니다)"
        )
    return embedding_functions.OpenAIEmbeddingFunction(
        api_key=api_key, model_name=EMBEDDING_MODEL
    )


def chunk_text(text: str, source_name: str) -> list[dict]:
    """문서를 빈 줄(문단) 기준으로 쪼갭니다.

    너무 짧은 조각(예: 제목 한 줄)은 다음 조각과 합쳐서,
    검색했을 때 맥락 없는 파편이 나오지 않도록 합니다.
    """
    raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    buffer = ""
    for para in raw_paragraphs:
        if len(buffer) < 40:  # 너무 짧으면 다음 문단과 합침
            buffer = f"{buffer}\n\n{para}".strip()
        else:
            chunks.append(buffer)
            buffer = para
    if buffer:
        chunks.append(buffer)

    return [
        {"id": f"{source_name}::chunk{i}", "text": c, "source": source_name}
        for i, c in enumerate(chunks)
    ]


def build_index() -> None:
    if not os.path.isdir(SOURCES_DIR):
        raise FileNotFoundError(f"소스 폴더가 없습니다: {SOURCES_DIR}")

    txt_files = sorted(f for f in os.listdir(SOURCES_DIR) if f.endswith(".txt"))
    if not txt_files:
        raise FileNotFoundError(f"{SOURCES_DIR} 안에 .txt 파일이 없습니다.")

    all_chunks: list[dict] = []
    for filename in txt_files:
        path = os.path.join(SOURCES_DIR, filename)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        source_name = os.path.splitext(filename)[0]
        all_chunks.extend(chunk_text(text, source_name))

    print(f"총 {len(txt_files)}개 문서 -> {len(all_chunks)}개 조각(chunk)으로 분리")

    client = chromadb.PersistentClient(path=DB_DIR)

    # 기존 컬렉션이 있으면 지우고 새로 만듭니다 (재실행 시 중복 방지).
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        COLLECTION_NAME, embedding_function=_get_embedding_function()
    )

    collection.add(
        ids=[c["id"] for c in all_chunks],
        documents=[c["text"] for c in all_chunks],
        metadatas=[{"source": c["source"]} for c in all_chunks],
    )

    print(f"'{COLLECTION_NAME}' 컬렉션에 {collection.count()}개 조각 저장 완료")
    print(f"저장 위치: {DB_DIR}")


if __name__ == "__main__":
    build_index()
