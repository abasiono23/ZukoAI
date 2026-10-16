# ZukoAI Python Service

FastAPI service for Ono's ZukoAI workstream: expense-text parsing, student-budget insights, and a read-only BMONI API proxy. It is designed to sit beside the existing frontend and Node.js/Supabase service; it does not replace either one.

## Local setup

```bash
cd python-service
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

The app reads environment variables from the process; it does not automatically load `.env`. For local use, export the variables in your shell or load `.env` with your preferred local environment tool.

- Health: `GET http://localhost:8000/health`
- Interactive API docs: `http://localhost:8000/docs`
- Automated tests: `pip install -r requirements-dev.txt && pytest -q`

Set `SERVICE_API_KEY` in deployment and send it as `X-API-Key` for all `/api/*` routes. Keep it and the BMONI API key server-side only. Configure `CORS_ORIGINS` as a comma-separated list of exact trusted frontend origins.

## Expense parsing

`POST /api/expense/parse`

```json
{
  "text": "Spent ₦1,250 on lunch",
  "currency": "NGN"
}
```

The response includes a normalized amount, currency, keyword-based category, and `needs_review`. This is deterministic rule-based parsing, not an LLM; unknown or ambiguous entries are flagged for review rather than silently treated as certain.

## Financial insights

`POST /api/insights`

```json
{
  "currency": "NGN",
  "transactions": [
    {
      "amount": "1250.00",
      "category": "Food",
      "type": "expense",
      "description": "Lunch",
      "status": "posted",
      "is_budget_eligible": true
    },
    {
      "amount": "50000",
      "category": "Income",
      "type": "income",
      "description": "Allowance",
      "status": "posted",
      "is_budget_eligible": false
    }
  ],
  "budget_limits": {
    "Food": "10000"
  }
}
```

The response contains eligible expenses by category, recorded income and net cashflow, per-category budget progress, 80% budget warnings, over-budget alerts, and simple suggestions. Only transactions in `posted`, `completed`, `settled`, or `success` status count; pending transactions are excluded. Expenses marked `is_budget_eligible: false` are excluded from budget totals.

The endpoint is stateless: the Node.js/Supabase service or frontend must pass the authenticated user's authorized transaction data. Do not let a client submit another user's records. Amounts are processed with `Decimal` before values are serialized to JSON.

## BMONI sandbox read endpoints

The BMONI key is read from `BMONI_API_TOKEN` and sent upstream as `x-api-key`. The default base URL is `https://embedded-dev.bmoni.com`; never use production credentials against the sandbox or expose the key in frontend code.

| ZukoAI endpoint | BMONI endpoint | Purpose |
| --- | --- | --- |
| `GET /api/bmoni/users/{user_id}/wallets` | `GET /v1/users/{userId}/smart-wallets/account/wallets` | List a user's smart wallets |
| `GET /api/bmoni/users/{user_id}/balances` | `GET /v1/users/{userId}/smart-wallets/account/balances` | Read balances |
| `GET /api/bmoni/users/{user_id}/transactions?source=card&smart_wallet_id=...&card_id=...` | `GET /v1/users/{userId}/smart-wallets/{smartWalletId}/cards/{cardId}/transactions` | Read card transactions |
| `GET /api/bmoni/users/{user_id}/transactions?source=business&currency=MXN` | `GET /v1/users/{userId}/kyb/transactions?currency=...` | Read a business-wallet statement |

Transaction query parameters supported by the proxy:
- `source=card`: requires `smart_wallet_id` and `card_id`; supports `size` (1–100), `status`, `from`, and `to`.
- `source=business`: supports `currency`, `from`, `to`, `status`, `page`, and `per_page`. BMONI documents ISO-8601 `from`/`to` timestamps with a timezone and a maximum 366-day window for business statements.

These are read-only proxy routes. They do not create users, perform KYC, provision wallets, move money, or sign transactions. BMONI's wallet balance routes require the BMONI `userId`; wallet creation and some onboarding flows also require the embedded SDK to generate/sign owner proofs. Do not substitute the ZukoAI/Supabase user ID for BMONI's user ID unless a verified mapping exists in the Node.js backend.

**Important transaction-history limitation:** the official documentation reviewed confirms a smart-wallet account balance/list API, a card transaction endpoint, and a business-wallet statement endpoint. It does not establish a universal personal smart-wallet transaction-history endpoint for an ordinary student wallet. For personal accounts without a card, confirm the intended ledger endpoint with BMONI before claiming complete transaction syncing.

See [`BMONI_SANDBOX_INVESTIGATION.md`](BMONI_SANDBOX_INVESTIGATION.md) for the API investigation, prerequisites, and hackathon questions to confirm.

## Environment variables

- `SERVICE_API_KEY`: shared secret between trusted backend callers and this service.
- `CORS_ORIGINS`: comma-separated frontend origins.
- `BMONI_API_BASE_URL`: official BMONI development host by default.
- `BMONI_API_TOKEN`: BMONI partner/sandbox API key. Never commit a real key.

## Limitations / integration contract

- This service does not connect to Supabase directly. Keep auth, authorization, and user-to-BMONI-ID mapping in the Node.js/Supabase service unless the team explicitly agrees on another contract.
- The parser is a rules-based baseline, not an LLM. A hosted language model can be added later behind a server-side provider key if the hackathon expects generative AI.
- Insights are descriptive and depend on the transaction records and budgets supplied. They are not financial advice.
- Live BMONI verification requires a valid sandbox API key and real sandbox user/wallet/card identifiers. Automated tests mock the upstream response and do not claim a live sandbox call succeeded.
