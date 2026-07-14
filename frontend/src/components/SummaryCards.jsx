import ShieldIcon from "./ShieldIcon";
import { won } from "../utils/format";

export default function SummaryCards({ result }) {
  const { financial_income_tax, pension_compare } = result;

  return (
    <div className="summary-row">
      <div className="card metric-card">
        <span className="metric-label">금융소득</span>
        <span className="metric-value mono">{won(financial_income_tax.financial_income)}</span>
      </div>
      <div className="card metric-card">
        <span className="metric-label">종합과세 예상 추가세액</span>
        <span className="metric-value mono">{won(financial_income_tax.additional_total_tax)}</span>
      </div>
      <div className="card metric-card metric-card--highlight">
        <div className="metric-card-header">
          <ShieldIcon size={18} />
          <span className="metric-label">연금 분할수령 절세 효과</span>
        </div>
        <span className="metric-value mono metric-value--gold">
          {won(pension_compare.saving_by_split)}
        </span>
      </div>
    </div>
  );
}
