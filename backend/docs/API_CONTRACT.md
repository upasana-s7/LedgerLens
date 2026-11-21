# LedgerLens — API Contract

The single source of truth for the shape of every API response. The React
frontend and the FastAPI backend both build against this document.

**Status:** Stage 1. Only `GET /api/health` is live; every other route exists
but returns `501 Not Implemented` until its stage.

---

## Conventions (read this first)

**Sample data is fictional.** The demo business is "Bloom & Bean", a small
Bengaluru café. Every name, invoice and number is made up for demonstration.

**Money is a number, in rupees.** `342500` means ₹3,42,500. No `₹`, no commas,
no `"3.4L"` — the API always sends a plain JSON number. The frontend adds the
symbol and Indian (`en-IN`) digit grouping, e.g. with
`Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" })`.

> The one deliberate exception is `risk.alerts[].metric`. It is a
> **pre-formatted display string** such as `"₹85,000"`, `"+12%"` or
> `"90 days"`, because it mixes money, percentages and durations in a single
> badge. Render it as-is; do not re-format it.

**Dates are ISO `YYYY-MM-DD` strings** (`"2026-11-19"`). They sort and compare
correctly as plain strings, and JavaScript's `new Date(iso)` parses them
reliably. The frontend formats them for display (`"19 Nov 2026"`).

**Chart months carry `month_iso`.** Every point in a cash-flow series has a
short `month` label for the axis (`"Jun"`) **and** a `month_iso`
(`"2026-06"`) for keys, sorting and tooltips.

**`actual` is `null` for future months — never `0`.** A month that has not
happened has no actual value. Sending `0` would draw the line down to zero.
Keep `connectNulls={false}` in Recharts so the actual line stops where the data
stops.

**Amounts are signed, and `type` always matches the sign.** Income is positive
(`48500`, `type: "income"`); expenses are negative (`-22000`,
`type: "expense"`). Never send a negative income or a positive expense.

**Errors use `{"detail": "..."}`** with a 4xx/5xx code. That is FastAPI's
standard shape, so the frontend can always read `error.detail` for a message.

| Code | Meaning here |
| --- | --- |
| 400 | Bad input that validation did not catch (e.g. malformed CSV) |
| 404 | Unknown id (e.g. `INV-999`) |
| 409 | Conflict with current state (e.g. invoice is already Paid) |
| 422 | Request body failed Pydantic validation (wrong type, out of range) |
| 501 | Route exists but is not built yet (Stage 1 placeholders) |

**IDs are strings**, human-readable: `TXN-1048`, `INV-204`, `RISK-1`. They are
never integers, so the frontend must not do arithmetic on them.

**`tone` is a design token, not a colour code.** Values are `green`, `sage`,
`amber`, `coral`, matching the CSS variables `--color-forest`,
`--color-sage`, `--color-amber`, `--color-coral`. The frontend maps them to
classes.

---

## Health

### `GET /api/health` — ✅ live

```json
{ "status": "ok", "service": "LedgerLens API", "version": "0.1.0" }
```

---

## Dashboard

### `GET /api/dashboard` — Stage 3

Everything the Overview screen needs in one request: identity, KPI cards, the
cash-flow chart, the AI CFO card, risk highlights and recent activity.

```json
{
  "workspace": {
    "name": "Bloom & Bean",
    "type": "Small business",
    "city": "Bengaluru",
    "is_sample_data": true
  },
  "period": { "label": "Nov 2026", "start": "2026-11-01", "end": "2026-11-30" },
  "as_of_date": "2026-11-19",
  "kpis": {
    "available_cash": {
      "value": 342500, "change": "+8.2%", "note": "vs. last month", "tone": "green"
    },
    "projected_30d": {
      "value": 130513.34, "change": "Based on forecast", "note": "estimated closing balance", "tone": "amber"
    },
    "overdue_receivables": {
      "value": 85000, "change": "2 invoices", "note": "awaiting payment", "tone": "amber"
    },
    "safe_to_spend": {
      "value": -19486.66, "change": "After commitments", "note": "available for decisions", "tone": "coral"
    }
  },
  "cashflow_series": [
    { "month": "Jun", "month_iso": "2026-06", "actual": 310000, "forecast": 310000 },
    { "month": "Dec", "month_iso": "2026-12", "actual": null,   "forecast": 298000 }
  ],
  "series_range_label": "Jun 2026 — Feb 2027",
  "insight": "string (deterministic template text)",
  "ai_cfo": {
    "tag": "CASH FLOW WATCH",
    "title": "string",
    "body": "string",
    "updated_at": "ISO datetime",
    "source": "rules|gemini"
  },
  "risk_items": [
    { "tone": "coral|amber|sage", "title": "string", "detail": "string" }
  ],
  "recent_transactions": [ { "...": "Transaction, 4 items" } ]
}
```

*(Illustrative values from the seeded dataset. The dashboard delegates to the same forecast engine that powers /api/cashflow/forecast, so values stay consistent across views.)*

Notes:

- `kpis.*.value` is a **number** (format with `money()`). `change`, `note`,
  `tone` are display strings chosen by the backend, ready to print.
- `tone` is one of `green`, `sage`, `amber`, `coral`.
- `cashflow_series` is the same shape used by `/api/cashflow/forecast`.
- `ai_cfo.source` is `"rules"` when Gemini is unavailable or disabled, and
  `"gemini"` when the text was written by the model. The numbers are identical
  either way — Gemini only writes prose.
- `insight` is a deterministic template string, not AI output.

### Transaction

```json
{
  "id": "TXN-1048",
  "name": "Aarav Foods — bulk order",
  "category": "Sales",
  "date": "2026-11-19",
  "amount": 48500,
  "type": "income"
}
```

`category` is one of `Sales`, `Inventory`, `Rent`, `Utilities`, `Payroll`,
`General`. `type` is `income` or `expense` and always matches the sign of
`amount`.

---

## Transactions

### `GET /api/transactions` — Stage 3

| Query | Type | Default | Notes |
| --- | --- | --- | --- |
| `q` | string | — | Free text over `name` and `category` |
| `type` | `all` \| `income` \| `expense` | `all` | |
| `category` | string | — | Exact category match |
| `from` | ISO date | — | Inclusive start |
| `to` | ISO date | — | Inclusive end |
| `page` | int | `1` | 1-based |
| `limit` | int | `50` | Max 200 |

```json
{
  "total": 5,
  "page": 1,
  "limit": 50,
  "items": [ { "...": "Transaction, newest first" } ]
}
```

`total` is the count **after filtering**, not the page size.

### `POST /api/transactions` — Stage 3 → `201`

Request:

```json
{
  "name": "Aarav Foods — bulk order",
  "amount": 48500,
  "type": "income",
  "category": "optional",
  "date": "optional ISO date"
}
```

Response: the created `Transaction`.

The client sends a **positive** `amount` and a `type`. The backend applies the
sign (negative for `expense`), picks the next `TXN-####` id and defaults
`date`/`category` when omitted.

### `POST /api/transactions/upload` — Stage 3

`multipart/form-data` with a single field `file` (a `.csv`).

```json
{
  "imported": 12,
  "skipped": 1,
  "rows": [ { "...": "Transaction" } ],
  "errors": [ { "row": 7, "message": "amount is not a number" } ]
}
```

`errors[].row` is the **1-based CSV line number**. A row that fails validation
is skipped; the rest still import. Partial success is normal, not an error
response.

---

## Cash flow

### `GET /api/cashflow/forecast?days=90` — Stage 4

`days` accepts `30`–`180` (default `90`); anything outside that returns **422**.

```json
{
  "opening_balance": 342500,
  "inflows_30d": 338998.67,
  "outflows_30d": 550985.33,
  "series": [
    { "month": "Jun", "month_iso": "2026-06", "actual": 310000, "forecast": 310000 },
    { "month": "Nov", "month_iso": "2026-11", "actual": 342500, "forecast": 342500 },
    { "month": "Dec", "month_iso": "2026-12", "actual": null,   "forecast": 115118.67 },
    { "month": "Feb", "month_iso": "2027-02", "actual": null,   "forecast": 186928.23 }
  ],
  "daily_series": [
    { "date": "2026-11-20", "balance": 343717.11 },
    { "date": "2027-02-17", "balance": 173540.01 }
  ],
  "range_label": "Jun 2026 — Feb 2027",
  "commitments": [
    { "label": "Monthly rent", "amount": 22000, "date": "2026-12-01" }
  ],
  "assumptions": [
    "Baseline daily net flow: Rs 1,217 (derived from 90-day historical average; already includes typical rent, payroll, EMI, utilities and vendor payments)",
    "Scheduled commitments are applied as lump-sum outflows on their due dates (conservative upper bound on near-term outflows)",
    "Safety buffer: Rs 150,000",
    "Projection horizon: 90 days",
    "Model intentionally overstates near-term outflows because historical recurring payments are also averaged in the baseline"
  ],
  "lowest_balance": { "value": 111467.34, "date": "2026-12-28" },
  "shortfall_date": "2026-12-07",
  "is_sample_data": true
}
```

*(Forecast model: historical 90-day averages + scheduled commitments + probability-weighted AR collections. Values shown are illustrative from the seeded dataset.)*

- `opening_balance` is cash at the **start of the projection** (today), the same
  figure the dashboard shows as available cash — not the pre-history opening
  balance.
- `outflows_30d` is a **positive number** describing money going out, even
  though transaction amounts for expenses are negative.
- `inflows_30d` / `outflows_30d` always cover the first 30 days of the
  projection, whatever `days` was requested, and are built from the same daily
  model as `daily_series`: `outflows_30d` = 30 days of routine outflow **plus**
  the commitments due in those 30 days, so the two numbers still net to the
  change in balance.
- The model is one 90-day average **net** flow per day, plus commitments as
  lump sums on their due dates. Recurring payments therefore count twice (once
  in the average, once as a commitment) - a deliberate, conservative
  overstatement of near-term outflows. Pending invoices are not added as
  separate probability-weighted collections, because their past payments are
  already inside the average.
- The dashboard's `kpis.projected_30d.value` is this same payload's day-30
  balance (`days=30`), so the two screens can never disagree.
- `series` has the same shape as the dashboard's `cashflow_series`: nine points,
  `actual` is `null` for months that have not happened. The three future points
  are read off the daily projection, so they reflect commitments and
  collections rather than one flat step.
- `daily_series` has exactly `days` points, starting `2026-11-20`.
- `lowest_balance` is the lowest point of `daily_series` (ties go to the earlier
  date). `shortfall_date` is the **first** day whose balance drops below the
  ₹1,50,000 safety buffer, or `null` when the buffer is never breached.
- `commitments` are known upcoming payments (rent, payroll, loan EMIs) that
  the forecast already accounts for. `amount` is positive; the list is sorted by
  date.
- `assumptions` are short, human-readable lines shown under the chart.

---

## What-If simulator

### `POST /api/simulator/run` — Stage 5

Request:

```json
{ "purchase_amount": 50000, "revenue_uplift_pct": 15 }
```

| Field | Range | UI control |
| --- | --- | --- |
| `purchase_amount` | `10000`–`200000`, step `5000` | purchase slider |
| `revenue_uplift_pct` | `0`–`40`, step `1` | uplift slider |

Response:

```json
{
  "base_balance": 130513.34,
  "scenario_cost": 50000.0,
  "additional_revenue": 5477.0,
  "projected_balance": 85990.34,
  "verdict": "caution",
  "verdict_label": "Proceed with caution",
  "threshold": 225000.0,
  "explanation": "This Rs 50,000 purchase would push your projected 30-day balance to Rs 85,990, below the Rs 225,000 comfort threshold. Even with a 15% revenue uplift contributing about Rs 5,477, the buffer would not hold. Consider a smaller purchase, or wait until overdue invoices are collected.",
  "explanation_source": "rules"
}
```

- Values outside the ranges return **422**.
- `base_balance` comes from the forecast engine, never a hardcode, so the
  simulator and the cash-flow chart can never disagree.
- `projected_balance` =
  `base_balance − scenario_cost + additional_revenue`, computed in Python.
- `verdict` compares `projected_balance` against `threshold`, which is 1.5x
  the ₹1,50,000 safety buffer (₹2,25,000). `verdict_label` is the ready-to-show
  text: "Comfortably affordable" or "Proceed with caution".
- `explanation_source` is `"rules"` unless Gemini wrote the text.

---

## Copilot

### `POST /api/copilot/chat` — Stage 8

Request:

```json
{
  "message": "Can I afford ₹50,000 of new inventory?",
  "history": [
    { "role": "user", "text": "How much is overdue?" },
    { "role": "assistant", "text": "₹85,000 across 2 invoices." }
  ]
}
```

Response:

```json
{
  "reply": "string",
  "suggested_questions": ["string"],
  "citations": [
    { "kind": "invoice|transaction|alert", "id": "INV-204", "label": "Aarav Foods · ₹52,000" }
  ],
  "source": "gemini|fallback"
}
```

- `history` is the last few turns only; the backend trims long histories.
- `citations` point at real records the reply relied on. `label` is
  pre-formatted for display.
- `source` is `"fallback"` when `GEMINI_API_KEY` is missing or the call fails.
  The reply is still useful and still uses verified numbers, so the UI should
  not show an error for a fallback.

### `GET /api/copilot/suggestions` — Stage 8

```json
{
  "chips": [
    "Can I afford new inventory?",
    "What needs my attention?",
    "How much is overdue?"
  ],
  "panel": [
    "Can I afford a ₹50,000 inventory order?",
    "Which invoices should I follow up on?",
    "What is changing my cash position?"
  ]
}
```

`chips` are the short buttons above the input; `panel` fills the empty state.

---

## Invoices

### Invoice

```json
{
  "id": "INV-204",
  "client": "Aarav Foods",
  "due_date": "2026-11-12",
  "amount": 52000,
  "status": "Overdue|Pending|Paid",
  "days_overdue": 7
}
```

`days_overdue` is `0` for anything not overdue. `status` is derived by the
backend from `due_date` and the payment state — the client never computes it.

### `GET /api/invoices` — Stage 7

```json
{
  "summary": {
    "total_outstanding": 109500,
    "outstanding_count": 3,
    "overdue_total": 85000,
    "collected_this_month": 184000
  },
  "items": [ { "...": "Invoice" } ]
}
```

`total_outstanding` and `overdue_total` cover **unpaid** invoices only.
`collected_this_month` is money actually received this month.

### `POST /api/invoices/upload` — Stage 9 → `201`

`multipart/form-data` with `file`: `pdf`, `png`, `jpg` or `jpeg`. Other types
return **400**.

```json
{
  "id": "INV-212",
  "status": "Draft",
  "fields": {
    "client": "",
    "due_date": "",
    "amount": 0,
    "invoice_number": ""
  },
  "confidence": 0.82,
  "warnings": ["string"]
}
```

The extracted fields are a **suggestion**, not truth. The UI must let the user
correct them and then call `/confirm`. `confidence` is `0.0`–`1.0`;
`warnings` lists anything the extractor was unsure about.

### `POST /api/invoices/{id}/confirm` — Stage 9

Request:

```json
{
  "client": "Aarav Foods",
  "due_date": "2026-12-05",
  "amount": 52000,
  "invoice_number": "INV-212"
}
```

Response:

```json
{
  "id": "INV-212",
  "status": "Pending",
  "invoice": { "...": "Invoice" }
}
```

Confirms a `Draft` invoice and makes it `Pending`. Unknown id → **404**.

### `POST /api/invoices/{id}/mark-paid` — Stage 7

Also available as `POST /api/receivables/{id}/mark-paid` — identical behaviour,
same handler, so the Receivables screen and the Invoices screen agree.

```json
{
  "id": "INV-204",
  "status": "Paid",
  "paid_at": "2026-11-20",
  "outstanding_total": 57500,
  "overdue_count": 0
}
```

- Unknown id → **404**.
- Already `Paid` → **409** (`{"detail": "Invoice INV-204 is already paid"}`).
- `outstanding_total` and `overdue_count` are the **post-update** totals, so
  the UI can refresh its counters from the same response.

---

## Receivables

### `GET /api/receivables` — Stage 7

```json
{
  "outstanding_total": 109500,
  "overdue_count": 2,
  "collection_progress_pct": 62,
  "items": [ { "...": "Invoice, Paid excluded, overdue first" } ]
}
```

- `items` contains **unpaid invoices only**, sorted overdue-first, then by
  `days_overdue` descending.
- `collection_progress_pct` is an integer `0`–`100`: money collected ÷ money
  billed for the period. The backend computes it so the progress bar is
  consistent with the totals above it.

---

## Risk radar

### `GET /api/risk/alerts` — Stage 6

```json
{
  "summary": {
    "attention_count": 2,
    "note": "Plus 1 planning consideration",
    "tag": "REVIEW RECOMMENDED"
  },
  "alerts": [
    {
      "id": "RISK-1",
      "severity": "high|medium|low",
      "tone": "coral|amber|sage",
      "title": "Overdue customer invoices",
      "subtitle": "string",
      "metric": "₹85,000",
      "body": "string",
      "impact_label": "Potential impact",
      "impact_value": "Cash collection delay",
      "action_label": "Review collection plan",
      "evidence": [ { "kind": "invoice", "id": "INV-204" } ]
    }
  ]
}
```

- **`metric` is a pre-formatted display string** (e.g. `"₹85,000"`, `"+12%"`,
  `"90 days"`). Print it verbatim — do not pass it through `money()`.
- `severity` drives ordering (`high` → `medium` → `low`); `tone` drives colour.
- `attention_count` counts `high` and `medium` alerts and matches the badge on
  the Risk Radar nav item. `note` explains any additional `low` alerts.
- `evidence` links an alert to the records behind it, so the UI can deep-link.

---

## Frontend integration notes (for the frontend developer)

The React app currently has **no API client, no TypeScript types and no
environment config** — everything is mock data in `App.tsx`. To connect it:

1. **Add a base URL.** Create `frontend/.env.example` with
   `VITE_API_BASE_URL=http://localhost:8000` and read it via
   `import.meta.env.VITE_API_BASE_URL`. Never hardcode the URL in components.
2. **Add one API client module** (e.g. `src/api/client.ts`) that wraps `fetch`,
   prefixes `/api`, parses JSON, and throws an `ApiError` carrying `status` and
   `detail`. `axios` is already a dependency if you prefer it.
3. **Add TypeScript interfaces** matching this contract: `Workspace`, `Period`,
   `Kpi`, `CashflowPoint`, `Transaction`, `Invoice`, `RiskAlert`,
   `SimulatorResult`, `CopilotReply`. Pass `actual` as `number | null`.
4. **Format money on the client.** Every numeric money field — KPI `value`,
   `commitments[].amount`, simulator `base_balance` / `scenario_cost` /
   `additional_revenue` / `projected_balance`, invoice amounts, totals — goes
   through the existing `money()` helper. The only strings to print as-is are
   `kpis.*.change`, `kpis.*.note` and `risk.alerts[].metric`.
5. **Add a date formatter.** `due_date`, `date`, `paid_at`, `as_of_date` and
   `month_iso` arrive as ISO strings; format them for display and handle
   `null` dates gracefully.
6. **Keep `actual: null`.** Send `null` straight to Recharts with
   `connectNulls={false}`; do not coerce it to `0`.
7. **Surface 4xx errors as toasts.** A 404/409 from mark-paid should show
   `detail` in a toast (`sonner` is already installed) and refresh the list.
   A **501 means that screen is not built yet** — show a friendly "coming in
   Stage N" state rather than a red error.
8. **New UI is needed** for these, which have no screen today:
   CSV upload with an imported/skipped summary, the invoice upload → review →
   confirm flow, and copilot citations rendered as clickable chips.

Until a stage ships, expect `501` from its routes. Build the screens against
this contract and swap the mocks out one endpoint at a time.
