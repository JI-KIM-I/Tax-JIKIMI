from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import re


@dataclass
class RAGDocument:
    doc_id: str
    title: str
    content: str
    text: str
    category: str
    source: str
    date: str


class DocumentLoader:
    """rag/sources/*.txt 문서를 읽어서 검색 가능한 문서 조각으로 변환한다."""

    def __init__(self, sources_dir: str | Path):
        self.sources_dir = Path(sources_dir)

    def _guess_category(self, filename: str, text: str) -> str:
        joined = f"{filename} {text}"
        if "금융소득" in joined or "종합과세" in joined:
            return "금융소득"
        if "연금" in joined:
            return "연금"
        if "ISA" in joined or "IRP" in joined or "연금저축" in joined or "절세한도" in joined:
            return "절세계좌"
        if "증여" in joined or "상속" in joined:
            return "상속증여"
        return "세금"

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _chunk_text(self, text: str, min_chars: int = 80, max_chars: int = 900) -> list[str]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        chunks: list[str] = []
        buffer = ""

        for para in paragraphs:
            candidate = f"{buffer}\n\n{para}".strip() if buffer else para

            if len(candidate) < min_chars:
                buffer = candidate
            elif len(candidate) <= max_chars:
                chunks.append(candidate)
                buffer = ""
            else:
                if buffer:
                    chunks.append(buffer)
                    buffer = ""
                chunks.append(para[:max_chars])

        if buffer:
            chunks.append(buffer)

        return chunks or [text]

    def load_documents(self) -> list[RAGDocument]:
        if not self.sources_dir.exists():
            raise FileNotFoundError(f"RAG sources 폴더가 없습니다: {self.sources_dir}")

        txt_files = sorted(self.sources_dir.glob("*.txt"))
        if not txt_files:
            raise FileNotFoundError(f"{self.sources_dir} 안에 .txt 파일이 없습니다.")

        documents: list[RAGDocument] = []
        seen_contents: set[str] = set()

        for path in txt_files:
            text = self._normalize_text(path.read_text(encoding="utf-8"))
            if not text:
                continue

            title = path.stem.replace("_", " ").replace("-", " ").strip()
            category = self._guess_category(path.name, text)
            source = "국세청 및 관련 안내자료 기반 정리"
            date = "2026"

            for idx, chunk in enumerate(self._chunk_text(text)):
                content = self._normalize_text(chunk)
                if not content or content in seen_contents:
                    continue

                seen_contents.add(content)
                digest = hashlib.md5(content.encode("utf-8")).hexdigest()[:10]
                doc_id = f"{path.stem}::{idx}::{digest}"

                documents.append(
                    RAGDocument(
                        doc_id=doc_id,
                        title=title,
                        content=content,
                        text=content,
                        category=category,
                        source=source,
                        date=date,
                    )
                )

        return documents
