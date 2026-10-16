"""ZukoAI Python financial intelligence service."""
import os
import re
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="ZukoAI Python Service", version="0.1.0")

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "*").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials="*" not in origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

def require_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("SERVICE_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")

class ExpenseText(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    currency: str = "NGN"

class Transaction(BaseModel):
    amount: float
    category: str = "Uncategorized"
    type: str = "expense"
    description: str = ""
    status: str = "posted"
    is_budget_eligible: bool = True

class InsightRequest(BaseModel):
    transactions: list[Transaction] = Field(default_factory=list)
    budget_limits: dict[str, float] = Field(default_factory=dict)
    currency: str = "NGN"

def categorize(text: str) -> str:
    value = text.lower()
    rules = {
        "Food": ("food", "lunch", "dinner", "breakfast", "rice", "snack", "restaurant", "canteen"),
        "Transport": ("transport", "bus", "keke", "taxi", "uber", "bolt", "fuel", "ride"),
        "Education": ("photocopy", "printing", "textbook", "book", "school", "course", "lab manual"),
        "Housing": ("rent", "hostel", "accommodation"),
        "Utilities": ("electricity", "data", "airtime", "internet", "water"),
        "Health": ("drug", "medicine", "hospital", "clinic"),
        "Shopping": ("shirt", "shoe", "clothes", "shopping"),
    }
    for category, keywords in rules.items():
        if any(word in value for word in keywords):
            return category
    return "Uncategorized"

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "zukoai-python"}

@app.post("/api/expense/parse")
def parse_expense(payload: ExpenseText, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_api_key(x_api_key)
    text = payload.text.strip()
    amount_match = re.search(r"(?<!\w)(\d[\d,]*(?:\.\d{1,2})?)(?!\w)", text)
    amount = float(amount_match.group(1).replace(",", "")) if amount_match else None
    category = categorize(text)
    return {
        "description": text,
        "amount": amount,
        "currency": payload.currency.upper(),
        "category": category,
        "type": "expense",
        "status": "posted",
        "is_budget_eligible": True,
        "needs_review": amount is None or category == "Uncategorized",
    }

@app.post("/api/insights")
def insights(payload: InsightRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_api_key(x_api_key)
    totals: dict[str, float] = defaultdict(float)
    overall = 0.0
    count = 0
    for tx in payload.transactions:
        if tx.status.lower() not in {"posted", "completed", "settled"}:
            continue
        if tx.type.lower() != "expense" or not tx.is_budget_eligible:
            continue
        amount = abs(tx.amount)
        totals[tx.category] += amount
        overall += amount
        count += 1
    category_totals = dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))
    alerts = []
    for category, limit in payload.budget_limits.items():
        spent = category_totals.get(category, 0.0)
        remaining = float(limit) - spent
        if limit >= 0 and spent > limit:
            alerts.append({"type": "over_budget", "category": category, "spent": round(spent, 2), "limit": limit, "remaining": round(remaining, 2)})
        elif limit > 0 and spent / limit >= 0.8:
            alerts.append({"type": "budget_near_limit", "category": category, "spent": round(spent, 2), "limit": limit, "remaining": round(remaining, 2)})
    return {
        "currency": payload.currency.upper(),
        "total_eligible_expenses": round(overall, 2),
        "eligible_transaction_count": count,
        "spend_by_category": {key: round(value, 2) for key, value in category_totals.items()},
        "alerts": alerts,
        "disclaimer": "Insights are informational and do not execute financial transactions.",
    }

@app.get("/api/bmoni/wallets")
def bmoni_wallets(x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_api_key(x_api_key)
    if not os.getenv("BMONI_API_BASE_URL") or not os.getenv("BMONI_API_TOKEN"):
        raise HTTPException(status_code=503, detail="BMONI integration is not configured")
    raise HTTPException(status_code=501, detail="Configure the verified BMONI wallet endpoint before enabling this proxy")

@app.get("/api/bmoni/balances")
def bmoni_balances(x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_api_key(x_api_key)
    if not os.getenv("BMONI_API_BASE_URL") or not os.getenv("BMONI_API_TOKEN"):
        raise HTTPException(status_code=503, detail="BMONI integration is not configured")
    raise HTTPException(status_code=501, detail="Configure the verified BMONI balance endpoint before enabling this proxy")

@app.get("/api/bmoni/transactions")
def bmoni_transactions(x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_api_key(x_api_key)
    raise HTTPException(status_code=501, detail="BMONI transaction-history endpoint has not been verified")
