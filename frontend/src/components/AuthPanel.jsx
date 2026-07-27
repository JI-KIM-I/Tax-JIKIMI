import { useState } from "react";
import { signup, login, listDiagnoses, deleteDiagnosis } from "../api/client";
import { saveAuth, clearAuth } from "../utils/authStorage";
import { won } from "../utils/format";

// 백엔드가 던지는 detail(문자열)을 그대로 보여줍니다. auth 쪽 에러 메시지는
// (이메일/비밀번호 오류, 중복 가입 등) 이미 한국어로 친절하게 내려오기 때문에
// 진단 폼처럼 별도 매핑 테이블을 두지 않고 detail을 바로 씁니다.
function authErrorMessage(err) {
  const detail = err.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return "요청 중 문제가 발생했어요. 잠시 후 다시 시도해주세요.";
}

const EMPTY_FORM = { email: "", password: "", name: "", nickname: "" };

export default function AuthPanel({ auth, onAuthSuccess, onLogout, onSelectDiagnosis }) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);
  // null = 아직 안 불러옴, [] = 불러왔는데 기록 없음
  const [diagnoses, setDiagnoses] = useState(null);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data =
        mode === "signup"
          ? await signup({
              email: form.email,
              password: form.password,
              name: form.name,
              nickname: form.nickname,
            })
          : await login({ email: form.email, password: form.password });

      const nextAuth = { token: data.access_token, user: data.user };
      saveAuth(nextAuth);
      onAuthSuccess(nextAuth);
      setOpen(false);
      setForm(EMPTY_FORM);
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    clearAuth();
    setDiagnoses(null);
    setHistoryOpen(false);
    onLogout();
  };

  const handleToggleHistory = async () => {
    const next = !historyOpen;
    setHistoryOpen(next);
    // 열 때마다 새로 불러옵니다. 처음 한 번만 불러오고 캐시해뒀더니, 그 이후 새로 저장한
    // 진단이 안 보이는 문제가 있었습니다(방금 저장해도 목록이 그대로 "없음"으로 보임).
    if (next && auth?.token) {
      setHistoryLoading(true);
      setHistoryError(null);
      try {
        const list = await listDiagnoses(auth.token);
        setDiagnoses(list);
      } catch (err) {
        setHistoryError(authErrorMessage(err));
      } finally {
        setHistoryLoading(false);
      }
    }
  };

  const handleDeleteDiagnosis = async (id) => {
    if (!auth?.token) return;
    if (!window.confirm("이 진단 기록을 삭제할까요? 되돌릴 수 없어요.")) return;
    try {
      await deleteDiagnosis(id, auth.token);
      setDiagnoses((prev) => (prev ? prev.filter((d) => d._id !== id) : prev));
    } catch (err) {
      setHistoryError(authErrorMessage(err));
    }
  };

  if (auth?.user) {
    const label = auth.user.nickname || auth.user.name || auth.user.email;

    return (
      <div className="auth-panel auth-panel--logged-in">
        <div className="auth-panel-user">
          <span className="auth-panel-user-label">{label} 님</span>
          <button type="button" className="auth-panel-link" onClick={handleToggleHistory}>
            내 진단 기록
          </button>
          <button type="button" className="auth-panel-link" onClick={handleLogout}>
            로그아웃
          </button>
        </div>

        {historyOpen && (
          <div className="auth-history-dropdown">
            {historyLoading && <p className="auth-history-empty">불러오는 중...</p>}
            {historyError && <p className="auth-history-empty">{historyError}</p>}
            {!historyLoading && !historyError && diagnoses && diagnoses.length === 0 && (
              <p className="auth-history-empty">저장된 진단 기록이 없어요.</p>
            )}
            {!historyLoading && diagnoses && diagnoses.length > 0 && (
              <ul>
                {diagnoses.map((d) => (
                  <li key={d._id} className="auth-history-item">
                    <button
                      type="button"
                      className="auth-history-select"
                      onClick={() => {
                        onSelectDiagnosis(d);
                        setHistoryOpen(false);
                      }}
                    >
                      <span className="auth-history-label">{d.label || "이름 없음"}</span>
                      <span className="auth-history-date">
                        {d.created_at ? new Date(d.created_at).toLocaleString("ko-KR") : ""}
                      </span>
                      {/* report_summary 문장 대신, 실제로 어떤 값이 저장됐는지 한눈에 보이는 핵심 수치를 보여줍니다. */}
                      <span className="auth-history-facts">
                        {d.input?.age}세 · 총소득 {won(d.input?.total_income)} · 예상 추가세액{" "}
                        {won(d.result?.financial_income_tax?.additional_total_tax)}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="auth-history-delete"
                      onClick={() => handleDeleteDiagnosis(d._id)}
                      aria-label="이 진단 기록 삭제"
                      title="삭제"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="auth-panel">
      <button type="button" className="auth-panel-toggle" onClick={() => setOpen((v) => !v)}>
        로그인
      </button>

      {open && (
        <div className="auth-panel-dropdown">
          <div className="auth-panel-tabs">
            <button
              type="button"
              className={mode === "login" ? "active" : ""}
              onClick={() => {
                setMode("login");
                setError(null);
              }}
            >
              로그인
            </button>
            <button
              type="button"
              className={mode === "signup" ? "active" : ""}
              onClick={() => {
                setMode("signup");
                setError(null);
              }}
            >
              회원가입
            </button>
          </div>

          <form onSubmit={handleSubmit} className="auth-panel-form">
            <input
              type="email"
              name="email"
              placeholder="이메일"
              value={form.email}
              onChange={handleChange}
              required
              autoComplete="email"
            />
            <input
              type="password"
              name="password"
              placeholder="비밀번호 (6자 이상)"
              value={form.password}
              onChange={handleChange}
              required
              minLength={6}
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
            />
            {mode === "signup" && (
              <>
                <input
                  type="text"
                  name="name"
                  placeholder="이름 (선택)"
                  value={form.name}
                  onChange={handleChange}
                  autoComplete="name"
                />
                <input
                  type="text"
                  name="nickname"
                  placeholder="닉네임 (선택)"
                  value={form.nickname}
                  onChange={handleChange}
                  autoComplete="off"
                />
              </>
            )}
            {error && <p className="auth-panel-error">{error}</p>}
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? "처리 중..." : mode === "signup" ? "회원가입" : "로그인"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
