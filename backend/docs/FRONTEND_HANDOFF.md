# Frontend Integration Guide (for Upasana)

All 16 endpoints are live. Full contract: `backend/docs/API_CONTRACT.md`.

## Base URL

- Dev: `http://localhost:8000` (uvicorn default)
- Set in frontend `.env.local`: `VITE_API_BASE_URL=http://localhost:8000`

## Endpoint → Screen mapping

| Screen | Endpoint | Method |
|---|---|---|
| Overview | /api/dashboard | GET |
| Transactions | /api/transactions | GET |
| Transactions (add) | /api/transactions | POST |
| Transactions (CSV import) | /api/transactions/upload | POST multipart |
| Cash Flow | /api/cashflow/forecast?days=90 | GET |
| Risk Radar | /api/risk/alerts | GET |
| What-If Simulator | /api/simulator/run | POST |
| AI Copilot (chat) | /api/copilot/chat | POST |
| AI Copilot (chips) | /api/copilot/suggestions | GET |
| Invoices (list) | /api/invoices | GET |
| Invoices (upload) | /api/invoices/upload | POST multipart |
| Invoices (confirm) | /api/invoices/{id}/confirm | POST |
| Invoices (mark paid) | /api/invoices/{id}/mark-paid | POST |
| Receivables | /api/receivables | GET |
| Receivables (mark paid) | /api/receivables/{id}/mark-paid | POST |
| Health check | /api/health | GET |

## Money formatting (critical)

- All money fields are numbers in **rupees** (float or int)
- Format in frontend: `new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR', maximumFractionDigits:0}).format(value)`
- This gives `₹3,42,500` (Indian grouping) — matches existing frontend helper

## Date formatting

- All dates in API are ISO: `"2026-11-19"`
- Format for display: `new Date(iso).toLocaleDateString('en-IN', {day:'2-digit', month:'short', year:'numeric'})` → `19 Nov 2026`

## Chart months

- `cashflow_series` has `actual` (number or null) and `forecast` (number)
- For future months (Dec–Feb), `actual` is `null` — render only the `forecast` line
- Do NOT replace `null` with `0`

## Error handling

- All errors: `{"detail": "message string"}` or `{"detail": [{...validation errors...}]}`
- Show `detail` as a toast; do not parse Pydantic validation arrays for display

## What changes when the user does things

- Mark-paid → dashboard `available_cash` increases, receivables `outstanding_total` decreases
- Upload+confirm → receivables `outstanding_total` increases
- Add transaction → dashboard KPIs update
- Copilot reply → no state change (read-only)

## Known mismatches with mock data

- `projected_30d` in mock was ₹2.18L; real value is ₹1.30L (real forecast)
- `safe_to_spend` in mock was ₹68,000; real value is -₹19,486 (cash-tight scenario)
- `collection_progress_pct` in mock was 62; real value is 63 (correct math)
- These are intentional — the real data is tighter than the mock, which makes the demo more interesting

## Pre-demo

- Backend running: `uvicorn app.main:app --reload` on port 8000
- Fresh DB: `python -m app.seed.seed_data --reset`
- CORS is already configured for localhost:5173 and localhost:4173
