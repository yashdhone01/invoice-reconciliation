"""
Optional "next stage" feature: AI-generated reconciliation summary.

Design decision: rather than hard-depending on a live LLM API call (which would
make this assignment fail to run for a reviewer without an API key, and adds
network latency to a simple GET endpoint), this module generates a natural
language narrative using a template-driven approach over the aggregated
numbers. This keeps the endpoint fast, deterministic, and runnable offline.

If an ANTHROPIC_API_KEY environment variable is present, it will instead call
the Claude API for a genuinely model-generated narrative. Both paths return
plain text in the same shape, so the rest of the app doesn't care which one
ran.
"""

import os


def _template_summary(summary: dict) -> str:
    total = summary["total_invoices"]
    matched = summary["matched_invoices"]
    match_rate = (matched / total * 100) if total else 0

    parts = [
        f"Out of {total} invoices processed, {matched} ({match_rate:.0f}%) were fully "
        f"reconciled against payments received."
    ]

    if summary["partially_matched_invoices"]:
        parts.append(
            f"{summary['partially_matched_invoices']} invoice(s) are only partially paid "
            f"and remain open for the balance."
        )
    if summary["overpaid_invoices"]:
        parts.append(
            f"{summary['overpaid_invoices']} invoice(s) received more than the billed amount "
            f"and should be reviewed for refund or credit note."
        )
    if summary["unmatched_invoices"]:
        parts.append(
            f"{summary['unmatched_invoices']} invoice(s) have no corresponding payment yet, "
            f"totalling a pending value of {summary['total_pending_value']:.2f}."
        )
    if summary["unmatched_payments_count"]:
        parts.append(
            f"Additionally, {summary['unmatched_payments_count']} incoming payment(s) worth "
            f"{summary['unmatched_payments_value']:.2f} could not be linked to any invoice and "
            f"may be advance payments or reference errors."
        )
    if summary["duplicate_payments_flagged"]:
        parts.append(
            f"{summary['duplicate_payments_flagged']} invoice(s) show signs of a duplicate "
            f"payment and need manual verification before closing the books."
        )

    return " ".join(parts)


def _llm_summary(summary: dict) -> str:
    """Calls the Anthropic API for a model-generated narrative. Requires ANTHROPIC_API_KEY."""
    import anthropic

    client = anthropic.Anthropic()
    prompt = (
        "You are a finance operations assistant. Write a concise 3-4 sentence "
        "executive summary of this invoice reconciliation run for a finance manager. "
        f"Data: {summary}"
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def generate_ai_summary(summary: dict) -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _llm_summary(summary)
        except Exception:
            # Fall back gracefully if the API call fails for any reason (no key, no network, etc.)
            return _template_summary(summary)
    return _template_summary(summary)
