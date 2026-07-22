import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";
import { won, pct } from "../../utils/format";

// 리포트 다운로드 버튼은 SummaryCards 옆(App.jsx)의 <ReportDownload />로 옮겼습니다.
// 이 탭까지 와야만 다운로드할 수 있었던 문제를 해결하기 위함이에요.
export default function RecommendationsTab({ result }) {
  const scenarioData = result.scenario_comparison.map((s) => ({
    name: s.scenario_name,
    예상세금: s.estimated_tax,
  }));

  return (
    <div className="tab-panel">
      <h3>AI 추천사항</h3>
      <ol className="recommendation-list">
        {result.recommendations.map((rec, i) => (
          <li key={i}>{rec}</li>
        ))}
      </ol>

      <div className="card chart-card">
        <h4>시나리오별 예상 세금 비교</h4>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={scenarioData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey="name" tick={{ fontSize: 13 }} />
            <YAxis tickFormatter={(v) => `${(v / 10000).toLocaleString()}만`} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v) => won(v)} />
            <Bar dataKey="예상세금" fill="var(--color-guard-green)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>

        <table className="data-table">
          <thead>
            <tr>
              <th>시나리오</th>
              <th>예상 세금</th>
              <th>절세액</th>
              <th>절세율</th>
            </tr>
          </thead>
          <tbody>
            {result.scenario_comparison.map((s) => (
              <tr key={s.scenario_name}>
                <td>{s.scenario_name}</td>
                <td className="mono num-cell">{won(s.estimated_tax)}</td>
                <td className="mono num-cell">{won(s.saving_amount)}</td>
                <td className="mono">{pct(s.saving_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="disclaimer">⚠️ {result.disclaimer}</p>
    </div>
  );
}
