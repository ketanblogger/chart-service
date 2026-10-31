#!/usr/bin/env python3
"""Write the explainer for each mantra page. DRY RUN unless --apply.

    .venv/bin/python scripts/generate_mantra_explainers.py --only hanuman-chalisa
    .venv/bin/python scripts/generate_mantra_explainers.py --apply

WHAT THE MODEL WRITES AND WHAT IT NEVER TOUCHES. The verses are not sent to be rewritten, reworded
or translated; they are sent as context so the explanation is about the actual text. The model
writes the introduction, what each group of verses is saying, how and when the text is traditionally
recited, and the questions people ask. That is the only part of these pages a model has written.

THE SOURCE PAGES ARE NOT SENT AT ALL. The model cannot paraphrase what it has not seen, and
app/mantra/originality.py checks the result against both source pages afterwards - any eight-word
run they share is a finding. Writing from the verses themselves is both the honest way to do it and
the one that passes.

EIGHT HUNDRED WORDS IS A FLOOR, not a target. A page that says less than that about a text people
recite daily has not earned the reader's visit, and a page padded to reach it has not either - the
brief asks for specific things in a specific order, and the floor is a check that they were all
actually written.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.ai.client import ClaudeClient
from app.ai.config import get_settings
from app.mantra import originality, texts as T

OUT = pathlib.Path(__file__).resolve().parents[1] / "app/mantra/explainers"
MIN_WORDS = 800

SYSTEM = """You write for RashiKundli, a Vedic astrology site in India. You are writing the
explanatory part of a page whose main content is a traditional devotional text.

WHAT YOU ARE WRITING: an introduction, a section explaining what each group of verses says, a
section on how and when the text is traditionally recited, and a FAQ. Nothing else.

WHAT YOU MUST NOT DO:
- Do not reproduce, translate or paraphrase the verses line by line. Explain what a group of verses
  is about, in your own words, as a knowledgeable friend would.
- Do not promise outcomes. No "chanting this will remove your problems", no "you will get a job".
  Say what the TRADITION holds, attributed: "it is traditionally recited when...", "the text itself
  says...".
- No fear. Never suggest something bad happens if the reader does not recite it.
- Do not invent history, authorship or dates you were not given.
- Do not use the words "guarantee", "cure", "miracle", or claim medical or financial results.

TONE: plain, warm, specific. Written for someone who already knows the text exists and wants to
understand it. Indian English. No marketing language."""


#: A CEILING, NOT A BAND. There was a 1% floor too, and chasing it was the expensive mistake of
#: this batch: natural writing lands at 0.1% to 0.8%, so the floor forced a rewrite of every page,
#: and the rewrites overshot to 3.6% as often as they landed. Worse, the floor was pushing the prose
#: toward the repetition rate the ceiling exists to prevent - a one-word Hindi name at 1% means
#: saying it 15 to 30 times in 1,500 words. The proprietor dropped the floor.
#:
#: The practical effect is that the first attempt now almost always passes, so a page costs ONE
#: call. The feedback machinery below is kept for the rare page that comes in over the ceiling,
#: because that is where it earns its keep: handing the model its own measured count converges in
#: one or two tries where asking again blindly does not converge at all.
DENSITY_HIGH = 0.020
WORD_TARGET = 1400


def mention_ceiling(name: str) -> int:
    """The most times the name may appear before the page is over the ceiling.

    DENSITY IS MEASURED BY WEIGHT, not by count: a mention of a three-word name puts three words of
    keyword into the text, so a long name may appear fewer times than a short one for the same
    percentage. A model cannot count its own output, so a correction has to state a count.
    """
    per = max(1, len(name.split()))
    return max(2, int(DENSITY_HIGH * WORD_TARGET / per))


def brief(text, language: str, verses: list[str]) -> str:
    sample = "\n".join(verses[:40])
    name = text.names[language]
    return f"""Write the explainer for this page.

TEXT: {text.names['hi']} ({text.names['en']})
KIND: {text.kind}
DEITY: {text.deity}
AUTHOR AND PERIOD, as recorded: {text.author}
LANGUAGE TO WRITE IN: {"Hindi (Devanagari)" if language == "hi" else "English"}

The verses (for your understanding - do not reproduce them):
{sample}

Return JSON with these keys:
  intro          - 120-180 words. What this text is, who wrote it, what it is for.
  groups         - a list of 6 to 10 objects, each {{"heading": ..., "body": ...}}, walking through
                   the text in order. 80-140 words each. Say what that part of the text is SAYING.
  recitation     - 150-220 words. How and when it is traditionally recited: the day, the occasion,
                   the count, what people do. Attribute customs to the tradition.
  tradition      - 120-180 words. What the tradition holds this text is for, carefully attributed.
  faq            - a list of 5 objects, each {{"q": ..., "a": ...}}. The questions people actually
                   ask. 40-80 words per answer.

The four prose sections plus the groups must come to at least {MIN_WORDS} words in total, and
should aim for about {WORD_TARGET}.

Use the name "{name}" where a sentence naturally calls for it - the opening, a few of the group
headings, and some of the questions. Do not repeat it mechanically: where it would make a sentence
clumsy, use a pronoun or "the text" instead. Writing it plainly is enough; there is no count to
hit."""


# `additionalProperties: false` on EVERY object: the API rejects a schema without it rather than
# ignoring it, which is the better failure - a loose schema would let a stray key through silently.
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intro", "groups", "recitation", "tradition", "faq"],
    "properties": {
        "intro": {"type": "string"},
        "groups": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["heading", "body"],
            "properties": {"heading": {"type": "string"}, "body": {"type": "string"}}}},
        "recitation": {"type": "string"},
        "tradition": {"type": "string"},
        "faq": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["q", "a"],
            "properties": {"q": {"type": "string"}, "a": {"type": "string"}}}},
    },
}


def _cost(usage: dict) -> float:
    """Dollars for one call, at Opus rates: $3 per million in, $15 per million out."""
    return (usage.get("input_tokens", 0) * 3 + usage.get("output_tokens", 0) * 15) / 1e6


def mentions(ours: str, name: str) -> int:
    """How many times the exact name appears, counted the way the test counts it."""
    words = originality.words(ours)
    phrase = originality.words(name)
    return sum(1 for i in range(len(words) - len(phrase) + 1)
               if words[i:i + len(phrase)] == phrase)


def keyword_density(ours: str, name: str) -> float:
    """What percentage of our words are the keyword - the same sum tests/test_mantra_pages.py does.

    MEASURED HERE SO A SHORT PAGE IS REJECTED BEFORE IT IS WRITTEN TO DISK. The test is the
    authority, and a generator that cannot check its own output against it just moves the failure
    to the suite.
    """
    words = originality.words(ours)
    return 100.0 * mentions(ours, name) * len(originality.words(name)) / max(len(words), 1)


def written_text(data: dict) -> str:
    """Everything the model wrote, as one string - what the floor and the check measure."""
    parts = [data.get("intro", ""), data.get("recitation", ""), data.get("tradition", "")]
    parts += [f"{g.get('heading','')} {g.get('body','')}" for g in data.get("groups", [])]
    parts += [f"{f.get('q','')} {f.get('a','')}" for f in data.get("faq", [])]
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the files")
    parser.add_argument("--only", action="append", default=[], help="one slug, repeatable")
    parser.add_argument("--force", action="store_true", help="rewrite files that already exist")
    parser.add_argument("--language", default="hi,en")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    client = ClaudeClient(get_settings())
    slugs = args.only or [t.slug for t in T.PHASE_1 if T.is_verified(t)]
    languages = args.language.split(",")
    spent = 0.0
    for slug in slugs:
        text = T.BY_SLUG[slug]
        verses = [v["text"] for v in T.verses(slug)]
        for language in languages:
            path = OUT / f"{slug}.{language}.json"
            if path.exists() and not args.only and not args.force:
                continue
            # THE SCHEMA CANNOT CATCH AN EMPTY STRING or a group count outside the brief, and the
            # model produced both - a heading with nothing under it reads, on the page, as a
            # section that failed to load. Asking again is cheap; shipping a blank section is not.
            # THE RETRY FEEDS BACK WHAT WENT WRONG, which is the whole difference between
            # converging and re-rolling. A blind second attempt is a fresh sample from the same
            # distribution: the first pass of this came in at 0.07%-0.79% against a 1-2% band, and
            # a blind retry then overshot to 3.6% just as often as it landed. A model cannot count
            # its own output, but it can act on a count it is given - "you used the name 4 times,
            # use it 8 to 13" is a followable instruction where "aim for 1.5% density" is not.
            correction = ""
            name = text.names[language]
            # EVERY ATTEMPT IS PAID FOR, including the rejected ones. Counting only the attempt
            # that was kept understated the spend by whatever the retries cost, which on a text
            # that took four tries is most of it.
            page_cost = 0.0
            for attempt in range(4):
                result = client.generate_json(
                    system=SYSTEM, user=brief(text, language, verses) + correction,
                    schema=SCHEMA)
                page_cost += _cost(result.usage or {})
                data = result.data
                blank = [g["heading"] for g in data["groups"] if not g["body"].strip()]
                blank += [f["q"] for f in data["faq"] if not f["a"].strip()]
                density = keyword_density(written_text(data), name)
                used = mentions(written_text(data), name)
                ceiling = mention_ceiling(name)
                ok_density = density <= DENSITY_HIGH * 100
                if not blank and 6 <= len(data["groups"]) <= 12 and ok_density:
                    break
                notes = []
                if blank:
                    notes.append(f"{len(blank)} section(s) came back with a heading and no text "
                                 f"under them; every section must have a body")
                if not 6 <= len(data["groups"]) <= 12:
                    notes.append(f"you wrote {len(data['groups'])} verse groups; write 6 to 12")
                if not ok_density:
                    notes.append(
                        f'you used the exact phrase "{name}" {used} time(s) in about '
                        f"{originality.word_count(written_text(data))} words, which reads as "
                        f"keyword stuffing. Use it at most {ceiling} times - replace the rest with "
                        f'a pronoun or "the text". Do not shorten the writing to compensate')
                correction = ("\n\nYOUR PREVIOUS ATTEMPT HAD TO BE REJECTED. Rewrite the whole "
                              "explainer, fixing this:\n- " + "\n- ".join(notes))
                print(f"    retry {attempt + 1}: {len(data['groups'])} groups, "
                      f"{len(blank)} blank, density {density:.2f}% ({used} mentions, "
                      f"ceiling {ceiling})")
            body = written_text(result.data)
            count = originality.word_count(body)
            cost = page_cost
            spent += cost
            final_density = keyword_density(body, text.names[language])
            flag = "" if count >= MIN_WORDS else f"  SHORT ({count} < {MIN_WORDS})"
            if final_density > DENSITY_HIGH * 100:
                flag += f"  OVER CEILING {final_density:.2f}%"
            print(f"  {slug:28} {language}  {count:5} words  {final_density:.2f}%  "
                  f"${cost:.4f}{flag}")
            if args.apply:
                path.write_text(json.dumps(result.data, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    print(f"  spent: ${spent:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
