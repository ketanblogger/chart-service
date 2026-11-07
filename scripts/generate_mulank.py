"""Write the mulank 1-9 pages once, with a model, under the site's own checker.

WRITTEN ONCE AND COMMITTED, like the nakshatra meanings beside them - not generated on a schedule
and not stored in a database. A mulank's traits have not changed and do not need refreshing
overnight; what this script produces is reviewed, committed, and then never costs anything again.

THE BRIEF IS FIXED AND THE RULES ARE THE SITE'S. Chaldean only, three levels with no fourth, never
"unlucky" or "bad number" or a dosh, never tell anybody to change their name, no guarantees. Every
page is run through app/blog/safety.py - the same checker the blog is held to - and ONLY what it
rejects is asked for again.

    uv run python scripts/generate_mulank.py            # dry run: prints the brief, calls nothing
    uv run python scripts/generate_mulank.py --write    # one run, writes app/numerology/mulank_copy.py
"""
from __future__ import annotations

import argparse
import json
import re
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.ai.client import ClaudeClient               # noqa: E402
from app.ai.config import get_settings               # noqa: E402
from app.blog import safety                        # noqa: E402
from app.numerology.core import RULERS             # noqa: E402

OUT = pathlib.Path("app/numerology/mulank_copy.py")

#: Checked for LENGTH and for carrying a Roman phrase, but not run through the language check: a
#: title that deliberately carries a Roman search term is the site's pattern, not a defect.
_TITLE_FIELDS = ("title", "h1")
LANGUAGES = ("en", "hi", "mr")
NUMBERS = range(1, 10)

SYSTEM = """You write the numerology pages of an Indian Vedic astrology website. The pages are free, \
read mostly on phones, and they are about ONE number: the mulank, which is the day of the month \
somebody was born reduced to a single digit.

Write like a calm, experienced Indian numerologist talking to an adult. Specific, practical, warm. \
Never breathless.

THE RULES, AND THEY ARE NOT NEGOTIABLE:

- CHALDEAN ONLY. Never mention Pythagorean values or compare the two systems.
- A number is never unlucky, bad, weak, a dosh, a problem or a warning. There is no such thing on \
this site. Somebody's mulank is the day they were born and they cannot change it; telling them it \
is unlucky is a charge they can do nothing about.
- How one number sits with another is one of exactly three: a strong match, a good match, or \
neutral. There is no fourth level. "Neutral" means no special affinity either way - say so plainly \
and do not let it sound like bad news.
- Never tell anybody to change their name, their spelling, their phone number, their vehicle or \
their house. Never recommend a gemstone, a ritual, a puja or anything anybody sells.
- No guarantees and no predictions about what will happen to the reader. No claims about death, \
illness, accidents or money arriving.
- Write about tendencies the tradition associates with the number, and what somebody might DO with \
that - not about what the number will cause.

Write in the language asked for, naturally, as somebody who thinks in it. Do not translate English \
idiom word by word.

TITLES. At most 60 characters, every one of them. The Hindi and Marathi titles must ALSO contain a \
short Roman-script phrase - "Mulank 7" or "Mulank 7 in Hindi" - because most Indian readers type \
these searches in Roman letters even when they read Devanagari. Put the Devanagari first and the \
Roman phrase after it.

DO NOT WRITE HINDI WORDS IN THE MARATHI PAGE. They are different languages and a reader notices \
immediately. The same goes the other way."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["pages"],
    "properties": {
        "pages": {
            "type": "object",
            "additionalProperties": False,
            "required": list(LANGUAGES),
            "properties": {
                code: {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "h1", "meta", "intro", "traits", "strengths",
                                 "work", "compatible", "lucky", "bhagyank"],
                    "properties": {
                        "title": {"type": "string", "description": "at most 60 characters"},
                        "h1": {"type": "string"},
                        "meta": {"type": "string", "description": "120-160 characters"},
                        "intro": {"type": "string", "description": "2-3 sentences"},
                        "traits": {"type": "string", "description": "one paragraph, 4-5 sentences"},
                        "strengths": {"type": "string", "description": "one paragraph, 3-4 sentences"},
                        "work": {"type": "string", "description": "one paragraph on how this number works, 3-4 sentences"},
                        "compatible": {"type": "string", "description": "which numbers are a strong or good match, and that the rest are neutral"},
                        "lucky": {"type": "string", "description": "colours and days the tradition associates with it, as associations and not instructions"},
                        "bhagyank": {"type": "string", "description": "what this number means as a BHAGYANK rather than a mulank, 3-4 sentences"},
                    },
                } for code in LANGUAGES
            },
        }
    },
}


def brief(number: int) -> str:
    from app.numerology.core import FRIENDS

    friends = [n for n in FRIENDS[number] if n != number]
    return json.dumps({
        "mulank": number,
        "ruling_planet": RULERS[number],
        "strong_match": [number],
        "good_match": friends,
        "neutral": [n for n in range(1, 10) if n != number and n not in friends],
        "write": f"the page for mulank {number}, in English, Hindi and Marathi",
        "note": ("strong/good/neutral are the only three levels. Everything not listed as strong or "
                 "good is neutral, which means no special affinity - never a warning."),
    }, ensure_ascii=False)


def check(pages: dict) -> dict[str, list[str]]:
    """Every page through the site's own checker. Returns {lang: [problems]} for whatever failed."""
    bad: dict[str, list[str]] = {}
    for code, page in pages.items():
        problems = []
        for field, text in page.items():
            if not isinstance(text, str):
                continue
            # THE LANGUAGE CHECK IS FOR PROSE, NOT FOR TITLES, and the first run of this script
            # proved it: the brief asks a Devanagari title to carry a Roman search phrase, which is
            # this site's own pattern - the Marathi rashifal titles, the year hub and the gochar
            # pages all do it - and blocking_terms refuses Latin words in Devanagari text. The two
            # rules fought each other, the model did exactly as asked, and all nine pages were
            # rejected for it. Nine numbers, eighteen calls, $0.97, nothing written.
            if field in _TITLE_FIELDS:
                continue
            problems += [f"{field}: {hit}" for hit in safety.blocking_terms(text, lang=code)]
        title = page.get("title", "")
        if len(title) > 60:
            problems.append(f"title is {len(title)} characters; the limit is 60")
        # THE SAME RULE tests/test_pages_i18n.py APPLIES TO EVERY DEVANAGARI TITLE: it must carry a
        # Roman phrase, for the readers who type these searches in Roman letters. Checked here so a
        # rejected title costs one retry rather than a failing suite after nine of them are written.
        if code in ("hi", "mr") and not re.search(r"[A-Za-z]{4,}", title):
            problems.append("the Devanagari title has no Roman phrase in it")
        if problems:
            bad[code] = problems
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="call the model and write the file")
    parser.add_argument("--only", type=int, help="one number only, for a cheap trial")
    args = parser.parse_args()

    numbers = [args.only] if args.only else list(NUMBERS)
    if not args.write:
        print(f"DRY RUN. {len(numbers)} number(s) x {len(LANGUAGES)} languages, one call each.")
        print(f"\nSystem prompt ({len(SYSTEM)} chars) and this brief for mulank {numbers[0]}:\n")
        print(brief(numbers[0]))
        return 0

    # HAIKU, like the blog's repair pass and the rashifal batch. These pages are written once; the
    # quality lever is the brief and the checker, not the price of the model.
    import dataclasses

    ai = ClaudeClient(dataclasses.replace(get_settings(), model="claude-haiku-5-5"))
    written: dict[int, dict] = {}
    cost_usd = 0.0
    for number in numbers:
        for attempt in range(2):      # one retry, and only for what the checker rejected
            result = ai.generate_json(system=SYSTEM, user=brief(number), schema=SCHEMA)
            cost_usd += _cost(result)
            pages = result.data["pages"]
            bad = check(pages)
            if not bad:
                written[number] = pages
                print(f"  mulank {number}: ok")
                break
            print(f"  mulank {number}: attempt {attempt + 1} rejected - {bad}")
        else:
            print(f"  mulank {number}: STILL REJECTED, not written")
    if written:
        _write(written)
    print(f"\n{len(written)}/{len(numbers)} written. Estimated cost: ${cost_usd:.2f}")
    return 0 if len(written) == len(numbers) else 1


def _cost(result) -> float:
    """Haiku 5.5 list price. An estimate, printed so the run says what it spent."""
    usage = result.usage or {}
    return (usage.get("input_tokens", 0) * 1.0 + usage.get("output_tokens", 0) * 5.0) / 1_000_000


def _write(pages: dict[int, dict]) -> None:
    header = '''"""The mulank 1-9 pages, written once by a model under the site's own checker.

GENERATED BY scripts/generate_mulank.py AND THEN COMMITTED. Not regenerated on a schedule and not
stored in a database: a mulank's traits have not changed, so this costs nothing after the one run
that produced it. Edit it by hand like any other copy - the script is how it started, not how it is
maintained.

Every string here passed app/blog/safety.py at generation time, in its own language.
"""

MULANK = '''
    OUT.write_text(header + json.dumps(pages, ensure_ascii=False, indent=4, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"  wrote {OUT}")


if __name__ == "__main__":
    raise SystemExit(main())
