"""
Basic tests for the reconciliation engine. Run with: pytest tests/
Focuses on the core matching logic rather than the API layer, since that's
where the actual business rules live.
"""

from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import Invoice, Payment, MatchStatus
from app.reconciliation import reconcile, build_summary


def make_invoice(inv_id, number, customer, amount):
    return Invoice(inv_id, number, customer, amount, date(2025, 1, 1), date(2025, 1, 31))


def make_payment(pmt_id, ref, customer, amount):
    return Payment(pmt_id, ref, customer, amount, date(2025, 1, 15))


def test_exact_match():
    inv = make_invoice("INV-1", "2025/100", "Acme Co", 1000.0)
    pmt = make_payment("PMT-1", "INV 100", "Acme Co", 1000.0)
    results, orphans = reconcile([inv], [pmt])
    assert results[0].status == MatchStatus.MATCHED
    assert orphans == []


def test_match_within_tolerance():
    inv = make_invoice("INV-1", "2025/100", "Acme Co", 1000.0)
    pmt = make_payment("PMT-1", "2025/100", "Acme Co", 995.0)  # 5 short, within default tolerance
    results, _ = reconcile([inv], [pmt], tolerance=10.0)
    assert results[0].status == MatchStatus.MATCHED


def test_partial_payment():
    inv = make_invoice("INV-1", "2025/100", "Acme Co", 1000.0)
    pmt = make_payment("PMT-1", "2025/100", "Acme Co", 400.0)
    results, _ = reconcile([inv], [pmt])
    assert results[0].status == MatchStatus.PARTIALLY_MATCHED
    assert results[0].outstanding_amount == 600.0


def test_overpayment():
    inv = make_invoice("INV-1", "2025/100", "Acme Co", 1000.0)
    pmt = make_payment("PMT-1", "2025/100", "Acme Co", 1500.0)
    results, _ = reconcile([inv], [pmt])
    assert results[0].status == MatchStatus.OVERPAID


def test_unmatched_invoice_no_payment():
    inv = make_invoice("INV-1", "2025/100", "Acme Co", 1000.0)
    results, orphans = reconcile([inv], [])
    assert results[0].status == MatchStatus.UNMATCHED
    assert orphans == []


def test_orphan_payment_no_invoice():
    inv = make_invoice("INV-1", "2025/100", "Acme Co", 1000.0)
    pmt = make_payment("PMT-1", "XYZ-999", "Someone Else", 5000.0)
    results, orphans = reconcile([inv], [pmt])
    assert results[0].status == MatchStatus.UNMATCHED
    assert len(orphans) == 1
    assert orphans[0].payment_id == "PMT-1"


def test_duplicate_payment_flagged():
    inv = make_invoice("INV-1", "2025/100", "Acme Co", 1000.0)
    pmt1 = make_payment("PMT-1", "2025/100", "Acme Co", 1000.0)
    pmt2 = make_payment("PMT-2", "2025/100", "Acme Co", 1000.0)
    results, _ = reconcile([inv], [pmt1, pmt2])
    assert results[0].is_duplicate_payment_flagged is True
    assert results[0].status == MatchStatus.OVERPAID  # net paid = 2000 against 1000 invoice


def test_summary_aggregation():
    invoices = [
        make_invoice("INV-1", "2025/100", "Acme Co", 1000.0),
        make_invoice("INV-2", "2025/101", "Acme Co", 2000.0),
    ]
    payments = [
        make_payment("PMT-1", "2025/100", "Acme Co", 1000.0),  # matched
        # INV-2 gets no payment -> unmatched
    ]
    results, orphans = reconcile(invoices, payments)
    summary = build_summary(results, orphans)
    assert summary["total_invoices"] == 2
    assert summary["matched_invoices"] == 1
    assert summary["unmatched_invoices"] == 1
    assert summary["total_matched_value"] == 1000.0
    assert summary["total_pending_value"] == 2000.0


def test_invalid_negative_tolerance_raises():
    inv = make_invoice("INV-1", "2025/100", "Acme Co", 1000.0)
    try:
        reconcile([inv], [], tolerance=-5)
        assert False, "expected ValueError"
    except ValueError:
        pass
