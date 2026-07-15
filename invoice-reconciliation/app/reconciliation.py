"""
Core reconciliation engine.

Matching strategy (in order of confidence):
  1. Exact reference match: payment's reference number contains the invoice
     number (normalized - punctuation/spacing/case insensitive) AND customer
     name matches.
  2. Fallback match: customer name matches AND payment amount matches the
     invoice amount within tolerance, used when the reference number is too
     messy to parse (handles real-world free-text bank references).

Once payments are linked to an invoice, we sum them (to support partial /
split payments) and classify the invoice:
  - Matched            -> paid_amount within tolerance of invoice_amount
  - Partially Matched  -> 0 < paid_amount < invoice_amount - tolerance
  - Overpaid           -> paid_amount > invoice_amount + tolerance
  - Unmatched          -> no linked payments at all

Duplicate payments (>1 payment fully covering the same invoice) are flagged
separately as they need manual review even though the invoice itself looks
"paid".

All amount comparisons use a configurable tolerance (default ₹10) to absorb
bank charges / rounding, as real bank transfers rarely land on the exact paisa.
"""

import re
from collections import defaultdict
from typing import Dict, List, Tuple

from app.models import Invoice, Payment, MatchStatus, ReconciliationResult

DEFAULT_TOLERANCE = 10.0


def _normalize(text: str) -> str:
    """Strip everything but digits and lowercase letters, for fuzzy reference matching."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _invoice_number_in_reference(invoice_number: str, reference: str) -> bool:
    inv_norm = _normalize(invoice_number)
    ref_norm = _normalize(reference)
    # Match on the numeric tail of the invoice number (e.g. "1042" from "2025/1042"),
    # since that's what customers usually type in a bank transfer note.
    inv_tail = re.sub(r"^\d*", "", inv_norm) if inv_norm.isdigit() else inv_norm
    numeric_part = re.findall(r"\d+", invoice_number)
    if numeric_part and numeric_part[-1] in ref_norm:
        return True
    return inv_norm in ref_norm


def reconcile(
    invoices: List[Invoice],
    payments: List[Payment],
    tolerance: float = DEFAULT_TOLERANCE,
) -> Tuple[List[ReconciliationResult], List[Payment]]:
    """
    Runs reconciliation and returns:
      - a list of ReconciliationResult, one per invoice
      - a list of payments that could not be linked to ANY invoice (orphan payments)
    """
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")

    # Group remaining (unclaimed) payments by customer for efficient lookup.
    payments_by_customer: Dict[str, List[Payment]] = defaultdict(list)
    for p in payments:
        payments_by_customer[_normalize(p.customer_name)].append(p)

    claimed_payment_ids: set = set()
    results: List[ReconciliationResult] = []

    for inv in invoices:
        candidates = payments_by_customer.get(_normalize(inv.customer_name), [])

        # Step 1: reference-based matches
        linked = [
            p for p in candidates
            if p.payment_id not in claimed_payment_ids
            and _invoice_number_in_reference(inv.invoice_number, p.reference_number)
        ]

        # Step 2: if nothing matched by reference, fall back to amount-based match
        # (within tolerance) against this customer's unclaimed payments.
        if not linked:
            linked = [
                p for p in candidates
                if p.payment_id not in claimed_payment_ids
                and abs(p.amount - inv.amount) <= tolerance
            ]
            # Only take the single closest amount match in fallback mode, to avoid
            # accidentally scooping up an unrelated payment to a different invoice.
            if linked:
                linked = [min(linked, key=lambda p: abs(p.amount - inv.amount))]

        for p in linked:
            claimed_payment_ids.add(p.payment_id)

        paid_amount = round(sum(p.amount for p in linked), 2)
        outstanding = round(inv.amount - paid_amount, 2)

        # Duplicate detection: 2+ payments each individually already covering
        # the invoice amount (within tolerance) is a red flag worth a manual look,
        # even though the invoice nets out as "paid".
        full_amount_payments = [p for p in linked if abs(p.amount - inv.amount) <= tolerance]
        is_duplicate = len(full_amount_payments) > 1

        if not linked:
            status = MatchStatus.UNMATCHED
            notes = "No payment found for this invoice."
        elif outstanding > tolerance:
            status = MatchStatus.PARTIALLY_MATCHED
            notes = f"Partial payment received. Outstanding: {outstanding:.2f}"
        elif outstanding < -tolerance:
            status = MatchStatus.OVERPAID
            notes = f"Overpayment received. Excess: {abs(outstanding):.2f}"
        else:
            status = MatchStatus.MATCHED
            notes = "Fully matched within tolerance."

        if is_duplicate:
            notes += " [DUPLICATE PAYMENT DETECTED - manual review required]"

        results.append(ReconciliationResult(
            invoice=inv,
            status=status,
            matched_payment_ids=[p.payment_id for p in linked],
            paid_amount=paid_amount,
            outstanding_amount=max(outstanding, 0.0),
            is_duplicate_payment_flagged=is_duplicate,
            notes=notes,
        ))

    orphan_payments = [p for p in payments if p.payment_id not in claimed_payment_ids]
    return results, orphan_payments


def build_summary(
    results: List[ReconciliationResult],
    orphan_payments: List[Payment],
) -> dict:
    """Aggregates reconciliation results into the summary shape required by the assignment."""
    total_invoices = len(results)
    matched = [r for r in results if r.status == MatchStatus.MATCHED]
    partial = [r for r in results if r.status == MatchStatus.PARTIALLY_MATCHED]
    overpaid = [r for r in results if r.status == MatchStatus.OVERPAID]
    unmatched = [r for r in results if r.status == MatchStatus.UNMATCHED]

    total_invoice_value = round(sum(r.invoice.amount for r in results), 2)
    total_matched_value = round(sum(r.paid_amount for r in matched), 2)
    # Pending = anything not fully matched: unmatched + outstanding portion of partials
    total_pending_value = round(
        sum(r.invoice.amount for r in unmatched) + sum(r.outstanding_amount for r in partial),
        2,
    )

    duplicates_flagged = sum(1 for r in results if r.is_duplicate_payment_flagged)

    return {
        "total_invoices": total_invoices,
        "matched_invoices": len(matched),
        "partially_matched_invoices": len(partial),
        "overpaid_invoices": len(overpaid),
        "unmatched_invoices": len(unmatched),
        "total_invoice_value": total_invoice_value,
        "total_matched_value": total_matched_value,
        "total_pending_value": total_pending_value,
        "unmatched_payments_count": len(orphan_payments),
        "unmatched_payments_value": round(sum(p.amount for p in orphan_payments), 2),
        "duplicate_payments_flagged": duplicates_flagged,
    }
