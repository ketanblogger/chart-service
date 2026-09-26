"""The trust positioning rules, enforced on the rendered pages.

The one rule the brief calls out by name: **a page may never mention AI without naming Swiss Ephemeris nearby - in the
same section, not just once somewhere on the site.** "AI astrology" on its own invites "so it's just guessing"; the
answer is not to hide the AI but to keep saying which half does what - Swiss Ephemeris calculates (deterministic
astronomy), AI only explains. A copy edit six months from now will not remember that, so the test does.

"Section" here is the innermost `<section>`, `<aside>`, `<details>`, `<article>`, `<header>` or `<footer>` a piece of
text sits in, plus each `li.tool-card`. `<nav>` is deliberately NOT a boundary: a link list is part of the header or
footer it lives in, and the header carries the engine's name in its own trust line.
"""

import re
from html.parser import HTMLParser

import pytest

from app.web import i18n
from tests.test_web import client

# How each tree writes the two halves. AI is written "AI" in all three (that is how it is searched and read in
# India); the Devanagari spellings are listed so that switching to them later cannot silently disable the rule.
AI = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])|एआई|एआय|कृत्रिम बुद्धिमत्ता")
ENGINE = re.compile(r"Swiss Ephemeris|स्विस एफेमेरिस")

# "RashiKundli AI" is the registered business name (app/web/site.py) that the policy pages have to print in full.
# It is not a claim about how the product works, so it is not an "AI mention" - every other use of the word is.
BUSINESS_NAME = "RashiKundli AI"

# Nothing is held out of this sweep any more: the four policies.py sections that described the AI provider without
# naming the engine have landed, so the rule is enforced on every page the site serves. Keep this empty - a page that
# cannot pass the rule is a page to fix, not a page to park here.
PLATFORM_OWNED: set[str] = set()

SECTION_TAGS = {"header", "footer", "section", "aside", "details", "article"}
VOID_TAGS = {"br", "img", "input", "meta", "link", "hr", "source", "area", "base", "col", "embed", "param",
             "track", "wbr"}


class Sections(HTMLParser):
    """Visible text of a page, bucketed by the innermost section-like element it sits in."""

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str]] = []
        self.text: dict[str, list[str]] = {}
        self.order: list[str] = []
        self._skip = 0
        self.feed(html)

    def _current(self) -> str:
        return self.stack[-1][1] if self.stack else "page"

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag in VOID_TAGS:
            return
        attributes = dict(attrs)
        classes = attributes.get("class") or ""
        if tag in SECTION_TAGS or (tag == "li" and "tool-card" in classes):
            key = f"<{tag} id={attributes.get('id') or '-'} class={classes or '-'}> #{len(self.order)}"
            self.order.append(key)
            self.text.setdefault(key, [])
            self.stack.append((tag, key))
        else:
            self.stack.append((tag, self._current()))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        if tag in VOID_TAGS:
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        if not self._skip:
            self.text.setdefault(self._current(), []).append(data)

    def sections(self) -> list[tuple[str, str]]:
        return [(key, " ".join(self.text.get(key, [])).replace(BUSINESS_NAME, "RashiKundli"))
                for key in self.order]


PATHS = [(path, key, lang) for path, key, lang, _ in i18n.all_paths() if key not in PLATFORM_OWNED]


@pytest.fixture(scope="module")
def pages_html() -> dict[str, str]:
    html = {}
    for path, _, _ in PATHS:
        response = client.get(path)
        assert response.status_code == 200, path
        html[path] = response.text.split("</head>", 1)[-1]  # the <head> is metadata, not what a reader reads
    return html


def test_the_test_covers_every_page_the_web_layer_owns():
    """PLATFORM_OWNED may only ever hold policy pages - it must not become a place to park a failing tool page."""
    assert PLATFORM_OWNED <= set(i18n.POLICY_KEYS)
    assert len(PATHS) == 247 - sum(len(i18n.page_langs(key)) for key in PLATFORM_OWNED) == 247


def test_no_section_mentions_ai_without_naming_swiss_ephemeris(pages_html):
    """The rule itself, on all 247 pages the site serves."""
    offenders = []
    for path, _, _ in PATHS:
        for key, text in Sections(pages_html[path]).sections():
            if AI.search(text) and not ENGINE.search(text):
                excerpt = re.sub(r"\s+", " ", text).strip()[:180]
                offenders.append(f"{path} {key}" + "\n      " + excerpt)
    assert not offenders, (
        "these sections name AI with no Swiss Ephemeris beside it:\n    "
        + "\n    ".join(offenders))


def test_the_rule_is_actually_being_exercised(pages_html):
    """A rule nothing triggers is a rule that has quietly stopped applying. Several sections must really name
    AI - if none does any more, the copy has drifted the other way and this file is asleep."""
    with_ai = [(path, key) for path, _, _ in PATHS
               for key, text in Sections(pages_html[path]).sections() if AI.search(text)]
    assert len(with_ai) > 100, f"only {len(with_ai)} sections mention AI at all - is the parser still working?"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_page_carries_the_engine_in_its_chrome_and_its_footer(lang, pages_html):
    """A trust requirement: a short line in the header and in every footer, in the tree's own language."""
    for path, _, page_lang in PATHS:
        if page_lang != lang:
            continue
        html = pages_html[path]
        header = html.split("</header>", 1)[0]
        footer = html.rsplit("<footer", 1)[-1]
        assert ENGINE.search(header), f"{path}: the header names no calculation engine"
        assert ENGINE.search(footer), f"{path}: the footer names no calculation engine"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_tool_page_has_a_trust_line_beside_its_form(lang):
    """A trust requirement: the "is this just a guess?" question is asked at the form, so it is answered there."""
    for key in (*i18n.TOOL_KEYS, "consultation"):
        html = client.get(i18n.url_for(key, lang)).text
        card = html.split('class="card tool__form"', 1)[1].split("</section>", 1)[0]
        line = card.split('class="trust-line"', 1)
        assert len(line) == 2, f"{key}/{lang}: no trust line beside the form"
        assert ENGINE.search(line[1].split("</p>", 1)[0]), f"{key}/{lang}: the trust line does not name the engine"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_consultation_says_what_the_chat_reads_before_the_first_message(lang):
    html = client.get(i18n.url_for("consultation", lang)).text
    trust = html.split('class="chat__trust"', 1)[1].split("</p>", 1)[0]
    assert ENGINE.search(trust) and AI.search(trust), f"consultation/{lang}: {trust!r}"
    # ... and it comes before the log, which is where the first message appears.
    assert html.index('class="chat__trust"') < html.index('id="chat-log"')


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_home_hero_leads_with_accuracy(lang):
    """A trust requirement: the hero leads with accuracy, not with the AI - so the engine is named in the hero,
    and it is named before the first time the word AI appears there."""
    html = client.get(i18n.url_for("home", lang)).text
    hero = html.split('class="hero"', 1)[1].split("</section>", 1)[0]
    assert ENGINE.search(hero), f"home/{lang}: the hero never names the engine"
    mentions_ai = AI.search(hero)
    if mentions_ai:
        assert ENGINE.search(hero).start() < mentions_ai.start(), f"home/{lang}: the hero leads with AI"


def test_no_page_makes_a_standalone_ai_claim(pages_html):
    """A trust requirement: never "100% AI" or "fully AI-powered" as a claim, in any tree."""
    banned = re.compile(r"100% AI|fully AI-powered|पूरी तरह AI|संपूर्णपणे AI|पूर्णपणे AI", re.I)
    for path, _, _ in PATHS:
        assert not banned.search(pages_html[path]), path
