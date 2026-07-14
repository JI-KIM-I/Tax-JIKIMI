const TABS = [
  { key: "financial", label: "금융소득 진단" },
  { key: "pension", label: "연금 수령 비교" },
  { key: "timing", label: "연금 시작 시점" },
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
