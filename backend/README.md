# LedgerLens — Backend (FastAPI)

LedgerLens is an **AI financial decision intelligence** tool — a "virtual CFO" —
for small Indian businesses. It reads your transactions, forecasts your cash
flow, warns you before money gets tight, and explains the numbers in plain
English.

The demo business is **Bloom & Bean**, a small café in Bengaluru. **All sample
data is fictional.**

> **Stage 1 (this commit):** the project skeleton — settings, CORS, every API
> route stubbed with a clear `501`, tests, and the agreed API contract.
> Database, finance logic and Gemini come in later stages.

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
│   ├── models/            # database tables (Stage 2)
│   ├── schemas/           # Pydantic request/response models (Stage 3)
│   ├── services/          # finance calculations (Stage 3+)
│   ├── ai/                # Gemini explanations (Stage 8)
│   └── seed/              # fictional Bloom & Bean sample data (Stage 2)
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
