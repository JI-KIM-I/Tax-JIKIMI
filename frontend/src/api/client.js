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

export default client;
