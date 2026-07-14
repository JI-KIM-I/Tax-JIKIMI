import { useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";
import { won, pct } from "../../utils/format";
import { exportReport } from "../../api/client";

export default function RecommendationsTab({ result, requestPayload }) {
  const [downloading, setDownloading] = useState(false);

  const scenarioData = result.scenario_comparison.map((s) => ({
    name: s.scenario_name,
    예상세금: s.estimated_tax,
  }));

  const handleDownload = async (format) => {
    setDownloading(true);
    try {
      const blob = await exportReport({ ...requestPayload, format });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = format === "pdf" ? "세금지킴이_report.pdf" : "세금지킴이_report.txt";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert("리포트 다운로드에 실패했습니다: " + err.message);
    } finally {
      setDownloading(false);
    }
  };

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

      <div className="download-row">
        <button className="btn-secondary" onClick={() => handleDownload("text")} disabled={downloading}>
          📄 텍스트 리포트 다운로드
        </button>
        <button className="btn-secondary" onClick={() => handleDownload("pdf")} disabled={downloading}>
          📑 PDF 리포트 다운로드
        </button>
      </div>
    </div>
  );
}
