# BMONI sandbox investigation for ZukoAI

**Owner:** Ono (Python workstream)  
**Status:** API documentation reviewed; read-only proxy implemented; live wallet/transaction verification is pending valid sandbox account identifiers and credentials.

## Official references reviewed

- [BMONI Embedded API introduction](https://embedded-docs.bmoni.com/api-reference/introduction/)
- [Sandbox & test tokens](https://embedded-docs.bmoni.com/get-started/sandbox/)
- [Integration flow](https://embedded-docs.bmoni.com/get-started/api-call-sequence/)
- [Business payouts & statements](https://embedded-docs.bmoni.com/api-reference/business-payouts/)
- [Cards guide and card transaction endpoint](https://embedded-docs.bmoni.com/guides/cards/)

## Confirmed API facts

- Development base URL: `https://embedded-dev.bmoni.com`.
- Every request uses `x-api-key: <sandbox/partner key>`.
- User-scoped routes require BMONI's `userId`, not ZukoAI's Supabase user ID.
- Wallet list: `GET /v1/users/{userId}/smart-wallets/account/wallets`.
- Wallet balances: `GET /v1/users/{userId}/smart-wallets/account/balances`.
- Card transactions: `GET /v1/users/{userId}/smart-wallets/{smartWalletId}/cards/{cardId}/transactions`. Documented filters include `size`, `status`, `from`, and `to`.
- Business wallet statement: `GET /v1/users/{userId}/kyb/transactions?currency=...`; supports `from`, `to`, `status`, `page`, and `perPage`.
- The docs say approved sandbox test-token requests are credited manually, typically within one business day, with sample allocation NGN 1,000 and USD 10. Sandbox funds are test-only and resettable. Follow the official sandbox instructions rather than assuming a new account has a balance.
- Provisioning a smart wallet is not a simple server-side GET/POST flow: the official integration flow includes an owner address and signatures from BMONI's embedded SDK.

## Implemented in `main.py`

The service proxies the documented wallet list and balance endpoints and exposes transaction reads for two explicitly supported sources: card transactions and business statements. It keeps the BMONI key on the server, limits the base URL to BMONI's official HTTPS hosts, adds request timeouts, and avoids forwarding arbitrary upstream error bodies.

The current automated tests mock BMONI calls. They validate the proxy route construction and configuration errors but **do not** constitute a live sandbox test.

## Live test checklist

Before testing real records:

1. Obtain or confirm an approved BMONI sandbox key and store it as `BMONI_API_TOKEN` in the backend environment only.
2. Complete the documented sandbox user/wallet setup and record the returned `bmoniUserId`, `smartWalletId`, and (for card-history testing) `cardId`.
3. Confirm the test wallet has test funds if the scenario needs transactions; use BMONI's test-token request process.
4. Call `GET /api/bmoni/users/{user_id}/wallets`, then `/balances`, and compare the sanitized results with BMONI's official API response.
5. If a sandbox card is available, call `/transactions?source=card&smart_wallet_id=...&card_id=...` and compare returned records.
6. If the account is a BMONI business wallet, test `source=business` with a supported currency and a valid ISO-8601 date window.
7. Do not use production users, BVNs/NINs, or real financial data for this hackathon test unless BMONI and the organizers explicitly authorize it.

## Important gap: personal wallet transaction history

The docs reviewed clearly document account wallet balances, card transaction history, and business-wallet statements. They do not establish a universal transaction-history route for a regular personal smart wallet without a card. We should ask BMONI whether the account has an additional ledger/history endpoint and whether the hackathon sandbox exposes it. Until confirmed, don't describe personal wallet transaction syncing as complete.

## Questions for hackathon organizers

The original team task says the hackathon's exact BMONI requirements must be confirmed with organizers. No organizer contact details or official hackathon brief were included in the files available here, so this has **not** been confirmed. Ask:

1. Is BMONI integration mandatory for judging, or is a documented sandbox investigation/demo sufficient?
2. Which product/rail is expected for this use case: embedded smart wallets, cards, employee wallets, or business wallets?
3. Which exact data must be shown: balances, wallet transactions, card transactions, or webhooks?
4. Must the demo use a live BMONI sandbox account, and will organizers provide partner credentials and a pre-provisioned test user?
5. Are there requirements for consent, data retention, attribution, webhook delivery, or a demo video?

## Integration boundary with the Node.js/Supabase workstream

- Node.js/Supabase remains responsible for authentication, user authorization, and securely mapping the signed-in app user to the correct BMONI `userId`.
- The Python service should receive only the BMONI identifier authorized by the Node.js service; never trust an arbitrary `user_id` from a public browser request.
- The frontend should call the team's authenticated Node.js API in production, not store either `SERVICE_API_KEY` or `BMONI_API_TOKEN` in browser code.
- BMONI records should be tagged with source and currency. Do not add amounts across different currencies without a conversion rule, and avoid double-counting the same transaction if it is also saved in Supabase.
