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

    def _split_frontmatter(self, raw_text: str) -> tuple[dict[str, str], str]:
        """모든 rag/sources/*.txt 파일 맨 앞에 있는 title/category/source/date 메타데이터 블록을
        본문과 분리합니다. 이 블록을 그대로 두면 청크 내용에 "title: ... / category: ... / ---" 같은
        문구가 그대로 섞여 들어가서, 챗봇 답변이나 출처 미리보기에 이상하게 노출되는 문제가 있었습니다.

        형식 예시:
            title: 연금수령 세율
            category: 연금
            source: 국세청 연금소득 안내 기반 정리
            date: 2026
            ---
            (본문...)

        이 형식이 아니면 메타데이터 없이 원문 그대로 반환합니다.
        """
        lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        meta: dict[str, str] = {}
        field_re = re.compile(r"^([A-Za-z_]+)\s*:\s*(.*)$")

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "---":
                body = "\n".join(lines[i + 1 :])
                return meta, body
            match = field_re.match(stripped)
            if not match:
                # frontmatter 형식이 아니면(첫 줄부터 안 맞으면) 그냥 원문을 본문으로 취급합니다.
                return {}, raw_text
            meta[match.group(1).strip().lower()] = match.group(2).strip()

        # "---" 구분자를 못 찾았으면 메타데이터로 보지 않고 원문 그대로 반환합니다.
        return {}, raw_text

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
            raw_text = path.read_text(encoding="utf-8")
            meta, body = self._split_frontmatter(raw_text)
            text = self._normalize_text(body)
            if not text:
                continue

            title = meta.get("title") or path.stem.replace("_", " ").replace("-", " ").strip()
            category = meta.get("category") or self._guess_category(path.name, text)
            source = meta.get("source") or "국세청 및 관련 안내자료 기반 정리"
            date = meta.get("date") or "2026"

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
