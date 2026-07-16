import axios from "axios";

// 백엔드(FastAPI) 서버 주소. uvicorn 기본 포트인 8000을 그대로 사용합니다.
// 배포 시에는 실제 서버 주소로 바꿔주세요 (예: 환경변수로 분리).
const BASE_URL = "http://localhost:8000";

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 10000,
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
  // LLM 응답은 계산 API보다 오래 걸릴 수 있어 타임아웃을 늘려서 별도 호출합니다.
  const response = await client.post(
    "/api/chat",
    { message, context, top_k: topK },
    { timeout: 30000 }
  );
  return response.data;
}

export default client;
