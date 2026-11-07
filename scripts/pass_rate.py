#!/usr/bin/env python
"""First-attempt pass rate by language, and what the retries cost - read-only, from runs already stored.

WHY THIS EXISTS. "Marathi is rejected more than English" was a number on a dashboard; this turns it into a
rate that can be compared before and after a change, from data the generator already records. It makes no
AI calls and writes nothing, so it is safe to run on the VPS at any time.

WHAT A REJECTION COSTS. RASHIFAL_MAX_ATTEMPTS is 2, so a draft the checker refuses is written twice: the
rejected attempt is paid for and thrown away. That makes the first-attempt pass rate a cost figure as much
as a quality one, and it is why cutting Marathi rejections is the cheapest saving available on these pages.

Run it before a prompt change to get the baseline, and again after a few days of runs to get the effect:

    cd /srv/astrology && .venv/bin/python scripts/pass_rate.py --days 30
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30, help="how far back to look (default 30)")
    args = parser.parse_args()

    from app.admin import rashifal_ops

    runs = [run for run in rashifal_ops.rashifal_runs()][: max(1, args.days * 8)]
    if not runs:
        print("no stored runs found - nothing to measure")
        return 0

    generated = collections.Counter()
    rejected = collections.Counter()
    by_kind: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    cost_total = 0.0
    calls_total = 0

    for run in runs:
        calls_total += run.get("calls") or 0
        if run.get("cost_inr") is not None:
            cost_total += float(run["cost_inr"])
        for language, count in (run.get("failed_by_language") or {}).items():
            rejected[language] += count
        for rejection in run.get("rejections") or []:
            if not isinstance(rejection, dict):
                continue
            language = rejection.get("language") or "?"
            rejected[language] += 0  # keep the language present even when the count came from elsewhere
            message = str(rejection.get("message") or "")
            by_kind[language][_kind_of(message)] += 1
        # Page-languages that reached an outcome, which is also the number of jobs: one call each before
        # any rewrite. "failed" ones were paid for too.
        generated["jobs"] += (run.get("generated") or 0) + (run.get("failed") or 0)
        generated["published"] += run.get("generated") or 0

    print(f"{len(runs)} runs, {calls_total} AI calls, "
          f"{'Rs %.2f' % cost_total if cost_total else 'cost not recorded'}\n")

    print("Rejections by language (what the checker refused):")
    for language, count in rejected.most_common():
        print(f"  {language:4} {count:5}")
    if not rejected:
        print("  none recorded")

    print("\nRejection reasons by language:")
    for language in sorted(by_kind):
        kinds = by_kind[language]
        shown = ", ".join(f"{kind} {n}" for kind, n in kinds.most_common(5))
        print(f"  {language:4} {shown}")
    if not by_kind:
        print("  none recorded")

    # A refused draft is paid for and discarded, so this is the share of spend that bought nothing.
    #
    # COUNTED IN CALLS, NOT IN MESSAGES. The first version of this divided the number of blocking MESSAGES
    # by the number of calls and called the result the wasted share - but one refused draft routinely
    # carries several messages, so it read 32% where the truth was 18%, and it would exceed 100% on a
    # draft with enough faults. The number of wasted calls is calls minus the page-languages produced:
    # every job costs one call, and every call beyond that is a rewrite.
    produced = generated["jobs"]
    extra = calls_total - produced
    if calls_total and produced and extra > 0:
        share = extra / calls_total
        print(f"\n{extra} of {calls_total} calls were rewrites after a refusal: {share:.1%} of the spend "
              f"bought a draft that was thrown away.")
        if cost_total:
            print(f"At the recorded cost that is about Rs {cost_total * share:.2f} of Rs {cost_total:.2f}.")
        print(f"({sum(rejected.values())} blocking messages were recorded across those {extra} rewrites; "
              f"a single refused draft often carries several, so messages are not a count of calls.)")
    print("\nFirst-attempt pass rate needs both halves: pages generated per language and refusals per\n"
          "language. Where a run recorded one and not the other, the figures above show what it did record\n"
          "rather than inferring the rest.")
    return 0


def _kind_of(message: str) -> str:
    """The checker's own issue kind, taken from the start of its message rather than guessed."""
    head = message.split(":", 1)[0].strip().lower()
    return head[:24] if head else "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
