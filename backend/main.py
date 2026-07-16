"""
세금지킴이 (팀 지킴 Jikim) - FastAPI 백엔드

taxguard_calculation_logic.py 의 계산 함수들을 그대로 감싸서
HTTP API(/api/...)로 노출합니다. 계산 로직 자체는 하나도 수정하지 않습니다.

실행:
    uvicorn main:app --reload

문서(자동 생성, 브라우저에서 각 API 직접 테스트 가능):
    http://localhost:8000/docs
"""

from __future__ import annotations

import os
from decimal import Decimal
from io import BytesIO
from typing import Optional

import chromadb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from taxguard_calculation_logic import (
    DiagnosisRequest,
    FinancialIncomeTaxRequest,
    LimitUsageGuideRequest,
    PensionCompareRequest,
    PensionStartRecommendationRequest,
    ProductShiftRequest,
    calculate_limit_usage_guide,
    calculate_product_shift_guide,
    compare_pension_withdrawal,
    diagnose,
    diagnose_financial_income_tax,
    recommend_pension_start_age,
)

# -----------------------------------------------------------------------------
# 한글 폰트 등록 (PDF 리포트용)
# fonts/NanumGothic.ttf 가 이 파일과 같은 폴더에 있어야 합니다.
# -----------------------------------------------------------------------------

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_KOREAN_FONT_PATH = os.path.join(_FONT_DIR, "NanumGothic.ttf")
KOREAN_FONT_NAME = "NanumGothic"

if os.path.exists(_KOREAN_FONT_PATH):
    pdfmetrics.registerFont(TTFont(KOREAN_FONT_NAME, _KOREAN_FONT_PATH))
    _PDF_FONT = KOREAN_FONT_NAME
else:
    # 폰트 파일이 없으면 한글이 깨지지만, 서버 자체는 계속 동작하도록 폴백합니다.
    _PDF_FONT = "Helvetica"

# -----------------------------------------------------------------------------
# RAG 설정 (ChromaDB 검색 + OpenAI 답변 생성)
#
# rag/sources/*.txt 를 rag/build_index.py로 먼저 인덱싱해둬야 검색이 됩니다.
#   cd rag && python build_index.py
#
# 답변 생성에는 OpenAI API를 사용합니다. 환경변수 OPENAI_API_KEY가 필요합니다.
#   export OPENAI_API_KEY="sk-..."
# -----------------------------------------------------------------------------

_RAG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rag")
_CHROMA_DB_DIR = os.path.join(_RAG_DIR, "chroma_db")
_RAG_COLLECTION_NAME = "tax_knowledge"
_RAG_EMBEDDING_MODEL = "text-embedding-3-small"

_chroma_collection = None  # 첫 요청 때 한 번만 로드 (lazy load)


def _get_rag_embedding_function():
    """rag/build_index.py에서 인덱싱할 때 쓴 것과 반드시 같은 임베딩 방식이어야
    검색 결과가 정확합니다 (다르면 저장할 때 기준과 검색할 때 기준이 어긋남)."""
    from chromadb.utils import embedding_functions

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
                "검색(임베딩)에도 OpenAI를 사용하므로 키 설정이 필요합니다."
            ),
        )
    return embedding_functions.OpenAIEmbeddingFunction(
        api_key=api_key, model_name=_RAG_EMBEDDING_MODEL
    )


def _get_rag_collection():
    """ChromaDB 컬렉션을 최초 호출 시 한 번만 로드해서 재사용합니다."""
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection

    if not os.path.isdir(_CHROMA_DB_DIR):
        raise HTTPException(
            status_code=503,
            detail=(
                "RAG 벡터DB가 아직 만들어지지 않았습니다. "
                "'cd rag && python build_index.py'를 먼저 실행해주세요."
            ),
        )

    client = chromadb.PersistentClient(path=_CHROMA_DB_DIR)
    try:
        _chroma_collection = client.get_collection(
            _RAG_COLLECTION_NAME, embedding_function=_get_rag_embedding_function()
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"RAG 컬렉션을 불러오지 못했습니다: {e}",
        ) from e
    return _chroma_collection


def _retrieve_chunks(query: str, top_k: int = 4) -> list[dict]:
    """질문과 의미상 가까운 문서 조각 top_k개를 벡터DB에서 찾아 반환합니다."""
    collection = _get_rag_collection()
    result = collection.query(query_texts=[query], n_results=top_k)

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    return [
        {"text": doc, "source": meta.get("source", "unknown"), "distance": dist}
        for doc, meta, dist in zip(documents, metadatas, distances)
    ]


_openai_client: Optional[OpenAI] = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
                    "터미널에서 export OPENAI_API_KEY=\"sk-...\" 실행 후 서버를 다시 켜주세요."
                ),
            )
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def _build_chat_prompt(question: str, chunks: list[dict], context: Optional[dict]) -> str:
    """검색된 문서 조각 + (있다면) 현재 화면의 계산 결과를 합쳐 LLM용 프롬프트를 만듭니다."""
    sources_text = "\n\n".join(
        f"[출처: {c['source']}]\n{c['text']}" for c in chunks
    )

    context_text = ""
    if context:
        context_text = f"\n\n[사용자의 현재 진단 결과 요약]\n{context}"

    return (
        "당신은 한국 세법에 정통한 절세 상담 도우미 '세금지킴이'입니다. "
        "아래 참고 자료와 사용자의 계산 결과만 근거로 답변하세요. "
        "참고 자료에 없는 내용은 추측하지 말고 모른다고 답하세요. "
        "숫자를 인용할 때는 반드시 참고 자료의 출처를 함께 언급하세요.\n\n"
        f"[참고 자료]\n{sources_text}"
        f"{context_text}\n\n"
        f"[사용자 질문]\n{question}"
    )

# -----------------------------------------------------------------------------
# 앱 & CORS 설정
# -----------------------------------------------------------------------------

app = FastAPI(
    title="세금지킴이 API",
    description="AI 기반 개인 맞춤 절세 진단 서비스 - 계산 API",
    version="0.1.0",
)

# React 개발 서버(Vite: 5173, CRA: 3000)에서 오는 요청 허용.
# 배포 시에는 실제 프론트 도메인으로 좁혀야 합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run(fn, *args, **kwargs):
    """계산 로직에서 발생하는 ValueError를 400 에러로 변환."""
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# -----------------------------------------------------------------------------
# 요청 바디 스키마 (pydantic)
# taxguard_calculation_logic.py 의 *Request 데이터클래스와 1:1로 대응됩니다.
# -----------------------------------------------------------------------------

class DiagnosisRequestBody(BaseModel):
    age: int
    retirement_age: int
    total_income: int
    interest_income: int
    dividend_income: int
    other_tax_base: int = 0
    annual_yield_rate: float = 0.04
    pension_savings_balance: int = 0
    irp_balance: int = 0
    expected_pension_amount: int = 0
    pension_split_years: int = 10
    lifetime_annuity_contract: bool = False
    tax_year: int = 2026
    isa_paid_this_year: int = 0
    isa_total_paid: int = 0
    pension_savings_paid_this_year: int = 0
    irp_paid_this_year: int = 0
    recommend_pension_start: bool = True
    max_pension_start_age: int = 85

    def to_dataclass(self) -> DiagnosisRequest:
        # 하위 클래스(ReportExportRequestBody 등)에서 추가한 필드는 제외하고,
        # DiagnosisRequest가 실제로 받는 필드만 골라서 전달합니다.
        allowed_fields = DiagnosisRequestBody.model_fields.keys()
        data = {k: v for k, v in self.dict().items() if k in allowed_fields}
        data["annual_yield_rate"] = Decimal(str(data["annual_yield_rate"]))
        return DiagnosisRequest(**data)


class FinancialIncomeTaxRequestBody(BaseModel):
    interest_income: int
    dividend_income: int
    other_tax_base: int = 0


class ProductShiftRequestBody(BaseModel):
    financial_income: int
    annual_yield_rate: float = 0.04


class PensionCompareRequestBody(BaseModel):
    start_age: int
    pension_amount: int
    split_years: int = 10
    lifetime_annuity_contract: bool = False
    tax_year: int = 2026


class PensionStartRecommendationRequestBody(BaseModel):
    current_age: int
    max_start_age: int
    pension_amount: int
    split_years: int = 10
    lifetime_annuity_contract: bool = False
    tax_year: int = 2026


class LimitUsageGuideRequestBody(BaseModel):
    isa_paid_this_year: int
    isa_total_paid: int
    pension_savings_paid_this_year: int
    irp_paid_this_year: int
    gross_salary: int


class ReportExportRequestBody(DiagnosisRequestBody):
    format: str = Field(default="pdf", description="'pdf' 또는 'text'")


class ChatRequestBody(BaseModel):
    message: str
    top_k: int = 4
    context: Optional[dict] = None  # 프론트에서 현재 진단 결과(DiagnosisResponse)를 함께 보낼 수 있음


# -----------------------------------------------------------------------------
# 헬스체크
# -----------------------------------------------------------------------------

@app.get("/")
def health_check():
    return {"status": "ok", "service": "세금지킴이 API"}


# -----------------------------------------------------------------------------
# 계산 · 진단 엔드포인트
# -----------------------------------------------------------------------------

@app.post("/api/diagnosis")
def api_diagnosis(body: DiagnosisRequestBody):
    """통합 절세 진단 실행 ("절세 진단 시작" 버튼)."""
    request = body.to_dataclass()
    return _run(diagnose, request)


@app.post("/api/diagnosis/comprehensive-tax")
def api_comprehensive_tax(body: FinancialIncomeTaxRequestBody):
    """금융소득종합과세 진단 (분리과세 vs 종합과세)."""
    request = FinancialIncomeTaxRequest(**body.dict())
    return _run(diagnose_financial_income_tax, request)


@app.post("/api/tax-saving/product-shift")
def api_product_shift(body: ProductShiftRequestBody):
    """금융소득 초과분을 줄이기 위한 절세 상품 이동 금액 가이드."""
    request = ProductShiftRequest(
        financial_income=body.financial_income,
        annual_yield_rate=Decimal(str(body.annual_yield_rate)),
    )
    return _run(calculate_product_shift_guide, request)


@app.post("/api/pension/withdrawal-comparison")
def api_pension_withdrawal_comparison(body: PensionCompareRequestBody):
    """연금 수령방식별 세액 비교 (일시금 vs 분할)."""
    request = PensionCompareRequest(**body.dict())
    return _run(compare_pension_withdrawal, request)


@app.post("/api/pension/timing-recommendation")
def api_pension_timing_recommendation(body: PensionStartRecommendationRequestBody):
    """연금 수령 시점 추천."""
    request = PensionStartRecommendationRequest(**body.dict())
    return _run(recommend_pension_start_age, request)


@app.post("/api/tax-saving/utilization")
def api_tax_saving_utilization(body: LimitUsageGuideRequestBody):
    """절세 한도 활용 가이드 (ISA·연금저축·IRP)."""
    request = LimitUsageGuideRequest(**body.dict())
    return _run(calculate_limit_usage_guide, request)


@app.post("/api/diagnosis/scenario-comparison")
def api_scenario_comparison(body: DiagnosisRequestBody):
    """시나리오 비교 (A. 현재 방식 / B. ISA 활용 / C. 연금 분할 수령).

    시나리오 계산은 통합 진단(diagnose) 내부에서 함께 산출되므로,
    동일 함수를 호출한 뒤 시나리오 비교 부분만 추려서 반환합니다.
    """
    request = body.to_dataclass()
    result = _run(diagnose, request)
    return {
        "scenario_comparison": result.scenario_comparison,
        "report_summary": result.report_summary,
    }


# -----------------------------------------------------------------------------
# 리포트 저장 (PDF / 텍스트)
# -----------------------------------------------------------------------------

def _won(value) -> str:
    return f"{round(value):,}원"


def _pct(ratio) -> str:
    return f"{float(ratio) * 100:.1f}%"


def _build_report_text(result) -> str:
    """텍스트(.txt) 리포트 - 표는 줄글 형태로 풀어서 담습니다."""
    fit = result.financial_income_tax
    ps = result.product_shift
    pc = result.pension_compare
    lu = result.limit_usage

    lines = [
        "세금지킴이 절세 진단 리포트",
        "=" * 40,
        result.report_summary,
        "",
        "[금융소득종합과세]",
        fit.message,
        f"- 금융소득 합계: {_won(fit.financial_income)}",
        f"- 2,000만원 초과분: {_won(fit.excess_amount)}",
        f"- 예상 추가세액 합계: {_won(fit.additional_total_tax)}",
        f"- {ps.recommendation}",
        "",
        "[연금 수령 비교]",
        pc.rate_note,
        pc.message,
        f"- 일시금 세금: {_won(pc.lump_total_tax)}",
        f"- 분할 수령 세금 합계: {_won(pc.split_total_tax)}",
        "- 연도별 상세:",
    ]
    for a in pc.annual_taxes:
        lines.append(
            f"  {a.year}년차 ({a.age}세): 수령액 {_won(a.annual_amount)}, "
            f"세율 {float(a.national_tax_rate) * 100:.1f}%, 세금 {_won(a.total_tax)}, "
            f"누적 {_won(a.cumulative_tax)}"
        )

    if result.pension_start_recommendation:
        rec = result.pension_start_recommendation
        lines += [
            "",
            "[연금 시작 시점 추천]",
            f"- 추천 시작 나이: {rec.recommended_start_age}세",
            f"- 예상 분할 수령 세금: {_won(rec.expected_split_total_tax)}",
            rec.reason,
        ]

    lines += [
        "",
        "[절세 한도 활용]",
        lu.message,
        f"- ISA 연간 한도 활용률: {_pct(lu.isa_annual_usage_rate)} ({_won(lu.isa_paid_this_year)} / {_won(lu.isa_annual_limit)})",
        f"- ISA 누적 한도 활용률: {_pct(lu.isa_total_usage_rate)} ({_won(lu.isa_total_paid)} / {_won(lu.isa_total_limit)})",
        f"- 연금저축+IRP 합산 한도 활용률: {_pct(lu.pension_irp_combined_usage_rate)} ({_won(lu.combined_pension_paid)} / {_won(lu.pension_irp_combined_tax_credit_limit)})",
        f"- 예상 세액공제액: {_won(lu.estimated_tax_credit)}",
        "",
        "[AI 추천사항]",
        *[f"- {r}" for r in result.recommendations],
        "",
        "[시나리오 비교]",
    ]
    for s in result.scenario_comparison:
        lines.append(
            f"- {s.scenario_name}: 예상 세금 {_won(s.estimated_tax)}, "
            f"절세액 {_won(s.saving_amount)} ({_pct(s.saving_rate)}) - {s.description}"
        )

    lines += ["", result.disclaimer]
    return "\n".join(lines)


def _pdf_styles():
    body = ParagraphStyle(
        "body", fontName=_PDF_FONT, fontSize=10, leading=14, spaceAfter=4,
    )
    heading = ParagraphStyle(
        "heading", fontName=_PDF_FONT, fontSize=13, leading=18, spaceBefore=14, spaceAfter=6,
        textColor=colors.HexColor("#16302E"),
    )
    title = ParagraphStyle(
        "title", fontName=_PDF_FONT, fontSize=18, leading=24, spaceAfter=10,
        textColor=colors.HexColor("#16302E"),
    )
    muted = ParagraphStyle(
        "muted", fontName=_PDF_FONT, fontSize=8.5, leading=12, textColor=colors.HexColor("#4D6462"),
    )
    return body, heading, title, muted


def _make_table(header: list[str], rows: list[list[str]]) -> Table:
    data = [header] + rows
    table = Table(data, hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _PDF_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF4F1")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#16302E")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DBE3E0")),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_report_pdf(result) -> BytesIO:
    """한글 폰트(나눔고딕) + 세부 표까지 포함한 PDF 리포트 생성."""
    body, heading, title, muted = _pdf_styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    fit = result.financial_income_tax
    ps = result.product_shift
    pc = result.pension_compare
    lu = result.limit_usage

    story = [
        Paragraph("세금지킴이 절세 진단 리포트", title),
        Paragraph(result.report_summary, body),
        Spacer(1, 6),
    ]

    # 금융소득종합과세
    story.append(Paragraph("금융소득종합과세 진단", heading))
    story.append(Paragraph(fit.message, body))
    story.append(
        _make_table(
            ["항목", "금액"],
            [
                ["금융소득 합계", _won(fit.financial_income)],
                ["2,000만원 초과분", _won(fit.excess_amount)],
                ["기본계산 산출세액", _won(fit.basic_national_tax)],
                ["비교계산 산출세액", _won(fit.compare_national_tax)],
                ["최종 산출세액", _won(fit.final_national_tax)],
                ["예상 추가 국세", _won(fit.additional_national_tax)],
                ["예상 추가 지방세", _won(fit.additional_local_tax)],
                ["예상 추가세액 합계", _won(fit.additional_total_tax)],
            ],
        )
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph(ps.recommendation, body))

    # 연금 수령 비교
    story.append(Paragraph("연금 일시금 vs 분할 수령 비교", heading))
    story.append(Paragraph(pc.rate_note, muted))
    story.append(Paragraph(pc.message, body))
    story.append(
        _make_table(
            ["연차", "나이", "연간 수령액", "세율", "연간 세금", "누적 세금"],
            [
                [
                    str(a.year),
                    f"{a.age}세",
                    _won(a.annual_amount),
                    f"{float(a.national_tax_rate) * 100:.1f}%",
                    _won(a.total_tax),
                    _won(a.cumulative_tax),
                ]
                for a in pc.annual_taxes
            ],
        )
    )

    # 연금 시작 시점 추천
    if result.pension_start_recommendation:
        rec = result.pension_start_recommendation
        story.append(Paragraph("연금 수령 시작 시점 추천", heading))
        story.append(
            Paragraph(
                f"추천 시작 나이: <b>{rec.recommended_start_age}세</b> "
                f"(예상 분할 수령 세금 {_won(rec.expected_split_total_tax)})",
                body,
            )
        )
        story.append(Paragraph(rec.reason, body))

    # 절세 한도 활용
    story.append(Paragraph("ISA · 연금저축 · IRP 절세 한도 활용", heading))
    story.append(Paragraph(lu.message, body))
    story.append(
        _make_table(
            ["구분", "납입/사용액", "한도", "활용률"],
            [
                ["ISA 연간", _won(lu.isa_paid_this_year), _won(lu.isa_annual_limit), _pct(lu.isa_annual_usage_rate)],
                ["ISA 누적", _won(lu.isa_total_paid), _won(lu.isa_total_limit), _pct(lu.isa_total_usage_rate)],
                [
                    "연금저축+IRP 합산",
                    _won(lu.combined_pension_paid),
                    _won(lu.pension_irp_combined_tax_credit_limit),
                    _pct(lu.pension_irp_combined_usage_rate),
                ],
            ],
        )
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"예상 세액공제액: <b>{_won(lu.estimated_tax_credit)}</b>", body))

    # AI 추천사항
    story.append(Paragraph("AI 추천사항", heading))
    for i, rec_text in enumerate(result.recommendations, start=1):
        story.append(Paragraph(f"{i}. {rec_text}", body))

    # 시나리오 비교
    story.append(Paragraph("시나리오별 예상 세금 비교", heading))
    story.append(
        _make_table(
            ["시나리오", "예상 세금", "절세액", "절세율"],
            [
                [s.scenario_name, _won(s.estimated_tax), _won(s.saving_amount), _pct(s.saving_rate)]
                for s in result.scenario_comparison
            ],
        )
    )

    story.append(Spacer(1, 10))
    story.append(Paragraph(f"⚠ {result.disclaimer}", muted))

    doc.build(story)
    buffer.seek(0)
    return buffer


@app.post("/api/report/export")
def api_report_export(body: ReportExportRequestBody):
    """결과 리포트 저장 (PDF/텍스트). 한글은 나눔고딕 폰트로 정상 출력되며, PDF에는
    금융소득/연금/한도 관련 세부 표까지 함께 포함됩니다."""
    request = body.to_dataclass()
    result = _run(diagnose, request)

    if body.format == "text":
        text = _build_report_text(result)
        return StreamingResponse(
            iter([text.encode("utf-8")]),
            media_type="text/plain",
            headers={"Content-Disposition": "attachment; filename=taxguard_report.txt"},
        )

    pdf_buffer = _build_report_pdf(result)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=taxguard_report.pdf"},
    )


# -----------------------------------------------------------------------------
# RAG 챗봇
# -----------------------------------------------------------------------------

@app.post("/api/search")
def api_search(body: ChatRequestBody):
    """벡터DB 문서 검색 (retrieval only, 내부·평가용). LLM 호출 없이 검색 결과만 반환합니다."""
    chunks = _retrieve_chunks(body.message, top_k=body.top_k)
    return {"query": body.message, "results": chunks}


@app.post("/api/chat")
def api_chat(body: ChatRequestBody):
    """RAG 질의응답 (검색 + 계산값 + 질문 → LLM 답변)."""
    chunks = _retrieve_chunks(body.message, top_k=body.top_k)
    prompt = _build_chat_prompt(body.message, chunks, body.context)

    client = _get_openai_client()
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI API 호출 실패: {e}") from e

    answer = completion.choices[0].message.content

    return {
        "answer": answer,
        "sources": [{"source": c["source"], "text": c["text"]} for c in chunks],
    }
