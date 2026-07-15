# AI-Assisted Invoice Reconciliation Platform

A prototype invoice reconciliation service that automatically matches invoices
against incoming bank payments, identifies exceptions requiring manual review,
and produces a concise AI-assisted reconciliation summary.

Built as a lightweight FastAPI service with a deterministic reconciliation
engine and a dashboard powered entirely by the public API.

**Tech Stack**

- Python 3
- FastAPI
- Pydantic
- Chart.js
- Faker
- Pytest

---

# Features

### Core functionality

- Generates realistic invoice and bank payment datasets
- Reconciles invoices against incoming payments
- Matches using:
  - Invoice reference
  - Customer
  - Amount (with configurable tolerance)
- Supports multiple payments against a single invoice
- Categorizes invoices as:
  - Matched
  - Partially Matched
  - Overpaid
  - Unmatched

### Exception detection

- Duplicate payments
- Orphan payments
- Missing payments
- Partial payments
- Overpayments

### AI Assistance

Produces a natural-language reconciliation summary alongside the structured
JSON response.

The reconciliation logic itself is fully deterministic. AI is used only to
summarize the results—not to make financial decisions.

### Dashboard

A lightweight dashboard built directly on top of the API displaying:

- KPI cards
- Status distribution
- Matched vs pending value
- Live exceptions table

No additional backend endpoints or database are required.

---

# Quick Start

```bash
git clone <repo-url>

cd invoice-reconciliation

python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt

uvicorn app.main:app --reload
```

Open

```
http://localhost:8000/docs
```

to explore the API.

The dashboard is available at

```
http://localhost:8000/dashboard
```

The root endpoint redirects to the dashboard.

---

# API

| Method | Endpoint | Description |
|---------|----------|-------------|
| GET | `/summary` | Aggregate reconciliation summary |
| GET | `/invoices` | Invoice-level reconciliation results |
| GET | `/exceptions` | Items requiring manual review |
| GET | `/dashboard` | Dashboard UI |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |

---

# Example Summary

```json
{
  "total_invoices": 40,
  "matched_invoices": 32,
  "partially_matched_invoices": 1,
  "overpaid_invoices": 4,
  "unmatched_invoices": 3,
  "total_matched_value": 4005829.08,
  "total_pending_value": 504076.53,
  "duplicate_payments_flagged": 1,
  "ai_summary": "..."
}
```

---

# Project Structure

```
invoice-reconciliation/

app/
    main.py
    reconciliation.py
    data_generator.py
    models.py
    ai_summary.py

data/

tests/

requirements.txt
README.md
```

---

# Design Decisions

### Deterministic reconciliation

Invoice matching is deterministic and fully explainable.

The matching order is:

1. Invoice reference
2. Customer + amount fallback

Reference numbers are normalized before comparison to tolerate differences in
spacing, punctuation and casing.

---

### Payment tolerance

A configurable ±₹10 tolerance absorbs minor bank charges and rounding
differences that commonly occur in real payment systems.

---

### Duplicate payments

Duplicate detection is treated independently from reconciliation status.

An invoice may reconcile successfully while still being flagged as a potential
duplicate payment requiring manual verification.

---

### Multiple payments

Invoices may receive multiple payments.

Rather than assuming a strict one-to-one relationship, all matching payments
are aggregated before determining the reconciliation status.

---

### AI summary

The reconciliation engine remains deterministic.

AI is used only to convert structured reconciliation output into a concise,
human-readable narrative.

If an `ANTHROPIC_API_KEY` is available, Claude generates the summary.
Otherwise a deterministic template is used so the project runs without any
external dependencies.

---

### Dashboard architecture

The dashboard contains no business logic.

It consumes the same REST endpoints that any external client would use,
demphasizing API-first design and avoiding duplicated backend logic.

---

# Assumptions

Because no input data was supplied, realistic sample data was generated.

The generated dataset intentionally contains:

- exact matches
- partial payments
- overpayments
- duplicate payments
- orphan payments
- malformed references
- bank-charge rounding differences

This produces reconciliation scenarios representative of real financial data
rather than ideal one-to-one examples.

---

# Testing

Run

```bash
pytest tests -v
```

Tests cover:

- Exact match
- Tolerance match
- Partial payment
- Overpayment
- Duplicate detection
- Orphan payments
- Summary aggregation
- Invalid input handling

---

# Complexity

Current implementation performs reconciliation in approximately **O(n × m)**,
which is acceptable for prototype-scale datasets.

For production systems, payments would be indexed by normalized invoice
reference and customer to reduce matching toward **O(n + m)**.

---

# Future Improvements

- PostgreSQL persistence
- Incremental reconciliation runs
- Upload API (`POST /reconcile`)
- Historical reconciliation trends
- Fuzzy customer matching (`rapidfuzz`)
- Multi-currency support
- Async background reconciliation
- Audit trail and reconciliation history

---

# Screenshots
<img width="1918" height="1042" alt="image" src="https://github.com/user-attachments/assets/d610c771-3f24-4cd2-b3ab-b6a62e7a9553" />
<img width="1918" height="1093" alt="image" src="https://github.com/user-attachments/assets/8438e28f-7d38-4526-9f56-380c1a27065e" />
