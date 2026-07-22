// "연금 시작 시점" 탭은 제외했습니다. 세율만 보고 가장 늦은 나이를 기계적으로 추천하는 게
// 단독 탭의 확정된 답처럼 보여서 오해를 줄 수 있어, 챗봇 상담(다른 고려사항까지 함께 설명)으로 옮겼습니다.
const TABS = [
  { key: "financial", label: "금융소득 진단" },
  { key: "pension", label: "연금 수령 비교" },
  { key: "limit", label: "절세계좌 한도" },
  { key: "summary", label: "종합 추천 & 시나리오" },
];

export default function TabNav({ active, onChange }) {
  return (
    <div className="tab-nav" role="tablist">
      {TABS.map((tab) => (
        <button
          key={tab.key}
          role="tab"
          aria-selected={active === tab.key}
          className={`tab-btn ${active === tab.key ? "tab-btn--active" : ""}`}
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export { TABS };
