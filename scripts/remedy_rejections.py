#!/usr/bin/env python3
"""Count remedy-linkage rejections per day. READ ONLY - opens nothing but the run files.

    .venv/bin/python scripts/remedy_rejections.py            # the last 7 days
    .venv/bin/python scripts/remedy_rejections.py --days 30
    .venv/bin/python scripts/remedy_rejections.py --days 7 --show   # with the messages

WHAT IT COUNTS. The checker refuses a reading whose tip names a graha the reading itself never
discusses: "Chant the Hanuman Chalisa" under a page that never mentions Mangal is filler that would fit
any page. Every refusal is recorded in var/rashifal/runs/<run>.json under `rejections`, with the rashi,
the period, the language and the attempt it happened on.

WHY THE COUNT MATTERS. A rejection is not a failure - the generator retries and usually passes on the
second attempt, so these cost tokens and time rather than quality. The question is whether the prompt
has stopped producing them. If it has, nothing needs doing; if it has not, the remedy's graha should be
chosen deterministically rather than asked for.

ATTEMPT 1 IS COUNTED SEPARATELY from later ones, because they mean different things: a first-attempt
rejection is the prompt being imperfect, and a rejection on attempt 2 or 3 is the prompt being unable
to fix itself when told.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "var" / "rashifal" / "runs"

#: The checker's own words, from app/rashifal/generate.py. Matched on the stable part of the sentence
#: rather than the whole of it, so a reworded ending does not silently drop the count to zero.
NEEDLE = re.compile(r"a remedy must\s+follow from a graha", re.S)

#: The run id ends with the moment the run started: <uuid>-YYYYMMDDTHHMMSS.
STAMP = re.compile(r"-(\d{8})T(\d{6})$")


def run_day(run_id: str, fallback: Path) -> str:
    match = STAMP.search(run_id or "")
    if match:
        return f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
    # No stamp in the id: fall back to the file's own mtime rather than skipping the run, and say so.
    return dt.datetime.fromtimestamp(fallback.stat().st_mtime).strftime("%Y-%m-%d") + " (mtime)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--show", action="store_true", help="print each rejection's message")
    args = parser.parse_args()

    if not RUNS.is_dir():
        print(f"no run directory at {RUNS} - nothing has been generated on this machine")
        return 0

    cutoff = (dt.date.today() - dt.timedelta(days=args.days - 1)).isoformat()
    per_day: dict[str, list[dict]] = defaultdict(list)
    runs = total = 0

    for path in sorted(RUNS.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"  ! {path.name} could not be read: {exc}", file=sys.stderr)
            continue
        day = run_day(data.get("run_id", ""), path)
        if day[:10] < cutoff:
            continue
        runs += 1
        for rejection in data.get("rejections") or []:
            total += 1
            if NEEDLE.search(str(rejection.get("message", ""))):
                per_day[day].append(rejection)

    print(f"remedy-linkage rejections, the {args.days} days to {dt.date.today()} "
          f"({runs} run file(s) in range)\n")
    if not per_day:
        print("  none.")
        print(f"  ({total} rejection(s) of every other kind in the same runs.)")
        return 0

    for day in sorted(per_day):
        rows = per_day[day]
        first = sum(1 for r in rows if int(r.get("attempt") or 0) <= 1)
        print(f"  {day}  {len(rows):>3}  (attempt 1: {first}, later: {len(rows) - first})")
        if args.show:
            for row in rows:
                print(f"       {row.get('language','?')}/{row.get('rashi','?')}/{row.get('period','?')} "
                      f"attempt {row.get('attempt','?')}: {str(row.get('message',''))[:120]}")
    print(f"\n  {sum(len(v) for v in per_day.values())} remedy-linkage of {total} rejection(s) in total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
