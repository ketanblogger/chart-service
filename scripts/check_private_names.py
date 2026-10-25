#!/usr/bin/env python3
"""Refuse to publish a tree that names somebody on the private list.

    python scripts/check_private_names.py <tree>        # the candidate in ~/rashikundli-publish

WHY A LIST, AND WHY OUTSIDE THE TREE. A real reader's given name and her rashi sat in two code comments
in app/ai/chat.py and app/ai/chat_routes.py and were published for weeks. Nothing caught it because
nothing was looking: the publication checks searched for the proprietor's birth record, by component, and
for nothing else.

THIS FILE DOES NOT NAME HER EITHER, and the first run of this check is why - it found her name in this
very docstring, where it had been written as an example of what must not be published.

The list cannot live in the repository, because a file enumerating the people who must not be named would
publish their names itself. It lives beside the token, outside every tree this project pushes, and this
script is the only thing that reads it.

    printf '%s\\n' 'Given Name' 'दिलेले नाव' > ~/.rashikundli-private-names && chmod 600 ~/...

A MISSING LIST IS A REFUSAL, not a pass. A safety check that waves everything through when it is
misconfigured is worse than no check, because it is believed. Pass --no-private-list to say out loud that
there is deliberately nothing to check.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path

DEFAULT_LIST = Path(os.environ.get("PRIVATE_NAMES_FILE", Path.home() / ".rashikundli-private-names"))
#: Binary and vendored things a name cannot meaningfully hide in, and that would make this unusably slow.
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "var"}
SKIP_SUFFIXES = {".woff2", ".ttf", ".otf", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".pdf", ".zip",
                 ".gz", ".db", ".pyc", ".se1", ".jsonl"}


def names_from(path: Path) -> list[str]:
    """One name per line; blanks and # comments ignored."""
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        name = raw.strip()
        if name and not name.startswith("#"):
            out.append(name)
    return out


def _normalise(text: str) -> str:
    """Case-folded and NFC-composed, so "Meera" and "meera" match, and so do the two ways Devanagari can
    encode the same word. A check that only catches the exact spelling somebody happened to type is the
    one that already failed here once."""
    return unicodedata.normalize("NFC", text).casefold()


def scan(tree: Path, names: list[str], listing: Path | None = None) -> list[tuple[str, int, str]]:
    """`listing` is skipped if it happens to sit inside the tree: the file that lists the names to block
    contains every one of them by definition, and reporting it would make the check fail on itself. In
    production it lives outside every published tree, but a check that cannot survive being pointed at
    its own list is a check that will be worked around."""
    hits = []
    listing = listing.resolve() if listing else None
    patterns = [(name, re.compile(re.escape(_normalise(name)))) for name in names]
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(tree).parts):
            continue
        if listing and path.resolve() == listing:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            folded = _normalise(line)
            for name, pattern in patterns:
                if pattern.search(folded):
                    hits.append((str(path.relative_to(tree)), number, name))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tree", help="the directory to check")
    parser.add_argument("--list", default=str(DEFAULT_LIST), help="the private names file")
    parser.add_argument("--no-private-list", action="store_true",
                        help="say explicitly that there is no list, instead of failing on its absence")
    args = parser.parse_args()

    tree = Path(args.tree).expanduser()
    if not tree.is_dir():
        print(f"FAIL: {tree} is not a directory")
        return 2

    listing = Path(args.list).expanduser()
    if not listing.exists():
        if args.no_private_list:
            print("no private list, and --no-private-list was passed: nothing checked.")
            return 0
        print(f"REFUSING: no private names list at {listing}.\n"
              "       This check exists because a real reader's name and rashi were published in two code\n"
              "       comments and nobody noticed. An absent list is not an empty one.\n"
              "       Create it (one name per line, outside every published tree):\n"
              f"         printf '%s\\n' 'Given Name' > {listing} && chmod 600 {listing}\n"
              "       Or pass --no-private-list to state that there is deliberately nothing to check.")
        return 1

    names = names_from(listing)
    if not names:
        print(f"the list at {listing} is empty: nothing to check.")
        return 0

    hits = scan(tree, names, listing)
    if not hits:
        print(f"PASS: {len(names)} private name(s) checked against {tree}; none appear.")
        return 0

    print(f"REFUSING TO PUBLISH: {len(hits)} line(s) name somebody on the private list.\n")
    for where, number, name in hits[:40]:
        print(f"  {where}:{number}   names {name!r}")
    if len(hits) > 40:
        print(f"  ... and {len(hits) - 40} more")
    print("\nNothing was published. Replace them with invented names and build the candidate again.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
