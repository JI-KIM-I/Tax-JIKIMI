import { useState } from "react";

const initialForm = {
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

function NumberField({ label, hint, name, value, onChange, min, max, step = 1000000 }) {
  return (
    <Field label={label} hint={hint}>
      <input
        type="number"
        name={name}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={onChange}
        onFocus={selectAllOnFocus}
        inputMode="numeric"
      />
    </Field>
  );
}

export default function DiagnosisForm({ onSubmit, loading }) {
  const [form, setForm] = useState(initialForm);

  const handleChange = (e) => {
    const { name, type, value, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : type === "number" ? Number(value) : value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const { annual_yield_rate_pct, ...rest } = form;
    onSubmit({
      ...rest,
      annual_yield_rate: annual_yield_rate_pct / 100,
    });
  };

  return (
    <form className="diagnosis-form" onSubmit={handleSubmit}>
      <fieldset>
        <legend>1. 기본 정보</legend>
        <NumberField
          label="현재 나이"
          name="age"
          min="19"
          max="100"
          step={1}
          value={form.age}
          onChange={handleChange}
        />
        <NumberField
          label="연금 수령 예정 나이 (연금을 받기 시작할 나이)"
          name="retirement_age"
          min={form.age}
          max="100"
          step={1}
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
          label="예상 연금 수령 총액 (앞으로 받을 연금 총액)"
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
          label="ISA 올해 납입액 (올해 ISA에 넣은 돈)"
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
          label="연금저축 올해 납입액 (올해 연금저축에 넣은 돈)"
          name="pension_savings_paid_this_year"
          min="0"
          step={500000}
          value={form.pension_savings_paid_this_year}
          onChange={handleChange}
        />
        <NumberField
          label="IRP 올해 납입액 (올해 IRP에 넣은 돈)"
          name="irp_paid_this_year"
          min="0"
          step={500000}
          value={form.irp_paid_this_year}
          onChange={handleChange}
        />
      </fieldset>

      <fieldset>
        <legend>5. 연금 수령 시작 시점 추천</legend>
        <Field label="연금 수령 시작 시점 추천 받기" hint="켜두면 아래 나이 범위 안에서 세금이 가장 적은 시작 나이를 찾아드려요">
          <input type="checkbox" name="recommend_pension_start" checked={form.recommend_pension_start} onChange={handleChange} />
        </Field>
        <NumberField
          label="추천 탐색 최대 나이 (몇 살까지 계산해볼지)"
          hint="예: 85로 두면 '연금 수령 예정 나이'부터 85세까지 한 살씩 계산해서 가장 세금이 적은 나이를 찾아드려요"
          name="max_pension_start_age"
          min={form.retirement_age}
          max="100"
          step={1}
          value={form.max_pension_start_age}
          onChange={handleChange}
        />
      </fieldset>

      <button type="submit" className="btn-primary" disabled={loading}>
        {loading ? "진단 중..." : "🔍 절세 진단 시작"}
      </button>
    </form>
  );
}
