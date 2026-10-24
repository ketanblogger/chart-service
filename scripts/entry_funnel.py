#!/usr/bin/env python3
"""The 30-day funnel, split by the kind of page people ARRIVE on. READ ONLY.

    .venv/bin/python scripts/entry_funnel.py            # last 30 days
    .venv/bin/python scripts/entry_funnel.py --days 14  # a window, for before/after

WHY BY ENTRY PAGE. 8,626 visitors and 4 orders is one number, and one number cannot be acted on: it does
not say whether the rashifal pages bring people who never had any intention of buying, or whether the
kundli page converts and simply gets no traffic. Splitting the same 90 days by where the visit STARTED
turns one unusable figure into six comparable ones.

THE FIRST PAGE OF A VISIT, not every page. A visitor is the daily salted hash analytics already stores,
so "entry page" is the earliest path that hash was seen on that day. Nobody is identified by it and it
survives no longer than the hash does.

WHAT EACH STEP MEANS, exactly, because a funnel whose steps are vague is a funnel that gets argued about:

  landed            a browser-confirmed visit (not a crawler fetch)
  used tool         a calculator actually RAN - kundali, matching, mangal-dosha or sade-sati
  saw an offer      a priced offer was rendered to them: the paywall, or a tool result with a buy box
  started checkout  an order row exists, which is written when checkout opens, before any payment
  paid              that order reached status 'paid'

The gap between "started checkout" and "paid" is counted separately as ORDERS CREATED BUT UNPAID,
because that is the one step where somebody decided to buy and then did not, and it is the only step a
change to the checkout can move.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# The classifier lives in app/analytics.py, beside the counting it serves - importing it from here
# would make a script a dependency of the application.
from app.analytics import ENTRY_KINDS, entry_kind  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    from app import analytics, db  # noqa: F401  - imported for its schema registration
    from app.payments import store  # noqa: F401

    now = dt.datetime.now(IST)
    since = (now - dt.timedelta(days=args.days)).timestamp()
    print(f"the {args.days} days to {now:%d %b %Y}, IST\n")

    with db.transaction(write=False) as conn:
        # THE ENTRY PAGE PER VISITOR-DAY: the earliest path that hash was seen on, that day. Admin and
        # crawler-suspect rows are excluded the way the dashboard excludes them.
        rows = conn.execute(
            "SELECT visitor, day, path, MIN(ts) AS first_ts FROM site_visits "
            "WHERE ts >= ? AND COALESCE(is_admin,0)=0 AND COALESCE(suspect,0)=0 AND visitor <> '' "
            "GROUP BY visitor, day", (since,)).fetchall()
        entry = {}
        for row in rows:
            entry.setdefault((row["visitor"], row["day"]), row["path"])
        landed = {}
        for (visitor, day), path in entry.items():
            landed.setdefault(entry_kind(path), set()).add(visitor)

        # The steps that ARE attributable to a visitor. site_events carries a hashed account_id, not the
        # visit hash, so a step can only be tied to an entry page where the account is known - which is
        # most of the funnel's lower half and none of its top. Stated rather than papered over.
        used = conn.execute(
            "SELECT feature, COUNT(*) AS n FROM site_events WHERE ts >= ? AND action='generated' "
            "AND COALESCE(internal,0)=0 GROUP BY feature", (since,)).fetchall()
        offers = conn.execute(
            "SELECT COUNT(*) AS n FROM site_events WHERE ts >= ? AND feature='chat' AND action='paywall' "
            "AND COALESCE(internal,0)=0", (since,)).fetchone()["n"]
        # CUSTOMERS ONLY. `internal` marks our own test and comp orders, and they were being counted
        # as paid and unpaid alongside real ones - on a month with four real sales, two internal rows
        # move every ratio on this page. They are reported separately below rather than dropped,
        # because "none of these were real" is itself worth seeing.
        created = conn.execute(
            "SELECT product, status, COUNT(*) AS n, SUM(amount_paise) AS paise FROM orders "
            "WHERE created_at >= ? AND COALESCE(internal,0)=0 "
            "GROUP BY product, status ORDER BY n DESC", (since,)).fetchall()
        internal = conn.execute(
            "SELECT COALESCE(internal_reason,'(no reason given)') AS why, status, COUNT(*) AS n, "
            "       SUM(amount_paise) AS paise FROM orders "
            "WHERE created_at >= ? AND COALESCE(internal,0)=1 "
            "GROUP BY why, status ORDER BY n DESC", (since,)).fetchall()
        # BY ENTRY PAGE, which is the whole point of the split. NULL for every order placed before the
        # column existed, and those are reported as "not recorded" rather than folded into "other" - an
        # order from before we measured is not an order that came from nowhere in particular.
        by_entry = conn.execute(
            "SELECT COALESCE(entry, '(not recorded)') AS entry, status, COUNT(*) AS n, "
            "       SUM(amount_paise) AS paise FROM orders WHERE created_at >= ? "
            "AND COALESCE(internal,0)=0 GROUP BY entry, status ORDER BY entry, status", (since,)).fetchall()

    print(f"{'entry page':12} {'landed':>8}")
    for name, _ in (*ENTRY_KINDS, ("other", ())):
        print(f"  {name:10} {len(landed.get(name, ())):>8}")
    print(f"  {'TOTAL':10} {len(set().union(*landed.values())) if landed else 0:>8}")

    print("\ntools actually run (not attributable to an entry page - see the module docstring):")
    for row in used:
        print(f"  {row['feature']:14} {row['n']:>6}")
    if not used:
        print("  none recorded")
    print(f"\npaywall shown: {offers}")

    print("\norders created in the window, by product and status - CUSTOMERS ONLY:")
    paid_total = unpaid = 0
    for row in created:
        rupees = (row["paise"] or 0) / 100
        print(f"  {row['product'][:28]:28} {row['status']:10} {row['n']:>4}  Rs {rupees:9.2f}")
        if row["status"] == "paid":
            paid_total += row["n"]
        else:
            unpaid += row["n"]
    if not created:
        print("  none")
    print("\norders by the page the buyer ARRIVED on:")
    for row in by_entry:
        print(f"  {row['entry']:16} {row['status']:10} {row['n']:>4}  Rs {(row['paise'] or 0)/100:9.2f}")
    if not by_entry:
        print("  none")

    print("\nour own orders, counted separately and in none of the figures above:")
    for row in internal:
        print(f"  {row['why'][:28]:28} {row['status']:10} {row['n']:>4}  Rs {(row['paise'] or 0)/100:9.2f}")
    if not internal:
        print("  none")

    print(f"\n  paid {paid_total}, created but NOT paid {unpaid}   (customers only)")
    if unpaid:
        print("  Those are people who opened checkout and stopped. It is the only step a change to the")
        print("  checkout itself can move, which is why it is counted on its own.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
