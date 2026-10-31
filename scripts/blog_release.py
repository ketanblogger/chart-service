#!/usr/bin/env python3
"""Publish what today's allowance permits from the blog queue. DRY RUN unless --apply.

    .venv/bin/python scripts/blog_release.py              # what would go live, writes nothing
    .venv/bin/python scripts/blog_release.py --apply      # publish them

WHY THIS EXISTS, SAID PLAINLY. Autopublish fired only when a post ARRIVED or was edited through the
API. A draft that was already in the database - because it predates the checks, or because the
catch-up unblocked it - had nothing to pick it up, ever. The queue and the two-a-day cap were built
and nothing called them. This is the caller.

IT PUBLISHES AT MOST `AUTOPUBLISH_PER_DAY`, counted from what is already live TODAY, so a manual
publish from /admin/blog earlier in the day reduces the automatic allowance rather than adding to it.
Safe to run twice: the second run finds the allowance spent.

NOTHING HAPPENS WHILE BLOG_AUTOPUBLISH IS OFF, and the output says so rather than failing quietly.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="publish (default: report only)")
    args = parser.parse_args()

    from app.blog import config, publishing, store

    # THE MANTRA RELEASE RIDES THIS TIMER, and runs FIRST and unconditionally - before the
    # autopublish gate below, because those pages do not publish themselves and are not affected by
    # BLOG_AUTOPUBLISH. They are already answering: the gate is the date, so all this does is tell
    # IndexNow that today's four URLs exist. Nothing here can fail the blog release.
    _release_mantra_pages(args.apply)

    if not config.autopublish():
        print("  BLOG_AUTOPUBLISH is off, so nothing publishes itself. Nothing was done.")
        return 0

    already = store.published_count_today()
    allowance = publishing.AUTOPUBLISH_PER_DAY - already
    queue = publishing.publish_queue()

    print(f"  {len(queue)} draft(s) ready, {already} already published today, "
          f"{max(0, allowance)} slot(s) left of {publishing.AUTOPUBLISH_PER_DAY}")
    if not queue:
        print("  nothing waiting")
        return 0
    for position, post in enumerate(queue[:8], start=1):
        marker = "->" if position <= allowance else "  "
        print(f"   {marker} {post['slug']}  ({post['title'][:54]})")
    if len(queue) > 8:
        print(f"      ... and {len(queue) - 8} more behind them")

    if not args.apply:
        print("\n  Nothing was published. Re-run with --apply.")
        return 0
    if allowance <= 0:
        print("\n  Today's allowance is spent. The queue waits for tomorrow.")
        return 0

    done = publishing.release_due(actor="blog-release timer")
    for post in done:
        print(f"  PUBLISHED  {post['path']}  -  {post['title']}")
    print(f"\n  {len(done)} published. IndexNow was told about each one.")
    return 0


def _release_mantra_pages(apply: bool) -> None:
    """Tell IndexNow about the mantra pages whose release date is today."""
    import datetime as dt

    from app.mantra import texts as mantra_texts

    from app.mantra import submitted

    today = dt.date.today()
    outstanding = submitted.outstanding(today)
    if not outstanding:
        print("  mantra: nothing outstanding for IndexNow")
        return
    if not apply:
        print(f"  mantra: would submit {len(outstanding)} outstanding URL(s) to IndexNow "
              f"(+2 hubs): {', '.join(outstanding[:4])}"
              f"{' ...' if len(outstanding) > 4 else ''}")
        return
    from app.web import indexnow

    result = indexnow.submit_mantra_release(today)
    print(f"  mantra: {len(outstanding)} outstanding URL(s) -> IndexNow "
          f"{result.get('detail') or result.get('status')}"
          f"; recorded {result.get('recorded', 0)}")


if __name__ == "__main__":
    raise SystemExit(main())
