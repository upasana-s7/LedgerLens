# LedgerLens — See beyond the numbers

**AI-powered financial intelligence for small businesses and SMEs.**

LedgerLens helps small-business owners understand their financial position, anticipate cash-flow pressure, and make better day-to-day decisions. Instead of switching between spreadsheets, invoices, and payment trackers, users can work from one financial dashboard.

## Demo

- **Live application:** https://ledgerlens-frontend-bu3a1odt4-shreesha2.vercel.app/
- **Demo video:** YouTube link to be added. (The live application link above is not a substitute for the required under-5-minute demo video.)

## What LedgerLens does

The demo workspace represents **Bloom & Bean**, a fictional small business in Bengaluru. The sample financial records are synthetic and should not be treated as real business or banking data.

- **Financial dashboard:** Key financial indicators and a consolidated view of the business.
- **Transaction management:** Review and manage income and expenses.
- **Cash-flow forecasting:** View projected cash positions and upcoming cash-flow pressure.
- **Risk Radar:** Surface potential issues such as overdue receivables and cash-buffer risks.
- **What-if simulator:** Explore how a proposed expense or business decision could affect cash flow.
- **Invoice processing:** Upload an invoice and use AI-assisted extraction to identify key fields for review and confirmation.
- **Receivables management:** Track outstanding invoices and payment status.
- **AI Financial Copilot:** Ask questions about the business's financial position and receive explanations grounded in the application's financial context.

## How AI is used

LedgerLens integrates **Google Gemini 3.1 Flash-Lite** through Google's **Gemini API** and the official `google-genai` Python SDK.

1. **Invoice extraction:** Gemini processes an uploaded invoice document/image and extracts relevant invoice details for the user to review.
2. **Financial Copilot:** Gemini turns verified financial context and results calculated by the backend into clear, natural-language explanations.

**Important design choice:** Financial calculations, forecasts, and simulator results are computed by backend Python logic. Gemini is used to interpret/explain the prepared context; it is not the source of truth for financial arithmetic. A deterministic fallback is available if the Gemini API key is not configured or a request fails.

## Technology stack

| Layer | Technologies |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, Recharts, Lucide React, Motion |
| Backend | Python, FastAPI, Uvicorn, Pydantic |
| Data | SQLite, SQLAlchemy |
| AI | Google Gemini 3.1 Flash-Lite, Gemini API, `google-genai` SDK |
| Frontend-to-backend communication | HTTP REST API, Axios |
| Authentication | Password hashing and signed session tokens in HttpOnly cookies |

## Repository layout and branches

The project code is currently maintained in two branches:

- `frontend` — React/TypeScript application in `frontend/`
- `backend` — FastAPI application in `backend/`

The `main` branch contains this project README. To run the complete application locally, clone the frontend branch and bring the backend directory from the backend branch into that checkout:

```bash
git clone --branch frontend https://github.com/upasana-s7/LedgerLens.git
cd LedgerLens
git fetch origin backend
git checkout origin/backend -- backend/
```

After these commands, the working directory should contain both `frontend/` and `backend/`.

## Run locally

### Prerequisites

- Node.js and npm
- Python 3.11+
- A Google Gemini API key for live Gemini-powered features (optional; fallback responses are available without it)

### 1. Start the backend

From the repository root:

**Windows PowerShell:**
```powershell
cd backend
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

**macOS/Linux:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `backend/.env` and configure the following values as needed:

```env
GEMINI_API_KEY=your_google_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite
```

Keep the API key private. Never commit `.env` or paste secrets into source code.

Start the API from inside the `backend/` directory:

```bash
uvicorn app.main:app --reload
```

The backend runs at `http://127.0.0.1:8000`. Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

### 2. Start the frontend

Open a second terminal at the repository root:

```bash
cd frontend
npm install
```

Create `frontend/.env` with:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Run the Vite development server:

```bash
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`).

### 3. Build the frontend

From `frontend/`:

```bash
npm run build
```

## Configuration and security

- Store the Gemini API key and authentication secret only in environment variables.
- Use the provided `.env.example` files as templates; do not commit real `.env` files.
- The included Bloom & Bean dataset is fictional demo data. Do not upload real bank details, passwords, PAN, UPI IDs, or other sensitive financial information to a public demo.
- For production deployment, configure the backend's allowed frontend origin and secure cookie settings for the deployed domains.

## Notes

LedgerLens is a hackathon/demo project intended to demonstrate financial visibility and AI-assisted decision support. It is not a bank, accounting/tax filing service, or substitute for professional financial advice. Forecasts and alerts are decision-support estimates; users should verify information before acting.

---

**LedgerLens — See beyond the numbers.**
