#!/usr/bin/env python3
"""Bring an over-dense explainer back into the band by hand, without another AI call.

    .venv/bin/python scripts/trim_mantra_keyword.py              # show the edits, change nothing
    .venv/bin/python scripts/trim_mantra_keyword.py --apply

WHY THIS EXISTS. Nine pages were over the keyword ceiling when the AI budget ran out, and another
generation call per page would have bought the same result at a price. Removing a few mentions of a
name from OUR OWN prose is a mechanical edit on text we wrote, so it does not need a model: it
needs rules that cannot produce a clumsy sentence, and a human reading of every sentence they
touch.

It only ever REMOVES mentions. The rule is a ceiling, not a band - a page that says the name rarely
is left exactly as written.

THE RULES ARE DELIBERATELY NARROW, and an occurrence that does not match one is left alone:
  * never the first sentence of the intro - the brief puts the keyword in the first hundred words;
  * never a group heading - the brief wants the keyword in at least one H2;
  * never at the start of a sentence, where Hindi would need यह rather than इस and English would
    need a capital;
  * in Hindi, only directly before a postposition, which is where "इस चालीसा के" is correct;
  * in English, only after "the", which is where "the aarti" is correct.
It works from the END of the text backwards, so the earliest mentions - the ones that establish
what the page is about - are the last to go.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.mantra import originality, texts as T

EXPLAINERS = pathlib.Path(__file__).resolve().parents[1] / "app/mantra/explainers"
#: A CEILING ONLY - the 1% floor was dropped, because chasing it pushed the prose toward the
#: repetition the ceiling exists to prevent. This script therefore only ever REMOVES mentions, and
#: a page below the old floor is left exactly as written.
BAND_HIGH = 2.0
TARGET = 1.5          # comfortably under the ceiling, not at its edge

POSTPOSITIONS = ("का", "के", "की", "को", "में", "से", "पर", "ने")

#: What a reader calls this kind of text, per language - taken from the registry's `kind`.
KIND_WORD = {
    "en": {"chalisa": "chalisa", "aarti": "aarti", "stotra": "stotra", "mantra": "mantra",
           "sahasranamam": "sahasranamam"},
    "hi": {"chalisa": "चालीसा", "aarti": "आरती", "stotra": "स्तोत्र", "mantra": "मंत्र",
           "sahasranamam": "सहस्रनाम"},
}


def density(body: str, name: str) -> float:
    words = originality.words(body)
    phrase = originality.words(name)
    hits = sum(1 for i in range(len(words) - len(phrase) + 1)
               if words[i:i + len(phrase)] == phrase)
    return 100.0 * hits * len(phrase) / max(len(words), 1)


def substitute(text: str, name: str, lang: str, kind_word: str, budget: int, *,
               first_sentence_safe: bool) -> tuple[str, int, list[tuple[str, str]]]:
    """Replace up to `budget` mentions, latest first. Returns (text, used, [(before, after)]).

    THE SUBSTITUTE WORD COMES FROM THE REGISTRY, not from the name. Taking the name's last word
    gave "the Ganesh Aarti (Jai Ganesh Deva)" -> "the deva)", which is not a sentence; the registry
    already records what kind of text each one is, and that is the word a reader would use.
    """
    if lang == "hi":
        # A POSTPOSITION PUTS THE NOUN IN THE OBLIQUE, which is the only case where "इस चालीसा" is
        # correct - "इस चालीसा केवल..." as a subject is not Hindi. The first version of this guard
        # used \b after the postposition and matched "केवल" as "के", because a Devanagari matra is
        # not alphanumeric to Python and therefore counts as a word boundary. The check is on the
        # whole following token now, which cannot be fooled that way.
        pattern = re.compile(re.escape(name) + r"\s+(\S+)")
        replacement = f"इस {kind_word}"
    else:
        # TWO ENGLISH SHAPES. Some explainers write "the Hanuman Aarti", where dropping the name
        # leaves "the aarti"; others treat the name as a proper noun - "Bajrang Baan is recited" -
        # and never put an article in front of it, which is why the first version of this found
        # nothing to do on three pages. The bare form becomes "the <kind>", and the guard below
        # refuses any occurrence already preceded by a determiner so it cannot produce "the the".
        pattern = re.compile(r"(?<![\w'])" + re.escape(name))
        replacement = kind_word.lower()

    spans = []
    for match in pattern.finditer(text):
        if lang == "hi":
            following = match.group(1).strip(",।.;:)")
            if following not in POSTPOSITIONS:
                continue
            spans.append((match.start(), match.start() + len(name)))
        else:
            start = match.start()
            before_text = text[max(0, start - 14):start]
            if re.search(r"\b(?:the|a|an|this|that|its|their)\s+$", before_text, re.I):
                spans.append((start, match.end()))          # "the Hanuman Aarti" -> "the aarti"
            elif re.search(r"[(\[\u201c\"]\s*$", before_text):
                continue                                     # inside a quote or a bracket
            else:
                spans.append((start, match.end(), "the " + replacement))
    if first_sentence_safe:
        # Leave everything in the opening sentence alone.
        end = text.find(".") if lang == "en" else max(text.find("।"), text.find("."))
        if end > 0:
                spans = [span for span in spans if span[0] > end]
    # Never at the start of a sentence.
    spans = [span for span in spans
             if not re.search(r"(?:^|[.।]\s*)$", text[max(0, span[0] - 3):span[0]])]

    edits = []
    for span in reversed(spans):
        if len(edits) >= budget:
            break
        start, stop = span[0], span[1]
        into = span[2] if len(span) > 2 else replacement
        before = text[max(0, start - 55):min(len(text), stop + 45)]
        text = text[:start] + into + text[stop:]
        after = text[max(0, start - 55):min(len(text), start + len(into) + 45)]
        edits.append((before, after))
    return text, len(edits), edits


def written(data: dict) -> str:
    parts = [data["intro"], data["recitation"], data["tradition"]]
    parts += [g["heading"] + " " + g["body"] for g in data["groups"]]
    parts += [f["q"] + " " + f["a"] for f in data["faq"]]
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    for path in sorted(EXPLAINERS.glob("*.json")):
        slug, lang = path.stem.rsplit(".", 1)
        text = T.BY_SLUG[slug]
        name = text.names[lang]
        kind_word = KIND_WORD[lang][text.kind]
        data = json.loads(path.read_text(encoding="utf-8"))
        before = density(written(data), name)
        if before <= BAND_HIGH:
            continue
        total_words = len(originality.words(written(data)))
        phrase_len = len(originality.words(name))
        # How many mentions to remove to land at TARGET.
        want = int(TARGET / 100 * total_words / phrase_len)
        have = round(before / 100 * total_words / phrase_len)
        budget = max(0, have - want)
        print(f"  {path.stem}: {before:.2f}% -> aiming {TARGET}%, removing up to {budget}")

        # The FAQ answers first, then the group bodies, then the prose: the questions are where a
        # repeated name reads most like filler.
        all_edits = []
        for item in reversed(data["faq"]):
            item["a"], used, edits = substitute(item["a"], name, lang, kind_word, budget,
                                                first_sentence_safe=False)
            budget -= used
            all_edits += edits
        for group in reversed(data["groups"]):
            group["body"], used, edits = substitute(group["body"], name, lang, kind_word, budget,
                                                    first_sentence_safe=False)
            budget -= used
            all_edits += edits
        for key in ("tradition", "recitation", "intro"):
            data[key], used, edits = substitute(data[key], name, lang, kind_word, budget,
                                                first_sentence_safe=(key == "intro"))
            budget -= used
            all_edits += edits

        after = density(written(data), name)
        for was, now in all_edits:
            print(f"      - {was.strip()}")
            print(f"      + {now.strip()}")
        print(f"    {before:.2f}% -> {after:.2f}%  ({len(all_edits)} edit(s))"
              f"{'' if after <= BAND_HIGH else '   STILL OVER THE CEILING'}")
        if args.apply:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
