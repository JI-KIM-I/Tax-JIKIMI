import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";
import { won } from "../../utils/format";

export default function PensionCompareTab({ result }) {
  const pc = result.pension_compare;

  const compareData = [
    { name: "일시금(연금외수령)", 세금: pc.lump_total_tax },
    { name: "분할 수령", 세금: pc.split_total_tax },
  ];

  const annualData = pc.annual_taxes.map((a) => ({
    연차: a.year,
    나이: a.age,
    "연간 세금": a.total_tax,
    "누적 세금": a.cumulative_tax,
  }));

  return (
    <div className="tab-panel">
      <h3>연금 일시금 vs 분할 수령 비교</h3>
      <p className="muted">{pc.rate_note}</p>
      <p className="lead-text">{pc.message}</p>

      <div className="summary-row">
        <div className="card metric-card">
          <span className="metric-label">일시금 세금</span>
          <span className="metric-value mono">{won(pc.lump_total_tax)}</span>
        </div>
        <div className="card metric-card">
          <span className="metric-label">분할 수령 세금 합계</span>
          <span className="metric-value mono">{won(pc.split_total_tax)}</span>
        </div>
        <div className="card metric-card metric-card--highlight">
          <span className="metric-label">분할 수령시 절세액</span>
          <span className="metric-value mono metric-value--gold">{won(pc.saving_by_split)}</span>
        </div>
      </div>

      <div className="card chart-card">
        <h4>수령 방식별 세금 비교</h4>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={compareData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey="name" tick={{ fontSize: 13 }} />
            <YAxis tickFormatter={(v) => `${(v / 10000).toLocaleString()}만`} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v) => won(v)} />
            <Bar dataKey="세금" fill="var(--color-ink)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <h4>연도별 분할 수령 세부 내역</h4>
        <table className="data-table">
          <thead>
            <tr>
              <th>연차</th>
              <th>나이</th>
              <th>연간 수령액</th>
              <th>적용 세율</th>
              <th>연간 세금</th>
              <th>누적 세금</th>
            </tr>
          </thead>
          <tbody>
            {pc.annual_taxes.map((a) => (
              <tr key={a.year}>
                <td>{a.year}</td>
                <td>{a.age}세</td>
                <td className="mono num-cell">{won(a.annual_amount)}</td>
                <td className="mono">{(a.national_tax_rate * 100).toFixed(1)}%</td>
                <td className="mono num-cell">{won(a.total_tax)}</td>
                <td className="mono num-cell">{won(a.cumulative_tax)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card chart-card">
        <h4>누적 세금 추이</h4>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={annualData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey="연차" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v) => `${(v / 10000).toLocaleString()}만`} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v) => won(v)} />
            <Line type="monotone" dataKey="연간 세금" stroke="var(--color-guard-green)" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="누적 세금" stroke="var(--color-gold)" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
