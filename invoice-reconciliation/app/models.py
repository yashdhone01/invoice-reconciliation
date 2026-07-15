"""
Data models used across the reconciliation engine.

We use plain dataclasses for the internal engine (fast, no validation overhead
when generating thousands of rows) and Pydantic models for the API response
layer (so FastAPI gives us request/response validation + auto-generated docs).
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Internal engine models (dataclasses)
# ---------------------------------------------------------------------------

@dataclass
class Invoice:
    invoice_id: str
    invoice_number: str
    customer_name: str
    amount: float
    invoice_date: date
    due_date: date


@dataclass
class Payment:
    payment_id: str
    reference_number: str          # what the customer typed as a reference; may or may not equal invoice_number
    customer_name: str
    amount: float
    payment_date: date


class MatchStatus(str, Enum):
    MATCHED = "Matched"
    PARTIALLY_MATCHED = "Partially Matched"
    OVERPAID = "Overpaid"
    UNMATCHED = "Unmatched"


@dataclass
class ReconciliationResult:
    invoice: Invoice
    status: MatchStatus
    matched_payment_ids: List[str]
    paid_amount: float
    outstanding_amount: float
    is_duplicate_payment_flagged: bool
    notes: str


# ---------------------------------------------------------------------------
# API response models (Pydantic)
# ---------------------------------------------------------------------------

class SummaryResponse(BaseModel):
    total_invoices: int
    matched_invoices: int
    partially_matched_invoices: int
    overpaid_invoices: int
    unmatched_invoices: int
    total_invoice_value: float
    total_matched_value: float
    total_pending_value: float
    unmatched_payments_count: int
    unmatched_payments_value: float
    duplicate_payments_flagged: int
    ai_summary: Optional[str] = None


class ReconciliationItem(BaseModel):
    invoice_id: str
    invoice_number: str
    customer_name: str
    invoice_amount: float
    paid_amount: float
    outstanding_amount: float
    status: str
    matched_payment_ids: List[str]
    is_duplicate_payment_flagged: bool
    notes: str


class ExceptionsResponse(BaseModel):
    count: int
    items: List[ReconciliationItem]
