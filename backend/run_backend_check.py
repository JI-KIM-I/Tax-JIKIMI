"""백엔드 설치 후 빠른 점검 스크립트."""
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

payload = {
    "age": 45,
    "retirement_age": 60,
    "total_income": 80000000,
    "interest_income": 12000000,
    "dividend_income": 12000000,
    "pension_savings_balance": 25000000,
    "irp_balance": 18000000,
    "expected_pension_amount": 20000000,
    "isa_paid_this_year": 15000000,
    "isa_total_paid": 15000000,
    "pension_savings_paid_this_year": 7200000,
    "irp_paid_this_year": 6000000,
}

res = client.post("/api/diagnosis", json=payload)
print("/api/diagnosis", res.status_code)
print(res.json()["report_summary"])

search = client.post("/api/search", json={"message": "금융소득종합과세 기준이 뭐야?", "top_k": 3})
print("/api/search", search.status_code, "hits:", len(search.json()["results"]))

chat = client.post("/api/chat", json={"message": "연금을 분할로 받으면 세금이 줄어?", "context": res.json(), "top_k": 3})
print("/api/chat", chat.status_code)
print(chat.json()["answer"][:300])
