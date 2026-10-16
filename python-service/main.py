"""ZukoAI Python financial intelligence and BMONI read-only proxy."""
from __future__ import annotations

import os
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal
from urllib.parse import quote, urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

app = FastAPI(
    title="ZukoAI Python Service",
    description="Expense parsing, student-budget insights, and read-only BMONI sandbox data access.",
    version="0.2.0",
)

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or [],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


def require_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("SERVICE_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid service API key")


def money(value: Decimal | float | int) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class ExpenseText(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    currency: str = Field(default="NGN", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isalpha():
            raise ValueError("currency must be a 3-letter currency code")
        return value


class Transaction(BaseModel):
    amount: Decimal = Field(ge=0, le=Decimal("1000000000000"))
    category: str = Field(default="Uncategorized", min_length=1, max_length=80)
    type: Literal["expense", "income", "transfer"] = "expense"
    description: str = Field(default="", max_length=500)
    status: str = Field(default="posted", max_length=40)
    is_budget_eligible: bool = True

    @field_validator("amount")
    @classmethod
    def amount_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("amount must be finite")
        return value


class InsightRequest(BaseModel):
    transactions: list[Transaction] = Field(default_factory=list, max_length=10000)
    budget_limits: dict[str, Decimal] = Field(default_factory=dict)
    currency: str = Field(default="NGN", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isalpha():
            raise ValueError("currency must be a 3-letter currency code")
        return value


CATEGORY_RULES: dict[str, tuple[str, ...]] = {
    "Food": ("food", "lunch", "dinner", "breakfast", "rice", "snack", "restaurant", "canteen", "suya", "shawarma", "groceries", "bread"),
    "Transport": ("transport", "bus", "keke", "taxi", "uber", "bolt", "fuel", "ride", "danfo", "okada", "fare"),
    "Education": ("photocopy", "printing", "textbook", "book", "school", "course", "lab manual", "tuition", "lecture", "assignment"),
    "Housing": ("rent", "hostel", "accommodation", "lodging"),
    "Utilities": ("electricity", "data", "airtime", "internet", "water", "subscription", "wifi"),
    "Health": ("drug", "medicine", "hospital", "clinic", "pharmacy", "doctor"),
    "Shopping": ("shirt", "shoe", "clothes", "shopping", "bag", "accessory"),
    "Entertainment": ("movie", "cinema", "game", "concert", "netflix", "spotify"),
    "Personal Care": ("haircut", "salon", "barber", "soap", "toiletries"),
}


def categorize(text: str) -> str:
    value = text.casefold()
    for category, keywords in CATEGORY_RULES.items():
        if any(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", value) for word in keywords):
            return category
    return "Uncategorized"


def extract_amount(text: str) -> Decimal | None:
    """Extract a currency amount while avoiding digits embedded in words."""
    normalized = text.replace("\u00a0", " ")
    patterns = (
        r"(?:₦|NGN\s*)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?:\$|USD\s*)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?:€|EUR\s*)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?:£|GBP\s*)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?<![\w.])([0-9][0-9,]*(?:\.[0-9]{1,2})?)(?![\w.])",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            try:
                amount = Decimal(match.group(1).replace(",", ""))
                if amount.is_finite() and amount >= 0:
                    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except InvalidOperation:
                return None
    return None


def bmoni_config() -> tuple[str, str]:
    base_url = os.getenv("BMONI_API_BASE_URL", "https://embedded-dev.bmoni.com").rstrip("/")
    api_key = os.getenv("BMONI_API_TOKEN", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="BMONI is not configured. Set BMONI_API_TOKEN in the server environment; never expose it in frontend code.",
        )
    parsed_base = urlparse(base_url)
    if parsed_base.scheme != "https" or parsed_base.hostname not in {"embedded-dev.bmoni.com", "embedded.bmoni.com"}:
        raise HTTPException(status_code=503, detail="BMONI base URL must be the official HTTPS development or production host.")
    return base_url, api_key


async def bmoni_get(path: str, params: dict[str, Any] | None = None) -> Any:
    base_url, api_key = bmoni_config()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            response = await client.get(
                f"{base_url}{path}",
                headers={"x-api-key": api_key, "Accept": "application/json"},
                params=params,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="BMONI sandbox request timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not connect to BMONI") from exc

    if response.status_code in (401, 403):
        raise HTTPException(status_code=502, detail="BMONI rejected the configured API key; verify it is valid for this environment.")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="BMONI resource was not found; verify the BMONI user/wallet IDs and endpoint prerequisites.")
    if response.status_code == 429:
        raise HTTPException(status_code=503, detail="BMONI rate limit reached; retry later.")
    if response.status_code >= 500:
        raise HTTPException(status_code=502, detail="BMONI returned a server error.")
    if not response.is_success:
        raise HTTPException(status_code=400, detail=f"BMONI rejected the read request (HTTP {response.status_code}); check query parameters and account eligibility.")
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="BMONI returned a non-JSON response.") from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "zukoai-python", "version": app.version}


@app.post("/api/expense/parse")
def parse_expense(payload: ExpenseText, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_api_key(x_api_key)
    text = payload.text.strip()
    amount = extract_amount(text)
    category = categorize(text)
    return {
        "description": text,
        "amount": money(amount) if amount is not None else None,
        "currency": payload.currency,
        "category": category,
        "type": "expense",
        "status": "posted",
        "is_budget_eligible": True,
        "needs_review": amount is None or category == "Uncategorized",
        "parser": "rules-v1",
    }


@app.post("/api/insights")
def insights(payload: InsightRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_api_key(x_api_key)
    totals: dict[str, Decimal] = defaultdict(Decimal)
    overall = Decimal("0")
    count = 0
    income = Decimal("0")
    eligible_statuses = {"posted", "completed", "settled", "success"}
    for tx in payload.transactions:
        if tx.status.casefold() not in eligible_statuses:
            continue
        amount = abs(tx.amount)
        if tx.type == "income":
            income += amount
            continue
        if tx.type != "expense" or not tx.is_budget_eligible:
            continue
        totals[tx.category] += amount
        overall += amount
        count += 1

    category_totals = dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))
    alerts: list[dict[str, Any]] = []
    budget_summary: dict[str, Any] = {}
    for category, limit in payload.budget_limits.items():
        if not limit.is_finite() or limit < 0:
            raise HTTPException(status_code=422, detail=f"Budget limit for {category!r} must be a finite non-negative number.")
        spent = category_totals.get(category, Decimal("0"))
        remaining = limit - spent
        percent = (spent / limit * 100) if limit > 0 else (Decimal("100") if spent > 0 else Decimal("0"))
        budget_summary[category] = {
            "spent": money(spent),
            "limit": money(limit),
            "remaining": money(remaining),
            "percent_used": money(percent),
        }
        if limit > 0 and spent > limit:
            alerts.append({"type": "over_budget", "category": category, "spent": money(spent), "limit": money(limit), "remaining": money(remaining)})
        elif limit > 0 and percent >= 80:
            alerts.append({"type": "budget_near_limit", "category": category, "spent": money(spent), "limit": money(limit), "remaining": money(remaining)})

    top_category = next(iter(category_totals), None)
    suggestions: list[str] = []
    if top_category:
        suggestions.append(f"{top_category} is your highest recorded spending category; review recent purchases there for possible savings.")
    if income > 0 and overall > income:
        suggestions.append("Recorded expenses exceed recorded income for this dataset. Check that all amounts and transaction types are correct.")
    if alerts:
        suggestions.append("At least one category is near or over its budget; consider pausing non-essential spending in those categories.")
    if not payload.transactions:
        suggestions.append("Add or sync transactions to get personalized spending insights.")

    return {
        "currency": payload.currency,
        "total_eligible_expenses": money(overall),
        "total_recorded_income": money(income),
        "net_recorded_cashflow": money(income - overall),
        "eligible_transaction_count": count,
        "spend_by_category": {key: money(value) for key, value in category_totals.items()},
        "budgets": budget_summary,
        "alerts": alerts,
        "suggestions": suggestions,
        "disclaimer": "Insights are informational estimates based only on the transactions supplied; they are not financial advice.",
    }


@app.get("/api/bmoni/users/{user_id}/wallets")
async def bmoni_wallets(user_id: str, x_api_key: str | None = Header(default=None)) -> Any:
    require_api_key(x_api_key)
    return await bmoni_get(f"/v1/users/{quote(user_id, safe='')}/smart-wallets/account/wallets")


@app.get("/api/bmoni/users/{user_id}/balances")
async def bmoni_balances(user_id: str, x_api_key: str | None = Header(default=None)) -> Any:
    require_api_key(x_api_key)
    return await bmoni_get(f"/v1/users/{quote(user_id, safe='')}/smart-wallets/account/balances")


@app.get("/api/bmoni/users/{user_id}/transactions")
async def bmoni_transactions(
    user_id: str,
    source: Literal["card", "business"] = Query(description="Use 'card' for card transactions or 'business' for a business wallet statement."),
    smart_wallet_id: str | None = None,
    card_id: str | None = None,
    currency: str = "NGN",
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    size: int = Query(default=50, ge=1, le=100),
    x_api_key: str | None = Header(default=None),
) -> Any:
    """Read transactions using an explicitly documented BMONI ledger source."""
    require_api_key(x_api_key)
    encoded_user = quote(user_id, safe="")
    if source == "business":
        params: dict[str, Any] = {"currency": currency.upper(), "page": page, "perPage": per_page}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if status:
            params["status"] = status
        return await bmoni_get(f"/v1/users/{encoded_user}/kyb/transactions", params=params)

    if not smart_wallet_id or not card_id:
        raise HTTPException(status_code=422, detail="For source=card, smart_wallet_id and card_id are required.")
    params = {"size": size}
    if status:
        params["status"] = status
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    return await bmoni_get(
        f"/v1/users/{encoded_user}/smart-wallets/{quote(smart_wallet_id, safe='')}/cards/{quote(card_id, safe='')}/transactions",
        params=params,
    )
