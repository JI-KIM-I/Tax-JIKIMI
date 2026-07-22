// 챗봇 대화창에서 사용자가 자연어로 언급한 숫자(나이, 연금액, 소득 등)를 규칙 기반으로
// 추출해서 진단 폼과 같은 모양의 부분 객체로 변환합니다.
// LLM 없이 정규식만으로 동작하기 때문에 OpenAI 크레딧 상태와 무관하게 항상 동작합니다.
// 100% 정확하진 않아서, 추출 결과는 항상 사용자에게 확인받은 뒤 진단에 사용해야 합니다.

const UNIT_VALUES = {
  억: 1_0000_0000,
  천만: 1000_0000,
  백만: 100_0000,
  십만: 10_0000,
  만: 1_0000,
  원: 1,
};

// 알려진 단위(억, 천만, 백만, 십만, 만, 원) 앞의 숫자를 모두 찾아 합산합니다.
// 정규식이 왼쪽부터 겹치지 않게 소비하기 때문에 "1억 2천만원" 같은 복합 표현도 정확히 더해집니다.
function parseKoreanAmount(text) {
  const cleaned = text.replace(/,/g, "");
  const re = /(\d+(?:\.\d+)?)\s*(억|천만|백만|십만|만|원)/g;
  let match;
  let total = null;
  let sawNonWonUnit = false;
  while ((match = re.exec(cleaned))) {
    const value = parseFloat(match[1]);
    const unit = match[2];
    if (Number.isNaN(value)) continue;
    total = (total ?? 0) + value * UNIT_VALUES[unit];
    if (unit !== "원") sawNonWonUnit = true;
  }
  // "원"만 단독으로 잡힌 아주 작은 숫자(예: "3원")는 오탐일 가능성이 높으므로
  // 단위가 없는 순수 "숫자원" 표현은 1만원 이상일 때만 신뢰합니다.
  if (total !== null && !sawNonWonUnit && total < 10000) return null;
  return total;
}

// chunk(문장 일부) 안에서 금액 표현을 찾아 반환. 못 찾으면 null.
function findAmountNear(text, keywordRegex, windowSize = 20) {
  const m = keywordRegex.exec(text);
  if (!m) return null;
  const start = m.index;
  const windowText = text.slice(start, start + m[0].length + windowSize);
  return parseKoreanAmount(windowText);
}

// 나이 표현("68세", "68살")을 등장 순서대로 모두 추출.
function extractAges(text) {
  const re = /(\d{1,3})\s*(?:세|살)\b/g;
  const ages = [];
  let m;
  while ((m = re.exec(text))) {
    const age = parseInt(m[1], 10);
    if (age >= 19 && age <= 100) ages.push(age);
  }
  return ages;
}

/**
 * 사용자 메시지에서 진단에 쓸 수 있는 필드를 최대한 추출합니다.
 * @param {string} text 사용자가 입력한 문장
 * @returns {object} DiagnosisRequestBody와 겹치는 키만 담은 부분 객체 (없으면 {})
 */
export function extractProfileFromText(text) {
  if (!text) return {};
  const profile = {};

  const ages = extractAges(text);
  if (ages.length === 1) {
    // 나이가 하나만 언급되면 현재 나이로 간주
    profile.age = ages[0];
  } else if (ages.length >= 2) {
    // 두 개 이상이면 더 작은 값을 현재 나이, 더 큰 값을 연금 수령 나이로 추정
    const [a, b] = [ages[0], ages[1]].sort((x, y) => x - y);
    profile.age = a;
    profile.retirement_age = b;
  }

  // "연금 받는/타는/수령 나이" 명시적 표현이 있으면 우선 적용
  const startAgeMatch = /(?:연금).{0,10}(?:받|수령|타는|개시).{0,6}(\d{1,3})\s*(?:세|살)/.exec(text);
  if (startAgeMatch) {
    const v = parseInt(startAgeMatch[1], 10);
    if (v >= 19 && v <= 100) profile.retirement_age = v;
  }

  const financial = findAmountNear(text, /금융\s*소득/);
  if (financial !== null) {
    // 이자/배당 구분이 없으면 절반씩 나눠서 반영 (근사치)
    profile.interest_income = Math.round(financial / 2);
    profile.dividend_income = Math.round(financial / 2);
  }

  const interest = findAmountNear(text, /이자\s*소득/);
  if (interest !== null) profile.interest_income = Math.round(interest);

  const dividend = findAmountNear(text, /배당\s*소득/);
  if (dividend !== null) profile.dividend_income = Math.round(dividend);

  const pensionSavings = findAmountNear(text, /연금\s*저축/);
  if (pensionSavings !== null) profile.pension_savings_balance = Math.round(pensionSavings);

  const irp = findAmountNear(text, /IRP/i);
  if (irp !== null) profile.irp_balance = Math.round(irp);

  const isa = findAmountNear(text, /ISA/i);
  if (isa !== null) profile.isa_total_paid = Math.round(isa);

  // "연금"만 언급되고 위의 세부 계좌(연금저축/IRP) 키워드가 안 잡혔다면
  // 전체 예상 연금 수령액으로 취급
  if (
    profile.pension_savings_balance === undefined &&
    profile.irp_balance === undefined
  ) {
    const pensionTotal = findAmountNear(text, /연금(?:이|은|을|도)?\s*(?:이만큼|이정도|약)?/, 15);
    if (pensionTotal !== null) profile.expected_pension_amount = Math.round(pensionTotal);
  }

  const totalIncome = findAmountNear(text, /(?:연\s*소득|총\s*소득|총급여|연봉)/);
  if (totalIncome !== null) profile.total_income = Math.round(totalIncome);

  return profile;
}

// 진단에 필요한 최소 핵심 필드가 모였는지 확인 (나이 + 연금/소득 관련 정보 하나 이상)
export function hasEnoughForDiagnosis(profile) {
  if (!profile) return false;
  const hasAge = typeof profile.age === "number";
  const hasFinancialSignal =
    typeof profile.expected_pension_amount === "number" ||
    typeof profile.pension_savings_balance === "number" ||
    typeof profile.irp_balance === "number" ||
    typeof profile.interest_income === "number" ||
    typeof profile.dividend_income === "number";
  return hasAge && hasFinancialSignal;
}

// 사람이 읽을 수 있는 형태로 프로필 요약 (확인 메시지에 사용)
export function describeProfile(profile) {
  const parts = [];
  if (profile.age) parts.push(`나이 ${profile.age}세`);
  if (profile.retirement_age) parts.push(`연금 수령 나이 ${profile.retirement_age}세`);
  if (profile.expected_pension_amount) {
    parts.push(`예상 연금 수령액 ${profile.expected_pension_amount.toLocaleString("ko-KR")}원`);
  }
  if (profile.pension_savings_balance) {
    parts.push(`연금저축 잔액 ${profile.pension_savings_balance.toLocaleString("ko-KR")}원`);
  }
  if (profile.irp_balance) {
    parts.push(`IRP 잔액 ${profile.irp_balance.toLocaleString("ko-KR")}원`);
  }
  if (profile.interest_income || profile.dividend_income) {
    const fin = (profile.interest_income || 0) + (profile.dividend_income || 0);
    parts.push(`금융소득 ${fin.toLocaleString("ko-KR")}원`);
  }
  if (profile.isa_total_paid) {
    parts.push(`ISA 누적 납입 ${profile.isa_total_paid.toLocaleString("ko-KR")}원`);
  }
  if (profile.total_income) {
    parts.push(`연 총소득 ${profile.total_income.toLocaleString("ko-KR")}원`);
  }
  return parts;
}
