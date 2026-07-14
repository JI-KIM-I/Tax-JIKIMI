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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

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

def _build_report_text(result) -> str:
    lines = [
        "세금지킴이 절세 진단 리포트",
        "=" * 40,
        result.report_summary,
        "",
        "[금융소득종합과세]",
        result.financial_income_tax.message,
        "",
        "[연금 수령 비교]",
        result.pension_compare.message,
        "",
        "[절세 한도 활용]",
        result.limit_usage.message,
        "",
        "[AI 추천사항]",
        *[f"- {r}" for r in result.recommendations],
        "",
        result.disclaimer,
    ]
    return "\n".join(lines)


def _wrap_line(text: str, font_name: str, font_size: int, max_width: float) -> list[str]:
    """긴 한 줄을 페이지 폭에 맞게 여러 줄로 나눕니다 (단어 단위가 아닌 글자 단위 -
    한글은 띄어쓰기가 없어도 줄이 길어질 수 있어 글자 단위로 자릅니다)."""
    if not text:
        return [""]

    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = candidate
    lines.append(current)
    return lines


def _build_report_pdf(text: str) -> BytesIO:
    """한글 폰트(나눔고딕)를 사용한 PDF 생성. 긴 줄은 자동으로 줄바꿈됩니다."""
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    x_margin = 20 * mm
    y = height - 20 * mm
    line_height = 6.5 * mm
    font_size = 11
    max_text_width = width - 2 * x_margin

    page.setFont(_PDF_FONT, font_size)
    for raw_line in text.split("\n"):
        for line in _wrap_line(raw_line, _PDF_FONT, font_size, max_text_width):
            if y < 20 * mm:
                page.showPage()
                page.setFont(_PDF_FONT, font_size)
                y = height - 20 * mm
            page.drawString(x_margin, y, line)
            y -= line_height

    page.save()
    buffer.seek(0)
    return buffer


@app.post("/api/report/export")
def api_report_export(body: ReportExportRequestBody):
    """결과 리포트 저장 (PDF/텍스트). 한글은 나눔고딕 폰트로 정상 출력됩니다."""
    request = body.to_dataclass()
    result = _run(diagnose, request)
    text = _build_report_text(result)

    if body.format == "text":
        return StreamingResponse(
            iter([text.encode("utf-8")]),
            media_type="text/plain",
            headers={"Content-Disposition": "attachment; filename=taxguard_report.txt"},
        )

    pdf_buffer = _build_report_pdf(text)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=taxguard_report.pdf"},
    )


# -----------------------------------------------------------------------------
# RAG 챗봇 (아직 미구현 - 스텁)
# -----------------------------------------------------------------------------

@app.post("/api/search")
def api_search(body: ChatRequestBody):
    """벡터DB 문서 검색 (retrieval only). RAG 파이프라인 연동 전 스텁입니다."""
    raise HTTPException(
        status_code=501,
        detail="RAG 검색 기능은 아직 연동되지 않았습니다. ChromaDB 인덱싱 완료 후 구현 예정입니다.",
    )


@app.post("/api/chat")
def api_chat(body: ChatRequestBody):
    """RAG 질의응답. RAG 파이프라인 연동 전 스텁입니다."""
    raise HTTPException(
        status_code=501,
        detail="챗봇 기능은 아직 연동되지 않았습니다. RAG 파이프라인 구현 후 사용 가능합니다.",
    )
