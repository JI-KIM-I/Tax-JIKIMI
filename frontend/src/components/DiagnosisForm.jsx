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

function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
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
        <Field label="현재 나이">
          <input type="number" name="age" min="19" max="100" value={form.age} onChange={handleChange} />
        </Field>
        <Field label="연금 수령 예정 나이">
          <input
            type="number"
            name="retirement_age"
            min={form.age}
            max="100"
            value={form.retirement_age}
            onChange={handleChange}
          />
        </Field>
        <Field label="연간 총급여 / 종합소득 (원)">
          <input type="number" name="total_income" min="0" step="1000000" value={form.total_income} onChange={handleChange} />
        </Field>
      </fieldset>

      <fieldset>
        <legend>2. 금융소득</legend>
        <Field label="이자소득 (원)">
          <input type="number" name="interest_income" min="0" step="1000000" value={form.interest_income} onChange={handleChange} />
        </Field>
        <Field label="배당소득 (원)">
          <input type="number" name="dividend_income" min="0" step="1000000" value={form.dividend_income} onChange={handleChange} />
        </Field>
        <Field label="금융소득 제외 종합소득 과세표준 (원)" hint="모르면 0으로 두면 총급여로 대체됩니다">
          <input type="number" name="other_tax_base" min="0" step="1000000" value={form.other_tax_base} onChange={handleChange} />
        </Field>
        <Field label={`보유 금융상품 예상 연 수익률 (${form.annual_yield_rate_pct}%)`}>
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
        <Field label="연금저축 잔액 (원)">
          <input type="number" name="pension_savings_balance" min="0" step="1000000" value={form.pension_savings_balance} onChange={handleChange} />
        </Field>
        <Field label="IRP 잔액 (원)">
          <input type="number" name="irp_balance" min="0" step="1000000" value={form.irp_balance} onChange={handleChange} />
        </Field>
        <Field label="예상 연금 수령 총액 (원)" hint="0이면 위 잔액 합산 사용">
          <input type="number" name="expected_pension_amount" min="0" step="1000000" value={form.expected_pension_amount} onChange={handleChange} />
        </Field>
        <Field label={`연금 분할 수령 기간 (${form.pension_split_years}년)`}>
          <input type="range" name="pension_split_years" min="1" max="20" value={form.pension_split_years} onChange={handleChange} />
        </Field>
        <Field label="종신계약 연금 여부">
          <input type="checkbox" name="lifetime_annuity_contract" checked={form.lifetime_annuity_contract} onChange={handleChange} />
        </Field>
        <Field label="귀속 세율 기준연도">
          <select name="tax_year" value={form.tax_year} onChange={handleChange}>
            <option value={2026}>2026</option>
            <option value={2025}>2025</option>
          </select>
        </Field>
      </fieldset>

      <fieldset>
        <legend>4. 절세계좌 현황</legend>
        <Field label="ISA 올해 납입액 (원)">
          <input type="number" name="isa_paid_this_year" min="0" step="1000000" value={form.isa_paid_this_year} onChange={handleChange} />
        </Field>
        <Field label="ISA 누적 납입액 (원)">
          <input type="number" name="isa_total_paid" min="0" step="1000000" value={form.isa_total_paid} onChange={handleChange} />
        </Field>
        <Field label="연금저축 올해 납입액 (원)">
          <input type="number" name="pension_savings_paid_this_year" min="0" step="500000" value={form.pension_savings_paid_this_year} onChange={handleChange} />
        </Field>
        <Field label="IRP 올해 납입액 (원)">
          <input type="number" name="irp_paid_this_year" min="0" step="500000" value={form.irp_paid_this_year} onChange={handleChange} />
        </Field>
      </fieldset>

      <fieldset>
        <legend>5. 연금 시작 시점 추천</legend>
        <Field label="최적 시작 나이 추천 받기">
          <input type="checkbox" name="recommend_pension_start" checked={form.recommend_pension_start} onChange={handleChange} />
        </Field>
        <Field label="추천 탐색 최대 나이">
          <input
            type="number"
            name="max_pension_start_age"
            min={form.retirement_age}
            max="100"
            value={form.max_pension_start_age}
            onChange={handleChange}
          />
        </Field>
      </fieldset>

      <button type="submit" className="btn-primary" disabled={loading}>
        {loading ? "진단 중..." : "🔍 절세 진단 시작"}
      </button>
    </form>
  );
}
