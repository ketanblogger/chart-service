#!/usr/bin/env python3
"""Which paid reports have actually been downloaded - and send the one reminder to those that have not.

    cd /srv/astrology && .venv/bin/python scripts/delivery_report.py              # shows, changes nothing
    cd /srv/astrology && .venv/bin/python scripts/delivery_report.py --remind     # sends the reminders

The listing covers every live paid order with a report. "downloaded" is the FIRST time anybody opened it;
orders paid before this column existed show as unknown rather than as never-opened, because nobody was
recording it then and a blank is not a no.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def when(stamp) -> str:
    if not stamp:
        return "-"
    return dt.datetime.fromtimestamp(float(stamp), IST).strftime("%d %b %H:%M")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--remind", action="store_true", help="send the one reminder where it is due")
    parser.add_argument("--after-hours", type=int, default=24)
    args = parser.parse_args()

    import time

    from app import db
    from app.payments import delivery, store  # noqa: F401  (registers the orders columns)

    since = time.time() - args.days * 86400
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT id, product, amount_paise, paid_at, mail_status, mail_at, downloaded_at, "
            "       reminded_at, COALESCE(live, 1) AS live "
            "FROM orders WHERE status = 'paid' AND report_id IS NOT NULL AND paid_at > ? "
            "ORDER BY paid_at DESC", (since,)).fetchall()

    if not rows:
        print(f"no paid orders with a report in the last {args.days} days.")
        return 0

    print(f"{'order':<22} {'product':<24} {'paid':<14} {'e-mail':<10} {'downloaded':<14} mode")
    # ONE CLASSIFIER, SHARED WITH THE ADMIN ORDERS PAGE AND THE REMINDER GATE. This script used to read
    # orders.downloaded_at on its own and reported all fourteen orders as "NEVER downloaded" while the
    # Orders page showed the PDF delivered for four of them. Two screens answering one question from two
    # sources will always end up disagreeing; now they call the same function.
    from app.payments import delivery as _delivery

    started = _delivery.tracking_started()
    opened = never = unknown = 0
    for row in rows:
        state, at = _delivery.download_state(dict(row), started=started)
        if state == _delivery.DOWNLOADED:
            downloaded = when(at)
            opened += 1
        elif state == _delivery.UNKNOWN:
            downloaded = "unknown"
            unknown += 1
        else:
            downloaded = "NEVER"
            never += 1
        print(f"{row['id'][:22]:<22} {row['product'][:24]:<24} {when(row['paid_at']):<14} "
              f"{(row['mail_status'] or '-')[:10]:<10} {downloaded:<14} "
              f"{'live' if row['live'] else 'TEST'}")

    print(f"\n{len(rows)} order(s): {opened} downloaded, {never} never opened, "
          f"{unknown} unknown (paid before this was recorded - NOT a no).")
    if unknown and args.remind:
        print(f"  {unknown} order(s) will NOT be reminded: their download state is unknown, and a nudge "
              "about a report somebody already has is worse than no nudge at all.")

    if args.remind:
        result = delivery.remind_undownloaded(after_hours=args.after_hours)
        print(f"\nreminders: {result['sent']} sent, {result['skipped']} skipped, "
              f"of {result['considered']} considered.")
    else:
        print("\nNothing sent. Re-run with --remind to send the one reminder where it is due.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
