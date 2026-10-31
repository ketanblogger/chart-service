#!/usr/bin/env python3
"""The one mail to orders abandoned at checkout. DRY RUN BY DEFAULT.

    .venv/bin/python scripts/unpaid_mail.py              # shows who would be written to, sends nothing
    .venv/bin/python scripts/unpaid_mail.py --send       # actually sends

A dry run writes no stamp, so rehearsing it does not silently consume anybody's one mail.

Each address is owed exactly ONE of these, ever. The stamp is taken before the send, so a failure costs
a missing mail rather than a duplicated one - a missing nudge costs one e-mail, a duplicate costs trust.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--send", action="store_true", help="actually send; omit to rehearse")
    parser.add_argument("--created-after", metavar="WHEN",
                        help="only orders created at or after this IST moment - 'YYYY-MM-DD' or "
                             "'YYYY-MM-DD HH:MM'. REQUIRED with --send.")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    # REQUIRED FOR A REAL SEND, and that is the point of it. The rolling window says "still live"; it
    # cannot say "placed after we decided to write about these at all". Without a floor, a run a
    # fortnight from now would sweep in orders that predate the decision - people who abandoned a
    # checkout long ago and have heard nothing since, which is exactly who must not be written to.
    if args.send and not args.created_after:
        parser.error("--send needs --created-after; refusing to mail orders older than the decision "
                     "to start mailing. Use the deploy date, e.g. --created-after 2026-10-23")

    floor = _moment(args.created_after) if args.created_after else None

    from app.payments import unpaid

    summary = unpaid.mail_abandoned(limit=args.limit, dry_run=not args.send, created_after=floor)
    verb = "would be written to" if summary["dry_run"] else "written to"
    scope = f" created on or after {args.created_after} IST" if args.created_after else ""
    print(f"  {summary['considered']} abandoned order(s){scope} considered, "
          f"{summary['sent']} {verb}, {summary['skipped']} skipped")
    if summary["dry_run"]:
        print("  Nothing was sent and no stamp was written. Re-run with --send to do it for real.")
    return 0


def _moment(text: str) -> float:
    """'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM', read as IST, as a POSIX timestamp.

    IST because every other date this business states is IST - an invoice, a panchang, a rashifal day.
    A floor read as UTC would be five and a half hours out, which on a date boundary is a different set
    of orders.
    """
    import datetime as dt

    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    for shape in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, shape).replace(tzinfo=ist).timestamp()
        except ValueError:
            continue
    raise SystemExit(f"could not read {text!r} as a date: use YYYY-MM-DD or 'YYYY-MM-DD HH:MM'")


if __name__ == "__main__":
    raise SystemExit(main())
