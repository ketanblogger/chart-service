#!/usr/bin/env python3
"""Put the cost onto report usage events that were written without one.

Every report sale went onto the dashboard with revenue and a cost of zero, because `_count_sale` never
carried the order's own `cost_inr` across. The orders table HAS the number - the generation pipeline has
been writing it all along - so the events can be repaired from it.

    cd /srv/astrology && .venv/bin/python scripts/backfill_event_costs.py          # shows what it would do
    cd /srv/astrology && .venv/bin/python scripts/backfill_event_costs.py --apply

CHATS ARE NOT BACKFILLED, on purpose. A chat answer's cost lived only in the reply's meta at the time, and
for the months this was broken it was never written anywhere - so there is nothing to recover. Those
events stay marked "not recorded", which is the truth, rather than being given a made-up number or a zero
that would read as free.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the costs (default: show only)")
    args = parser.parse_args()

    from app import analytics  # noqa: F401  (registers site_events and its columns)
    from app.payments import store  # noqa: F401  (registers orders and its columns)

    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT e.id, e.day, e.detail, e.revenue_inr, o.id AS order_id, o.cost_inr "
            "FROM site_events e "
            "JOIN orders o ON o.user_id = e.account_id AND o.product = e.detail "
            "WHERE e.feature = 'report' AND e.action != 'refund' AND e.cost_known = 0 "
            "  AND o.cost_inr IS NOT NULL "
            "GROUP BY e.id").fetchall()

    if not rows:
        print("no report events are missing a cost.")
        return 0

    total = 0.0
    for row in rows:
        total += float(row["cost_inr"] or 0)
        print(f"  {row['day']}  event {row['id']}  {row['detail']:<10} "
              f"revenue {float(row['revenue_inr'] or 0):8.2f}  cost {float(row['cost_inr'] or 0):8.2f}")
    print(f"\n{len(rows)} event(s), {total:.2f} of cost to record.")

    if not args.apply:
        print("\nNothing written. Re-run with --apply to write these costs.")
        return 0

    with db.transaction() as conn:
        for row in rows:
            conn.execute("UPDATE site_events SET cost_inr = ?, cost_known = 1 WHERE id = ?",
                         (float(row["cost_inr"] or 0), row["id"]))
    print(f"\nwritten: {len(rows)} event(s) now carry their cost.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
