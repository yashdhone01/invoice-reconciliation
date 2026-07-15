# Invoice Reconciliation Platform (Prototype)

An AI-powered invoice reconciliation prototype that matches invoices against
bank payments, flags exceptions needing manual review, and exposes the results
through a FastAPI endpoint.

## What it does

1. Generates realistic dummy invoice and payment data (with deliberately messy,
   real-world edge cases — see "Assumptions" below).
2. Reconciles invoices against payments using a two-step matching strategy
   (reference number, then amount + customer as a fallback).
3. Classifies every invoice as `Matched`, `Partially Matched`, `Overpaid`, or
   `Unmatched`.
4. Flags duplicate payments and orphan payments (payments with no matching invoice).
5. Serves a `/summary` JSON endpoint (plus a couple of bonus endpoints).

## Project structure

```
invoice-reconciliation/
├── app/
│   ├── models.py            # Dataclasses (engine) + Pydantic models (API)
│   ├── data_generator.py    # Realistic dummy data generation
│   ├── reconciliation.py    # Core matching + summary logic
│   ├── ai_summary.py        # Optional natural-language summary generator
│   └── main.py               # FastAPI app and routes
├── data/                      # Generated CSVs live here (invoices.csv, payments.csv)
├── tests/
│   └── test_reconciliation.py
├── requirements.txt
└── README.md
```

## How to run

```bash
# 1. Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate sample data (optional — the API auto-generates it on first run if missing)
python3 -m app.data_generator

# 4. Run the API
uvicorn app.main:app --reload

# 5. Try it
curl http://localhost:8000/summary
```

Interactive API docs (Swagger UI) are available at `http://localhost:8000/docs`
once the server is running.

### Endpoints

| Method | Path                          | Description                                              |
|--------|-------------------------------|------------------------------------------------------------|
| GET    | `/summary`                    | Required by the assignment — reconciliation summary        |
| GET    | `/invoices`                   | Bonus — full per-invoice detail, filterable by `?status=`   |
| GET    | `/exceptions`                 | Bonus — only invoices needing manual review                |
| GET    | `/health`                     | Basic liveness check                                        |

### Running tests

```bash
pytest tests/ -v
```

## Assumptions

- **No input files were given**, so I generated my own dataset (`app/data_generator.py`)
  with 40 invoices and ~42 payments. Rather than making every record match
  perfectly, I deliberately injected the kinds of messiness a real reconciliation
  system has to handle: exact matches, partial payments, overpayments, duplicate
  payments, amounts off by a few rupees (bank charges), free-text/garbled payment
  references, and a few orphan payments with no matching invoice. This makes the
  reconciliation logic actually get exercised instead of trivially matching everything.
- **One invoice can have multiple payments** (installments), so paid amounts are
  summed per invoice rather than assuming a strict 1:1 relationship.
- **A payment tolerance of ₹10** is applied by default to absorb bank charges and
  rounding differences — an exact-only match would be unrealistic for real bank data.
- **Matching priority**: reference number match first (normalized — case, spacing,
  and punctuation-insensitive, matching on the invoice's numeric tail since that's
  what people actually type into a bank transfer note), falling back to
  customer + amount match only when no reference match is found. This mirrors how
  a human accountant would reconcile a messy bank statement.
- **Duplicate detection** flags an invoice when 2+ *individually full-amount*
  payments are linked to it — this is a common real error (e.g. paid via two
  different channels) and needs a human to decide whether to refund or credit.
- Currency is written as ₹ (INR) throughout given the "±₹5 or ±₹10" example in
  the brief, but the logic is currency-agnostic.

## Design decisions worth highlighting

- **Dataclasses for the engine, Pydantic for the API boundary.** The reconciliation
  engine doesn't need validation overhead on every object; validation matters at
  the API boundary, where Pydantic also gives us free OpenAPI docs.
- **Reconciliation runs once at startup**, not on every request. For a prototype
  this is fine and keeps `/summary` fast; a production version would re-run this
  on a schedule, on file upload, or via a `POST /reconcile` trigger instead.
- **Graceful CSV validation.** Malformed rows are skipped with a log message
  rather than crashing the whole load — see `_load_csv_data()` in `main.py`.
- **AI-generated summary (bonus feature).** `/summary` includes a natural-language
  narrative (`ai_summary` field) built from the aggregated numbers. If an
  `ANTHROPIC_API_KEY` environment variable is set, it calls the Claude API for a
  genuinely model-generated narrative instead; otherwise it falls back to a
  template-based narrative so the endpoint stays fast, deterministic, and runnable
  without any API key. This was a deliberate choice — a reviewer running this
  locally shouldn't hit a broken endpoint just because they don't have a key handy.
- **Tolerance and duplicate detection are separate concerns.** An invoice can be
  "Matched" (net amount reconciles) while still being flagged as a duplicate
  payment risk — these are surfaced as two independent signals rather than
  collapsed into one status, since they call for different follow-up actions.

## What I'd add with more time

- Persist reconciliation runs to a real database (Postgres) instead of in-memory/CSV,
  with a `POST /reconcile` endpoint to re-run on new uploads.
- A simple dashboard (e.g. Streamlit) visualizing matched vs. pending value over time.
- Fuzzy customer name matching (e.g. `rapidfuzz`) to handle minor spelling
  variations between invoice and bank records.
- Async/batch processing for larger datasets instead of the current in-memory
  O(n·m) matching (fine at prototype scale, would need indexing at real volume).
