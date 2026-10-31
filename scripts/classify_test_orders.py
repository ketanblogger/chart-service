#!/usr/bin/env python
"""Show, and optionally mark, the paid orders that were rehearsals rather than sales.

WHY THIS CANNOT BE AUTOMATIC. Neither a Razorpay order id nor a payment id says which key made it, and
until now nothing recorded the mode - so for rows that predate the `live` column there is no fact in the
database that distinguishes a real sale from a browser check. What there IS is a date the owner knows:
the first real sale. Everything paid before it was a rehearsal.

So this prints them and changes nothing unless told to. Run it, read the list, and only then --apply.

    .venv/bin/python scripts/classify_test_orders.py                      # show every paid order
    .venv/bin/python scripts/classify_test_orders.py --before 2026-09-29  # show what would be marked
    .venv/bin/python scripts/classify_test_orders.py --before 2026-09-29 --apply

Marking sets `live = 0`, which takes the order out of revenue, order counts and margin on the dashboard.
Nothing is deleted and no invoice changes: a marked order still resolves, still downloads, still has its
number. `--unmark` puts one back.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def ist(stamp) -> str:
    if not stamp:
        return "—"
    return dt.datetime.fromtimestamp(float(stamp), dt.timezone.utc).astimezone(IST).strftime("%Y-%m-%d %H:%M")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", metavar="YYYY-MM-DD",
                        help="treat paid orders before this IST date as rehearsals")
    parser.add_argument("--apply", action="store_true", help="actually set live = 0 (default: show only)")
    parser.add_argument("--unmark", metavar="ORDER_ID", help="put one order back into the figures")
    args = parser.parse_args(argv)

    if args.unmark:
        with db.transaction() as conn:
            done = conn.execute("UPDATE orders SET live = 1 WHERE id = ?", (args.unmark,))
        print(f"{'marked live again' if done.rowcount else 'no such order'}: {args.unmark}")
        return 0 if done.rowcount else 1

    cutoff = None
    if args.before:
        day = dt.date.fromisoformat(args.before)
        cutoff = dt.datetime.combine(day, dt.time(0, 0), tzinfo=IST).timestamp()

    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT id, product, amount_paise, currency, paid_at, created_at, email, live, razorpay_order_id "
            "FROM orders WHERE status = 'paid' ORDER BY paid_at").fetchall()

    if not rows:
        print("no paid orders at all.")
        return 0

    print(f"{'order':24} {'paid (IST)':17} {'amount':>9}  {'live':>4}  product")
    print("-" * 78)
    doomed, kept_total, doomed_total = [], 0, 0
    for row in rows:
        amount = (row["amount_paise"] or 0) / 100
        flag = "—" if row["live"] is None else ("yes" if row["live"] else "NO")
        mark = cutoff is not None and (row["paid_at"] or 0) < cutoff and row["live"] != 0
        if mark:
            doomed.append(row["id"])
            doomed_total += amount
        elif row["live"] != 0:
            kept_total += amount
        print(f"{row['id']:24} {ist(row['paid_at']):17} {amount:9.2f}  {flag:>4}  "
              f"{row['product'] or '?'}{'   <-- would be marked' if mark else ''}")

    print("-" * 78)
    print(f"{len(rows)} paid order(s). Counted as revenue now: Rs {kept_total + doomed_total:.2f}")
    if cutoff is not None:
        print(f"Would mark {len(doomed)} as rehearsals (Rs {doomed_total:.2f}), "
              f"leaving Rs {kept_total:.2f} as real revenue.")
        if not args.apply:
            print("Nothing changed. Re-run with --apply if that list is right.")
            return 0
        with db.transaction() as conn:
            for order_id in doomed:
                conn.execute("UPDATE orders SET live = 0 WHERE id = ?", (order_id,))
        print(f"marked {len(doomed)} order(s) as rehearsals. The dashboard excludes them from now on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
