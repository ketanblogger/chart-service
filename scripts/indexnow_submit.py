#!/usr/bin/env python
"""Submit URLs to IndexNow (Bing and Yandex). Dry run by default.

    cd /srv/astrology && .venv/bin/python scripts/indexnow_submit.py --all           # what it would send
    cd /srv/astrology && .venv/bin/python scripts/indexnow_submit.py --all --send    # send it

GOOGLE IS NOT HERE ON PURPOSE. Its Indexing API is restricted to job postings and livestreams; using it
for ordinary pages breaks its terms and does nothing. Bing and Yandex accept IndexNow, and whether that
becomes traffic is answerable rather than assumed - the source tracking names Bing arrivals, so a month
from now this either shows up in Usage or it does not.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="every indexable URL in the sitemap")
    parser.add_argument("--period", help="one rashifal period's pages, e.g. weekly")
    parser.add_argument("--url", action="append", default=[], help="a single path, repeatable")
    parser.add_argument("--send", action="store_true", help="actually submit (default: dry run)")
    args = parser.parse_args()

    from app.web import i18n, indexnow, site

    if not indexnow.KEY:
        print("REFUSING: no INDEXNOW_KEY configured and no built-in key")
        return 1

    if args.all:
        paths = [path for path, *_ in i18n.all_paths()]
        what = "every indexable URL"
    elif args.period:
        paths = [i18n.url_for("rashifal-reading", lang, rashi=rashi, period=args.period)
                 for lang in i18n.LANGS for rashi in i18n.RASHI_KEYS]
        what = f"the {args.period} rashifal pages"
    elif args.url:
        paths = args.url
        what = f"{len(args.url)} path(s) given on the command line"
    else:
        parser.error("give --all, --period or --url")

    base = site.base_url().rstrip("/")
    print(f"{what}: {len(paths)} URL(s) on {base}")
    print(f"key file: {base}{indexnow.key_path()}  (public by design - it proves control of the domain)")
    for path in paths[:6]:
        print(f"  {base}{path}")
    if len(paths) > 6:
        print(f"  ... and {len(paths) - 6} more")

    if not args.send:
        print("\nDRY RUN: nothing was submitted. Re-run with --send.")
        return 0

    result = indexnow.submit(paths, reason=what)
    print(f"\nsubmitted {result['sent']} URL(s); status {result['status']}"
          f"{' - ' + result['detail'] if result['detail'] else ''}")
    if result["status"] == 422:
        print("422 means the engines could not verify the key. Check that "
              f"{base}{indexnow.key_path()} is reachable and returns the key.")
    return 0 if result["sent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
