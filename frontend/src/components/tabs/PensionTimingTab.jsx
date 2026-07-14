import { won } from "../../utils/format";

export default function PensionTimingTab({ result }) {
  const rec = result.pension_start_recommendation;

  return (
    <div className="tab-panel">
      <h3>연금 수령 시작 시점 추천</h3>
      {!rec ? (
        <p className="muted">
          이번 진단에서는 시작 시점 추천을 요청하지 않았습니다. 왼쪽 폼에서 "최적 시작 나이 추천 받기"를 켜주세요.
        </p>
      ) : (
        <>
          <div className="summary-row">
            <div className="card metric-card metric-card--highlight">
              <span className="metric-label">추천 시작 나이</span>
              <span className="metric-value mono metric-value--gold">{rec.recommended_start_age}세</span>
            </div>
            <div className="card metric-card">
              <span className="metric-label">예상 분할 수령 세금</span>
              <span className="metric-value mono">{won(rec.expected_split_total_tax)}</span>
            </div>
          </div>
          <p className="lead-text">{rec.reason}</p>
        </>
      )}
    </div>
  );
}
