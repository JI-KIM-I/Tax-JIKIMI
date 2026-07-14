import { won, pct } from "../../utils/format";

function UsageBar({ label, used, limit, ratio }) {
  const clamped = Math.min(ratio, 1);
  return (
    <div className="usage-bar">
      <div className="usage-bar-labels">
        <span>{label}</span>
        <span className="mono">{pct(ratio)}</span>
      </div>
      <div className="usage-bar-track">
        <div className="usage-bar-fill" style={{ width: `${clamped * 100}%` }} />
      </div>
      {used !== undefined && limit !== undefined && (
        <div className="usage-bar-sub mono">
          {won(used)} / {won(limit)}
        </div>
      )}
    </div>
  );
}

export default function LimitUsageTab({ result }) {
  const lu = result.limit_usage;

  return (
    <div className="tab-panel">
      <h3>ISA · 연금저축 · IRP 절세 한도 활용</h3>
      <p className="lead-text">{lu.message}</p>

      <div className="card">
        <UsageBar
          label="ISA 연간 한도"
          used={lu.isa_paid_this_year}
          limit={lu.isa_annual_limit}
          ratio={lu.isa_annual_usage_rate}
        />
        <UsageBar
          label="ISA 누적(총) 한도"
          used={lu.isa_total_paid}
          limit={lu.isa_total_limit}
          ratio={lu.isa_total_usage_rate}
        />
        <UsageBar
          label="연금저축 세액공제 한도"
          ratio={lu.pension_savings_usage_rate}
        />
        <UsageBar
          label="연금저축+IRP 합산 세액공제 한도"
          used={lu.combined_pension_paid}
          limit={lu.pension_irp_combined_tax_credit_limit}
          ratio={lu.pension_irp_combined_usage_rate}
        />
      </div>

      <div className="card metric-card metric-card--highlight">
        <span className="metric-label">예상 세액공제액</span>
        <span className="metric-value mono metric-value--gold">{won(lu.estimated_tax_credit)}</span>
      </div>
    </div>
  );
}
