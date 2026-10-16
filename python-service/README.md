# ZukoAI Python Service

A small FastAPI service for expense-text parsing and deterministic budget insights. This is a separate backend workstream and does not replace the existing frontend.

## Local setup

```bash
cd python-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

Health check: `GET /health`. Interactive API docs: `/docs`.

## Endpoints

- `POST /api/expense/parse` — extracts a numeric amount and assigns a simple keyword category.
- `POST /api/insights` — totals eligible posted expenses by category and returns budget threshold alerts.
- `GET /api/bmoni/wallets`, `/api/bmoni/balances`, and `/api/bmoni/transactions` — intentionally return a not-configured/not-implemented response until the actual BMONI API routes and authentication contract are verified.

Set `SERVICE_API_KEY` to require the `X-API-Key` header. Leave it empty only for local development. Configure `CORS_ORIGINS` as a comma-separated list of trusted frontend origins before deployment.

## Important limitations

Expense parsing is rules-based, not an LLM. Review ambiguous results before storing them. Budget insights are informational and do not execute financial transactions. Do not put API secrets in source control. The BMONI routes are placeholders and must not be treated as live wallet integrations until verified against official BMONI documentation.
