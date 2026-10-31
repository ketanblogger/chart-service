#!/usr/bin/env python3
"""Check, and then enforce, that no two rows share a tax-invoice number.

    .venv/bin/python scripts/invoice_numbers.py --check     # READ ONLY, changes nothing
    .venv/bin/python scripts/invoice_numbers.py --apply     # adds the unique index

WHY THIS IS A SCRIPT AND NOT A REGISTERED SCHEMA. `db.register_schema` runs its DDL lazily against
whatever database is in use, on import, in every process - including the web app's. A unique index that
cannot be created because the data already violates it would then raise on a production start, and the
site would be down over a bookkeeping problem. So the constraint is applied deliberately, by a person,
after they have seen what is in the way.

WHY A UNIQUE INDEX IS THE WHOLE MIGRATION. SQLite refuses to build one over duplicate values, so
"refuses to apply if duplicates exist" is not a check this script performs and could get wrong - it is
what the database does. The check below exists to say WHICH rows, and to say it without writing
anything.

The index is PARTIAL (`WHERE invoice_no IS NOT NULL`): every order that has not been paid has a NULL
number, and SQLite treats NULLs as distinct anyway - the partial clause says so out loud and keeps the
index to the rows that matter.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

INDEX = "orders_invoice_no_unique"
DDL = (f"CREATE UNIQUE INDEX {INDEX} ON orders (invoice_no) WHERE invoice_no IS NOT NULL")


def duplicates(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT invoice_no, COUNT(*) AS n, GROUP_CONCAT(id, ' ') AS ids FROM orders "
        "WHERE invoice_no IS NOT NULL AND TRIM(invoice_no) <> '' "
        "GROUP BY invoice_no HAVING n > 1 ORDER BY invoice_no").fetchall()
    return [dict(row) for row in rows]


def index_exists(conn) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                             (INDEX,)).fetchone())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="list duplicates; writes nothing")
    parser.add_argument("--apply", action="store_true", help="create the unique index")
    args = parser.parse_args()
    if not (args.check or args.apply):
        parser.error("say --check or --apply")

    from app import db
    from app.payments import store  # noqa: F401  - imported for its schema registration

    with db.transaction(write=False) as conn:
        found = duplicates(conn)
        already = index_exists(conn)

    print(f"unique index present: {'yes' if already else 'no'}")
    if found:
        total = sum(row["n"] for row in found)
        print(f"\nDUPLICATE INVOICE NUMBERS: {len(found)} number(s) across {total} rows")
        for row in found:
            print(f"  {row['invoice_no']}  x{row['n']}  orders: {row['ids']}")
        print("\nA tax-invoice series must have no repeats: two documents with one number cannot both be\n"
              "filed, and whichever is wrong has already gone to a buyer. Decide what each row should be\n"
              "before enforcing - this script will not choose for you.")
    else:
        print("no duplicate invoice numbers")

    if not args.apply:
        print("\nREAD ONLY: nothing was written.")
        return 1 if found else 0

    if already:
        print("\nnothing to do: the index is already there.")
        return 0
    if found:
        print("\nREFUSING to apply: fix the duplicates above first. Nothing was written.")
        return 1
    with db.transaction() as conn:
        conn.execute(DDL)
    print(f"\nAPPLIED: {INDEX}. A second row with an existing invoice number is now refused by the\n"
          "database rather than by whoever reads the export.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
