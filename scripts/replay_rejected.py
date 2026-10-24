#!/usr/bin/env python3
"""Replay the words that got chat answers rejected, through the repair step that now fixes them.

WHY THIS IS A SCRIPT AND NOT A TEST. The drafts themselves are not stored anywhere - a rejected draft is
chat content, and this service does not keep it. What IS kept is the checker's REASON, which names the
offending word ("the word 'chintित' mixes Latin and Devanagari letters"), and those reasons live in the
errors table on the machine that served them. So the replay has to run where the data is.

    cd /srv/astrology && .venv/bin/python scripts/replay_rejected.py            # last 30 days
    cd /srv/astrology && .venv/bin/python scripts/replay_rejected.py --days 7

It reads nothing but the stored reasons, prints what each word becomes, and says how many of them the
repair step would now have fixed without asking the model again. It changes nothing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.chat_style import repair, script_problems, to_roman  # noqa: E402

#: The checker names the word it refused, in quotes. That is the whole of what we can recover.
_WORD = re.compile(r"the word '([^']+)' mixes Latin and Devanagari")
_STRAY = re.compile(r"letters from another script entirely \(([^)]+)\)")


def rejected_reasons(days: int) -> list[tuple[float, str]]:
    import time

    from app import db

    since = time.time() - days * 86400
    from app.admin import errors as _errors  # registers the table before it is read

    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT last_at, message, times FROM admin_error_events "
            "WHERE last_at > ? AND message LIKE '%rejected%' ORDER BY last_at",
            (since,)).fetchall()
    # `times` is how often that identical message repeated - each one was a reader who got a non-answer.
    out: list[tuple[float, str]] = []
    for row in rows:
        out.extend([(row["last_at"], row["message"])] * max(1, int(row["times"] or 1)))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    try:
        reasons = rejected_reasons(args.days)
    except Exception as exc:  # noqa: BLE001 - a missing table is a fine answer here
        print(f"could not read the errors table: {exc}")
        return 1

    words: list[str] = []
    for _, message in reasons:
        words.extend(_WORD.findall(message))
        for group in _STRAY.findall(message):
            words.extend(group.split())

    if not words:
        print(f"no rejected chat answers recorded in the last {args.days} days.")
        return 0

    print(f"{len(words)} offending word(s) from {len(reasons)} rejection(s), last {args.days} days\n")
    settled, broken = 0, []
    for word in dict.fromkeys(words):
        repaired, changed = repair(word, "hi-Latn")
        if not script_problems(repaired, "hi-Latn"):
            # Either it was repaired, or it never needed repairing - both mean no regeneration is spent.
            settled += 1
            how = "repaired " if changed else "was clean"
            print(f"  ok   {how} {word!r} -> {repaired!r}")
        else:
            broken.append(word)
            print(f"  MISS still broken {word!r} -> {repaired!r}")

    distinct = len(dict.fromkeys(words))
    print(f"\n{settled}/{distinct} need no regeneration now.")
    if broken:
        print("These still do - send them to whoever is working on chat_style.to_roman:")
        for word in broken:
            print(f"    {word!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
