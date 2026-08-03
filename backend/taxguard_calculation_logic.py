"""절세지킴이 계산 로직 전용 파일.

포함 기능
1. 금융소득종합과세 진단
2. 금융소득 2,000만 원 초과분을 줄이기 위한 상품 이동 금액 계산
3. 연금 일시금/연금외수령 vs 분할 연금수령 세액 비교
4. 연금 수령 시작 시점 추천
5. ISA·연금저축·IRP 한도 활용률 및 예상 세액공제액 계산
6. UI 그래프용 시나리오 비교 데이터 생성
7. 통합 진단 실행

주의
- 실제 세액은 소득공제, 세액공제, 감면, 배당세액공제, 상품 유형, 신고 방식,
  연금계좌 원천, 연금수령한도 초과 여부 등에 따라 달라질 수 있습니다.
- 금융소득종합과세 로직은 MVP용 단순화 비교과세 구조입니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Optional

D = Decimal

# -----------------------------------------------------------------------------
# 1. 세법/상품 기준 상수
# -----------------------------------------------------------------------------

FINANCIAL_INCOME_THRESHOLD = 20_000_000
FINANCIAL_WITHHOLDING_RATE = D("0.14")
LOCAL_INCOME_TAX_RATE = D("0.10")
PENSION_LUMP_SUM_RATE = D("0.15")

ISA_GENERAL_ANNUAL_LIMIT = 20_000_000
ISA_GENERAL_TOTAL_LIMIT = 100_000_000
PENSION_SAVINGS_TAX_CREDIT_LIMIT = 6_000_000
PENSION_IRP_COMBINED_TAX_CREDIT_LIMIT = 9_000_000

# 국민연금 노령연금 수급개시연령 (출생연도 기준, 국민연금법 부칙).
# 개인이 선택하는 값이 아니라 출생연도로 고정되며, 조기노령연금으로 최대 5년 앞당길 수 있지만
# 그만큼 감액되는 별도 제도입니다. (start_year, end_year, start_age)
NATIONAL_PENSION_START_AGE_BY_BIRTH_YEAR: tuple[tuple[int, int, int], ...] = (
    (0, 1952, 60),
    (1953, 1956, 61),
    (1957, 1960, 62),
    (1961, 1964, 63),
    (1965, 1968, 64),
    (1969, 9999, 65),
)

# 공무원연금은 국민연금과 지급개시연령 산정 기준(퇴직연도)부터 다른 별도 제도입니다.
# 이 앱의 대상 페르소나(은퇴 후 국민연금+사적연금+ISA를 굴리는 일반인)에는 해당하지 않는 경우가
# 대부분이라 전용 계산 필드는 두지 않고, 관련 질문은 챗봇이 일반 지식으로 안내합니다.

# 사적연금(연금저축·IRP) 연간 합산 수령액이 이 금액을 초과하면 종합과세 대상이 됩니다.
# (소득세법 제20조의3, 2023년 세법개정으로 기준금액이 1,200만 원에서 1,500만 원으로 상향)
# 이 경우 다른 종합소득과 합산해 누진세율을 적용하거나, 16.5%(국세 15%+지방세 10%)
# 분리과세를 선택할 수 있습니다. 본 로직은 MVP 단순화를 위해 "선택 가능한 분리과세율"을
# 하한으로 반영하여, 원천징수 나이 구간 세율(3~5%)만으로 과소 추정되지 않도록 합니다.
PRIVATE_PENSION_COMPREHENSIVE_THRESHOLD = 15_000_000
PRIVATE_PENSION_SEPARATE_TAX_RATE = D("0.15")

# 연금 수령 시점 추천(NPV 비교)에 사용하는 기본 할인율.
# 사적연금 원천징수세율은 나이가 많을수록 단조 감소(5%→4%→3%)하기 때문에, 세금만 비교하면
# 항상 최대 나이가 추천되는 구조적 왜곡이 생깁니다. 수령을 미루는 동안 돈을 늦게 받는
# 기회비용을 이 할인율로 반영해 이 왜곡을 바로잡습니다.
PENSION_START_DEFAULT_DISCOUNT_RATE = D("0.03")


@dataclass(frozen=True)
class TaxBand:
    """종합소득세 과세표준 구간."""

    min_exclusive: int
    max_inclusive: int
    rate: Decimal
    quick_deduction: int


# 2023~2025년 귀속 종합소득세율표 기준. 지방소득세 미포함.
COMPREHENSIVE_TAX_BANDS: tuple[TaxBand, ...] = (
    TaxBand(0, 14_000_000, D("0.06"), 0),
    TaxBand(14_000_000, 50_000_000, D("0.15"), 1_260_000),
    TaxBand(50_000_000, 88_000_000, D("0.24"), 5_760_000),
    TaxBand(88_000_000, 150_000_000, D("0.35"), 15_440_000),
    TaxBand(150_000_000, 300_000_000, D("0.38"), 19_940_000),
    TaxBand(300_000_000, 500_000_000, D("0.40"), 25_940_000),
    TaxBand(500_000_000, 1_000_000_000, D("0.42"), 35_940_000),
    TaxBand(1_000_000_000, 10**18, D("0.45"), 65_940_000),
)


# -----------------------------------------------------------------------------
# 2. 입력 DTO
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class FinancialIncomeTaxRequest:
    """금융소득종합과세 진단 입력 DTO."""

    interest_income: int
    dividend_income: int
    other_tax_base: int


@dataclass(frozen=True)
class ProductShiftRequest:
    """금융소득을 낮추기 위한 상품 이동 금액 계산 입력 DTO."""

    financial_income: int
    annual_yield_rate: Decimal = D("0.04")


@dataclass(frozen=True)
class PensionCompareRequest:
    """연금 일시금 vs 분할 수령 세액 비교 입력 DTO."""

    start_age: int
    pension_amount: int
    split_years: int = 10
    lifetime_annuity_contract: bool = False
    tax_year: int = 2026


@dataclass(frozen=True)
class PensionStartRecommendationRequest:
    """연금 수령 시작 시점 추천 입력 DTO."""

    current_age: int
    max_start_age: int
    pension_amount: int
    split_years: int = 10
    lifetime_annuity_contract: bool = False
    tax_year: int = 2026
    # 수령 지연에 따른 화폐의 시간가치(기회비용)를 반영하는 연간 할인율.
    discount_rate: Decimal = PENSION_START_DEFAULT_DISCOUNT_RATE


@dataclass(frozen=True)
class LimitUsageGuideRequest:
    """ISA·연금저축·IRP 절세 한도 활용률 입력 DTO."""

    isa_paid_this_year: int
    isa_total_paid: int
    pension_savings_paid_this_year: int
    irp_paid_this_year: int
    gross_salary: int


@dataclass(frozen=True)
class DiagnosisRequest:
    """UI 한 페이지 입력값을 한 번에 받는 통합 진단 입력 DTO."""

    age: int
    retirement_age: int
    total_income: int
    interest_income: int
    dividend_income: int

    # 0이면 total_income을 단순 과세표준으로 사용
    other_tax_base: int = 0
    annual_yield_rate: Decimal = D("0.04")

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
    pension_start_discount_rate: Decimal = PENSION_START_DEFAULT_DISCOUNT_RATE

    # 국민연금 수급개시연령은 age/retirement_age(사적연금 수령 시점)와는 별개로 출생연도로 고정되어
    # 계산됩니다. birth_year를 안 주면 tax_year - age로 추정합니다.
    birth_year: Optional[int] = None


# -----------------------------------------------------------------------------
# 3. 결과 DTO
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class FinancialIncomeTaxResponse:
    financial_income: int
    is_subject_to_comprehensive_tax: bool
    excess_amount: int
    basic_national_tax: int
    compare_national_tax: int
    final_national_tax: int
    additional_national_tax: int
    additional_local_tax: int
    additional_total_tax: int
    message: str


@dataclass(frozen=True)
class ProductShiftResponse:
    income_to_reduce: int
    annual_yield_rate: Decimal
    suggested_transfer_amount: int
    recommendation: str


@dataclass(frozen=True)
class AnnualPensionTaxResponse:
    year: int
    age: int
    annual_amount: int
    national_tax_rate: Decimal
    national_tax: int
    local_tax: int
    total_tax: int
    cumulative_tax: int
    # 해당 연도 수령액이 사적연금 종합과세 판단 기준(연 1,500만 원)을 초과하는지 여부
    exceeds_comprehensive_threshold: bool = False


@dataclass(frozen=True)
class PensionCompareResponse:
    start_age: int
    pension_amount: int
    split_years: int
    lifetime_annuity_contract: bool
    tax_year: int
    rate_note: str
    lump_national_tax: int
    lump_local_tax: int
    lump_total_tax: int
    split_national_tax: int
    split_local_tax: int
    split_total_tax: int
    saving_by_split: int
    annual_taxes: list[AnnualPensionTaxResponse]
    message: str
    # 분할 수령 기간 중 한 해라도 종합과세 판단 기준(연 1,500만 원)을 초과하는지 여부
    any_year_exceeds_threshold: bool = False


@dataclass(frozen=True)
class PensionStartRecommendationResponse:
    recommended_start_age: int
    expected_split_total_tax: int
    reason: str
    # 추천 시작 나이 기준, 할인율을 반영한 세후 수령액의 현재가치(NPV)
    expected_npv_after_tax_income: int = 0


@dataclass(frozen=True)
class PublicPensionStartAgeResponse:
    """개인이 선택할 수 없고 규정으로 고정된 연금 수급개시연령. 지금은 국민연금에만 씁니다.
    pension_type/basis_label을 문자열로 열어둔 건, 나중에 공무원연금처럼 기준(퇴직연도 등)이
    다른 연금이 추가돼도 이 구조를 그대로 재사용할 수 있게 하기 위해서입니다."""

    pension_type: str  # 예: "국민연금"
    basis_label: str  # 예: "출생연도"
    basis_year: int
    start_age: int
    note: str


@dataclass(frozen=True)
class LimitUsageGuideResponse:
    isa_paid_this_year: int
    isa_annual_limit: int
    isa_annual_usage_rate: Decimal
    isa_total_paid: int
    isa_total_limit: int
    isa_total_usage_rate: Decimal
    pension_savings_paid_this_year: int
    pension_savings_tax_credit_limit: int
    pension_savings_usage_rate: Decimal
    combined_pension_paid: int
    pension_irp_combined_tax_credit_limit: int
    pension_irp_combined_usage_rate: Decimal
    combined_credit_base: int
    tax_credit_rate_with_local: Decimal
    estimated_tax_credit: int
    message: str


@dataclass(frozen=True)
class ScenarioComparisonItem:
    scenario_name: str
    estimated_tax: int
    saving_amount: int
    saving_rate: Decimal
    description: str


@dataclass(frozen=True)
class DiagnosisResponse:
    financial_income_tax: FinancialIncomeTaxResponse
    product_shift: ProductShiftResponse
    pension_compare: PensionCompareResponse
    pension_start_recommendation: Optional[PensionStartRecommendationResponse]
    national_pension_start_age: PublicPensionStartAgeResponse
    limit_usage: LimitUsageGuideResponse
    recommendations: list[str]
    scenario_comparison: list[ScenarioComparisonItem]
    report_summary: str
    disclaimer: str = (
        "본 결과는 입력값 기반의 예상 계산이며 실제 세액은 공제·감면·상품 조건 등에 따라 달라질 수 있습니다."
    )


# -----------------------------------------------------------------------------
# 4. 공통 유틸 함수
# -----------------------------------------------------------------------------

def _validate_non_negative(value: int, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _validate_positive(value: int, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _money_mul(amount: int, rate: Decimal) -> int:
    """원 단위 반올림."""
    return int((D(amount) * rate).quantize(D("1"), rounding=ROUND_HALF_UP))


def _ratio(used: int, limit: int) -> Decimal:
    if limit <= 0:
        return D("0")
    return (D(used) / D(limit)).quantize(D("0.0001"), rounding=ROUND_HALF_UP)


def _saving_rate(saving_amount: int, base_tax: int) -> Decimal:
    if base_tax <= 0:
        return D("0")
    return (D(saving_amount) / D(base_tax)).quantize(D("0.0001"), rounding=ROUND_HALF_UP)


def _percent_text(ratio: Decimal) -> str:
    return str((ratio * D("100")).quantize(D("0.1"), rounding=ROUND_HALF_UP))


# -----------------------------------------------------------------------------
# 5. 계산 로직 1: 금융소득종합과세 진단
# -----------------------------------------------------------------------------

def calculate_comprehensive_income_tax(tax_base: int) -> int:
    """종합소득세 산출세액 계산.

    산식: 과세표준 × 세율 - 누진공제
    지방소득세는 별도입니다.
    """
    _validate_non_negative(tax_base, "tax_base")

    for band in COMPREHENSIVE_TAX_BANDS:
        if tax_base <= band.max_inclusive:
            tax = _money_mul(tax_base, band.rate) - band.quick_deduction
            return max(tax, 0)

    raise RuntimeError("No tax band found")


def diagnose_financial_income_tax(request: FinancialIncomeTaxRequest) -> FinancialIncomeTaxResponse:
    """금융소득종합과세 진단.

    1. 이자소득 + 배당소득이 2,000만 원을 초과하는지 판단합니다.
    2. 초과하면 기본계산과 비교계산을 모두 계산합니다.
    3. 둘 중 큰 금액을 최종 산출세액으로 사용합니다.
    """
    interest_income = request.interest_income
    dividend_income = request.dividend_income
    other_tax_base = request.other_tax_base

    _validate_non_negative(interest_income, "interest_income")
    _validate_non_negative(dividend_income, "dividend_income")
    _validate_non_negative(other_tax_base, "other_tax_base")

    financial_income = interest_income + dividend_income
    subject = financial_income > FINANCIAL_INCOME_THRESHOLD

    withholding_national_tax = _money_mul(financial_income, FINANCIAL_WITHHOLDING_RATE)
    other_income_national_tax = calculate_comprehensive_income_tax(other_tax_base)
    compare_national_tax = withholding_national_tax + other_income_national_tax

    if not subject:
        return FinancialIncomeTaxResponse(
            financial_income=financial_income,
            is_subject_to_comprehensive_tax=False,
            excess_amount=0,
            basic_national_tax=0,
            compare_national_tax=compare_national_tax,
            final_national_tax=compare_national_tax,
            additional_national_tax=0,
            additional_local_tax=0,
            additional_total_tax=0,
            message="금융소득이 2,000만 원 이하이므로 금융소득종합과세 대상이 아닙니다.",
        )

    excess = financial_income - FINANCIAL_INCOME_THRESHOLD
    threshold_tax = _money_mul(FINANCIAL_INCOME_THRESHOLD, FINANCIAL_WITHHOLDING_RATE)

    # 기본계산: 2천만 원까지는 14%, 초과분은 다른 종합소득과 합산하여 누진세율 적용
    basic_national_tax = threshold_tax + calculate_comprehensive_income_tax(other_tax_base + excess)

    # 비교계산: 전체 금융소득 14% + 다른 종합소득만 누진세율 적용
    final_national_tax = max(basic_national_tax, compare_national_tax)
    additional_national_tax = max(0, final_national_tax - compare_national_tax)
    additional_local_tax = _money_mul(additional_national_tax, LOCAL_INCOME_TAX_RATE)
    additional_total_tax = additional_national_tax + additional_local_tax

    return FinancialIncomeTaxResponse(
        financial_income=financial_income,
        is_subject_to_comprehensive_tax=True,
        excess_amount=excess,
        basic_national_tax=basic_national_tax,
        compare_national_tax=compare_national_tax,
        final_national_tax=final_national_tax,
        additional_national_tax=additional_national_tax,
        additional_local_tax=additional_local_tax,
        additional_total_tax=additional_total_tax,
        message=(
            f"금융소득이 2,000만 원을 {excess:,}원 초과했습니다. "
            f"비교과세 결과 예상 추가세액은 약 {additional_total_tax:,}원입니다."
        ),
    )


# -----------------------------------------------------------------------------
# 6. 계산 로직 2: 금융상품 이동 금액 계산
# -----------------------------------------------------------------------------

def calculate_product_shift_guide(request: ProductShiftRequest) -> ProductShiftResponse:
    """금융소득 2,000만 원 초과분을 줄이기 위한 일반 과세 상품 이동 금액 계산.

    예: 줄여야 하는 금융소득 400만 원, 연 수익률 4%라면
    4,000,000 ÷ 0.04 = 100,000,000원 이동 필요.
    """
    financial_income = request.financial_income
    annual_yield_rate = D(str(request.annual_yield_rate))

    _validate_non_negative(financial_income, "financial_income")
    if annual_yield_rate <= 0:
        raise ValueError("annual_yield_rate must be positive")

    income_to_reduce = max(0, financial_income - FINANCIAL_INCOME_THRESHOLD)

    if income_to_reduce == 0:
        suggested_transfer_amount = 0
    else:
        suggested_transfer_amount = int(
            (D(income_to_reduce) / annual_yield_rate).quantize(D("1"), rounding=ROUND_CEILING)
        )

    recommendation = (
        "금융소득이 기준 이하이므로 종합과세 회피 목적의 상품 이동은 필수는 아닙니다."
        if income_to_reduce == 0
        else "일반 과세 상품 일부를 ISA, 연금저축, IRP, 비과세·분리과세 상품으로 분산하는 방안을 검토하세요."
    )

    return ProductShiftResponse(
        income_to_reduce=income_to_reduce,
        annual_yield_rate=annual_yield_rate,
        suggested_transfer_amount=suggested_transfer_amount,
        recommendation=recommendation,
    )


# -----------------------------------------------------------------------------
# 7. 계산 로직 3: 연금 일시금 vs 분할 수령 세액 비교
# -----------------------------------------------------------------------------

def get_private_pension_national_rate(
    age: int,
    lifetime_annuity_contract: bool = False,
    tax_year: int = 2026,
) -> Decimal:
    """국세청 기준 사적연금 연금수령 원천징수세율.

    일반 사적연금
    - 70세 미만: 5%
    - 70세 이상 80세 미만: 4%
    - 80세 이상: 3%

    종신계약 연금
    - 2026.1.1 이후 수령분: 3%
    - 2025년 이전 수령분: 4%

    지방소득세 10%는 이 함수가 아니라 세금 계산 단계에서 별도로 더합니다.

    주의: 이 세율은 "원천징수" 단계의 세율입니다. 연간 사적연금 수령액이
    PRIVATE_PENSION_COMPREHENSIVE_THRESHOLD(1,500만 원)를 초과하면 종합과세
    대상이 되어 실제 부담 세율이 이 표보다 높아질 수 있습니다. 해당 판단은
    compare_pension_withdrawal에서 별도로 반영합니다.
    """
    _validate_non_negative(age, "age")

    if age < 70:
        age_rate = D("0.05")
    elif age < 80:
        age_rate = D("0.04")
    else:
        age_rate = D("0.03")

    if lifetime_annuity_contract:
        lifetime_rate = D("0.03") if tax_year >= 2026 else D("0.04")
        return min(age_rate, lifetime_rate)

    return age_rate


def get_private_pension_rate_note(tax_year: int = 2026) -> str:
    if tax_year >= 2026:
        return (
            "국세청 기준: 일반 사적연금 70세 미만 5%, 70~79세 4%, 80세 이상 3%. "
            "종신계약 연금은 2026.1.1 이후 3% 적용. "
            "단, 연간 사적연금 수령액이 1,500만 원을 초과하면 종합과세 대상이 되며, "
            "16.5%(국세 15%+지방세 10%) 분리과세를 선택할 수 있습니다."
        )
    return (
        "국세청 종전 기준: 일반 사적연금 70세 미만 5%, 70~79세 4%, 80세 이상 3%. "
        "종신계약 연금은 2025년 이전 4% 적용. "
        "단, 연간 사적연금 수령액이 1,500만 원을 초과하면 종합과세 대상이 되며, "
        "16.5%(국세 15%+지방세 10%) 분리과세를 선택할 수 있습니다."
    )


def compare_pension_withdrawal(request: PensionCompareRequest) -> PensionCompareResponse:
    """연금 일시금/연금외수령과 분할 연금수령 세금 비교."""
    start_age = request.start_age
    pension_amount = request.pension_amount
    split_years = request.split_years
    lifetime_annuity_contract = request.lifetime_annuity_contract
    tax_year = request.tax_year

    _validate_non_negative(start_age, "start_age")
    _validate_non_negative(pension_amount, "pension_amount")
    _validate_positive(split_years, "split_years")

    # 일시금/연금외수령: 15% + 지방소득세 10%
    lump_national_tax = _money_mul(pension_amount, PENSION_LUMP_SUM_RATE)
    lump_local_tax = _money_mul(lump_national_tax, LOCAL_INCOME_TAX_RATE)
    lump_total_tax = lump_national_tax + lump_local_tax

    # 분할 연금수령: 매년 수령 나이에 따른 사적연금 세율 적용 + 지방소득세 10%
    # 단, 해당 연도 수령액이 종합과세 판단 기준(1,500만 원)을 초과하면 원천징수 나이 구간
    # 세율 대신 선택 가능한 분리과세율(15%)을 하한으로 적용해 세부담을 과소 추정하지 않습니다.
    annual_base = pension_amount // split_years
    remainder = pension_amount % split_years

    annual_taxes: list[AnnualPensionTaxResponse] = []
    split_national_tax = 0
    split_local_tax = 0
    cumulative_tax = 0
    any_year_exceeds_threshold = False

    for i in range(split_years):
        age = start_age + i
        annual_amount = annual_base + (remainder if i == split_years - 1 else 0)

        exceeds_threshold = annual_amount > PRIVATE_PENSION_COMPREHENSIVE_THRESHOLD
        age_rate = get_private_pension_national_rate(age, lifetime_annuity_contract, tax_year)
        rate = max(age_rate, PRIVATE_PENSION_SEPARATE_TAX_RATE) if exceeds_threshold else age_rate
        if exceeds_threshold:
            any_year_exceeds_threshold = True

        national_tax = _money_mul(annual_amount, rate)
        local_tax = _money_mul(national_tax, LOCAL_INCOME_TAX_RATE)
        total_tax = national_tax + local_tax
        cumulative_tax += total_tax

        annual_taxes.append(
            AnnualPensionTaxResponse(
                year=i + 1,
                age=age,
                annual_amount=annual_amount,
                national_tax_rate=rate,
                national_tax=national_tax,
                local_tax=local_tax,
                total_tax=total_tax,
                cumulative_tax=cumulative_tax,
                exceeds_comprehensive_threshold=exceeds_threshold,
            )
        )

        split_national_tax += national_tax
        split_local_tax += local_tax

    split_total_tax = split_national_tax + split_local_tax
    saving_by_split = lump_total_tax - split_total_tax

    message = (
        f"{start_age}세부터 {pension_amount:,}원을 {split_years}년간 나누어 받으면 "
        f"일시금 대비 약 {saving_by_split:,}원의 세금 차이가 발생합니다."
    )
    if any_year_exceeds_threshold:
        message += (
            " 단, 연간 수령액이 1,500만 원을 초과하는 해에는 종합과세 대상이 되어 "
            "16.5% 분리과세(또는 다른 소득 합산 누진세율) 기준으로 세금을 다시 계산했습니다."
        )

    return PensionCompareResponse(
        start_age=start_age,
        pension_amount=pension_amount,
        split_years=split_years,
        lifetime_annuity_contract=lifetime_annuity_contract,
        tax_year=tax_year,
        rate_note=get_private_pension_rate_note(tax_year),
        lump_national_tax=lump_national_tax,
        lump_local_tax=lump_local_tax,
        lump_total_tax=lump_total_tax,
        split_national_tax=split_national_tax,
        split_local_tax=split_local_tax,
        split_total_tax=split_total_tax,
        saving_by_split=saving_by_split,
        annual_taxes=annual_taxes,
        message=message,
        any_year_exceeds_threshold=any_year_exceeds_threshold,
    )


# -----------------------------------------------------------------------------
# 7.5. 계산 로직 3.5: 국민연금 수급개시연령 (개인 선택 불가, 출생연도로 고정)
# -----------------------------------------------------------------------------
#
# 위 recommend_pension_start_age()/compare_pension_withdrawal()는 개인연금·IRP 같은
# "사적연금"에만 해당합니다. 사적연금은 55세 이후 본인이 수령 시점을 고를 수 있어서
# 세율 비교로 "추천"이 성립하지만, 국민연금은 출생연도로 수급개시연령이 고정되어 있어
# 개인이 선택할 수 없습니다. 그래서 "추천"이 아니라 "계산된 고정값 안내"로 다룹니다.
# (공무원연금은 국민연금과 산정 기준 자체가 달라 이 앱의 계산 대상에는 포함하지 않고,
# 관련 질문은 챗봇이 일반 지식으로 안내합니다.)

def get_national_pension_start_age(birth_year: int) -> int:
    """국민연금 노령연금 수급개시연령 계산 (출생연도 기준, 개인 선택 불가)."""
    _validate_non_negative(birth_year, "birth_year")

    for start, end, age in NATIONAL_PENSION_START_AGE_BY_BIRTH_YEAR:
        if start <= birth_year <= end:
            return age

    raise ValueError("birth_year out of supported range")


def build_national_pension_start_age_info(birth_year: int) -> PublicPensionStartAgeResponse:
    start_age = get_national_pension_start_age(birth_year)
    return PublicPensionStartAgeResponse(
        pension_type="국민연금",
        basis_label="출생연도",
        basis_year=birth_year,
        start_age=start_age,
        note=(
            f"{birth_year}년생은 국민연금 노령연금을 {start_age}세부터 받을 수 있습니다. "
            "이 나이는 출생연도로 고정되어 있어 개인연금·IRP처럼 본인이 시점을 고를 수 없습니다. "
            "조기노령연금 제도로 최대 5년 앞당길 수는 있지만, 그만큼 연금액이 감액됩니다."
        ),
    )


# -----------------------------------------------------------------------------
# 8. 계산 로직 4: 연금 수령 시작 시점 추천
# -----------------------------------------------------------------------------

def recommend_pension_start_age(request: PensionStartRecommendationRequest) -> PensionStartRecommendationResponse:
    """시작 나이별 세후 수령액의 현재가치(NPV)를 비교해 가장 유리한 시작 나이를 추천.

    이전 로직의 구조적 문제:
    사적연금 원천징수세율은 나이가 많을수록 단조 감소(5%→4%→3%)하기 때문에,
    "총 세금이 가장 적은 나이"만 비교하면 항상 max_start_age(입력 가능한 최대 나이)가
    선택되는 왜곡이 발생했습니다. 이는 수령을 늦추는 동안 돈을 받지 못하는 기회비용을
    전혀 반영하지 않았기 때문입니다.

    개선된 로직:
    각 시작 나이 후보에 대해 "세후 수령액"을 계산한 뒤, discount_rate(연간 할인율)로
    현재 시점(current_age) 기준 현재가치(NPV)로 환산해 비교합니다. 수령을 늦출수록
    세금은 줄어들지만 현금 흐름 자체가 뒤로 밀려 NPV가 할인되므로, 세금 절감 효과와
    지연에 따른 기회비용이 함께 반영된 균형 잡힌 추천이 가능합니다.
    """
    _validate_non_negative(request.current_age, "current_age")
    _validate_non_negative(request.max_start_age, "max_start_age")
    _validate_non_negative(request.pension_amount, "pension_amount")
    _validate_positive(request.split_years, "split_years")

    if request.current_age > request.max_start_age:
        raise ValueError("current_age must be <= max_start_age")

    discount_rate = D(str(request.discount_rate))
    if discount_rate < 0:
        raise ValueError("discount_rate must be non-negative")

    best_result: PensionCompareResponse | None = None
    best_npv: Decimal | None = None
    best_deferral_years = 0

    for start_age in range(request.current_age, request.max_start_age + 1):
        result = compare_pension_withdrawal(
            PensionCompareRequest(
                start_age=start_age,
                pension_amount=request.pension_amount,
                split_years=request.split_years,
                lifetime_annuity_contract=request.lifetime_annuity_contract,
                tax_year=request.tax_year,
            )
        )

        deferral_years = start_age - request.current_age
        npv = D("0")
        for i, annual_tax in enumerate(result.annual_taxes):
            years_from_now = deferral_years + i
            net_amount = annual_tax.annual_amount - annual_tax.total_tax
            discount_factor = (D("1") + discount_rate) ** years_from_now
            npv += D(net_amount) / discount_factor

        if best_npv is None or npv > best_npv:
            best_npv = npv
            best_result = result
            best_deferral_years = deferral_years

    assert best_result is not None and best_npv is not None

    npv_rounded = int(best_npv.quantize(D("1"), rounding=ROUND_HALF_UP))

    if best_deferral_years == 0:
        timing_note = (
            "세금 절감 효과보다 수령 지연에 따른 기회비용이 더 커서, "
            "가능한 가장 이른 나이부터 수령을 시작하는 편이 유리합니다."
        )
    else:
        timing_note = (
            f"{best_deferral_years}년을 미뤄 {best_result.start_age}세부터 수령을 시작하면, "
            "나이 구간별 세율 하락에 따른 절세 효과가 지연에 따른 기회비용보다 커서 유리합니다."
        )

    reason = (
        f"[개인연금·IRP 등 사적연금 기준] 연 할인율 {_percent_text(discount_rate)}%를 가정하고 "
        f"{request.pension_amount:,}원을 {request.split_years}년간 나누어 받을 때, "
        f"{best_result.start_age}세부터 시작하는 경우의 세후 수령액 현재가치(NPV)가 약 "
        f"{npv_rounded:,}원으로 가장 큽니다. {timing_note} 이 추천은 세금과 화폐의 시간가치만 "
        "반영한 것으로, 실제 의사결정에는 필요한 생활비, 건강 상태, 다른 소득과의 종합과세 여부를 "
        "함께 고려해야 합니다. 국민연금·공무원연금은 이 계산과 무관하게 출생연도/퇴직연도로 "
        "수급개시연령이 고정되어 있어 이 추천이 적용되지 않습니다."
    )

    return PensionStartRecommendationResponse(
        recommended_start_age=best_result.start_age,
        expected_split_total_tax=best_result.split_total_tax,
        reason=reason,
        expected_npv_after_tax_income=npv_rounded,
    )


# -----------------------------------------------------------------------------
# 9. 계산 로직 5: ISA·연금저축·IRP 한도 활용률 계산
# -----------------------------------------------------------------------------

def calculate_limit_usage_guide(request: LimitUsageGuideRequest) -> LimitUsageGuideResponse:
    """ISA·연금저축·IRP 절세 한도 활용률과 예상 세액공제액 계산."""
    for name, value in {
        "isa_paid_this_year": request.isa_paid_this_year,
        "isa_total_paid": request.isa_total_paid,
        "pension_savings_paid_this_year": request.pension_savings_paid_this_year,
        "irp_paid_this_year": request.irp_paid_this_year,
        "gross_salary": request.gross_salary,
    }.items():
        _validate_non_negative(value, name)

    combined_pension_paid = request.pension_savings_paid_this_year + request.irp_paid_this_year

    # 연금저축은 600만 원까지만 별도 표시, IRP 포함 전체 연금계좌 세액공제 한도는 900만 원으로 단순화
    pension_savings_credit_base = min(
        request.pension_savings_paid_this_year,
        PENSION_SAVINGS_TAX_CREDIT_LIMIT,
    )
    combined_credit_base = min(
        combined_pension_paid,
        PENSION_IRP_COMBINED_TAX_CREDIT_LIMIT,
    )

    # 총급여 5,500만 원 이하 16.5%, 초과 13.2%로 단순화. 지방소득세 포함 세액공제율.
    tax_credit_rate_with_local = D("0.165") if request.gross_salary <= 55_000_000 else D("0.132")
    estimated_tax_credit = _money_mul(combined_credit_base, tax_credit_rate_with_local)

    isa_annual_usage_rate = _ratio(request.isa_paid_this_year, ISA_GENERAL_ANNUAL_LIMIT)
    isa_total_usage_rate = _ratio(request.isa_total_paid, ISA_GENERAL_TOTAL_LIMIT)
    pension_savings_usage_rate = _ratio(pension_savings_credit_base, PENSION_SAVINGS_TAX_CREDIT_LIMIT)
    pension_irp_combined_usage_rate = _ratio(combined_credit_base, PENSION_IRP_COMBINED_TAX_CREDIT_LIMIT)

    message = (
        f"ISA 연간 한도 활용률은 {_percent_text(isa_annual_usage_rate)}%, "
        f"연금저축+IRP 세액공제 한도 활용률은 {_percent_text(pension_irp_combined_usage_rate)}%입니다. "
        f"예상 세액공제액은 약 {estimated_tax_credit:,}원입니다."
    )

    return LimitUsageGuideResponse(
        isa_paid_this_year=request.isa_paid_this_year,
        isa_annual_limit=ISA_GENERAL_ANNUAL_LIMIT,
        isa_annual_usage_rate=isa_annual_usage_rate,
        isa_total_paid=request.isa_total_paid,
        isa_total_limit=ISA_GENERAL_TOTAL_LIMIT,
        isa_total_usage_rate=isa_total_usage_rate,
        pension_savings_paid_this_year=request.pension_savings_paid_this_year,
        pension_savings_tax_credit_limit=PENSION_SAVINGS_TAX_CREDIT_LIMIT,
        pension_savings_usage_rate=pension_savings_usage_rate,
        combined_pension_paid=combined_pension_paid,
        pension_irp_combined_tax_credit_limit=PENSION_IRP_COMBINED_TAX_CREDIT_LIMIT,
        pension_irp_combined_usage_rate=pension_irp_combined_usage_rate,
        combined_credit_base=combined_credit_base,
        tax_credit_rate_with_local=tax_credit_rate_with_local,
        estimated_tax_credit=estimated_tax_credit,
        message=message,
    )


# -----------------------------------------------------------------------------
# 10. 계산 로직 6: UI 그래프용 시나리오 비교 + 통합 진단
# -----------------------------------------------------------------------------

def _build_recommendations(
    *,
    financial_income: int,
    excess_amount: int,
    product_transfer_amount: int,
    saving_by_split: int,
    estimated_tax_credit: int,
    pension_start_reason: Optional[str],
    national_pension_note: Optional[str] = None,
) -> list[str]:
    """계산 결과 기반 추천 문구 생성. AI가 아니라 규칙 기반 추천입니다."""
    recommendations: list[str] = []

    if national_pension_note:
        recommendations.append(national_pension_note)

    if financial_income > FINANCIAL_INCOME_THRESHOLD:
        recommendations.append(
            f"금융소득이 기준을 {excess_amount:,}원 초과했습니다. 일반 과세 금융상품 일부를 ISA·연금저축·IRP 등 절세 계좌로 분산해 금융소득을 낮춰보세요."
        )
        if product_transfer_amount > 0:
            recommendations.append(
                f"예상 수익률 기준으로 약 {product_transfer_amount:,}원 정도를 일반 과세 상품에서 절세 상품으로 옮기면 초과 금융소득을 줄이는 데 도움이 됩니다."
            )
    else:
        recommendations.append("금융소득은 현재 2,000만 원 이하로, 금융소득종합과세 위험은 낮은 편입니다.")

    if saving_by_split > 0:
        recommendations.append(
            f"연금은 일시금보다 분할 수령 시 약 {saving_by_split:,}원 정도 세금 부담이 낮을 수 있습니다."
        )
    elif saving_by_split < 0:
        recommendations.append(
            "입력 조건에서는 분할 수령이 항상 유리하게 나오지는 않습니다. 생활비 필요성과 수령 조건을 함께 확인하세요."
        )

    if estimated_tax_credit > 0:
        recommendations.append(
            f"연금저축·IRP 납입액 기준 예상 세액공제액은 약 {estimated_tax_credit:,}원입니다. 남은 한도 활용 여부를 점검해보세요."
        )

    if pension_start_reason:
        recommendations.append(pension_start_reason)

    # 국민연금 안내 문구를 새로 맨 앞에 추가하면서 기존 5개 제한에 걸려 마지막 항목(개인연금·IRP
    # 시작나이 추천)이 잘려나가던 문제가 있어, 국민연금 항목 1개만큼 한도를 늘렸습니다.
    return recommendations[:6]


def diagnose(request: DiagnosisRequest) -> DiagnosisResponse:
    """절세지킴이 통합 진단 실행.

    UI에서 한 번에 받은 입력값을 계산 로직에 연결하고,
    결과 카드/추천사항/시나리오 그래프에 필요한 데이터를 만들어 반환합니다.
    """
    for name, value in {
        "age": request.age,
        "retirement_age": request.retirement_age,
        "total_income": request.total_income,
        "interest_income": request.interest_income,
        "dividend_income": request.dividend_income,
        "other_tax_base": request.other_tax_base,
        "pension_savings_balance": request.pension_savings_balance,
        "irp_balance": request.irp_balance,
        "expected_pension_amount": request.expected_pension_amount,
        "isa_paid_this_year": request.isa_paid_this_year,
        "isa_total_paid": request.isa_total_paid,
        "pension_savings_paid_this_year": request.pension_savings_paid_this_year,
        "irp_paid_this_year": request.irp_paid_this_year,
        "max_pension_start_age": request.max_pension_start_age,
    }.items():
        _validate_non_negative(value, name)

    if request.birth_year is not None:
        _validate_non_negative(request.birth_year, "birth_year")

    if request.retirement_age < request.age:
        raise ValueError("retirement_age must be greater than or equal to age")
    if request.pension_split_years <= 0:
        raise ValueError("pension_split_years must be positive")
    if request.annual_yield_rate <= 0:
        raise ValueError("annual_yield_rate must be positive")

    other_tax_base = request.other_tax_base if request.other_tax_base > 0 else request.total_income

    financial_income_result = diagnose_financial_income_tax(
        FinancialIncomeTaxRequest(
            interest_income=request.interest_income,
            dividend_income=request.dividend_income,
            other_tax_base=other_tax_base,
        )
    )

    product_shift = calculate_product_shift_guide(
        ProductShiftRequest(
            financial_income=financial_income_result.financial_income,
            annual_yield_rate=request.annual_yield_rate,
        )
    )

    pension_amount = request.expected_pension_amount or (request.pension_savings_balance + request.irp_balance)

    pension_compare = compare_pension_withdrawal(
        PensionCompareRequest(
            start_age=request.retirement_age,
            pension_amount=pension_amount,
            split_years=request.pension_split_years,
            lifetime_annuity_contract=request.lifetime_annuity_contract,
            tax_year=request.tax_year,
        )
    )

    pension_start_recommendation = None
    if request.recommend_pension_start:
        max_age = max(request.max_pension_start_age, request.retirement_age)
        pension_start_recommendation = recommend_pension_start_age(
            PensionStartRecommendationRequest(
                current_age=request.retirement_age,
                max_start_age=max_age,
                pension_amount=pension_amount,
                split_years=request.pension_split_years,
                lifetime_annuity_contract=request.lifetime_annuity_contract,
                tax_year=request.tax_year,
                discount_rate=request.pension_start_discount_rate,
            )
        )

    limit_usage = calculate_limit_usage_guide(
        LimitUsageGuideRequest(
            isa_paid_this_year=request.isa_paid_this_year,
            isa_total_paid=request.isa_total_paid,
            pension_savings_paid_this_year=request.pension_savings_paid_this_year,
            irp_paid_this_year=request.irp_paid_this_year,
            gross_salary=request.total_income,
        )
    )

    # 국민연금은 개인이 시점을 고를 수 없는, 출생연도로 고정된 값입니다.
    # birth_year를 별도로 안 받으면 tax_year - age로 근사합니다 (생월 미고려 MVP 근사치).
    birth_year = request.birth_year if request.birth_year is not None else (request.tax_year - request.age)
    national_pension_start_age = build_national_pension_start_age_info(birth_year)

    # 시나리오 비교: UI 그래프에 쓰기 위한 단순 시나리오.
    # A 현재 방식: 금융소득 추가세액 + 연금 일시금 세금
    current_tax = financial_income_result.additional_total_tax + pension_compare.lump_total_tax

    # B ISA 활용: 금융소득 초과분이 사라진다고 가정한 추가세액 + 연금 일시금 세금
    adjusted_financial_income = min(financial_income_result.financial_income, FINANCIAL_INCOME_THRESHOLD)
    adjusted_financial_result = diagnose_financial_income_tax(
        FinancialIncomeTaxRequest(
            interest_income=adjusted_financial_income,
            dividend_income=0,
            other_tax_base=other_tax_base,
        )
    )
    isa_scenario_tax = adjusted_financial_result.additional_total_tax + pension_compare.lump_total_tax

    # C 연금 분할 수령: ISA 활용 + 연금 분할 수령 세금
    split_scenario_tax = adjusted_financial_result.additional_total_tax + pension_compare.split_total_tax

    scenarios = [
        ScenarioComparisonItem(
            scenario_name="현재 방식",
            estimated_tax=current_tax,
            saving_amount=0,
            saving_rate=D("0"),
            description="현재 금융소득 구조와 연금 일시금 수령을 가정한 예상 세금입니다.",
        ),
        ScenarioComparisonItem(
            scenario_name="ISA 활용",
            estimated_tax=isa_scenario_tax,
            saving_amount=max(0, current_tax - isa_scenario_tax),
            saving_rate=_saving_rate(max(0, current_tax - isa_scenario_tax), current_tax),
            description="금융소득 2,000만 원 초과분을 절세 상품으로 분산한다고 가정한 시나리오입니다.",
        ),
        ScenarioComparisonItem(
            scenario_name="연금 분할 수령",
            estimated_tax=split_scenario_tax,
            saving_amount=max(0, current_tax - split_scenario_tax),
            saving_rate=_saving_rate(max(0, current_tax - split_scenario_tax), current_tax),
            description="ISA 활용과 함께 연금을 분할 수령한다고 가정한 시나리오입니다.",
        ),
    ]

    start_reason = pension_start_recommendation.reason if pension_start_recommendation else None
    recommendations = _build_recommendations(
        financial_income=financial_income_result.financial_income,
        excess_amount=financial_income_result.excess_amount,
        product_transfer_amount=product_shift.suggested_transfer_amount,
        saving_by_split=pension_compare.saving_by_split,
        estimated_tax_credit=limit_usage.estimated_tax_credit,
        pension_start_reason=start_reason,
        national_pension_note=national_pension_start_age.note,
    )

    best = min(scenarios, key=lambda item: item.estimated_tax)
    report_summary = (
        f"금융소득은 {financial_income_result.financial_income:,}원이며, "
        f"예상 추가세액은 {financial_income_result.additional_total_tax:,}원입니다. "
        f"연금 분할 수령 시 일시금 대비 {pension_compare.saving_by_split:,}원의 세금 차이가 예상됩니다. "
        f"시나리오 중 '{best.scenario_name}'의 예상 세금이 가장 낮습니다."
    )

    return DiagnosisResponse(
        financial_income_tax=financial_income_result,
        product_shift=product_shift,
        pension_compare=pension_compare,
        pension_start_recommendation=pension_start_recommendation,
        national_pension_start_age=national_pension_start_age,
        limit_usage=limit_usage,
        recommendations=recommendations,
        scenario_comparison=scenarios,
        report_summary=report_summary,
    )


# -----------------------------------------------------------------------------
# 11. 간단 실행 검증
# -----------------------------------------------------------------------------

def _print_money(label: str, value: int) -> None:
    print(f"{label}: {value:,}원")


def run_sample_validation() -> None:
    """대표 예시 숫자로 계산 로직이 동작하는지 확인."""
    print("\n[1] 금융소득종합과세 예시")
    financial = diagnose_financial_income_tax(
        FinancialIncomeTaxRequest(
            interest_income=18_000_000,
            dividend_income=6_000_000,
            other_tax_base=70_000_000,
        )
    )
    print(financial.message)
    _print_money("금융소득", financial.financial_income)
    _print_money("초과금액", financial.excess_amount)
    _print_money("예상 추가세액", financial.additional_total_tax)

    print("\n[2] 상품 이동 금액 예시")
    shift = calculate_product_shift_guide(
        ProductShiftRequest(financial_income=financial.financial_income, annual_yield_rate=D("0.04"))
    )
    _print_money("줄여야 할 금융소득", shift.income_to_reduce)
    _print_money("이동 필요 금액", shift.suggested_transfer_amount)

    print("\n[3] 연금 일시금 vs 분할 수령 예시")
    pension = compare_pension_withdrawal(
        PensionCompareRequest(start_age=65, pension_amount=30_000_000, split_years=10, tax_year=2026)
    )
    _print_money("일시금 세금", pension.lump_total_tax)
    _print_money("분할 수령 세금", pension.split_total_tax)
    _print_money("분할 수령 절세액", pension.saving_by_split)

    print("\n[4] 종신계약 연금 세율 확인")
    print("2025년 종신계약 65세 세율:", get_private_pension_national_rate(65, True, 2025))
    print("2026년 종신계약 65세 세율:", get_private_pension_national_rate(65, True, 2026))

    print("\n[5] 통합 진단 예시")
    diagnosis = diagnose(
        DiagnosisRequest(
            age=58,
            retirement_age=65,
            total_income=80_000_000,
            other_tax_base=70_000_000,
            interest_income=18_000_000,
            dividend_income=6_000_000,
            annual_yield_rate=D("0.04"),
            expected_pension_amount=30_000_000,
            pension_split_years=10,
            isa_paid_this_year=10_000_000,
            isa_total_paid=30_000_000,
            pension_savings_paid_this_year=4_000_000,
            irp_paid_this_year=2_000_000,
        )
    )
    print(diagnosis.report_summary)
    for item in diagnosis.scenario_comparison:
        print(f"- {item.scenario_name}: 예상 세금 {item.estimated_tax:,}원 / 절세액 {item.saving_amount:,}원")


if __name__ == "__main__":
    run_sample_validation()
