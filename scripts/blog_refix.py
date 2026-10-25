#!/usr/bin/env python3
"""Run the auto-fix over every existing draft. DRY RUN unless --apply is given.

    .venv/bin/python scripts/blog_refix.py                 # report only, writes nothing
    .venv/bin/python scripts/blog_refix.py --apply         # save the repaired bodies
    .venv/bin/python scripts/blog_refix.py --no-ai         # deterministic rules only, no model calls
    .venv/bin/python scripts/blog_refix.py --slug a-post   # one draft

WHY A ONE-OFF. Auto-fix runs when a post ARRIVES. Drafts already in the database arrived before it
existed, so they carry problems - an outside astrologer, a path that was never a page, "your kundli
shows" - that are now repaired automatically for everybody else. This is the catch-up.

IT NEVER PUBLISHES ANYTHING. Not with --apply, not when a draft comes out perfectly clean. Publishing
follows the autopublish rules exactly as it does for a new post: the flag, no blocking checks, no
fact-check warnings, and the two-a-day cap. All this does is repair and report; what the report calls
"now publishable" means "would pass the gate", not "has gone live".

THE DRY RUN TELLS THE TRUTH, which means it runs the model too, on exactly the drafts the real run
would - the model is only asked when the rules leave something blocking. The call count is printed so
the bill is visible before --apply repeats it. --no-ai makes it free and says so in the output.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _NoModel:
    """Stands in for the client when --no-ai is given: asked for nothing, returns nothing."""

    def generate_json(self, **kwargs):
        raise RuntimeError("the model is switched off for this run (--no-ai)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the repairs (default: report only)")
    parser.add_argument("--no-ai", action="store_true", help="deterministic rules only; no model calls")
    parser.add_argument("--slug", help="one draft, by slug")
    args = parser.parse_args()

    from app.blog import config, publishing, store

    drafts = [post for post in store.drafts() if not args.slug or post["slug"] == args.slug]
    if not drafts:
        print("  no drafts to look at")
        return 0

    mode = "APPLYING" if args.apply else "DRY RUN - nothing is written"
    print(f"{len(drafts)} draft(s). {mode}."
          f"{' Rules only, no model calls.' if args.no_ai else ''}\n")

    client = _NoModel() if args.no_ai else None
    counts = {"repaired": 0, "publishable": 0, "blocked": 0, "unchanged": 0}
    model_calls = 0

    for post in drafts:
        before = post.get("body_md") or ""
        fixed, report, fixes = publishing.repair_and_check(post, client=client)
        changed = fixed["body_md"] != before
        model_calls += sum(1 for fix in fixes if fix.get("by") == "haiku")

        print(f"  {post['slug']}")
        if fixes:
            counts["repaired"] += 1
            for fix in fixes:
                print(f"      fixed ({fix['by']}): {fix['what']}")
                print(f"        - {_short(fix['before'])}")
                print(f"        + {_short(fix['after'])}")
        elif not changed:
            counts["unchanged"] += 1
            print("      nothing to repair")

        warnings = post.get("fact_check_warnings") or []
        if report["blocking"]:
            counts["blocked"] += 1
            print(f"      STILL BLOCKED, {len(report['blocking'])} problem(s):")
            for problem in report["blocking"][:5]:
                print(f"        - {_short(problem, 150)}")
        elif warnings:
            counts["blocked"] += 1
            print(f"      waits for a person: {len(warnings)} fact-check warning(s)")
            for warning in warnings[:3]:
                print(f"        - {_short(warning, 150)}")
        else:
            counts["publishable"] += 1
            print("      NOW PUBLISHABLE - passes every check and carries no fact-check warning")

        if args.apply and (fixes or changed):
            store.save({**fixed, "fixes": (post.get("fixes") or []) + fixes}, report)
        print()

    print(f"  {counts['repaired']} repaired, {counts['publishable']} now publishable, "
          f"{counts['blocked']} still waiting, {counts['unchanged']} untouched")
    if model_calls:
        print(f"  {model_calls} replacement(s) came from the model"
              f"{' - the same calls would be made again by --apply' if not args.apply else ''}")
    if not args.apply:
        print("\n  Nothing was written. Re-run with --apply to save the repairs.")
    print("\n  NOTHING WAS PUBLISHED and nothing will be by this command. A post goes live only through"
          f"\n  the usual gate: BLOG_AUTOPUBLISH is {'on' if config.autopublish() else 'off'}, no blocking"
          f"\n  checks, no fact-check warnings, and at most {publishing.AUTOPUBLISH_PER_DAY} a day.")
    return 0


def _short(text: str, limit: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


if __name__ == "__main__":
    raise SystemExit(main())
