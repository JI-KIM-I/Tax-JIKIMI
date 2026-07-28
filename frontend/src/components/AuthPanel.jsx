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
  return "요청 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주시기 바랍니다.";
}

// 완벽한 이메일 검증(RFC 전체 스펙)은 안 하고, "누가 봐도 이메일이 아닌" 값만 걸러내는
// 정도로 단순하게 둡니다 - 브라우저 기본 검증 팝업 대신 우리 스타일 문구로 보여주기 위함입니다.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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

  const openWithMode = (nextMode) => {
    setMode(nextMode);
    setOpen(true);
    setError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    // 브라우저 기본 "이메일 형식을 확인하세요" 팝업은 스타일이 안 맞아서, 직접 검사하고
    // 우리 문구(.auth-panel-error)로 보여줍니다. <form noValidate>로 네이티브 팝업 자체를 꺼둡니다.
    if (!EMAIL_PATTERN.test(form.email.trim())) {
      setError("올바른 이메일 형식이 아닙니다. (예: name@example.com)");
      return;
    }

    setLoading(true);
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
        if (err.response?.status === 401) {
          // 토큰이 만료/무효화된 상태로 남아있던 경우 - 에러 문구만 보여주면 로그인된
          // 것처럼 보이는 화면이 계속 남아 헷갈리므로, 바로 로그아웃 처리하고 로그인
          // 패널을 열어 안내 문구를 보여줍니다(닫혀있으면 setError만으론 안 보임).
          handleLogout();
          setMode("login");
          setOpen(true);
          setError("로그인이 만료되었습니다. 다시 로그인해 주세요.");
          return;
        }
        setHistoryError(authErrorMessage(err));
      } finally {
        setHistoryLoading(false);
      }
    }
  };

  const handleDeleteDiagnosis = async (id) => {
    if (!auth?.token) return;
    if (!window.confirm("이 진단 기록을 삭제하시겠습니까? 삭제 후에는 되돌릴 수 없습니다.")) return;
    try {
      await deleteDiagnosis(id, auth.token);
      setDiagnoses((prev) => (prev ? prev.filter((d) => d._id !== id) : prev));
    } catch (err) {
      setHistoryError(authErrorMessage(err));
    }
  };

  if (auth?.user) {
    const label = auth.user.nickname || auth.user.name || auth.user.email;
    const avatarInitial = label.trim().charAt(0).toUpperCase();

    return (
      <div className="auth-panel auth-panel--logged-in">
        <div className="auth-panel-user">
          <div className="auth-panel-identity">
            <span className="auth-panel-avatar" aria-hidden="true">
              {avatarInitial}
            </span>
            <span className="auth-panel-user-label">{label} 님</span>
          </div>
          <div className="auth-panel-actions">
            <button
              type="button"
              className="auth-panel-toggle auth-panel-toggle--ghost auth-panel-toggle--small"
              onClick={handleToggleHistory}
            >
              내 진단 기록
            </button>
            {/* 로그아웃은 "내 진단 기록"보다 덜 중요하고 잘 안 쓰는 동작이라, 같은 버튼
                박스 대신 옅은 텍스트 링크로 눈에 덜 띄게 구분합니다. */}
            <button type="button" className="auth-panel-logout-btn" onClick={handleLogout}>
              로그아웃
            </button>
          </div>
        </div>

        {historyOpen && (
          <div className="auth-history-dropdown">
            {historyLoading && <p className="auth-history-empty">불러오는 중입니다...</p>}
            {historyError && <p className="auth-history-empty">{historyError}</p>}
            {!historyLoading && !historyError && diagnoses && diagnoses.length === 0 && (
              <p className="auth-history-empty">저장된 진단 기록이 없습니다.</p>
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
      <div className="auth-panel-toggle-group">
        <button type="button" className="auth-panel-toggle" onClick={() => openWithMode("login")}>
          로그인
        </button>
        <button
          type="button"
          className="auth-panel-toggle auth-panel-toggle--ghost"
          onClick={() => openWithMode("signup")}
        >
          회원가입
        </button>
      </div>

      {open && (
        <div className="auth-panel-dropdown">
          {/* 위 로그인/회원가입 버튼으로 이미 모드를 정하고 들어왔으니, 패널 안에 또
              탭을 두는 건 중복이었습니다. 지금 모드를 제목으로 보여주고, 잘못 들어왔을 때만
              아래 "계정이 없으신가요?" 링크로 전환하게 했습니다. */}
          <p className="auth-panel-heading">{mode === "signup" ? "회원가입" : "로그인"}</p>

          <form onSubmit={handleSubmit} className="auth-panel-form" noValidate>
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
              {loading ? "처리 중입니다..." : mode === "signup" ? "회원가입" : "로그인"}
            </button>
          </form>

          <p className="auth-panel-switch">
            {mode === "signup" ? "이미 계정이 있으십니까? " : "계정이 없으십니까? "}
            <button
              type="button"
              onClick={() => {
                setMode(mode === "signup" ? "login" : "signup");
                setError(null);
              }}
            >
              {mode === "signup" ? "로그인" : "회원가입"}
            </button>
          </p>
        </div>
      )}
    </div>
  );
}
