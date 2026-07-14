import { won } from "../../utils/format";

export default function FinancialIncomeTab({ result }) {
  const fit = result.financial_income_tax;
  const ps = result.product_shift;

  const rows = [
    ["금융소득 합계", fit.financial_income],
    ["2,000만원 초과분", fit.excess_amount],
    ["기본계산 산출세액", fit.basic_national_tax],
    ["비교계산 산출세액", fit.compare_national_tax],
    ["최종 산출세액", fit.final_national_tax],
    ["예상 추가 국세", fit.additional_national_tax],
    ["예상 추가 지방세", fit.additional_local_tax],
    ["예상 추가세액 합계", fit.additional_total_tax],
  ];

  return (
    <div className="tab-panel">
      <h3>금융소득종합과세 진단</h3>
      <p className="lead-text">{fit.message}</p>

      <div className="two-col">
        <div className="card">
          <h4>세부 내역</h4>
          <table className="data-table">
            <tbody>
              {rows.map(([label, value]) => (
                <tr key={label}>
                  <td>{label}</td>
                  <td className="mono num-cell">{won(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h4>절세 상품 이동 가이드</h4>
          <p>{ps.recommendation}</p>
          {ps.suggested_transfer_amount > 0 ? (
            <>
              <div className="mini-metric">
                <span>줄여야 할 금융소득</span>
                <strong className="mono">{won(ps.income_to_reduce)}</strong>
              </div>
              <div className="mini-metric">
                <span>이동 권장 금액 (연 수익률 기준)</span>
                <strong className="mono">{won(ps.suggested_transfer_amount)}</strong>
              </div>
            </>
          ) : (
            <p className="muted">현재 조건에서는 상품 이동이 필수는 아닙니다.</p>
          )}
        </div>
      </div>
    </div>
  );
}
