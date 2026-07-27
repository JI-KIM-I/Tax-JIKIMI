import { useState } from "react";
import ShieldIcon from "./components/ShieldIcon";
import DiagnosisForm, { payloadToFormValues } from "./components/DiagnosisForm";
import SummaryCards from "./components/SummaryCards";
import ReportSummary from "./components/ReportSummary";
import ReportDownload from "./components/ReportDownload";
import TabNav from "./components/TabNav";
import FinancialIncomeTab from "./components/tabs/FinancialIncomeTab";
import PensionCompareTab from "./components/tabs/PensionCompareTab";
import LimitUsageTab from "./components/tabs/LimitUsageTab";
import RecommendationsTab from "./components/tabs/RecommendationsTab";
import ChatWidget from "./components/ChatWidget";
import AuthPanel from "./components/AuthPanel";
import { runDiagnosis, saveDiagnosis, listDiagnoses, deleteDiagnosis } from "./api/client";
import { friendlyDiagnosisError } from "./utils/errors";
import { loadAuth } from "./utils/authStorage";
import "./App.css";

// 두 진단 입력값이 사실상 같은지 비교합니다 (필드 순서에 상관없이). 저장하려는 값이 이미 저장된
// 기록과 완전히 같으면, 중복으로 또 쌓지 않도록 사용자에게 먼저 물어보기 위해 씁니다.
function diagnosisInputsMatch(a, b) {
  if (!a || !b) return false;
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => a[key] === b[key]);
}

export default function App() {
  const [result, setResult] = useState(null);
  const [requestPayload, setRequestPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("financial");

  // 새로고침해도 로그인 상태가 유지되도록 localStorage에서 복원합니다.
  const [auth, setAuth] = useState(() => loadAuth());
  const [saving, setSaving] = useState(false);
  // API 요청 결과(저장 성공/실패)만 담습니다. 이름을 안 적었다는 식의 입력값 검증은
  // 아래 nameError에 따로 둡니다 - 이 둘을 한 문구/색으로 같이 쓰다 보니, "이름을 입력해주세요"
  // 같은 경고 문구가 성공 메시지와 똑같은 초록색으로 보이는 문제가 있었습니다.
  const [saveMessage, setSaveMessage] = useState(null);
  const [saveMessageType, setSaveMessageType] = useState("success"); // "success" | "error"
  const [savePromptOpen, setSavePromptOpen] = useState(false);
  const [saveLabel, setSaveLabel] = useState("");
  const [nameError, setNameError] = useState(null);
  // 저장하려는 값과 완전히 같은 기존 기록을 발견했을 때: { id, label } (교체할지/새로 저장할지 물어보는 중)
  const [duplicateCandidate, setDuplicateCandidate] = useState(null);

  // "내 진단 기록"에서 과거 진단을 고르면 DiagnosisForm을 이 값으로 다시 마운트시켜서,
  // 오른쪽 결과뿐 아니라 왼쪽 폼에도 그때 입력했던 값이 그대로 보이게 합니다.
  const [formInitialValues, setFormInitialValues] = useState(null);
  const [formResetToken, setFormResetToken] = useState(0);

  const handleSubmit = async (payload) => {
    setLoading(true);
    setError(null);
    setSaveMessage(null);
    try {
      const data = await runDiagnosis(payload);
      setResult(data);
      setRequestPayload(payload);
      setActiveTab("financial");
      return data;
    } catch (err) {
      // 백엔드가 던지는 원본 에러(영어 필드명 등)를 그대로 보여주면 당황스러워서,
      // 자연스러운 한국어 안내 문구로 바꿔서 보여줍니다.
      const detail = err.response?.data?.detail;
      setError(detail ? friendlyDiagnosisError(detail) : "계산 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const handleAuthSuccess = (nextAuth) => {
    setAuth(nextAuth);
  };

  const handleLogout = () => {
    setAuth(null);
    setSaveMessage(null);
  };

  // "내 진단 기록"에서 과거 진단을 골랐을 때, 새로 계산하지 않고 저장된 결과를 그대로 복원합니다.
  // 왼쪽 폼도 그때 입력값으로 되돌리기 위해 key를 바꿔 DiagnosisForm을 다시 마운트시킵니다.
  const handleSelectDiagnosis = (record) => {
    setResult(record.result);
    setRequestPayload(record.input);
    setActiveTab("financial");
    setError(null);
    setSaveMessage(null);
    setDuplicateCandidate(null);
    setFormInitialValues(payloadToFormValues(record.input));
    setFormResetToken((t) => t + 1);
  };

  const openSavePrompt = () => {
    setSavePromptOpen(true);
    setSaveMessage(null);
    setNameError(null);
  };

  const closeSavePrompt = () => {
    setSavePromptOpen(false);
    setSaveLabel("");
    setNameError(null);
    setSaveMessage(null);
    setDuplicateCandidate(null);
  };

  const performSave = async (label) => {
    setSaving(true);
    setSaveMessage(null);
    try {
      await saveDiagnosis({ ...requestPayload, label }, auth.token);
      setSaveMessage(`"${label}"(으)로 저장했어요.`);
      setSaveMessageType("success");
      setSavePromptOpen(false);
      setSaveLabel("");
      setNameError(null);
      setDuplicateCandidate(null);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setSaveMessage(typeof detail === "string" ? detail : "저장 중 문제가 발생했어요. 잠시 후 다시 시도해주세요.");
      setSaveMessageType("error");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveDiagnosis = async () => {
    const label = saveLabel.trim();
    if (!label) {
      setNameError("진단 기록 이름을 입력해주세요.");
      return;
    }
    setNameError(null);
    if (!auth?.token || !requestPayload) return;

    setSaving(true);
    setSaveMessage(null);
    try {
      // 저장하기 전에, 지금 입력값과 완전히 같은 기록이 이미 있는지 확인합니다.
      // (조회에 실패해도 중복 확인은 참고용일 뿐이라 저장 자체는 그대로 진행합니다)
      const existing = await listDiagnoses(auth.token);
      const duplicate = existing.find((d) => diagnosisInputsMatch(d.input, requestPayload));
      if (duplicate) {
        setDuplicateCandidate({ id: duplicate._id, label: duplicate.label || "이름 없음" });
        setSaving(false);
        return;
      }
    } catch {
      // 무시하고 아래에서 그냥 저장 진행
    }
    await performSave(label);
  };

  const handleReplaceDuplicate = async () => {
    if (!duplicateCandidate || !auth?.token) return;
    const label = saveLabel.trim();
    setSaving(true);
    try {
      await deleteDiagnosis(duplicateCandidate.id, auth.token);
    } catch {
      // 삭제가 실패해도 새로 저장은 진행합니다 - 중복이 하나 남는 게, 저장 자체가 막히는 것보다 낫습니다.
    }
    setDuplicateCandidate(null);
    await performSave(label);
  };

  const handleSaveAsNewAnyway = async () => {
    const label = saveLabel.trim();
    setDuplicateCandidate(null);
    await performSave(label);
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <ShieldIcon size={30} />
        <div className="app-header-title">
          <h1>세금지킴이</h1>
          <p className="app-subtitle">은퇴를 앞둔 5060세대를 위한 AI 절세 진단</p>
        </div>
        <div className="app-header-auth">
          <AuthPanel
            auth={auth}
            onAuthSuccess={handleAuthSuccess}
            onLogout={handleLogout}
            onSelectDiagnosis={handleSelectDiagnosis}
          />
        </div>
      </header>

      <div className="app-body">
        <aside className="app-sidebar" id="diagnosis-form-anchor">
          <DiagnosisForm
            key={formResetToken}
            onSubmit={handleSubmit}
            loading={loading}
            initialValues={formInitialValues || undefined}
          />
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
              <div className="report-actions">
                <ReportDownload requestPayload={requestPayload} />
                {auth?.token && !savePromptOpen && (
                  <button type="button" className="btn-secondary" onClick={openSavePrompt}>
                    💾 진단 저장
                  </button>
                )}
                {!auth?.token && (
                  <span className="report-actions-hint">로그인하면 이 진단을 저장하고 나중에 다시 볼 수 있어요.</span>
                )}
              </div>

              {auth?.token && savePromptOpen && !duplicateCandidate && (
                <form
                  className="save-diagnosis-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSaveDiagnosis();
                  }}
                >
                  <div className="save-diagnosis-form-row">
                    <input
                      type="text"
                      placeholder="이 진단 기록 이름 (예: 2026년 은퇴 시뮬레이션)"
                      value={saveLabel}
                      onChange={(e) => {
                        setSaveLabel(e.target.value);
                        if (nameError) setNameError(null);
                      }}
                      autoFocus
                    />
                    <div className="save-diagnosis-form-actions">
                      <button type="submit" className="btn-primary" disabled={saving}>
                        {saving ? "저장 중..." : "저장"}
                      </button>
                      <button type="button" className="btn-secondary" onClick={closeSavePrompt} disabled={saving}>
                        취소
                      </button>
                    </div>
                  </div>
                  {nameError && <p className="save-diagnosis-form-error">{nameError}</p>}
                </form>
              )}

              {duplicateCandidate && (
                <div className="save-duplicate-confirm">
                  <p>
                    "{duplicateCandidate.label}"(이)라는 이름으로 이미 똑같은 값이 저장돼 있어요. 어떻게 할까요?
                  </p>
                  <div className="save-duplicate-actions">
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleReplaceDuplicate}
                      disabled={saving}
                    >
                      기존 기록 교체
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleSaveAsNewAnyway}
                      disabled={saving}
                    >
                      그냥 새로 저장
                    </button>
                    <button type="button" className="btn-secondary" onClick={closeSavePrompt} disabled={saving}>
                      취소
                    </button>
                  </div>
                </div>
              )}

              {saveMessage && (
                <p className={`save-message${saveMessageType === "error" ? " save-message--error" : ""}`}>
                  {saveMessage}
                </p>
              )}
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
