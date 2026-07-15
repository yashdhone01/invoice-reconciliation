"""
FastAPI application for the Invoice Reconciliation prototype.

Endpoints:
  GET /summary      -> required by the assignment. Reconciliation summary as JSON.
  GET /exceptions   -> bonus: line-item detail of everything needing manual review.
  GET /invoices     -> bonus: full reconciliation detail per invoice.
  GET /health       -> basic liveness check.

Data is loaded from CSV once at startup (data/invoices.csv, data/payments.csv).
If those files don't exist yet, they are generated automatically on first run
so the app works out of the box with `uvicorn app.main:app`.
"""

import csv
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.ai_summary import generate_ai_summary
from app.data_generator import generate_dataset, write_csv
from app.models import (
    ExceptionsResponse,
    Invoice,
    Payment,
    ReconciliationItem,
    SummaryResponse,
)
from app.reconciliation import build_summary, reconcile, DEFAULT_TOLERANCE

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(
    title="Invoice Reconciliation API",
    description="AI-powered invoice reconciliation prototype",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _load_csv_data():
    """Loads invoices.csv and payments.csv from disk, generating them first if missing."""
    invoices_path = DATA_DIR / "invoices.csv"
    payments_path = DATA_DIR / "payments.csv"

    if not invoices_path.exists() or not payments_path.exists():
        invoices, payments = generate_dataset(40)
        write_csv(invoices, payments, out_dir=str(DATA_DIR))

    invoices = []
    with open(invoices_path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                invoices.append(Invoice(
                    invoice_id=row["invoice_id"],
                    invoice_number=row["invoice_number"],
                    customer_name=row["customer_name"],
                    amount=float(row["amount"]),
                    invoice_date=_parse_date(row["invoice_date"]),
                    due_date=_parse_date(row["due_date"]),
                ))
            except (ValueError, KeyError) as e:
                # Basic validation: skip malformed rows rather than crashing the whole load.
                print(f"Skipping invalid invoice row {row}: {e}")

    payments = []
    with open(payments_path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                payments.append(Payment(
                    payment_id=row["payment_id"],
                    reference_number=row["reference_number"],
                    customer_name=row["customer_name"],
                    amount=float(row["amount"]),
                    payment_date=_parse_date(row["payment_date"]),
                ))
            except (ValueError, KeyError) as e:
                print(f"Skipping invalid payment row {row}: {e}")

    if not invoices:
        raise RuntimeError("No valid invoices could be loaded from data/invoices.csv")

    return invoices, payments


# Load + reconcile once at startup. For a prototype this is fine; a production
# version would re-run reconciliation on a schedule or on-demand via a POST endpoint.
_invoices, _payments = _load_csv_data()
_results, _orphan_payments = reconcile(_invoices, _payments, tolerance=DEFAULT_TOLERANCE)
_summary = build_summary(_results, _orphan_payments)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/summary", response_model=SummaryResponse)
def get_summary(include_ai_summary: bool = Query(default=True)):
    """Returns the reconciliation summary required by the assignment."""
    payload = dict(_summary)
    payload["ai_summary"] = generate_ai_summary(_summary) if include_ai_summary else None
    return payload


@app.get("/invoices", response_model=list[ReconciliationItem])
def get_invoices(status: str | None = Query(default=None, description="Filter by status, e.g. 'Matched'")):
    """Returns full reconciliation detail for every invoice, optionally filtered by status."""
    items = _results
    if status:
        items = [r for r in items if r.status.value.lower() == status.lower()]
        if not items:
            raise HTTPException(status_code=404, detail=f"No invoices with status '{status}'")

    return [
        ReconciliationItem(
            invoice_id=r.invoice.invoice_id,
            invoice_number=r.invoice.invoice_number,
            customer_name=r.invoice.customer_name,
            invoice_amount=r.invoice.amount,
            paid_amount=r.paid_amount,
            outstanding_amount=r.outstanding_amount,
            status=r.status.value,
            matched_payment_ids=r.matched_payment_ids,
            is_duplicate_payment_flagged=r.is_duplicate_payment_flagged,
            notes=r.notes,
        )
        for r in items
    ]


@app.get("/exceptions", response_model=ExceptionsResponse)
def get_exceptions():
    """Returns only the invoices that require manual review (anything not cleanly Matched)."""
    exceptions = [r for r in _results if r.status.value != "Matched" or r.is_duplicate_payment_flagged]
    items = [
        ReconciliationItem(
            invoice_id=r.invoice.invoice_id,
            invoice_number=r.invoice.invoice_number,
            customer_name=r.invoice.customer_name,
            invoice_amount=r.invoice.amount,
            paid_amount=r.paid_amount,
            outstanding_amount=r.outstanding_amount,
            status=r.status.value,
            matched_payment_ids=r.matched_payment_ids,
            is_duplicate_payment_flagged=r.is_duplicate_payment_flagged,
            notes=r.notes,
        )
        for r in exceptions
    ]
    return ExceptionsResponse(count=len(items), items=items)
