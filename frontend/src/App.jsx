import { useState } from "react";
import ShieldIcon from "./components/ShieldIcon";
import DiagnosisForm from "./components/DiagnosisForm";
import SummaryCards from "./components/SummaryCards";
import ReportSummary from "./components/ReportSummary";
import ReportDownload from "./components/ReportDownload";
import TabNav from "./components/TabNav";
import FinancialIncomeTab from "./components/tabs/FinancialIncomeTab";
import PensionCompareTab from "./components/tabs/PensionCompareTab";
import LimitUsageTab from "./components/tabs/LimitUsageTab";
import RecommendationsTab from "./components/tabs/RecommendationsTab";
import ChatWidget from "./components/ChatWidget";
import { runDiagnosis } from "./api/client";
import "./App.css";

export default function App() {
  const [result, setResult] = useState(null);
  const [requestPayload, setRequestPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("financial");

  const handleSubmit = async (payload) => {
    setLoading(true);
    setError(null);
    try {
      const data = await runDiagnosis(payload);
      setResult(data);
      setRequestPayload(payload);
      setActiveTab("financial");
      return data;
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setError(`계산 중 오류가 발생했습니다: ${detail}`);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <ShieldIcon size={30} />
        <div>
          <h1>세금지킴이</h1>
          <p className="app-subtitle">은퇴를 앞둔 5060세대를 위한 AI 절세 진단</p>
        </div>
      </header>

      <div className="app-body">
        <aside className="app-sidebar" id="diagnosis-form-anchor">
          <DiagnosisForm onSubmit={handleSubmit} loading={loading} />
        </aside>

        <main className="app-main">
          {error && <div className="error-banner">{error}</div>}

          {!result && !error && (
            <div className="empty-state">
              <ShieldIcon size={48} />
              <p>왼쪽 폼에 정보를 입력하고 <strong>"절세 진단 시작"</strong> 버튼을 눌러주세요.</p>
            </div>
          )}

          {result && (
            <>
              <ReportSummary text={result.report_summary} />
              <SummaryCards result={result} />
              <ReportDownload requestPayload={requestPayload} />
              <TabNav active={activeTab} onChange={setActiveTab} />

              {activeTab === "financial" && <FinancialIncomeTab result={result} />}
              {activeTab === "pension" && <PensionCompareTab result={result} />}
              {activeTab === "limit" && <LimitUsageTab result={result} />}
              {activeTab === "summary" && <RecommendationsTab result={result} />}
            </>
          )}
        </main>
      </div>

      <ChatWidget
        result={result}
        requestPayload={requestPayload}
        onRunDiagnosis={handleSubmit}
        onOpenDiagnosisForm={() =>
          document.getElementById("diagnosis-form-anchor")?.scrollIntoView({ behavior: "smooth", block: "start" })
        }
      />
    </div>
  );
}
