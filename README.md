# 세금지킴이 (Tax-JIKIMI)

KB국민은행 AI 챌린지 출품작. 은퇴 전후 중장년층을 위한 AI 기반 세금 최적화 서비스입니다.
금융소득종합과세·연금 수령 전략·ISA/연금저축/IRP 절세 한도 활용을 한 번에 진단하고,
RAG 챗봇으로 자연어 상담까지 지원합니다.

- GitHub: https://github.com/JI-KIM-I/Tax-JIKIMI
- 팀명: 지킴(JIKIM) — 강지호 · 박지연 · 정윤성

## 핵심 설계 원칙

계산 정확도(룰 엔진)와 설명(LLM/RAG 챗봇)의 역할을 분리했습니다.

- **계산**: `backend/taxguard_calculation_logic.py`의 규칙 기반 계산 엔진이 담당 (금융소득종합과세, 연금 일시금/분할 수령 비교, 연금 수령 시점 추천, 절세 한도 활용률 등)
- **설명·상담**: OpenAI 기반 RAG 챗봇이 계산 결과와 국세청·법령 문서를 결합해 자연어로 안내

## 기술 스택

| 영역 | 스택 |
| --- | --- |
| 프론트엔드 | React + Vite |
| 백엔드 | FastAPI (Python 3.12+) |
| RAG | ChromaDB + OpenAI (`text-embedding-3-small`, `gpt-4o-mini`) |
| DB | MongoDB Atlas |
| 인증 | JWT + bcrypt |
| 리포트 | reportlab (PDF, 한글 폰트 NanumGothic) |
| 배포 | 프론트 Vercel / 백엔드 Render |

## 폴더 구조

```
Tax-JIKIMI/
├── backend/
│   ├── main.py                        # FastAPI 앱, API 엔드포인트
│   ├── taxguard_calculation_logic.py  # 세금 계산 로직 (핵심 엔진)
│   ├── auth.py                        # 회원가입/로그인/JWT
│   ├── db.py                          # MongoDB 연결
│   ├── rag/                           # RAG 검색·임베딩·문서 로더
│   ├── fonts/                         # PDF 한글 폰트
│   └── tests/                         # 백엔드 테스트
└── frontend/
    └── src/
        ├── components/                # DiagnosisForm, ChatWidget, 결과 탭 등
        ├── api/                       # 백엔드 API 클라이언트
        └── utils/                     # 자연어 엔티티 추출 등
```

## 로컬 실행 방법

### 1. 백엔드 (FastAPI)

```bash
cd backend
cp ../.env.example .env   # 값 채워넣기 (아래 환경변수 참고)
pip install -r requirements.txt
# 또는 uv 사용 시: uv sync

python rag/build_index.py  # RAG 벡터 인덱스 최초 1회 빌드
uvicorn main:app --reload
```

기본적으로 `http://localhost:8000`에서 API가 뜹니다.

### 2. 프론트엔드 (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

기본적으로 `http://localhost:5173`에서 접속 가능합니다. 백엔드 API 주소는
`VITE_API_BASE_URL` 환경변수로 지정합니다 (미설정 시 로컬 기본값으로 폴백).

## 환경변수

`.env.example` 참고. 백엔드 루트(`backend/.env`)에 아래 값을 채워 넣어야 합니다.

| 변수 | 설명 |
| --- | --- |
| `MONGODB_URI` | MongoDB Atlas 연결 문자열 |
| `MONGODB_DB` | 사용할 DB 이름 (기본 `TAX-JIKIMI`) |
| `JWT_SECRET` | JWT 서명 키 |
| `JWT_ALGORITHM` | JWT 알고리즘 (기본 `HS256`) |
| `OPENAI_API_KEY` | RAG 챗봇용 OpenAI API 키 |
| `OPENAI_MODEL` | 사용할 OpenAI 모델명 |
| `CORS_ORIGINS` | 허용할 프론트엔드 origin (콤마 구분) |

> `.env` 파일과 실제 API 키는 절대 저장소에 커밋하지 않습니다 (`.gitignore`에 이미 제외 처리됨).

## 주요 API

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/diagnosis` | 통합 절세 진단 |
| POST | `/api/diagnosis/comprehensive-tax` | 금융소득종합과세 진단 |
| POST | `/api/pension/withdrawal-comparison` | 연금 일시금 vs 분할 수령 세액 비교 |
| POST | `/api/pension/timing-recommendation` | 연금 수령 시점 추천 (NPV 기반) |
| POST | `/api/tax-saving/utilization` | ISA·연금저축·IRP 절세 한도 활용 가이드 |
| POST | `/api/report/export` | 진단 결과 PDF 리포트 출력 |
| POST | `/api/chat` | RAG 기반 챗봇 질의응답 |

## 라이선스

`LICENSE` 파일 참고.
