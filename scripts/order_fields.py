#!/usr/bin/env python3
"""What is actually stored in the fields the GST export depends on. READ ONLY.

    .venv/bin/python scripts/order_fields.py

Writes nothing, opens the database read-only, and prints no e-mail address, no name and no birth detail -
only shapes and counts. It exists because the export's behaviour depends on what the column CONTAINS, and
the developer's database and production need not agree: a value that is impossible through the API can
still be sitting in a row somebody wrote by hand.

`place_of_supply` is the one that matters. The checkout API accepts `^[0-9]{2}$` only, so a two-LETTER
value such as "MH" cannot have come through it - but if production holds any, then those orders' issued
invoices carry no CGST/SGST split either, which is a bigger problem than a spreadsheet column.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from app import db
    from app.payments import states, store  # noqa: F401  - store imported for its schema registration

    with db.transaction(write=False) as conn:
        paid = conn.execute("SELECT COUNT(*) AS n FROM orders WHERE status='paid'").fetchone()["n"]
        invoiced = conn.execute("SELECT COUNT(*) AS n FROM orders "
                                "WHERE invoice_no IS NOT NULL AND TRIM(invoice_no) <> ''").fetchone()["n"]
        print(f"orders: {paid} paid, {invoiced} with an invoice number\n")

        print("place_of_supply, distinct values with counts:")
        rows = conn.execute(
            "SELECT COALESCE(place_of_supply, '<NULL>') AS value, COUNT(*) AS n FROM orders "
            "WHERE status='paid' GROUP BY value ORDER BY n DESC, value").fetchall()
        for row in rows:
            value = row["value"]
            if value == "<NULL>":
                shape = "not recorded (paid before checkout asked, 28 Sep 2026)"
            elif value.isdigit() and states.is_known(value):
                shape = f"numeric GST code - {states.name(value)}"
            elif value.isdigit():
                shape = "numeric but NOT a GST state code"
            else:
                shape = "LETTER code - cannot have come through the checkout API"
            print(f"  {value:<10} {row['n']:>4}   {shape}")
        if not rows:
            print("  (no paid orders)")

        print("\nfields the export prints, counts of blanks among invoiced orders:")
        for label, column in (("customer name", "json_extract(names_json, '$.self')"),
                              ("razorpay payment id", "payment_id"),
                              ("e-mail", "email")):
            try:
                blank = conn.execute(
                    f"SELECT COUNT(*) AS n FROM orders WHERE invoice_no IS NOT NULL "
                    f"AND TRIM(COALESCE({column}, '')) = ''").fetchone()["n"]
                print(f"  {label:<22} {blank:>4} blank of {invoiced}")
            except Exception as exc:  # noqa: BLE001 - a column that is not there is an answer too
                print(f"  {label:<22} could not read ({type(exc).__name__})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
