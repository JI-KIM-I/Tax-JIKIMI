"""RAG 문서 로더와 청킹 로직."""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    title: str
    content: str
    category: str
    source: str
    date: str
    path: str
    chunk_index: int

    @property
    def combined_text(self) -> str:
        return (
            f"제목: {self.title}\n"
            f"분류: {self.category}\n"
            f"출처: {self.source}\n"
            f"기준일: {self.date}\n\n"
            f"{self.content}"
        )

    def metadata(self) -> dict:
        data = asdict(self)
        data.pop("content", None)
        return data


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_metadata_and_body(raw_text: str, fallback_title: str, path: str) -> tuple[dict, str]:
    """txt 상단의 선택 메타데이터를 읽습니다.

    지원 형식:
        title: 금융소득종합과세
        category: 금융소득
        source: 국세청
        date: 2026-01-01
        ---
        본문...
    """
    text = normalize_text(raw_text)
    metadata = {
        "title": fallback_title,
        "category": "세금",
        "source": fallback_title,
        "date": "",
        "path": path,
    }

    if "---" in text[:500]:
        head, body = text.split("---", 1)
        for line in head.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key in metadata and value:
                metadata[key] = value
        return metadata, normalize_text(body)

    # 메타데이터가 없으면 첫 줄을 제목 후보로 씁니다.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        metadata["title"] = lines[0][:80]
    return metadata, text


def split_into_chunks(text: str, max_chars: int = 900, min_chars: int = 120) -> list[str]:
    """문서를 문단 단위로 쪼갠 뒤 너무 길면 문장 단위로 추가 분할합니다."""
    text = normalize_text(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    buffer = ""

    def flush():
        nonlocal buffer
        if buffer.strip():
            chunks.append(buffer.strip())
        buffer = ""

    for para in paragraphs:
        if len(para) > max_chars:
            flush()
            sentences = re.split(r"(?<=[.!?。！？다요음임함됨])\s+", para)
            tmp = ""
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(tmp) + len(sent) + 1 <= max_chars:
                    tmp = f"{tmp} {sent}".strip()
                else:
                    if tmp:
                        chunks.append(tmp)
                    tmp = sent
            if tmp:
                chunks.append(tmp)
            continue

        if len(buffer) + len(para) + 2 <= max_chars:
            buffer = f"{buffer}\n\n{para}".strip()
        else:
            flush()
            buffer = para

    flush()

    # 너무 짧은 chunk는 다음 chunk와 합칩니다.
    merged: list[str] = []
    for chunk in chunks:
        if merged and len(chunk) < min_chars:
            merged[-1] = f"{merged[-1]}\n\n{chunk}".strip()
        else:
            merged.append(chunk)

    return [c for c in merged if len(c.strip()) >= 20]


def load_documents(sources_dir: str | os.PathLike) -> list[DocumentChunk]:
    root = Path(sources_dir)
    if not root.exists():
        raise FileNotFoundError(f"RAG sources 폴더가 없습니다: {root}")

    files = sorted(root.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"{root} 안에 .txt 문서가 없습니다.")

    seen_hashes: set[str] = set()
    chunks: list[DocumentChunk] = []

    for file in files:
        raw = file.read_text(encoding="utf-8")
        meta, body = parse_metadata_and_body(raw, file.stem, str(file))
        for idx, content in enumerate(split_into_chunks(body)):
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)

            chunk_id = f"{file.stem}::{idx}::{content_hash[:10]}"
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    title=meta["title"],
                    category=meta["category"],
                    source=meta["source"],
                    date=meta["date"],
                    path=meta["path"],
                    content=content,
                    chunk_index=idx,
                )
            )

    return chunks
