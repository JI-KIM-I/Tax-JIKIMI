// 로그인 토큰/사용자 정보를 localStorage에 저장해서 새로고침해도 로그인 상태가 유지되게 합니다.
// ChatWidget의 대화 기록 저장 방식(taxjikimi_chat_history_v1)과 같은 네이밍 규칙을 따릅니다.
const AUTH_STORAGE_KEY = "taxjikimi_auth_v1";

/**
 * 저장된 로그인 정보를 불러옵니다.
 * @returns {{token: string, user: object} | null}
 */
export function loadAuth() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !parsed.token) return null;
    return parsed;
  } catch {
    return null;
  }
}

/**
 * 로그인 정보를 저장합니다 (회원가입/로그인 성공 시 호출).
 * @param {{token: string, user: object}} auth
 */
export function saveAuth(auth) {
  try {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
  } catch {
    // 저장 실패(프라이빗 모드 등)는 무시 - 로그인 자체는 세션 동안 정상 동작합니다.
  }
}

/**
 * 로그아웃 시 저장된 로그인 정보를 지웁니다.
 */
export function clearAuth() {
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    // 무시
  }
}
