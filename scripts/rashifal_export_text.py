#!/usr/bin/env python3
"""Dump a stored reading as plain text, for reading away from the site.

Not part of the pipeline - this exists so a page can be reviewed in a text editor before it is
published, which is the only way to catch prose that reads badly but passes every check.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rashifal import store  # noqa: E402
from app.rashifal.i18n import UI  # noqa: E402
from app.rashifal import i18n as rashifal_words  # noqa: E402
from app.rashifal.brief import build_brief  # noqa: E402
from app.rashifal.periods import base_period, is_dated_month  # noqa: E402
from app.rashifal.i18n import period_label  # noqa: E402
from app.rashifal.prompts import sections_for  # noqa: E402


def as_text(rashi: str, period: str, language: str) -> str:
    import datetime as dt

    row = store.get_page(rashi, period)
    if not row:
        raise SystemExit(f"nothing stored for {rashi}/{period}")
    page = (row.get("content") or {}).get(language)
    if not page:
        raise SystemExit(f"{rashi}/{period} has no {language}")

    words = UI[language]
    # The same brief the page renders from, so the dates and event descriptions match it exactly.
    brief = build_brief(rashi, period, dt.datetime(int(str(row["period_start"])[:4]), 1, 1, 9, 0))
    wrap = lambda s: "\n".join(textwrap.fill(line, 92) for line in s.splitlines())
    out = [page["headline"], "=" * 92, "", wrap(page["summary"]), "", wrap(page["overview"]), ""]

    # THROUGH base_period, the same as every other caller. sections_for("2027-01") falls through to
    # the three-section set, so this exported 438 words of a 1,526-word January reading and the
    # reviewer would have read a third of the page and the wrong headings with it. The fifth place
    # this same resolution was needed; the other four were found by tests, this one by looking at
    # the output and not believing the word count.
    for key in sections_for(base_period(period)):
        paragraphs = (page.get("sections") or {}).get(key)
        if not paragraphs:
            continue
        out += [f"--- {words.get(key, key)} ---", ""]
        out += [wrap(p) + "\n" for p in paragraphs]

    if page.get("saturn_note"):
        out += [f"--- {words.get('saturn_note_label', 'saturn')} ---", "", wrap(page["saturn_note"]), ""]
    if page.get("faq"):
        # the rashi's NAME in this language, not its slug: the heading read "dhanu राशि" before.
        from app.web import i18n as _i18n

        label = _i18n.rashi_names(rashi, language)["rashi"]
        # THE SAME `when` THE PAGE USES. The heading names the month on a monthly page and the year
        # on a yearly one; the label now takes both placeholders, and formatting with only `rashi`
        # raises KeyError - which is how this was caught rather than shipped as a broken export.
        when = (words.get("period_label_" + period)
                or (period_label(period, language) if is_dated_month(period)
                    else str(row["period_start"])[:4]))
        out += [f"--- {words.get('faq_heading', 'FAQ').format(rashi=label, when=when)} ---", ""]
        for question, answer in page["faq"]:
            out += [wrap(f"Q. {question}"), wrap(f"   {answer}") + "\n"]
    # THE EXPORT MUST SHOW WHAT THE PAGE SHOWS. The template hides the tip when the reading has its
    # own upay section, because the two said the same thing - that was one of the review fixes. The
    # export printed it unconditionally, so a review copy carried a block the live page does not,
    # under the very heading that was asked to be removed.
    if page.get("tip") and not (page.get("sections") or {}).get("upay"):
        out += [f"--- {words.get('tip', 'tip')} ---", "", wrap(page["tip"]), ""]
    if page.get("months"):
        out += [f"--- {words.get('months_heading', words.get('months', 'months'))} ---", ""]
        out += [wrap(f"{m['month']}: {m['text']}") + "\n" for m in page["months"]]
    if page.get("key_dates"):
        # THE DATE AND THE EVENT, as the page prints them - not the event id. The export is what a
        # reviewer reads, and "e3: ..." sent one back asking why an internal id was in the text when
        # the page itself had never shown one. An export that differs from the page is a trap.
        out += [f"--- {words.get('key_dates', 'key dates')} ---", ""]
        events = {event["id"]: event for event in (brief or {}).get("events", ())}
        for item in page["key_dates"]:
            event = events.get(item["event_id"])
            when = rashifal_words.format_date(event["date"], language) if event else item["event_id"]
            what = rashifal_words.describe_event(event, language) if event else ""
            out += [wrap(f"{when} - {what}"), wrap(f"    {item['note']}"), ""]

    body = "\n".join(out)
    count = len(" ".join(x for x in out if not x.startswith(("---", "=="))).split())
    return f"{body}\n\n[{count} words | {rashi}/{period}/{language} | stored model: {row.get('model')}]\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rashi")
    ap.add_argument("period")
    ap.add_argument("language")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()
    text = as_text(args.rashi, args.period, args.language)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"  wrote {args.out} ({len(text.split())} words)")
    else:
        print(text)


if __name__ == "__main__":
    main()
