"""Admin: issue the GST credit note for a refund that was processed before credit notes existed.

    .venv/bin/python scripts/issue_credit_notes.py                   # list refunds with no credit note (changes nothing)
    .venv/bin/python scripts/issue_credit_notes.py --issue           # issue them, oldest refund first
    .venv/bin/python scripts/issue_credit_notes.py --issue REFUND    # just this one (rfnd_...)

Read-only by default, because this allocates numbers in a series that is claimed to be consecutive and a
number cannot be given back. Every refund processed from now on gets its note automatically, in the webhook
(app/payments/routes.py); this exists for the ones that arrived before that code did - on 2026-09-29 there was
one, the live test refund.

OLDEST FIRST, deliberately. The series is consecutive in the thing being numbered, so backfilling a January
refund after a March one would number them in the order somebody ran a script, which is exactly what the
allocation at payment time was written to avoid.

It never moves money and never contacts Razorpay: it reads refunds this database already recorded. Exit code:
0 nothing to do or all issued, 1 something could not be issued, 2 usage.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.ai import config as _config  # noqa: E402,F401  (loads .env)
from app.payments import credit_note, gst, store  # noqa: E402


def _when(ts) -> str:
    return dt.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M") if ts else "-"


def _pending() -> list[dict]:
    """Every processed refund with no credit note, oldest first."""
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT * FROM webhook_refunds WHERE credit_no IS NULL ORDER BY at, refund_id").fetchall()
    return [dict(row) for row in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Issue credit notes for refunds recorded before they existed.")
    parser.add_argument("refund", nargs="?", help="one refund id (rfnd_...); default is all of them")
    parser.add_argument("--issue", action="store_true", help="actually allocate the numbers (default: list only)")
    args = parser.parse_args(argv)

    pending = [row for row in _pending() if not args.refund or row["refund_id"] == args.refund]
    if not pending:
        print("no refund is waiting for a credit note." if not args.refund else
              f"{args.refund}: not found, or it already has a credit note.")
        return 0

    print(f"{len(pending)} refund(s) with no credit note:")
    failed = 0
    for row in pending:
        order = store.get_order(row["order_id"])
        amounts = gst.recorded(order) if order else None
        why = ("order not found" if order is None else
               "the sale has no recorded GST (paid before the GST columns existed)" if amounts is None else
               "the order has no invoice number, so there is nothing for a note to reference"
               if not order.get("invoice_no") else "")
        print(f"  {row['refund_id']}  order {row['order_id']}  Rs {int(row['amount_paise']) / 100:g}  "
              f"refunded {_when(row['at'])}" + (f"  CANNOT ISSUE: {why}" if why else ""))
        if why:
            failed += 1
            continue
        if not args.issue:
            continue
        number = credit_note.issue(order, row["refund_id"])
        if number:
            issued = store.get_refund(row["refund_id"])
            print(f"      -> {number}: taxable value Rs {int(issued['base_paise']) / 100:g} + "
                  f"GST Rs {int(issued['gst_paise']) / 100:g} credited against invoice {issued['invoice_no']}")
        else:
            failed += 1
            print("      -> NOT ISSUED (see app/payments/credit_note.issue)")

    if not args.issue:
        print("\nnothing was changed. Add --issue to allocate these numbers.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
