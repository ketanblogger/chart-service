#!/usr/bin/env python
"""Mark our own orders and usage events internal, so business metrics mean what they say.

NOTHING IS DELETED. Every row keeps its invoice number, its credit note, its GST figures and its place of
supply: the 29 September Rs 59 order and its Rs 57.60 credit note are accounting records a CA and a GST
return both need. This changes what the dashboard COUNTS, not what the books contain.

    cd /srv/astrology && .venv/bin/python scripts/mark_internal_orders.py            # dry run
    cd /srv/astrology && .venv/bin/python scripts/mark_internal_orders.py --apply    # write

The dry run prints every order it would mark, with its date, product, amount and a masked address, and
every order it CANNOT judge. It writes nothing without --apply.

IT REFUSES TO RUN WITH AN EMPTY ADMIN_EMAILS. In that state no order can be recognised as the
proprietor's, so the script would mark nothing, find nothing, and report success - which reads exactly
like "there was nothing internal" and is the one wrong conclusion available.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the classification (default: dry run)")
    args = parser.parse_args()

    from app import db
    from app.payments import internal as payments_internal
    # IMPORTED FOR ITS SIDE EFFECT, and that is why it looks unused. Both modules call
    # db.register_columns at import time, and without them this script queries a column the local
    # database has never been told to add - which fails as "no such column: internal" on a schema that
    # is actually correct.
    from app import analytics as _analytics  # noqa: F401
    from app.payments import store as _store  # noqa: F401

    try:
        admins = payments_internal.require_admins()
    except payments_internal.NoAdminsConfigured as exc:
        print(f"REFUSING: {exc}")
        return 1
    print(f"admin addresses configured: {len(admins)}")

    # ONE TRANSACTION FOR THE WHOLE RUN. It used to read in one transaction, classify outside any, and
    # write in a second - so the rows being marked were not necessarily the rows that were read, and a
    # failure half way through the writes left the classification half applied. Reading and writing under
    # one write transaction also takes SQLite's lock for the duration, which is what makes "nothing was
    # written" true when this raises.
    with db.transaction(write=True) as conn:
        orders = [dict(row) for row in conn.execute(
            "SELECT id, product, amount_paise, status, email, live, internal, internal_reason, "
            "       created_at, invoice_no, refunded_paise "
            "FROM orders ORDER BY created_at").fetchall()]
        return _classify_and_maybe_write(conn, orders, admins, payments_internal, apply=args.apply)


def _classify_and_maybe_write(conn, orders, admins, payments_internal, *, apply: bool) -> int:
    import datetime as dt

    to_mark, undecided, already, business = [], [], [], []
    for order in orders:
        if order.get("internal") is not None:
            already.append(order)
            continue
        reason = payments_internal.reason_for(order, admins)
        # EVERY INTERNAL REASON, listed from the module that defines them rather than spelled out here.
        # This read `(ADMIN, TEST_MODE)`, so when BEFORE_FIRST_SALE was added the orders it identified
        # fell through to the `else` and were classified as BUSINESS - the exact opposite of the rule,
        # and silently: the dry run printed them under "look like customers'" and nothing complained.
        if reason in payments_internal.INTERNAL_REASONS:
            to_mark.append((order, reason))
        elif reason == payments_internal.UNDECIDED:
            undecided.append(order)
        else:
            business.append(order)

    def line(order, note=""):
        when = dt.datetime.fromtimestamp(order["created_at"] or 0,
                                         dt.timezone(dt.timedelta(hours=5, minutes=30)))
        return (f"  {when:%d %b %Y %H:%M}  {order['product']:20} "
                f"Rs {(order['amount_paise'] or 0) / 100:8.2f}  {order['status']:9} "
                f"{payments_internal.mask(order['email']):10} "
                f"{'invoice ' + order['invoice_no'] if order.get('invoice_no') else '':16} {note}")

    print(f"\n{len(to_mark)} order(s) WOULD BE MARKED INTERNAL:")
    for order, reason in to_mark:
        print(line(order, reason))
    if not to_mark:
        print("  none")

    print(f"\n{len(undecided)} order(s) CANNOT BE JUDGED (no razorpay mode recorded, non-admin address).")
    print("  These are left alone on purpose: marking a real sale internal makes revenue quietly too low,")
    print("  and nobody notices a number that is missing. Decide these by hand if any is ours.")
    for order in undecided:
        print(line(order, payments_internal.UNDECIDED))
    if not undecided:
        print("  none")

    paid_business = [o for o in business if o["status"] == "paid" and not (o.get("refunded_paise") or 0)]
    print(f"\n{len(business)} order(s) look like customers' ({len(paid_business)} paid and unrefunded).")
    print(f"{len(already)} already carry a classification.")

    if not apply:
        print("\nDRY RUN: nothing was written. Re-run with --apply.")
        return 0

    if True:
        for order, reason in to_mark:
            conn.execute("UPDATE orders SET internal = 1, internal_reason = ? WHERE id = ?",
                         (reason, order["id"]))
        # Everything judged a customer's is marked EXPLICITLY too, so "not yet classified" and "known to
        # be business" stop looking the same in the table.
        for order in business:
            conn.execute("UPDATE orders SET internal = 0, internal_reason = NULL WHERE id = ?",
                         (order["id"],))
        # Usage events belonging to an admin account: the AI they spent is real money, and it is shown
        # on its own line rather than folded into business cost.
        # THERE IS NO `users` TABLE AND NO `user_id` COLUMN. This read
        #     UPDATE site_events ... WHERE user_id IN (SELECT id FROM users WHERE lower(email) IN (...))
        # which is SQL written against a schema that does not exist, and it brought the whole --apply
        # down on production with "no such table: users". The identity table is `accounts`, keyed by
        # e-mail with no integer id, and site_events stores a HASHED account_id precisely so an address
        # cannot be recovered from it - so that join could never have worked.
        #
        # What the table does carry is `is_admin`, written at the point of the event by the same
        # accounts.is_admin() that reads ADMIN_EMAILS, including on the chat path where the AI money is.
        # That is the column that already means "this was us".
        #
        # ITS LIMIT, STATED: an event recorded while ADMIN_EMAILS was unset carries is_admin = 0 and
        # cannot be recovered here, because the address it would need was deliberately never stored.
        marked_events = conn.execute(
            "UPDATE site_events SET internal = 1 WHERE internal IS NULL AND is_admin = 1").rowcount
    print(f"\nAPPLIED: {len(to_mark)} internal, {len(business)} business, "
          f"{marked_events} usage event(s) marked internal.")
    print("Nothing was deleted; every invoice and credit note is untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
