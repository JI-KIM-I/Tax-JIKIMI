import { useState } from "react";

// ChatWidget이 채팅에서 추출한 정보를 진단 payload로 합칠 때 기본값으로 재사용합니다.
export const initialForm = {
  age: 58,
  retirement_age: 65,
  total_income: 80000000,
  interest_income: 18000000,
  dividend_income: 6000000,
  other_tax_base: 0,
  annual_yield_rate_pct: 4, // 화면에서는 %로 입력받고, 제출 시 0.04 형태로 변환
  pension_savings_balance: 80000000,
  irp_balance: 40000000,
  expected_pension_amount: 30000000,
  pension_split_years: 10,
  lifetime_annuity_contract: false,
  tax_year: 2026,
  isa_paid_this_year: 10000000,
  isa_total_paid: 30000000,
  pension_savings_paid_this_year: 4000000,
  irp_paid_this_year: 2000000,
  recommend_pension_start: true,
  max_pension_start_age: 85,
};

// 숫자 입력칸을 클릭(포커스)하면 안에 있던 숫자가 전체 선택되도록 해서,
// 바로 새 숫자를 타이핑하면 기존 값(예: 0)이 자동으로 지워지고 덮어써지게 합니다.
const selectAllOnFocus = (e) => e.target.select();

function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

// 천단위 쉼표를 보여주려고 type="text"를 씁니다 (type="number"는 쉼표를 입력할 수 없어요 —
// 그 대신 위/아래 스피너 화살표는 없어집니다). "원" 단위는 입력값 안에 같이 넣지 않고,
// 입력칸 오른쪽에 회색 글자로 따로 얹어서 보여줍니다 (편집할 때 방해되지 않게).
// 나이처럼 "원" 단위가 안 맞는 필드는 unit="" 으로 꺼둘 수 있습니다.
function NumberField({ label, hint, name, value, onChange, unit = "원" }) {
  const displayValue =
    value === "" || value === null || value === undefined ? "" : Number(value).toLocaleString("ko-KR");

  const handleChange = (e) => {
    const raw = e.target.value.replace(/[^\d]/g, "");
    onChange({ target: { name, type: "number", value: raw } });
  };

  return (
    <Field label={label} hint={hint}>
      <div className="field-number-wrap">
        <input
          type="text"
          inputMode="numeric"
          name={name}
          value={displayValue}
          onChange={handleChange}
          onFocus={selectAllOnFocus}
          className="field-number-input"
        />
        {unit && <span className="field-number-unit">{unit}</span>}
      </div>
    </Field>
  );
}

export default function DiagnosisForm({ onSubmit, loading }) {
  const [form, setForm] = useState(initialForm);
  // 백엔드까지 안 보내도 미리 알 수 있는 입력 오류(나이 관계 등)는 여기서 바로 잡아서
  // "retirement_age must be..." 같은 원본 에러 메시지가 아예 뜰 일이 없게 합니다.
  const [validationError, setValidationError] = useState(null);

  const handleChange = (e) => {
    const { name, type, value, checked } = e.target;
    setValidationError(null);
    setForm((prev) => ({
      ...prev,
      // 숫자칸을 전체 지우면 value가 ""가 되는데, 이걸 바로 Number("")=0으로 바꿔서 state에 넣으면
      // 화면에 "0"이 남아있는 채로 다음 입력이 그 뒤에 이어져서 "05" 같은 값이 됩니다.
      // 지워진 상태("")는 그대로 두고, 실제 숫자로 바꾸는 건 제출 시점(handleSubmit)에서 처리합니다.
      [name]: type === "checkbox" ? checked : type === "number" ? (value === "" ? "" : Number(value)) : value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const { annual_yield_rate_pct, ...rest } = form;
    // 입력칸이 비어있는 채로 제출하면(값 "") 0으로 간주합니다.
    const normalized = Object.fromEntries(
      Object.entries(rest).map(([key, val]) => [key, val === "" ? 0 : val])
    );

    // 백엔드에 물어보나마나인 흔한 입력 실수는 여기서 먼저 걸러서, 바로 안내하고 API 호출 자체를 막습니다.
    if (normalized.retirement_age < normalized.age) {
      setValidationError("연금 수령 예정 나이는 현재 나이보다 같거나 커야 해요. 나이를 다시 확인해주세요.");
      return;
    }

    setValidationError(null);
    onSubmit({
      ...normalized,
      annual_yield_rate: (annual_yield_rate_pct === "" ? 0 : Number(annual_yield_rate_pct)) / 100,
    });
  };

  return (
    <form className="diagnosis-form" onSubmit={handleSubmit}>
      {/* 예전엔 사이드바 전체가 하나로 스크롤되고 그 안에 버튼만 sticky를 걸었더니,
          내부 계산이 꼬여서 버튼 밑으로 다른 입력칸이 비쳐 보이는 버그가 있었습니다.
          지금은 입력칸 영역과 버튼 영역을 아예 분리해서(스크롤은 아래 영역에서만),
          버튼은 항상 그 아래 고정된 자리에 별도로 놓이게 구조를 바꿨습니다. */}
      <div className="diagnosis-form-fields">
      <fieldset>
        <legend>1. 기본 정보</legend>
        <NumberField
          label="현재 나이"
          name="age"
          unit="세"
          value={form.age}
          onChange={handleChange}
        />
        <NumberField
          label="연금 수령 예정 나이"
          name="retirement_age"
          unit="세"
          value={form.retirement_age}
          onChange={handleChange}
        />
        <NumberField
          label="연간 총급여·종합소득 (1년 동안 버는 돈 전체, 세전 기준)"
          name="total_income"
          min="0"
          value={form.total_income}
          onChange={handleChange}
        />
      </fieldset>

      <fieldset>
        <legend>2. 금융소득</legend>
        <NumberField
          label="이자소득 (예금·적금 이자로 받은 돈, 1년 합계)"
          name="interest_income"
          min="0"
          value={form.interest_income}
          onChange={handleChange}
        />
        <NumberField
          label="배당소득 (주식·펀드 배당금, 1년 합계)"
          name="dividend_income"
          min="0"
          value={form.dividend_income}
          onChange={handleChange}
        />
        <NumberField
          label="종합소득 과세표준 (이자·배당 소득 제외 나머지 소득)"
          hint="잘 모르시면 0으로 두세요. 위에 입력한 총소득으로 자동 계산됩니다"
          name="other_tax_base"
          min="0"
          value={form.other_tax_base}
          onChange={handleChange}
        />
        <Field label={`보유 금융상품 예상 연 수익률 (${form.annual_yield_rate_pct}%)`} hint="잘 모르면 4% 정도로 두세요">
          <input
            type="range"
            name="annual_yield_rate_pct"
            min="0.5"
            max="10"
            step="0.5"
            value={form.annual_yield_rate_pct}
            onChange={handleChange}
          />
        </Field>
      </fieldset>

      <fieldset>
        <legend>3. 연금</legend>
        <NumberField
          label="연금저축 잔액 (연금저축 계좌에 모인 돈)"
          name="pension_savings_balance"
          min="0"
          value={form.pension_savings_balance}
          onChange={handleChange}
        />
        <NumberField
          label="IRP 잔액 (개인형 퇴직연금 계좌에 모인 돈)"
          hint="IRP: 퇴직금 등을 넣어두는 개인형 퇴직연금 계좌"
          name="irp_balance"
          min="0"
          value={form.irp_balance}
          onChange={handleChange}
        />
        <NumberField
          label="예상 연금 수령 총액"
          hint="0으로 두면 위 연금저축 + IRP 잔액을 합쳐서 계산해요"
          name="expected_pension_amount"
          min="0"
          value={form.expected_pension_amount}
          onChange={handleChange}
        />
        <Field label={`연금 분할 수령 기간 (몇 년에 걸쳐 나눠 받을지, ${form.pension_split_years}년)`} hint="예: 10년으로 두면 매년 1/10씩 나눠 받는다고 계산해요">
          <input
            type="range"
            name="pension_split_years"
            min="1"
            max="20"
            value={form.pension_split_years}
            onChange={handleChange}
          />
        </Field>
        <Field label="종신계약 연금 여부 (평생 나눠 받는 종신형 상품 가입 여부)">
          <input type="checkbox" name="lifetime_annuity_contract" checked={form.lifetime_annuity_contract} onChange={handleChange} />
        </Field>
        <Field label="귀속 세율 기준연도 (세금 계산에 적용할 기준 연도)" hint="특별한 이유 없으면 최신 연도(2026) 그대로 두세요">
          <select name="tax_year" value={form.tax_year} onChange={handleChange}>
            <option value={2026}>2026년 기준</option>
            <option value={2025}>2025년 기준</option>
          </select>
        </Field>
      </fieldset>

      <fieldset>
        <legend>4. 절세계좌 현황</legend>
        <NumberField
          label="ISA 올해 납입액"
          name="isa_paid_this_year"
          min="0"
          value={form.isa_paid_this_year}
          onChange={handleChange}
        />
        <NumberField
          label="ISA 누적 납입액 (지금까지 ISA에 넣은 돈 전체)"
          name="isa_total_paid"
          min="0"
          value={form.isa_total_paid}
          onChange={handleChange}
        />
        <NumberField
          label="연금저축 올해 납입액"
          name="pension_savings_paid_this_year"
          min="0"
          step={500000}
          value={form.pension_savings_paid_this_year}
          onChange={handleChange}
        />
        <NumberField
          label="IRP 올해 납입액"
          name="irp_paid_this_year"
          min="0"
          step={500000}
          value={form.irp_paid_this_year}
          onChange={handleChange}
        />
      </fieldset>

      {/* 예전엔 여기에 "연금 수령 시작 시점 추천 받기" 체크박스 + 최대 나이 입력칸이 있었습니다.
          그 결과를 보여주던 전용 탭을 없애고 챗봇 컨텍스트로만 넘기는 방향으로 바꾸면서,
          사용자가 굳이 켜고 끄는 옵션일 필요가 없어져서 폼에서도 뺐습니다.
          initialForm의 recommend_pension_start(true)·max_pension_start_age(85) 기본값 그대로
          항상 계산해서 챗봇이 참고할 수 있게 합니다. */}
      </div>

      {/* 입력칸이 18개나 되다 보니 이 버튼이 맨 아래에만 있으면 스크롤을 끝까지 내려야만 보였습니다.
          위 .diagnosis-form-fields 안에서만 스크롤되고, 버튼은 그 바깥 고정된 자리에 항상 보입니다. */}
      <div className="diagnosis-submit-bar">
        {validationError && <p className="diagnosis-validation-error">{validationError}</p>}
        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? "진단 중..." : "🔍 절세 진단 시작"}
        </button>
      </div>
    </form>
  );
}
