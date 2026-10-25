#!/usr/bin/env python3
"""Where people stop filling in the birth-details form. READ ONLY.

    .venv/bin/python scripts/form_funnel.py              # last 30 days
    .venv/bin/python scripts/form_funnel.py --days 7     # a window, for before/after
    .venv/bin/python scripts/form_funnel.py --lang hi    # one tree

WHY. 6,372 people arrived on the kundli page in thirty days and 999 charts came out of it: five in six
left without one, and nothing recorded WHERE they stopped. Every explanation for that number was a
guess until these steps existed.

WHAT IS COUNTED. Events, not people: the browser sends one of each step per page load, so a step's
count is "page loads that reached this step". The percentages are against `form_seen`, which is the
only honest denominator here - somebody who never scrolled to the form never had the chance to leave it.

THE SPLIT THAT MATTERS IS MOBILE VS DESKTOP. A date picker, a time picker and a city search behave
differently on a phone, and the phone is where nearly all of this traffic is.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

#: In the order somebody meets them. The labels say what the step MEANS, because a funnel whose steps
#: are vague is a funnel that gets argued about.
STEPS = [
    ("form_seen", "form scrolled into view"),
    ("first_touch", "put a cursor in a field"),
    ("field_done:date", "date of birth filled"),
    ("field_done:time", "time of birth filled"),
    ("place_typed:city", "started typing a place"),
    ("place_none:city", "   ...and got NO match"),
    ("place_picked:city", "   ...or picked one"),
    ("field_done:city", "place filled"),
    ("submit", "pressed the button"),
    ("invalid", "form came back at them"),
    ("result", "chart shown"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--lang", default="", help="en, hi or mr; default all three")
    args = parser.parse_args()

    from app import analytics, db  # noqa: F401 - imported for its schema registration

    now = dt.datetime.now(IST)
    since = (now - dt.timedelta(days=args.days)).timestamp()
    where = "ts >= ? AND feature = 'kundli_form' AND COALESCE(internal,0)=0"
    params: list = [since]
    if args.lang:
        where += " AND lang = ?"
        params.append(args.lang)

    with db.transaction(write=False) as conn:
        rows = conn.execute(
            f"SELECT action, detail, COALESCE(device,'') AS device, COUNT(*) AS n "
            f"FROM site_events WHERE {where} GROUP BY action, detail, device", params).fetchall()
        # The same window and language filter, pointed at the offer events instead. Built outside the
        # f-string: a replace() with quotes in it cannot live inside one.
        offer_where = where.replace("feature = 'kundli_form'", "feature = 'offer'")
        offers = conn.execute(
            "SELECT action, COALESCE(device,'') AS device, COUNT(*) AS n FROM site_events "
            f"WHERE {offer_where} GROUP BY action, device", params).fetchall()
        by_entry = conn.execute(
            f"SELECT COALESCE(entry,'') AS entry, action, COUNT(*) AS n FROM site_events "
            f"WHERE {where} AND action IN ('form_seen','result') GROUP BY entry, action", params).fetchall()

    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        field = (row["detail"] or "").replace("field=", "")
        key = f"{row['action']}:{field}" if field else row["action"]
        counts.setdefault(key, {}).setdefault(row["device"] or "?", 0)
        counts[key][row["device"] or "?"] += row["n"]

    print(f"the {args.days} days to {now:%d %b %Y}, IST"
          f"{' - ' + args.lang + ' only' if args.lang else ''}\n")

    seen = sum(counts.get("form_seen", {}).values())
    if not seen:
        print("  Nothing recorded yet. The form steps ship in this candidate, so this stays empty")
        print("  until it is deployed and somebody opens the kundli page.")
        return 0

    print(f"{'step':34}{'all':>8}{'mobile':>9}{'desktop':>9}{'of seen':>9}{'drop':>8}")
    previous = None
    for key, label in STEPS:
        by_device = counts.get(key, {})
        total = sum(by_device.values())
        share = f"{100 * total / seen:5.1f}%" if seen else "    -"
        # The drop is measured against the step BEFORE it, and only for the steps everybody passes
        # through - the place branches are alternatives, not a sequence, so a "drop" there is noise.
        drop = ""
        if previous and key not in ("place_none:city", "place_picked:city", "invalid"):
            lost = previous - total
            drop = f"{100 * lost / previous:5.1f}%" if previous and lost > 0 else "    -"
        print(f"  {label:32}{total:>8}{by_device.get('mobile', 0):>9}"
              f"{by_device.get('desktop', 0):>9}{share:>9}{drop:>8}")
        if key not in ("place_none:city", "place_picked:city", "invalid"):
            previous = total

    print("\nthe field the form sent them back to:")
    invalid = {key: value for key, value in counts.items() if key.startswith("invalid:")}
    for key, by_device in sorted(invalid.items(), key=lambda item: -sum(item[1].values())):
        print(f"  {key.split(':', 1)[1]:32}{sum(by_device.values()):>8}"
              f"{by_device.get('mobile', 0):>9}{by_device.get('desktop', 0):>9}")
    if not invalid:
        print("  none recorded")

    print("\nthe paid report's offer:")
    offer_counts: dict[str, dict[str, int]] = {}
    for row in offers:
        offer_counts.setdefault(row["action"], {}).setdefault(row["device"] or "?", 0)
        offer_counts[row["action"]][row["device"] or "?"] += row["n"]
    views = sum(offer_counts.get("offer_seen", {}).values())
    clicks = sum(offer_counts.get("offer_click", {}).values())
    print(f"  {'seen':32}{views:>8}{offer_counts.get('offer_seen', {}).get('mobile', 0):>9}"
          f"{offer_counts.get('offer_seen', {}).get('desktop', 0):>9}")
    print(f"  {'pressed':32}{clicks:>8}{offer_counts.get('offer_click', {}).get('mobile', 0):>9}"
          f"{offer_counts.get('offer_click', {}).get('desktop', 0):>9}")
    if views:
        print(f"  {clicks / views * 100:.1f}% of people who saw the offer pressed it")

    print("\nform seen -> chart shown, by the page they ARRIVED on:")
    arrivals: dict[str, dict[str, int]] = {}
    for row in by_entry:
        arrivals.setdefault(row["entry"] or "(not recorded)", {})[row["action"]] = row["n"]
    for entry, actions in sorted(arrivals.items(), key=lambda item: -item[1].get("form_seen", 0)):
        shown, done = actions.get("form_seen", 0), actions.get("result", 0)
        rate = f"{100 * done / shown:5.1f}%" if shown else "    -"
        print(f"  {entry:32}{shown:>8}{done:>9}{rate:>9}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
