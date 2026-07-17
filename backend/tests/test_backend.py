from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

sample = {
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

def test_diagnosis():
    r = client.post("/api/diagnosis", json=sample)
    assert r.status_code == 200
    data = r.json()
    assert data["financial_income_tax"]["financial_income"] == 24000000
    assert "recommendations" in data
    assert "scenario_comparison" in data

def test_search_fallback():
    r = client.post("/api/search", json={"message": "금융소득 2천만원 넘으면 어떻게 돼?", "top_k": 3})
    assert r.status_code == 200
    assert len(r.json()["results"]) >= 1

def test_chat_fallback():
    ctx = client.post("/api/diagnosis", json=sample).json()
    r = client.post("/api/chat", json={"message": "연금 분할 수령하면 얼마나 유리해?", "context": ctx, "top_k": 3})
    assert r.status_code == 200
    assert "answer" in r.json()
