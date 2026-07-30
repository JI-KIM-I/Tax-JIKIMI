import axios from "axios";

// 백엔드(FastAPI) 서버 주소. 로컬 개발할 땐 uvicorn 기본 포트(8000)를 그대로 쓰고,
// 배포할 땐 프론트엔드 빌드 시 VITE_API_BASE_URL 환경변수로 실제 백엔드 주소를 넣어주세요.
// 예: frontend/.env.production 파일에 VITE_API_BASE_URL=https://your-backend.onrender.com
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const client = axios.create({
  baseURL: BASE_URL,
  // Render 무료 요금제는 일정 시간 요청이 없으면 서버가 잠들었다가, 첫 요청이 오면 그때 다시
  // 깨어나는 데 수십 초가 걸릴 수 있습니다. Render 자체 안내에도 "50초 이상 지연될 수 있다"고
  // 나와 있는데, 10초→30초로 늘렸을 때도 실제로 "timeout of 30000ms exceeded"가 발생해서
  // 콜드스타트를 다 못 견뎠던 사례가 있어 60초로 다시 늘렸습니다.
  timeout: 60000,
});

/**
 * 통합 절세 진단 실행.
 * @param {object} payload - DiagnosisRequestBody 모양의 입력값
 * @returns {Promise<object>} DiagnosisResponse 모양의 결과
 */
export async function runDiagnosis(payload) {
  const response = await client.post("/api/diagnosis", payload);
  return response.data;
}

/**
 * 리포트 다운로드 (PDF 또는 텍스트).
 * @param {object} payload - DiagnosisRequestBody + { format: "pdf" | "text" }
 * @returns {Promise<Blob>}
 */
export async function exportReport(payload) {
  const response = await client.post("/api/report/export", payload, {
    responseType: "blob",
  });
  return response.data;
}

/**
 * RAG 챗봇에 질문 전송.
 * @param {string} message - 사용자 질문
 * @param {object|null} context - 현재 진단 결과 요약 (선택)
 * @param {number} topK - 검색해올 문서 조각 개수
 * @returns {Promise<{answer: string, sources: Array<{source: string, text: string}>}>}
 */
export async function sendChatMessage(message, context = null, topK = 4) {
  // LLM 응답은 계산 API보다 오래 걸릴 수 있고, 콜드스타트 직후라면 그 위에 더해질 수 있어
  // 기본 client보다 더 넉넉하게 둡니다.
  const response = await client.post(
    "/api/chat",
    { message, context, top_k: topK },
    { timeout: 60000 }
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// 회원가입 · 로그인 · 진단 저장/불러오기
// 로그인 필요한 API는 매번 명시적으로 { Authorization: `Bearer ${token}` }를
// 넘겨받는 방식으로 구현합니다 (인터셉터로 숨기지 않고, 호출하는 쪽에서
// 토큰이 있는지 없는지 항상 눈에 보이게 하기 위함).
// ---------------------------------------------------------------------------

function authHeader(token) {
  return token ? { headers: { Authorization: `Bearer ${token}` } } : {};
}

/**
 * 회원가입.
 * @param {{email: string, password: string, name?: string, nickname?: string}} payload
 * @returns {Promise<{access_token: string, token_type: string, user: object}>}
 */
export async function signup(payload) {
  const response = await client.post("/api/auth/signup", payload);
  return response.data;
}

/**
 * 로그인.
 * @param {{email: string, password: string}} payload
 * @returns {Promise<{access_token: string, token_type: string, user: object}>}
 */
export async function login(payload) {
  const response = await client.post("/api/auth/login", payload);
  return response.data;
}

/**
 * 로그인된 사용자로 현재 진단 결과를 DB에 저장.
 * @param {object} payload - DiagnosisRequestBody 모양의 입력값 + { label: string } (이름 필수)
 * @param {string} token - 로그인 시 받은 access_token
 * @returns {Promise<{diagnosis_id: string, label: string, result: object}>}
 */
export async function saveDiagnosis(payload, token) {
  const response = await client.post("/api/diagnosis/save", payload, authHeader(token));
  return response.data;
}

/**
 * 저장된 진단 기록 삭제.
 * @param {string} diagnosisId
 * @param {string} token
 * @returns {Promise<{deleted: boolean}>}
 */
export async function deleteDiagnosis(diagnosisId, token) {
  const response = await client.delete(`/api/diagnoses/${diagnosisId}`, authHeader(token));
  return response.data;
}

/**
 * 로그인된 사용자의 저장된 진단 기록 목록 (최신순 최대 20건).
 * @param {string} token
 * @returns {Promise<Array<object>>}
 */
export async function listDiagnoses(token) {
  const response = await client.get("/api/diagnoses", authHeader(token));
  return response.data;
}

/**
 * 저장된 진단 기록 1건 상세 조회.
 * @param {string} diagnosisId
 * @param {string} token
 * @returns {Promise<object>}
 */
export async function getDiagnosis(diagnosisId, token) {
  const response = await client.get(`/api/diagnoses/${diagnosisId}`, authHeader(token));
  return response.data;
}

export default client;
