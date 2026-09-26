"""The 36 rashi hubs and the 3 homepages carry real body copy, and the 36 are genuinely 36 different pages.

Two things are being defended here, and the second matters more than the first.

**Depth.** Every one of these 39 pages has to clear 1000 words of visible body text. Measured the way the
brief measures it: strip everything up to `</head>`, drop script and style, strip tags, count whitespace-
separated tokens. The baseline before this work was 378-468 words on the rashi hubs and 439-534 on the
homepages, which is thin enough that the pages were competing with nothing.

**Distinctness.** `RASHIFAL_RASHI` is ONE PageCopy per language rendered twelve times with {rashi}, {latin},
{deva} and {lord} swapped in. Putting a thousand words of body into it would produce twelve pages of the same
essay with one noun changed - 36 pages of duplicate content, which is worse than the 418 words they started
with, and is the shape a search engine reads as doorway pages. So the body lives in `pages.RashiBody`, keyed
by rashi, and `test_no_two_rashi_hubs_are_the_same_essay` is what stops the cheap version coming back: it
compares every pair of hubs inside a language on shared 8-word runs. A templated rewrite scores near 1.0.
"""

import re

import pytest

from app.web import i18n, pages
from tests.test_web import client

WORD_FLOOR = 1000
DEEP_PAGES = ("rashifal-rashi", "home")
# The twelve hubs of a language share a closing section about how the pages are calculated, which is right -
# it is the same fact every time. Everything else has to differ. Measured today: 0.12 (en), 0.14 (hi),
# 0.21 (mr). A page built by substitution into one shared essay scores above 0.9.
MAX_PAIR_OVERLAP = 0.35
SHINGLE = 8


def visible_words(html: str) -> int:
    body = html.split("</head>", 1)[-1]
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S)
    return len(re.sub(r"<[^>]+>", " ", body).split())


def _hub(lang: str, rashi: str) -> pages.PageCopy:
    return pages.get("rashifal-rashi", lang, **i18n.rashi_names(rashi, lang))


def _body_text(copy: pages.PageCopy) -> str:
    parts = [copy.intro]
    for section in copy.sections:
        parts.append(section.heading)
        for block in section.blocks:
            parts.extend(block if isinstance(block, list) else [block])
    for question, answer in copy.faqs:
        parts += [question, answer]
    return " ".join(parts)


def _shingles(text: str) -> set:
    words = re.sub(r"\s+", " ", text).split()
    return {tuple(words[i:i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


DEEP_PATHS = [(path, key, lang) for path, key, lang, _ in i18n.all_paths() if key in DEEP_PAGES]


@pytest.fixture(scope="module")
def deep_pages() -> dict[str, str]:
    html = {}
    for path, _, _ in DEEP_PATHS:
        response = client.get(path)
        assert response.status_code == 200, path
        html[path] = response.text
    return html


def test_the_thirty_nine_pages_are_the_ones_being_measured():
    assert len(DEEP_PATHS) == 39, "36 rashi hubs + 3 homepages"
    assert sum(1 for _, key, _ in DEEP_PATHS if key == "rashifal-rashi") == 36


def test_every_rashi_hub_and_homepage_clears_a_thousand_words(deep_pages):
    thin = sorted((visible_words(html), path) for path, html in deep_pages.items()
                  if visible_words(html) < WORD_FLOOR)
    assert not thin, ("these pages are back under %d words of body copy:\n    " % WORD_FLOOR
                      + "\n    ".join(f"{count:5d}  {path}" for count, path in thin))


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_no_two_rashi_hubs_are_the_same_essay(lang):
    """The one that matters: twelve distinct bodies per language, not one body twelve times."""
    shingles = {rashi: _shingles(_body_text(_hub(lang, rashi))) for rashi in i18n.RASHI_KEYS}
    for rashi, runs in shingles.items():
        assert len(runs) > 200, f"{lang}/{rashi} has almost no body text to compare"
    worst = []
    for one in i18n.RASHI_KEYS:
        for other in i18n.RASHI_KEYS:
            if one >= other:
                continue
            overlap = len(shingles[one] & shingles[other]) / min(len(shingles[one]), len(shingles[other]))
            if overlap > MAX_PAIR_OVERLAP:
                worst.append(f"{lang}: {one} and {other} share {overlap:.0%} of their {SHINGLE}-word runs")
    assert not worst, ("rashi hubs have collapsed into one templated essay:\n    " + "\n    ".join(worst))


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_rashi_has_its_own_body_in_every_language(lang):
    bodies = pages.rashi_bodies(lang)
    assert set(bodies) == set(i18n.RASHI_KEYS), f"{lang} is missing a rashi body"
    headings = {rashi: tuple(s.heading for s in body.sections) for rashi, body in bodies.items()}
    for rashi, own in headings.items():
        assert len(own) >= 5, f"{lang}/{rashi} has only {len(own)} sections"
        twins = [other for other, theirs in headings.items() if other != rashi and theirs == own]
        assert not twins, f"{lang}/{rashi} has the same section headings as {twins}"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_faq_blocks_are_the_right_size_and_reach_the_page(lang):
    """The brief asks for 5-8 questions per page, and they have to be visible, not just defined."""
    for page_key, path in [("home", i18n.url_for("home", lang))] + [
            ("rashifal-rashi", i18n.url_for("rashifal-rashi", lang, rashi=rashi)) for rashi in i18n.RASHI_KEYS]:
        copy = _hub(lang, path.rsplit("/", 1)[-1]) if page_key == "rashifal-rashi" else pages.get("home", lang)
        assert 5 <= len(copy.faqs) <= 8, f"{path} has {len(copy.faqs)} FAQs"
        html = client.get(path).text
        assert 'id="faq"' in html, f"{path} defines FAQs but does not render the block"
        for question, _ in copy.faqs:
            assert question in html, (path, question)


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_visible_faq_is_mirrored_in_the_structured_data(lang):
    """Same wiring the tool pages have: a visible FAQ block and a matching FAQPage block."""
    import json

    for path in [i18n.url_for("home", lang), i18n.url_for("rashifal-rashi", lang, rashi="tula")]:
        html = client.get(path).text
        blocks = [json.loads(m) for m in re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, flags=re.S)]
        faq = [b for b in blocks if b.get("@type") == "FAQPage"]
        assert len(faq) == 1, f"{path} has {len(faq)} FAQPage blocks"
        assert faq[0]["inLanguage"] == lang
        questions = [entry["name"] for entry in faq[0]["mainEntity"]]
        copy = pages.get("home", lang) if path.endswith(("/", "/hi/", "/mr/")) else \
            _hub(lang, "tula")
        assert questions == [question for question, _ in copy.faqs], path


def test_no_price_is_written_into_the_new_body_copy():
    """Prices come from the catalogue at request time, in this copy as in every other."""
    offenders = []
    for lang in i18n.LANGS:
        for rashi, body in pages.rashi_bodies(lang).items():
            text = _body_text(pages.PageCopy(nav_label="", title="", meta_description="", h1="",
                                             intro=body.intro, sections=body.sections, faqs=body.faqs))
            if re.search(r"[₹Rs]\s*\d", text):
                offenders.append(f"{lang}/{rashi}")
        home = pages.raw("home", lang)
        if re.search(r"₹\s*\d", _body_text(home)):
            offenders.append(f"{lang}/home")
    assert not offenders, f"a rupee amount is typed into copy: {offenders}"


# ---- the two rashifal hubs: /horoscope, /hi/rashifal, /mr/rashi-bhavishya and their weekly twins ------------------

HUB_PAGES = ("rashifal-hub", "rashifal-weekly")


def test_the_rashifal_hubs_carry_their_own_weight_in_marathi():
    """Measured on 2026-09-25: the two Marathi hubs rendered 842 and 895 words against 1009-1091 for en and hi.

    A rendered floor cannot be asserted here, because 150-330 words of each hub page are the twelve stored card
    summaries and those come from the database, not from this repository. What IS in this repository is the static
    copy, and that is what was thin: 261 words of Marathi against 327 Hindi on the daily hub.

    The invariant, rather than a number per language: the Marathi copy is never thinner than the Hindi copy on
    these two pages. It is not a parity rule for its own sake - the Marathi page has the least text around the
    copy (the twelve-card grid renders 378 words against 510 in Hindi), so its copy has to carry more, not less.
    en is deliberately not compared: English words are not Devanagari words and the English grid is its own size.
    """
    for key in HUB_PAGES:
        words = {lang: len(_body_text(pages.get(key, lang)).split()) for lang in i18n.LANGS}
        assert words["mr"] >= words["hi"], (key, words)
        assert words["mr"] >= 300, (key, words)  # what it takes to clear 1000 rendered with today's summaries
