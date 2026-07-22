// 백엔드(taxguard_calculation_logic.py)가 던지는 ValueError는 영어 필드명이 그대로 섞여 있어서
// ("retirement_age must be greater than or equal to age") 사용자에게 그대로 보여주면 당황스럽습니다.
// 여기서 알려진 에러 메시지를 자연스러운 한국어 문장으로 바꿔주고, 모르는 에러는 필드명 노출 없이
// 일반적인 안내 문구로 대체합니다.

const FIELD_LABELS = {
  age: "현재 나이",
  retirement_age: "연금 수령 예정 나이",
  total_income: "연간 총급여·종합소득",
  interest_income: "이자소득",
  dividend_income: "배당소득",
  other_tax_base: "종합소득 과세표준",
  pension_savings_balance: "연금저축 잔액",
  irp_balance: "IRP 잔액",
  expected_pension_amount: "예상 연금 수령 총액",
  isa_paid_this_year: "ISA 올해 납입액",
  isa_total_paid: "ISA 누적 납입액",
  pension_savings_paid_this_year: "연금저축 올해 납입액",
  irp_paid_this_year: "IRP 올해 납입액",
  max_pension_start_age: "추천 탐색 최대 나이",
};

/**
 * 진단 API(/api/diagnosis)가 반환하는 에러 detail 문자열을 사용자 친화적인 한국어 문장으로 바꿉니다.
 * @param {string} detail - err.response?.data?.detail
 * @returns {string}
 */
export function friendlyDiagnosisError(detail) {
  if (!detail || typeof detail !== "string") {
    return "입력값을 다시 확인해주세요.";
  }

  const nonNegativeMatch = detail.match(/^(\w+) must be non-negative$/);
  if (nonNegativeMatch) {
    const label = FIELD_LABELS[nonNegativeMatch[1]] || nonNegativeMatch[1];
    return `"${label}" 값은 0 이상이어야 해요. 다시 확인해주세요.`;
  }

  if (detail === "retirement_age must be greater than or equal to age") {
    return "연금 수령 예정 나이는 현재 나이보다 같거나 커야 해요. 나이를 다시 확인해주세요.";
  }
  if (detail === "pension_split_years must be positive") {
    return "연금 분할 수령 기간은 1년 이상이어야 해요.";
  }
  if (detail === "annual_yield_rate must be positive") {
    return "보유 금융상품 예상 연 수익률은 0%보다 커야 해요.";
  }
  if (detail === "current_age must be <= max_start_age") {
    return "추천 탐색 최대 나이는 현재 나이보다 같거나 커야 해요.";
  }

  // 매핑에 없는 에러는 원문(영어 필드명 등)을 그대로 노출하지 않고 일반적인 안내로 대체합니다.
  return "입력값을 다시 확인해주세요. 문제가 계속되면 알려주세요.";
}
