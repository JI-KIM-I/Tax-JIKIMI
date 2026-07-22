from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

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
from rag.retriever import search_documents
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
API_LOG_PATH = LOG_DIR / "api_requests.jsonl"

ISA_POLICY_WARNING = (
    "※ ISA 비과세 한도 500만원(일반형)·1,000만원(서민·농어민형) 확대안은 "
    "개정 추진 또는 시행 여부 확인이 필요한 항목입니다. "
    "본 서비스의 계산은 현행 기준을 중심으로 한 예상 계산입니다."
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("taxjikimi")


def _model_dump(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _to_jsonable(obj: Any) -> Any:
    """dataclass/Decimal을 프론트가 바로 받을 수 있는 JSON 값으로 변환."""
    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))
    if isinstance(obj, Decimal):
        # 비율 값은 float로, 정수형 Decimal은 int로 처리
        if obj == obj.to_integral_value():
            return int(obj)
        return float(obj)
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, tuple):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def _won(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}원"
    except Exception:
        return f"{value}원"


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return f"{value}%"


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _log_api(endpoint: str, payload: dict, latency_ms: float, extra: Optional[dict] = None) -> None:
    record = {
        "endpoint": endpoint,
        "latency_ms": round(latency_ms, 2),
        "payload_preview": str(payload)[:500],
        "extra": extra or {},
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with API_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("api log write failed")


# -----------------------------------------------------------------------------
# FastAPI 앱 설정
# -----------------------------------------------------------------------------

class UTF8JSONResponse(JSONResponse):
    """배포 환경에서 한글 응답이 깨져 보이는 문제 대응.

    Starlette 기본 JSONResponse는 Content-Type을 그냥 'application/json'으로만 보내는데,
    JSON 스펙상 UTF-8이 기본이라 문제없어야 하지만 일부 브라우저/프록시가 charset을 명시하지
    않으면 시스템 기본 인코딩(EUC-KR/CP949 등)으로 잘못 해석해서 한글이 깨지는 경우가 있습니다.
    charset=utf-8을 명시해서 이런 애매함을 없앱니다.
    """

    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="절세지킴이 API",
    description="AI 기반 절세 진단 + RAG 챗봇 백엔드",
    version="1.0.0",
    default_response_class=UTF8JSONResponse,
)

cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in cors_origins.split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# 요청 DTO
# -----------------------------------------------------------------------------

class DiagnosisRequestBody(BaseModel):
    age: int = 45
    retirement_age: int = 60
    total_income: int = 80_000_000
    interest_income: int = 12_000_000
    dividend_income: int = 12_000_000
    other_tax_base: int = 0
    annual_yield_rate: float = 0.04
    pension_savings_balance: int = 25_000_000
    irp_balance: int = 18_000_000
    expected_pension_amount: int = 20_000_000
    pension_split_years: int = 10
    lifetime_annuity_contract: bool = False
    tax_year: int = 2026
    isa_paid_this_year: int = 15_000_000
    isa_total_paid: int = 15_000_000
    pension_savings_paid_this_year: int = 7_200_000
    irp_paid_this_year: int = 6_000_000
    recommend_pension_start: bool = True
    max_pension_start_age: int = 85

    def to_dataclass(self) -> DiagnosisRequest:
        data = _model_dump(self)
        # ReportExportRequestBody가 상속받아 format을 추가하더라도 제거
        allowed = DiagnosisRequest.__dataclass_fields__.keys()
        data = {k: v for k, v in data.items() if k in allowed}
        data["annual_yield_rate"] = Decimal(str(data.get("annual_yield_rate", 0.04)))
        # other_tax_base를 비워 보내는 프론트가 있어도 총소득을 기준으로 동작하게 보정
        if not data.get("other_tax_base"):
            data["other_tax_base"] = data.get("total_income", 0)
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
    max_start_age: int = 85
    pension_amount: int
    split_years: int = 10
    lifetime_annuity_contract: bool = False
    tax_year: int = 2026


class LimitUsageGuideRequestBody(BaseModel):
    isa_paid_this_year: int
    isa_total_paid: int = 0
    pension_savings_paid_this_year: int
    irp_paid_this_year: int
    gross_salary: int


class ReportExportRequestBody(DiagnosisRequestBody):
    format: str = Field(default="pdf", description="'pdf', 'text', 'image' 중 하나")


class ChatRequestBody(BaseModel):
    message: Optional[str] = None
    query: Optional[str] = None
    top_k: int = 10
    context: Optional[dict] = None

    @property
    def question(self) -> str:
        q = (self.message or self.query or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="message 또는 query가 필요합니다.")
        return q


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------

@app.get("/")
def health_check():
    return {"status": "ok", "service": "절세지킴이 API"}


# -----------------------------------------------------------------------------
# 계산 · 진단
# -----------------------------------------------------------------------------

@app.post("/api/diagnosis")
def api_diagnosis(body: DiagnosisRequestBody):
    started = time.perf_counter()
    result = _run(diagnose, body.to_dataclass())
    payload = _to_jsonable(result)
    _log_api("/api/diagnosis", _model_dump(body), (time.perf_counter() - started) * 1000)

    # 프론트 호환용 요약 필드를 추가로 제공. 기존 snake_case 결과도 그대로 유지.
    payload["ui_summary"] = {
        "risk_level": "주의" if payload["financial_income_tax"]["is_subject_to_comprehensive_tax"] else "안전",
        "estimated_additional_tax": payload["financial_income_tax"]["additional_total_tax"],
        "recommended_pension_method": "분할 수령" if payload["pension_compare"]["saving_by_split"] > 0 else "일시금",
        "isa_usage_rate": payload["limit_usage"]["isa_annual_usage_rate"],
        "pension_savings_usage_rate": payload["limit_usage"]["pension_savings_usage_rate"],
        "irp_usage_rate": payload["limit_usage"]["pension_irp_combined_usage_rate"],
    }
    return jsonable_encoder(payload)


@app.post("/api/diagnosis/comprehensive-tax")
def api_comprehensive_tax(body: FinancialIncomeTaxRequestBody):
    result = _run(diagnose_financial_income_tax, FinancialIncomeTaxRequest(**_model_dump(body)))
    return jsonable_encoder(_to_jsonable(result))


@app.post("/api/tax-saving/product-shift")
def api_product_shift(body: ProductShiftRequestBody):
    request = ProductShiftRequest(
        financial_income=body.financial_income,
        annual_yield_rate=Decimal(str(body.annual_yield_rate)),
    )
    result = _run(calculate_product_shift_guide, request)
    return jsonable_encoder(_to_jsonable(result))


@app.post("/api/pension/withdrawal-comparison")
def api_pension_withdrawal_comparison(body: PensionCompareRequestBody):
    result = _run(compare_pension_withdrawal, PensionCompareRequest(**_model_dump(body)))
    return jsonable_encoder(_to_jsonable(result))


@app.post("/api/pension/timing-recommendation")
def api_pension_timing_recommendation(body: PensionStartRecommendationRequestBody):
    result = _run(recommend_pension_start_age, PensionStartRecommendationRequest(**_model_dump(body)))
    return jsonable_encoder(_to_jsonable(result))


@app.post("/api/tax-saving/utilization")
def api_tax_saving_utilization(body: LimitUsageGuideRequestBody):
    result = _run(calculate_limit_usage_guide, LimitUsageGuideRequest(**_model_dump(body)))
    return jsonable_encoder(_to_jsonable(result))


@app.post("/api/diagnosis/scenario-comparison")
def api_scenario_comparison(body: DiagnosisRequestBody):
    result = _run(diagnose, body.to_dataclass())
    return jsonable_encoder(
        {
            "scenario_comparison": _to_jsonable(result.scenario_comparison),
            "report_summary": result.report_summary,
        }
    )


# -----------------------------------------------------------------------------
# 리포트 저장
# -----------------------------------------------------------------------------

def _build_report_text(result: Any) -> str:
    fit = result.financial_income_tax
    ps = result.product_shift
    pc = result.pension_compare
    lu = result.limit_usage

    lines = [
        "절세지킴이 절세 진단 리포트",
        "=" * 50,
        result.report_summary,
        "",
        "[금융소득종합과세]",
        f"- 금융소득 합계: {_won(fit.financial_income)}",
        f"- 기준 초과금액: {_won(fit.excess_amount)}",
        f"- 예상 추가세액: {_won(fit.additional_total_tax)}",
        f"- 설명: {fit.message}",
        "",
        "[절세 상품 이동 가이드]",
        f"- 줄여야 할 금융소득: {_won(ps.income_to_reduce)}",
        f"- 이동 필요 금액: {_won(ps.suggested_transfer_amount)}",
        f"- 추천: {ps.recommendation}",
        "",
        "[연금 수령 방식 비교]",
        f"- 일시금 예상 세금: {_won(pc.lump_total_tax)}",
        f"- 분할 수령 예상 세금: {_won(pc.split_total_tax)}",
        f"- 예상 절세액: {_won(pc.saving_by_split)}",
        f"- 설명: {pc.message}",
        "",
        "[절세 한도 활용]",
        f"- ISA 연간 활용률: {_pct(lu.isa_annual_usage_rate)}",
        f"- 연금저축 활용률: {_pct(lu.pension_savings_usage_rate)}",
        f"- 연금저축+IRP 합산 활용률: {_pct(lu.pension_irp_combined_usage_rate)}",
        f"- 예상 세액공제액: {_won(lu.estimated_tax_credit)}",
        f"- 참고: {ISA_POLICY_WARNING}",
        "",
        "[AI 추천사항]",
    ]
    lines += [f"{idx}. {rec}" for idx, rec in enumerate(result.recommendations, start=1)]
    lines += [
        "",
        "[시나리오 비교]",
    ]
    for scenario in result.scenario_comparison:
        lines.append(
            f"- {scenario.scenario_name}: 예상 세금 {_won(scenario.estimated_tax)}, "
            f"절세액 {_won(scenario.saving_amount)}, 절세율 {_pct(scenario.saving_rate)}"
        )
    lines += ["", f"※ {result.disclaimer}"]
    return "\n".join(lines)

def _build_detailed_report_image_v2(result: Any) -> BytesIO:
    from PIL import Image, ImageDraw, ImageFont

    text = _build_report_text(result)
    # 시스템 폰트 사용. 폰트 파일은 공유하지 않습니다.
    font = None
    for candidate in [
        BASE_DIR / "fonts" / "NanumGothic.ttf",
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]:
        if candidate.exists():
            try:
                font = ImageFont.truetype(str(candidate), 22)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()

    lines = []
    for raw in text.splitlines():
        if len(raw) <= 58:
            lines.append(raw)
        else:
            for i in range(0, len(raw), 58):
                lines.append(raw[i : i + 58])

    width = 1200
    line_h = 34
    height = max(800, 80 + line_h * len(lines))
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    y = 40
    for line in lines:
        draw.text((50, y), line, fill=(20, 35, 60), font=font)
        y += line_h

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def _report_font_v2() -> str:
    """
    한글 PDF 출력을 위한 폰트 설정.
    기존 _PDF_FONT가 있으면 그대로 쓰고, 없으면 프로젝트에 포함된 한글 TTF를 우선 등록한다.
    """
    if "_PDF_FONT" in globals():
        return globals()["_PDF_FONT"]

    font_candidates = [
        ("NanumGothic", BASE_DIR / "fonts" / "NanumGothic.ttf"),
        ("MalgunGothic", Path("C:/Windows/Fonts/malgun.ttf")),
        ("MalgunGothic", Path("C:/Windows/Fonts/malgunbd.ttf")),
        ("NanumGothic", Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")),
    ]

    checked_paths = []
    for font_name, path in font_candidates:
        checked_paths.append(str(path))
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(path)))
                globals()["_PDF_FONT"] = font_name
                return font_name
            except Exception:
                logger.warning("pdf font registration failed: %s", path, exc_info=True)

    logger.error("No Korean-compatible PDF font found. checked=%s", checked_paths)
    raise RuntimeError("Korean PDF font is not available")


def _won_v2(value) -> str:
    try:
        return f"{round(float(value)):,}원"
    except Exception:
        return "-"


def _pct_v2(value) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "-"


def _get_v2(obj, name: str, default=None):
    return getattr(obj, name, default) if obj is not None else default


def _table_v2(header: list[str], rows: list[list[str]]) -> Table:
    font = _report_font_v2()
    data = [header] + rows

    table = Table(data, hAlign="LEFT", repeatRows=1)

    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEADING", (0, 0), (-1, -1), 11),

                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF4F1")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#16302E")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDE6E3")),

                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    return table


def _split_long_text_v2(text, max_chars: int = 650) -> list[str]:
    """
    긴 문단이 PDF에서 잘리지 않도록 여러 문단으로 나눈다.
    텍스트를 삭제하지 않고, 가능한 문장 끝 기준으로 자른다.
    """
    if text is None:
        return []

    text = str(text).replace("\r\n", "\n").strip()

    if not text:
        return []

    result = []

    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        while len(paragraph) > max_chars:
            cut_candidates = [
                paragraph.rfind("다.", 0, max_chars),
                paragraph.rfind("요.", 0, max_chars),
                paragraph.rfind(".", 0, max_chars),
                paragraph.rfind(" ", 0, max_chars),
            ]

            cut = max(cut_candidates)

            if cut < int(max_chars * 0.5):
                cut = max_chars

            result.append(paragraph[: cut + 1].strip())
            paragraph = paragraph[cut + 1 :].strip()

        if paragraph:
            result.append(paragraph)

    return result


def _append_paragraphs_v2(story, text, style, max_chars: int = 650):
    """
    긴 텍스트를 여러 Paragraph로 안전하게 추가한다.
    """
    for chunk in _split_long_text_v2(text, max_chars=max_chars):
        story.append(Paragraph(chunk, style))

def _build_detailed_report_pdf_v2(result) -> BytesIO:
    
    font = _report_font_v2()

    body = ParagraphStyle(
        "report_body_v2",
        fontName=font,
        fontSize=10,
        leading=14,
        spaceAfter=4,
        textColor=colors.HexColor("#222222"),
        wordWrap="CJK",
    )

    heading = ParagraphStyle(
        "report_heading_v2",
        fontName=font,
        fontSize=13,
        leading=18,
        spaceBefore=14,
        spaceAfter=6,
        textColor=colors.HexColor("#16302E"),
        wordWrap="CJK",
    )

    title = ParagraphStyle(
        "report_title_v2",
        fontName=font,
        fontSize=18,
        leading=24,
        spaceAfter=10,
        textColor=colors.HexColor("#16302E"),
        wordWrap="CJK",
    )

    muted = ParagraphStyle(
        "report_muted_v2",
        fontName=font,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#4D6462"),
        wordWrap="CJK",
    )

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    fit = _get_v2(result, "financial_income_tax")
    ps = _get_v2(result, "product_shift")
    pc = _get_v2(result, "pension_compare")
    lu = _get_v2(result, "limit_usage")
    pension_rec = _get_v2(result, "pension_start_recommendation")

    story = []

    # 제목 + 요약
    story.append(Paragraph("세금지킴이 절세 진단 리포트", title))
    _append_paragraphs_v2(story, _get_v2(result, "report_summary", ""), body)
    story.append(Spacer(1, 8))

    # 금융소득종합과세 진단
    story.append(Paragraph("금융소득종합과세 진단", heading))
    _append_paragraphs_v2(story, _get_v2(fit, "message", ""), body)
    story.append(
        _table_v2(
            ["항목", "금액"],
            [
                ["금융소득 합계", _won_v2(_get_v2(fit, "financial_income", 0))],
                ["2,000만원 초과분", _won_v2(_get_v2(fit, "excess_amount", 0))],
                ["기본계산 산출세액", _won_v2(_get_v2(fit, "basic_national_tax", 0))],
                ["비교계산 산출세액", _won_v2(_get_v2(fit, "compare_national_tax", 0))],
                ["최종 산출세액", _won_v2(_get_v2(fit, "final_national_tax", 0))],
                ["예상 추가 국세", _won_v2(_get_v2(fit, "additional_national_tax", 0))],
                ["예상 추가 지방세", _won_v2(_get_v2(fit, "additional_local_tax", 0))],
                ["예상 추가세액 합계", _won_v2(_get_v2(fit, "additional_total_tax", 0))],
            ],
        )
    )

    recommendation = _get_v2(ps, "recommendation", "")
    if recommendation:
        story.append(Spacer(1, 6))
        _append_paragraphs_v2(story, recommendation, body)

    # 연금 일시금 vs 분할 수령 비교
    story.append(Paragraph("연금 일시금 vs 분할 수령 비교", heading))

    rate_note = _get_v2(pc, "rate_note", "")
    if rate_note:
        _append_paragraphs_v2(story, rate_note, muted)

    pension_message = _get_v2(pc, "message", "")
    if pension_message:
        _append_paragraphs_v2(story, pension_message, body)

    annual_taxes = _get_v2(pc, "annual_taxes", []) or []

    if annual_taxes:
        annual_rows = []

        for a in annual_taxes:
            rate = _get_v2(a, "national_tax_rate", _get_v2(a, "tax_rate", 0))
            annual_rows.append(
                [
                    str(_get_v2(a, "year", "")),
                    f"{_get_v2(a, 'age', '')}세",
                    _won_v2(_get_v2(a, "annual_amount", 0)),
                    _pct_v2(rate),
                    _won_v2(_get_v2(a, "total_tax", _get_v2(a, "annual_tax", 0))),
                    _won_v2(_get_v2(a, "cumulative_tax", 0)),
                ]
            )

        story.append(
            _table_v2(
                ["연차", "나이", "연간 수령액", "세율", "연간 세금", "누적 세금"],
                annual_rows,
            )
        )
    else:
        story.append(
            _table_v2(
                ["항목", "금액"],
                [
                    ["일시금 예상 세금", _won_v2(_get_v2(pc, "lump_total_tax", 0))],
                    ["분할 수령 예상 세금", _won_v2(_get_v2(pc, "split_total_tax", 0))],
                    ["예상 절세액", _won_v2(_get_v2(pc, "tax_saving", 0))],
                ],
            )
        )

    # 연금 수령 시작 시점 추천
    if pension_rec:
        story.append(Paragraph("연금 수령 시작 시점 추천", heading))
        story.append(
            Paragraph(
                f"추천 시작 나이: <b>{_get_v2(pension_rec, 'recommended_start_age', '-')}세</b> "
                f"(예상 분할 수령 세금 {_won_v2(_get_v2(pension_rec, 'expected_split_total_tax', 0))})",
                body,
            )
        )

        reason = _get_v2(pension_rec, "reason", "")
        if reason:
            _append_paragraphs_v2(story, reason, body)

    # ISA · 연금저축 · IRP 한도 활용
    story.append(Paragraph("ISA · 연금저축 · IRP 절세 한도 활용", heading))

    limit_message = _get_v2(lu, "message", "")
    if limit_message:
        _append_paragraphs_v2(story, limit_message, body)

    story.append(
        _table_v2(
            ["구분", "납입/사용액", "한도", "활용률"],
            [
                [
                    "ISA 연간",
                    _won_v2(_get_v2(lu, "isa_paid_this_year", 0)),
                    _won_v2(_get_v2(lu, "isa_annual_limit", 0)),
                    _pct_v2(_get_v2(lu, "isa_annual_usage_rate", 0)),
                ],
                [
                    "ISA 누적",
                    _won_v2(_get_v2(lu, "isa_total_paid", 0)),
                    _won_v2(_get_v2(lu, "isa_total_limit", 0)),
                    _pct_v2(_get_v2(lu, "isa_total_usage_rate", 0)),
                ],
                [
                    "연금저축+IRP 합산",
                    _won_v2(_get_v2(lu, "combined_pension_paid", 0)),
                    _won_v2(_get_v2(lu, "pension_irp_combined_tax_credit_limit", 0)),
                    _pct_v2(_get_v2(lu, "pension_irp_combined_usage_rate", 0)),
                ],
            ],
        )
    )

    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            f"예상 세액공제액: <b>{_won_v2(_get_v2(lu, 'estimated_tax_credit', 0))}</b>",
            body,
        )
    )
    story.append(Spacer(1, 4))
    _append_paragraphs_v2(story, ISA_POLICY_WARNING, muted)

    # AI 추천사항
    recommendations = _get_v2(result, "recommendations", []) or []
    if recommendations:
        story.append(Paragraph("AI 추천사항", heading))
        for i, rec_text in enumerate(recommendations, start=1):
            _append_paragraphs_v2(story, f"{i}. {rec_text}", body)

    # 시나리오별 예상 세금 비교
    scenarios = _get_v2(result, "scenario_comparison", []) or []
    if scenarios:
        story.append(Paragraph("시나리오별 예상 세금 비교", heading))
        story.append(
            _table_v2(
                ["시나리오", "예상 세금", "절세액", "절세율"],
                [
                    [
                        str(_get_v2(s, "scenario_name", "")),
                        _won_v2(_get_v2(s, "estimated_tax", 0)),
                        _won_v2(_get_v2(s, "saving_amount", 0)),
                        _pct_v2(_get_v2(s, "saving_rate", 0)),
                    ]
                    for s in scenarios
                ],
            )
        )

    # 하단 유의사항
    disclaimer = _get_v2(result, "disclaimer", "")
    if disclaimer:
        story.append(Spacer(1, 10))
        _append_paragraphs_v2(story, f"※ {disclaimer}", muted)

    doc.build(story)
    buffer.seek(0)
    return buffer

@app.post("/api/report/export")
def api_report_export(body: ReportExportRequestBody):
    result = _run(diagnose, body.to_dataclass())
    fmt = (body.format or "pdf").lower().strip()

    if fmt == "text" or fmt == "txt":
        text = _build_report_text(result)
        return StreamingResponse(
            iter([text.encode("utf-8")]),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=taxguard_report.txt"},
        )

    if fmt in {"image", "png"}:
        img = _build_detailed_report_image_v2(result)
        return StreamingResponse(
            img,
            media_type="image/png",
            headers={"Content-Disposition": "attachment; filename=taxguard_report.png"},
        )

    try:
        pdf = _build_detailed_report_pdf_v2(result)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=taxguard_report.pdf"},
    )


# -----------------------------------------------------------------------------
# RAG 검색 · 챗봇
# -----------------------------------------------------------------------------

@app.post("/api/search")
def api_search(body: ChatRequestBody):
    started = time.perf_counter()
    results, meta = search_documents(body.question, top_k=body.top_k)
    latency = (time.perf_counter() - started) * 1000
    _log_api("/api/search", _model_dump(body), latency, meta)
    return {
        "query": body.question,
        "top_k": body.top_k,
        "results": results,
        "meta": meta,
    }


# 세금과 무관한 인사말/잡담을 짧고 뚜렷한 패턴으로만 잡아냅니다 (오탐 방지를 위해 길이 제한 + 정확 매칭).
_GREETING_RE = re.compile(
    r"^\s*(안녕[!?~.\s]*(하세요|하십니까|)|하이|hi|hello|헬로|반가워요?|방가|ㅎㅇ|"
    r"고마워요?|고맙습니다|감사합니다|감사해요|수고하세요|수고했어요|잘\s*지내(요|니|셨어요)?)\s*[!?~.]*\s*$",
    re.IGNORECASE,
)


def _is_smalltalk(question: str) -> bool:
    """세금 상담과 무관한 인사말인지 가볍게 판별합니다.
    본문 내용을 억지로 채워 넣는 대신, RAG/LLM 호출 없이 바로 인사로 응답하기 위한 용도입니다."""
    q = (question or "").strip()
    if not q or len(q) > 12:
        return False
    return bool(_GREETING_RE.match(q))


def _smalltalk_answer(question: str) -> str:
    return (
        "안녕하세요! 저는 절세지킴이 AI 챗봇이에요. "
        "연금 수령, 금융소득종합과세, ISA·연금저축·IRP 절세 한도 같은 주제를 국세청 자료 기준으로 안내해드려요. "
        '궁금한 걸 편하게 물어보세요. 예를 들면 "연금을 나눠 받으면 세금이 왜 줄어들어?" 같은 질문이 좋아요.'
    )


def _build_prompt(question: str, context: Optional[dict], docs: list[dict]) -> str:
    context_text = json.dumps(context or {}, ensure_ascii=False, indent=2)
    doc_text = "\n\n".join(
        f"[문서 {i+1}] 제목: {d.get('title')} / 출처: {d.get('source')} / 분류: {d.get('category')}\n{d.get('content') or d.get('text')}"
        for i, d in enumerate(docs)
    )
    return f"""
당신은 '절세지킴이'의 RAG 기반 세금 상담 챗봇입니다.

규칙:
0. 질문이 세금과 무관한 인사말이나 잡담이면, [참고 문서]나 [현재 진단 결과]를 억지로 끌어와 답하지 말고
   자연스럽게 짧은 인사로 답하면서 어떤 걸 도와줄 수 있는지 안내하세요.
1. 세금 관련 질문이라면 반드시 [참고 문서]와 [현재 진단 결과]에 근거해서 답변하세요.
2. 근거가 부족하면 단정하지 말고 "입력값 기준 예상"이라고 말하세요.
3. 세무사 확정 상담처럼 말하지 말고, 실제 세액은 달라질 수 있다고 안내하세요.
4. 답변은 한국어로, 5060 사용자가 이해하기 쉽게 4~7문장으로 작성하세요.
5. 가능하면 마지막에 "확인할 것" 1개를 제시하세요.

[현재 진단 결과]
{context_text}

[참고 문서]
{doc_text}

[사용자 질문]
{question}
""".strip()


def _extract_nested(d: dict, *keys, default=None):
    cur = d or {}
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _fallback_chat_answer(question: str, context: Optional[dict], docs: list[dict]) -> str:
    """OPENAI_API_KEY가 없을 때도 챗봇이 작동하도록 하는 fallback 답변."""
    q = question
    context = context or {}

    pension = context.get("pension_compare") or context.get("pension") or {}
    fit = context.get("financial_income_tax") or context.get("financialIncomeTax") or {}
    limit = context.get("limit_usage") or context.get("limitUsage") or {}

    if "연금" in q or "분할" in q or "일시" in q:
        lump = pension.get("lump_total_tax") or pension.get("lumpSumTax")
        split = pension.get("split_total_tax") or pension.get("splitTax")
        saving = pension.get("saving_by_split") or pension.get("estimatedSaving")
        if lump is not None and split is not None:
            return (
                f"입력하신 진단 결과 기준으로는 일시금 수령 시 예상 세금은 약 {_won(lump)}, "
                f"분할 수령 시 예상 세금은 약 {_won(split)}입니다. "
                f"따라서 분할 수령이 약 {_won(saving or (int(lump)-int(split)))} 정도 유리할 수 있습니다. "
                "다만 실제 세액은 연금계좌의 원천, 수령 요건, 연금수령한도 초과 여부에 따라 달라질 수 있습니다. "
                "확인할 것: 실제 수령하려는 금액이 연금수령한도 안에 들어오는지 확인해 주세요."
            )
        # 진단 결과가 없을 때도 문서 원문을 그대로 붙이지 않고, 같은 말투로 다시 풀어서 답합니다.
        return (
            "사적연금은 나이에 따라 낮아지는 세율(70세 미만 5%, 70~79세 4%, 80세 이상 3%)을 적용받기 때문에, "
            "보통 일시금으로 한 번에 받는 것보다 나눠 받을 때 세금이 줄어드는 경우가 많습니다. "
            "반대로 연금 외 수령으로 처리되면 기타소득세 15%가 적용될 수 있어요. "
            "왼쪽 진단 폼에 정보를 입력해주시면 실제 금액 기준으로 일시금과 분할수령의 세금 차이를 계산해드릴 수 있어요."
        )

    if "금융소득" in q or "종합과세" in q or "2천" in q:
        fin = fit.get("financial_income") or fit.get("financialIncome")
        excess = fit.get("excess_amount") or fit.get("excessAmount")
        add_tax = fit.get("additional_total_tax") or fit.get("estimatedAdditionalTax")
        if fin is not None:
            return (
                f"입력하신 정보 기준 금융소득은 약 {_won(fin)}이며, "
                f"2천만 원 기준 초과금액은 약 {_won(excess or 0)}입니다. "
                f"예상 추가세액은 약 {_won(add_tax or 0)}으로 계산됩니다. "
                "금융소득종합과세 여부는 먼저 이자소득과 배당소득 합계가 2천만 원을 초과하는지로 판단하고, "
                "초과 후에는 다른 종합소득과 합산되어 세율이 달라질 수 있습니다."
            )
        # 진단 결과가 없을 때도 같은 말투로 일반 규칙만 안내합니다 (문서 원문을 그대로 붙이면
        # "~다"체 문어체와 나머지 "~습니다"체가 섞여 어색해집니다).
        return (
            "금융소득종합과세는 이자소득과 배당소득 등 금융소득의 합계액이 연 2천만 원을 초과할 때 적용될 수 있습니다. "
            "2천만 원 이하라면 보통 금융회사가 원천징수한 세금으로 과세가 끝나고, 초과분이 있으면 다른 종합소득과 합산되어 세율이 달라질 수 있어요. "
            "왼쪽 진단 폼을 채워주시면 실제 금융소득 기준으로 얼마나 초과되는지 계산해드릴 수 있어요."
        )

    if "ISA" in q or "IRP" in q or "한도" in q or "연금저축" in q:
        credit = limit.get("estimated_tax_credit")
        if credit is not None:
            return (
                "절세 한도는 ISA, 연금저축, IRP 납입액을 기준으로 활용률을 계산합니다. "
                f"현재 진단 기준 예상 세액공제액은 약 {_won(credit)}입니다. "
                "연금저축과 IRP는 합산 한도를 초과하면 추가 납입분이 같은 방식으로 공제되지 않을 수 있으니, "
                "먼저 올해 납입액과 남은 한도를 확인하는 것이 좋습니다. "
                + ISA_POLICY_WARNING
            )
        return (
            "절세 한도는 ISA, 연금저축, IRP 납입액을 기준으로 활용률을 계산합니다. "
            "연금저축과 IRP는 합산 한도를 초과하면 추가 납입분이 같은 방식으로 공제되지 않을 수 있으니, "
            "먼저 올해 납입액과 남은 한도를 확인하는 것이 좋습니다. "
            "왼쪽 진단 폼을 채워주시면 실제 예상 세액공제액을 계산해드릴 수 있어요. "
            + ISA_POLICY_WARNING
        )

    # 여기까지 왔다는 건 위 키워드 중 어디에도 안 걸렸다는 뜻입니다. 문서 원문을 그대로 잘라
    # 문장 중간에 이어붙이면 문어체("~다")와 나머지 말투("~습니다")가 섞여 어색해지므로,
    # 인용임을 알 수 있게 따옴표로 감싸서 붙입니다.
    first_doc = ""
    if docs:
        first_doc = (docs[0].get("content") or docs[0].get("text") or "").strip()
    if first_doc:
        excerpt = first_doc[:160].strip()
        ellipsis = "..." if len(first_doc) > 160 else ""
        return (
            "질문을 조금 더 구체적으로 해주시면 더 정확히 답변드릴 수 있을 것 같아요. "
            f'참고로 관련 자료에는 "{excerpt}{ellipsis}"라고 안내되어 있어요. '
            "실제 세액은 개인별 공제, 감면, 상품 조건에 따라 달라질 수 있습니다."
        )
    return (
        "관련 자료를 찾지 못했어요. 질문을 조금 더 구체적으로 해주시면 도와드릴게요 "
        '(예: "연금을 나눠 받으면 세금이 왜 줄어들어?", "ISA 한도가 얼마야?").'
    )


def _call_openai(prompt: str) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model=os.getenv("OPENAI_CHAT_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return completion.choices[0].message.content
    except Exception:
        logger.exception("OpenAI API failed")
        return None

@app.post("/api/chat")
def api_chat(body: ChatRequestBody):
    started = time.perf_counter()

    # "안녕" 같은 인사말은 RAG 검색·LLM 호출 없이 바로 응답합니다.
    # (그렇지 않으면 세금과 무관한 문서가 검색돼 엉뚱한 답이 만들어질 수 있습니다)
    if _is_smalltalk(body.question):
        answer = _smalltalk_answer(body.question)
        latency = (time.perf_counter() - started) * 1000
        log_meta = {"used_fallback": False, "smalltalk": True}
        _log_api("/api/chat", _model_dump(body), latency, log_meta)
        return {"answer": answer, "sources": [], "meta": log_meta}

    docs, meta = search_documents(body.question, top_k=body.top_k)
    prompt = _build_prompt(body.question, body.context, docs)

    answer = _call_openai(prompt)
    used_fallback = False
    if not answer or answer.startswith("OpenAI API 호출에 실패"):
        used_fallback = True
        fallback = _fallback_chat_answer(body.question, body.context, docs)
        if answer and answer.startswith("OpenAI API 호출에 실패"):
            answer = answer + "\n\n" + fallback
        else:
            answer = fallback

    latency = (time.perf_counter() - started) * 1000
    log_meta = {**meta, "used_fallback": used_fallback}
    _log_api("/api/chat", _model_dump(body), latency, log_meta)

    return {
        "answer": answer,
        "sources": [
            {
                "source": d.get("source"),
                "title": d.get("title"),
                "category": d.get("category"),
                "date": d.get("date"),
                "text": d.get("content") or d.get("text"),
                "score": d.get("score"),
            }
            for d in docs
        ],
        "meta": log_meta,
    }
