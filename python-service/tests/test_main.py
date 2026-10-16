import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_health_is_available():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_expense_parse_extracts_ngn_and_category():
    response = client.post("/api/expense/parse", json={"text": "Spent ₦1,250 on lunch", "currency": "NGN"})
    assert response.status_code == 200
    body = response.json()
    assert body["amount"] == 1250.0
    assert body["category"] == "Food"
    assert body["needs_review"] is False


def test_expense_parse_marks_ambiguous_text_for_review():
    response = client.post("/api/expense/parse", json={"text": "paid my friend"})
    assert response.status_code == 200
    assert response.json()["amount"] is None
    assert response.json()["needs_review"] is True


def test_insights_totals_only_posted_eligible_expenses():
    response = client.post(
        "/api/insights",
        json={
            "currency": "NGN",
            "transactions": [
                {"amount": "250.10", "category": "Food", "type": "expense", "status": "posted"},
                {"amount": "100", "category": "Food", "type": "expense", "status": "pending"},
                {"amount": "200", "category": "Transport", "type": "expense", "status": "completed"},
                {"amount": "1000", "category": "Salary", "type": "income", "status": "posted"},
                {"amount": "50", "category": "Food", "type": "expense", "status": "posted", "is_budget_eligible": False},
            ],
            "budget_limits": {"Food": "300", "Transport": "250"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_eligible_expenses"] == 450.1
    assert body["total_recorded_income"] == 1000.0
    assert body["spend_by_category"] == {"Food": 250.1, "Transport": 200.0}
    assert body["budgets"]["Food"]["remaining"] == 49.9
    assert {item["category"] for item in body["alerts"]} == {"Food", "Transport"}


def test_bmoni_not_configured_returns_clear_error(monkeypatch):
    monkeypatch.delenv("BMONI_API_TOKEN", raising=False)
    response = client.get("/api/bmoni/users/example-user/balances")
    assert response.status_code == 503
    assert "BMONI_API_TOKEN" in response.json()["detail"]


def test_bmoni_balances_calls_documented_endpoint(monkeypatch):
    monkeypatch.setenv("BMONI_API_TOKEN", "test-key")
    mocked = AsyncMock(return_value={"balances": []})
    with patch.object(main, "bmoni_get", mocked):
        response = client.get("/api/bmoni/users/example-user/balances")
    assert response.status_code == 200
    mocked.assert_awaited_once_with("/v1/users/example-user/smart-wallets/account/balances")


def test_card_transactions_require_wallet_and_card_ids():
    response = client.get("/api/bmoni/users/example-user/transactions?source=card")
    assert response.status_code == 422
