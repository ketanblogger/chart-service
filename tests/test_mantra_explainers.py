"""Our written part: long enough to be worth reading, and ours.

Both rules come from the proprietor and both are about the same thing - a page whose verses are
somebody else's text has to earn its place with what WE wrote around them.
"""
import json
import pathlib
import re

import pytest

from app.mantra import originality, review, texts as T

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPLAINERS = ROOT / "app/mantra/explainers"
SOURCES = ROOT / "var/mantra-sources"
MIN_WORDS = 800

#: Where each text's source pages live, so the check compares against what was actually read.
PAGES = {
    "bhaktibharat": "cbody",
    "stotranidhi": "entry-content",
}


def written(data: dict) -> str:
    parts = [data.get("intro", ""), data.get("recitation", ""), data.get("tradition", "")]
    parts += [f"{g.get('heading', '')} {g.get('body', '')}" for g in data.get("groups", [])]
    parts += [f"{f.get('q', '')} {f.get('a', '')}" for f in data.get("faq", [])]
    return "\n".join(parts)


def source_pages(slug: str) -> list[str]:
    """The pages the verses came from, as plain text."""
    out = []
    for site, container in PAGES.items():
        for path in (SOURCES / site).glob(f"{slug}*.html"):
            raw = path.read_bytes().decode("utf-8", "replace")
            out.append(" ".join(review.container_lines(raw, "div", container)))
    for path in list((SOURCES / "wikisource").glob(f"{slug}*")) + \
            list((SOURCES / "second").glob(f"{slug}*")):
        out.append(path.read_text(encoding="utf-8", errors="replace"))
    return out


def explainers() -> list[tuple]:
    return sorted((p.stem.rsplit(".", 1)[0], p.stem.rsplit(".", 1)[1], p)
                  for p in EXPLAINERS.glob("*.json"))


def test_there_is_an_explainer_for_every_verified_text():
    """A verified text with no explainer is a page that would be nothing but somebody else's
    verses, which is the one shape these pages must not take."""
    have = {slug for slug, _, _ in explainers()}
    want = {t.slug for t in T.PHASE_1 if T.is_verified(t)}
    assert want, "nothing is verified - has the registry been emptied?"
    assert want <= have, f"no explainer for: {sorted(want - have)}"
    for slug in want:
        for language in ("hi", "en"):
            assert (EXPLAINERS / f"{slug}.{language}.json").is_file(), (slug, language)


@pytest.mark.parametrize("slug, language, path", explainers())
def test_our_written_part_is_at_least_eight_hundred_words(slug, language, path):
    body = written(json.loads(path.read_text(encoding="utf-8")))
    count = originality.word_count(body)
    assert count >= MIN_WORDS, f"{slug}.{language}: {count} words"


@pytest.mark.parametrize("slug, language, path", explainers())
def test_no_eight_word_run_is_copied_from_a_source(slug, language, path):
    """AT EIGHT WORDS A SHARED RUN IS COPYING, not coincidence. The model is never shown the source
    pages - it writes from the verses - so a hit here means something went wrong upstream rather
    than that the wording was unlucky."""
    pages = source_pages(slug)
    if not pages:
        pytest.skip(f"no cached source pages for {slug} on this machine")
    body = written(json.loads(path.read_text(encoding="utf-8")))
    verses = " ".join(v["text"] for v in T.verses(slug))
    hits = originality.borrowed(body, pages, verses=verses)
    assert not hits, f"{slug}.{language} shares {len(hits)} run(s) with a source: {hits[:3]}"


#: Words that appear in a promise, in its denial, or in a description of what the text itself says.
PROMISE = re.compile(r"\b(guarantee[ds]?|cures?|miracle|miraculous)\b|गारंटी|चमत्कार", re.I)
#: A DENIAL OR AN ATTRIBUTION. The brief forbids promising the reader an outcome and expressly
#: permits two things that use the same words: saying it is NOT a promise, and describing what the
#: tradition or the verse itself holds. Both are checked, and in BOTH DIRECTIONS - Hindi puts its
#: negation after the noun ("किसी चमत्कारी उपाय के रूप में नहीं"), so a backward-only window reads
#: the disclaimer as the promise.
ALLOWED = re.compile(
    r"\b(not|never|no|rather than|instead of|without|does not|is not|"
    r"tradition|traditionally|the text|describes?|described|says|held|regarded)\b"
    r"|नहीं|बजाय|न कि|परंपरा|परम्परा|प्रसंग|कथा|दर्शाता|वर्णन|माना जाता|कहा जाता", re.I)


@pytest.mark.parametrize("slug, language, path", explainers())
def test_the_explainer_promises_nothing(slug, language, path):
    """No guarantees and no fear - BUT THE RULE IS ABOUT PROMISING, NOT ABOUT A WORD.

    Every one of these words first appeared here inside a disclaimer: "as an expression of devotion
    rather than as a technique guaranteed to produce a particular result" is the sentence the brief
    asks for, and a word-ban rejects it while passing a page that promises everything without ever
    using the word. So the assertion is the property: where a promising word appears, a denial
    appears with it. A banned substring also caught "secure" for "cure", which is the same mistake
    one level down.
    """
    body = written(json.loads(path.read_text(encoding="utf-8")))
    for match in PROMISE.finditer(body):
        window = body[max(0, match.start() - 110):match.end() + 110]
        assert ALLOWED.search(window), (
            f"{slug}.{language}: {match.group(0)!r} promised outright: "
            f"...{body[max(0, match.start() - 90):match.end() + 40]}...")


@pytest.mark.parametrize("slug, language, path", explainers())
def test_the_explainer_has_every_section(slug, language, path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"intro", "groups", "recitation", "tradition", "faq"}
    assert 6 <= len(data["groups"]) <= 12, (slug, len(data["groups"]))
    assert len(data["faq"]) >= 4
    for group in data["groups"]:
        assert group["heading"].strip() and group["body"].strip()
