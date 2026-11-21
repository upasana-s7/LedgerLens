# LedgerLens — Demo Script (5 minutes)

## Pre-demo checklist (do these before the demo)

- [ ] backend server running: `cd backend && venv\Scripts\activate && uvicorn app.main:app --reload`
- [ ] frontend dev server running (Upasana starts separately)
- [ ] Fresh DB: `python -m app.seed.seed_data --reset`
- [ ] `sample_invoice.pdf` present in backend/ (or wherever you upload from)
- [ ] `GEMINI_API_KEY` set in backend/.env
- [ ] Internet connection (for Gemini API)

## Demo narrative (5 minutes total)

### 0:00–0:30 — Problem statement

Say: "Indian SMBs make decisions on gut feel. 82% of small businesses fail due to poor cash flow management."

Show: empty home screen.

### 0:30–1:30 — Dashboard (Overview)

Click: **Overview**. Point to the 4 KPI cards.

Say: "Bloom & Bean has ₹3.42L in cash, but the platform predicts ₹1.30L in 30 days, below their ₹1.5L buffer. ₹85,000 in overdue invoices is the fix."

Numbers to verify: cash `342,500`, projected_30d `130,513`, overdue `85,000`, safe_to_spend `-19,486`.

### 1:30–2:30 — Cash Flow

Click: **Cash Flow**.

Say: "Real 90-day forecast. Watch December 7 — the system predicts the buffer break. Bottom is ₹1.29L on Dec 18."

Point to `lowest_balance` and `shortfall_date`.

### 2:30–3:00 — Risk Radar

Click: **Risk**. Point to the 6 alerts.

Say: "The system found 6 issues you'd miss: buffer breach, overdue invoices, duplicate payment, unusual expense, commitment cluster, rising spend."

### 3:00–3:30 — What-If Simulator

Click: **Simulator**. Enter `50,000` and `15%`.

Say: "Should I buy ₹50,000 of inventory? System says no — this drops you to ₹85,990, below buffer."

Show verdict = caution, explanation.

### 3:30–4:30 — AI Copilot (the wow)

Click: **Copilot**. Ask: "Can I afford a ₹50,000 inventory order?"

Wait ~2s. Show grounded reply citing INV-204, INV-198, RISK-1.

Say: "Not ChatGPT — every number in this reply is verified by our backend. No hallucination."

### 4:30–5:00 — Invoice upload (the closer)

Click: **Invoices → Upload**. Select `sample_invoice.pdf`.

Say: "Watch this." Gemini extracts 4 fields in ~2s.

Show: fields auto-filled, confidence 100%.

Click: **Confirm**. New invoice now in receivables.

Say: "From paper to verified data in 5 seconds."

## Q&A preparation

- Q: "How is this different from ChatGPT?" → "ChatGPT makes up numbers. Our backend computes every number first; Gemini only writes the narrative. There's a hallucination guard that rejects any rupee amount not from our services."
- Q: "Is the data real?" → "Everything is synthetic but realistic — real Indian SMB patterns, real Bloom & Bean story. Same architecture works for real data."
- Q: "What's the moat?" → "Deterministic finance engine + AI narrative. Competitors pick one or the other."
