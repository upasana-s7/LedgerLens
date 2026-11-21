# LedgerLens — Backend (FastAPI)

LedgerLens is an **AI financial decision intelligence** tool — a "virtual CFO" —
for small Indian businesses. It reads your transactions, forecasts your cash
flow, warns you before money gets tight, and explains the numbers in plain
English.

The demo business is **Bloom & Bean**, a small café in Bengaluru. **All sample
data is fictional.**

> **Stage 2 (this commit):** the SQLite database, all data models and the
> deterministic synthetic dataset for Bloom & Bean. API routes are still
> stubs (`501`); the KPIs, forecast, simulator, risk rules and Gemini arrive
> in later stages.

---

## What you need

- **Python 3.11 or newer**
- No database install needed — SQLite is built into Python.

---

## 1. Create a virtual environment

A virtual environment ("venv") keeps this project's packages separate from the
rest of your computer. Create it once inside the `backend/` folder.

**Windows (PowerShell or CMD):**

```bat
cd backend
py -m venv venv
venv\Scripts\activate
```

**macOS / Linux:**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
```

You should now see `(venv)` at the start of your terminal prompt.

---

## 2. Install the packages

```bat
pip install -r requirements.txt
```

---

## 3. Create your `.env` file

The app reads settings from `backend/.env`. Copy the example first:

**Windows:** `copy .env.example .env`
**macOS / Linux:** `cp .env.example .env`

Then open `.env` and paste in your own Gemini key if you have one. Leaving
`GEMINI_API_KEY` empty is fine — the app uses rule-based text instead.

> ⚠️ **Never commit `.env`.** It holds secret keys. `.gitignore` already
> blocks it, so you cannot commit it by accident — but do not remove that line.

---

## 4. Run the API

From the `backend/` folder, with the venv active:

```bash
uvicorn app.main:app --reload
```

- API docs (click and try every endpoint): <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/api/health>

`--reload` restarts the server whenever you save a file. Press `Ctrl+C` to stop.

---

## 5. Run the tests

```bash
pytest
```

You should see all tests passing. `pytest.ini` already points it at `tests/`.
The tests use a temporary in-memory database, so they never touch
`ledgerlens.db`.

---

## The database and the demo data

**Everything in the database is fictional.** The demo business is
"Bloom & Bean", a made-up specialty coffee and bakery supplier in Bengaluru.
The customers (`Aarav Foods`, `The Daily Table`, `Cafe Bloom`), the vendors
(`FreshKart Wholesale`, `Sri Lakshmi Packaging`), every invoice and every
GSTIN (all start with `SYNTH`) are invented. No row describes a real company.

**Where it lives.** A single SQLite file, `backend/ledgerlens.db`, created
automatically the first time the server starts. It is git-ignored — never
commit it. Delete the file at any time and restart the server to get a fresh,
identical copy.

**When it fills up.** On startup the app creates any missing tables, and if
`AUTO_SEED` is true (the default) it seeds the demo data **only when the
database is empty**. Restarting never duplicates rows.

### Seed commands

From the `backend/` folder with the venv active:

```bash
python -m app.seed.seed_data           # seed only if the database is empty
python -m app.seed.seed_data --reset   # wipe every table, then rebuild
```

Both print a summary of the row counts and the pinned figures (cash on the
demo date, month-end balances, open invoices, upcoming commitments), and the
script **fails loudly** if any of those numbers is off.

The dataset is deterministic: it uses its own `random.Random(2026)` and the
fixed demo date from `AS_OF_DATE`, never today's date. Running `--reset` twice
produces byte-identical rows.

### What is inside

| Table | Purpose |
| --- | --- |
| `business_profiles` | The workspace: name, city, opening balance, as-of date |
| `counterparties` | Customers we invoice and vendors we pay |
| `transactions` | Signed cash movements, June – 19 Nov 2026 |
| `invoices` | Sent invoices; status is only Draft / Pending / Paid |
| `commitments` | Known upcoming payments (rent, payroll, EMI, GST…) |
| `upload_batches` | Import history for CSV / invoice uploads |
| `risk_alerts`, `chat_messages`, `simulation_runs` | Tables for later stages |

### Rules worth remembering

- **Money is `Numeric(14, 2)` and Python `Decimal`** — never a float. SQLite
  has no native decimal type, so a warning about possible rounding is silenced
  in `app/core/database.py`; our amounts convert exactly.
- **Amounts are signed:** income positive, expense negative, and `type` always
  matches the sign. A balance is `opening_balance + SUM(amount)`.
- **"Overdue" is never stored.** Only Draft, Pending and Paid live in the
  database; overdue is worked out later by comparing `due_date` with
  `as_of_date`. Stored statuses would go stale the next day.
- **The history stops at `2026-11-19`**, the fixed demo date. There is no
  transaction after it.

### Resetting when numbers look wrong

If the data looks stale or you changed the seed script:

```bash
del ledgerlens.db                          # Windows
rm ledgerlens.db                           # macOS / Linux
python -m app.seed.seed_data               # rebuild from scratch
```

(Or simply `python -m app.seed.seed_data --reset`, which does both.)

---

## Project layout

```
backend/
├── app/
│   ├── main.py            # creates the FastAPI app, CORS, registers routers
│   ├── core/
│   │   ├── config.py      # settings loaded from .env
│   │   └── database.py    # SQLAlchemy setup (placeholder, Stage 2)
│   ├── routers/           # one file per feature area, all under /api
│   ├── models/            # database tables: transaction, invoice, ...
│   ├── schemas/           # Pydantic request/response models (Stage 3)
│   ├── services/          # finance calculations (Stage 3+)
│   ├── ai/                # Gemini explanations (Stage 8)
│   └── seed/
│       └── seed_data.py   # the fictional Bloom & Bean dataset
├── tests/
├── docs/
│   └── API_CONTRACT.md    # what the frontend can expect from every route
├── requirements.txt
├── pytest.ini
├── .env.example
└── README.md
```

---

## How the pieces fit together

**All money maths is plain, deterministic Python.** Gemini never calculates
anything and never invents a number — it only writes the explanation for
numbers Python has already produced. That keeps every figure on screen
auditable.

**Money is sent as numbers, not strings.** `342500` means ₹3,42,500. The React
frontend formats it with ₹ and Indian digit grouping (`en-IN`).

**Dates are ISO strings** (`2026-11-19`) so they sort and compare correctly.
The frontend turns them into readable dates.

**`actual: null` for future months** — a month that has not happened yet has no
actual value. It is `null`, never `0`, so the chart line stops instead of
dropping to zero.

**The database is SQLite** (`backend/ledgerlens.db`), created automatically on
first run and filled with fictional sample data. See
[The database and the demo data](#the-database-and-the-demo-data).

**Placeholder routes return `501`** with
`{"detail": "Not implemented yet (planned for Stage N)"}`. If you see a 501,
the route is simply not built yet.

Read `docs/API_CONTRACT.md` before writing frontend code against this API.

---

## Route map

| Method | Path | Stage |
| --- | --- | --- |
| GET | `/api/health` | ✅ 1 |
| GET | `/api/dashboard` | 3 |
| GET | `/api/transactions` | 3 |
| POST | `/api/transactions` | 3 |
| POST | `/api/transactions/upload` | 3 |
| GET | `/api/cashflow/forecast` | 4 |
| POST | `/api/simulator/run` | 5 |
| GET | `/api/risk/alerts` | 6 |
| GET | `/api/receivables` | 7 |
| POST | `/api/receivables/{id}/mark-paid` | 7 |
| GET | `/api/invoices` | 7 |
| POST | `/api/invoices/{id}/mark-paid` | 7 |
| POST | `/api/invoices/upload` | 9 |
| POST | `/api/invoices/{id}/confirm` | 9 |
| POST | `/api/copilot/chat` | 8 |
| GET | `/api/copilot/suggestions` | 8 |

---

## Demo & handoff

Presenting LedgerLens or wiring up the frontend? Start here:

- **`docs/DEMO_SCRIPT.md`** — the 5-minute live demo clickbook: pre-demo
  checklist, screen-by-screen narration with the exact numbers to point at,
  and prepared answers for the likely questions.
- **`docs/FRONTEND_HANDOFF.md`** — one page for the frontend: base URL, which
  endpoint backs which screen, money/date formatting, and how the numbers move
  when the user takes an action.

`tests/test_e2e_demo.py` walks that same story as one test — dashboard →
invoice upload → confirm → receivables → mark paid → dashboard → copilot — so a
passing suite means the demo's state transitions work on a single seed.

**All 16 endpoints are live. 184+ tests pass. The backend is feature-complete.**

---

## Troubleshooting

**`uvicorn: command not found`** — the venv is not active. Re-run the activate
command from step 1.

**`ModuleNotFoundError: No module named 'app'`** — you are in the wrong folder.
`cd` into `backend/` and run `uvicorn app.main:app --reload` again.

**CORS error in the browser** — the frontend must run on a port listed in
`CORS_ORIGINS` (default: 5173 for dev, 4173 for preview). Vite sometimes moves
to 5174 if 5173 is busy; `CORS_ORIGIN_REGEX` in `config.py` already covers that
during development.

**`py` not found (Windows)** — try `python -m venv venv` instead.
