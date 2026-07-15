"""
Generates realistic dummy data for invoices and bank payments/transactions.

Design decision: rather than generating perfectly clean 1:1 data, we deliberately
inject the kinds of messiness reconciliation systems deal with in real life:

  - Exact matches                      (happy path)
  - Partial payments                   (customer pays in installments)
  - Overpayments                       (customer pays extra, or pays twice by mistake)
  - Duplicate payments                 (same invoice paid twice - needs flagging)
  - Payments with slightly off amounts (bank fees / rounding -> needs tolerance)
  - Payments with messy references     ("Inv 1042", "INV-1042 part pay", missing ref)
  - Invoices with no payment at all     (unmatched / pending)
  - Orphan payments with no matching invoice (e.g. advance payment, wrong reference)

This gives the reconciliation engine something realistic to actually reconcile,
instead of a trivial dataset where everything matches perfectly.
"""

import csv
import random
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple

from faker import Faker

from app.models import Invoice, Payment

fake = Faker()
Faker.seed(42)
random.seed(42)

CUSTOMERS = [
    "Sunrise Textiles Pvt Ltd", "Bluewave Logistics", "Nimbus Cloud Services",
    "Greenfield Agro Traders", "Orion Steel Works", "Pinnacle Consulting Group",
    "Silverline Electronics", "Rapid Fresh Foods", "Vertex Software Solutions",
    "Coastal Shipping Co",
]


def _make_invoices(n: int) -> List[Invoice]:
    invoices = []
    for i in range(1, n + 1):
        invoice_date = date(2025, 1, 1) + timedelta(days=random.randint(0, 200))
        invoices.append(
            Invoice(
                invoice_id=f"INV-{i:04d}",
                invoice_number=f"2025/{1000 + i}",
                customer_name=random.choice(CUSTOMERS),
                amount=round(random.uniform(5_000, 250_000), 2),
                invoice_date=invoice_date,
                due_date=invoice_date + timedelta(days=30),
            )
        )
    return invoices


def _make_payments(invoices: List[Invoice]) -> List[Payment]:
    payments = []
    payment_counter = 1

    def next_payment_id():
        nonlocal payment_counter
        pid = f"PMT-{payment_counter:04d}"
        payment_counter += 1
        return pid

    for inv in invoices:
        roll = random.random()
        pay_date = inv.invoice_date + timedelta(days=random.randint(1, 45))

        if roll < 0.55:
            # Clean exact match, reference formatted slightly differently than the invoice number
            payments.append(Payment(
                payment_id=next_payment_id(),
                reference_number=f"INV {inv.invoice_number.split('/')[-1]}",
                customer_name=inv.customer_name,
                amount=inv.amount,
                payment_date=pay_date,
            ))

        elif roll < 0.65:
            # Amount slightly off (bank charges deducted) -> needs tolerance matching
            payments.append(Payment(
                payment_id=next_payment_id(),
                reference_number=inv.invoice_number,
                customer_name=inv.customer_name,
                amount=round(inv.amount - random.choice([5, 8, 10]), 2),
                payment_date=pay_date,
            ))

        elif roll < 0.75:
            # Partial payment (only part paid so far)
            payments.append(Payment(
                payment_id=next_payment_id(),
                reference_number=inv.invoice_number,
                customer_name=inv.customer_name,
                amount=round(inv.amount * random.uniform(0.3, 0.7), 2),
                payment_date=pay_date,
            ))

        elif roll < 0.82:
            # Duplicate payment by mistake -> same invoice paid twice in full
            payments.append(Payment(
                payment_id=next_payment_id(),
                reference_number=inv.invoice_number,
                customer_name=inv.customer_name,
                amount=inv.amount,
                payment_date=pay_date,
            ))
            payments.append(Payment(
                payment_id=next_payment_id(),
                reference_number=inv.invoice_number,
                customer_name=inv.customer_name,
                amount=inv.amount,
                payment_date=pay_date + timedelta(days=1),
            ))

        elif roll < 0.88:
            # Overpayment
            payments.append(Payment(
                payment_id=next_payment_id(),
                reference_number=inv.invoice_number,
                customer_name=inv.customer_name,
                amount=round(inv.amount + random.uniform(500, 2000), 2),
                payment_date=pay_date,
            ))

        elif roll < 0.94:
            # Messy / partial reference number, still resolvable by customer + amount
            payments.append(Payment(
                payment_id=next_payment_id(),
                reference_number=f"payment for {inv.invoice_number.split('/')[-1]} order",
                customer_name=inv.customer_name,
                amount=inv.amount,
                payment_date=pay_date,
            ))

        # else (remaining ~6%): no payment at all -> stays unmatched/pending

    # A few orphan payments that don't correspond to any invoice (wrong customer/reference,
    # advance payments, etc.) - these should show up as "unmatched payments" needing review.
    for _ in range(4):
        payments.append(Payment(
            payment_id=next_payment_id(),
            reference_number=f"ADV-{random.randint(100, 999)}",
            customer_name=random.choice(CUSTOMERS),
            amount=round(random.uniform(2_000, 50_000), 2),
            payment_date=date(2025, 1, 1) + timedelta(days=random.randint(0, 240)),
        ))

    random.shuffle(payments)
    return payments


def generate_dataset(n_invoices: int = 40) -> Tuple[List[Invoice], List[Payment]]:
    invoices = _make_invoices(n_invoices)
    payments = _make_payments(invoices)
    return invoices, payments


def write_csv(invoices: List[Invoice], payments: List[Payment], out_dir: str = "data") -> None:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    with open(out_path / "invoices.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(invoices[0]).keys()))
        writer.writeheader()
        for inv in invoices:
            writer.writerow(asdict(inv))

    with open(out_path / "payments.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(payments[0]).keys()))
        writer.writeheader()
        for pmt in payments:
            writer.writerow(asdict(pmt))


if __name__ == "__main__":
    invoices, payments = generate_dataset(40)
    write_csv(invoices, payments)
    print(f"Generated {len(invoices)} invoices and {len(payments)} payments in ./data/")
