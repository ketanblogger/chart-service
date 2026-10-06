"""Daily social cards: engine facts only, nothing a card must never say, and a deterministic pick.

A card is the one thing this project publishes that nobody can click through from before believing it. It is
seen out of context, by people who did not ask for it, and it carries the brand. So the rules are stricter
than for a page: every word is the engine's, no interpretation, and an absolute refusal on a short list of
topics. These tests are what make that true rather than intended.
"""

import datetime as dt

import pytest

from app.social import cards
from app.web import i18n

NOW = dt.datetime(2026, 10, 4, 6, 30, tzinfo=dt.timezone.utc)   # noon IST, a fixed day
BASE = "https://rashikundli.com"


@pytest.mark.parametrize("lang", cards.LANGS)
def test_every_rashi_gets_a_card_in_every_language(lang):
    for rashi in i18n.RASHI_KEYS:
        card = cards.card_for(rashi, lang, NOW)
        assert card["title"] and card["date"]
        assert card["facts"], f"{lang}/{rashi}: a card with no facts on it"
        assert len(card["lines"]) <= 2, "a card is read in a second and a half"


@pytest.mark.parametrize("lang", cards.LANGS)
def test_no_card_ever_says_any_of_the_things_a_card_must_not_say(lang):
    """Death, illness, accidents. The site does not say these anywhere and a card is the last place to
    start - it is seen by people who did not ask for it and cannot see the calculation behind it.

    Checked on the FULL caption, which is what actually gets posted, not on the fields separately."""
    for rashi in i18n.RASHI_KEYS:
        card = cards.card_for(rashi, lang, NOW)
        text = cards.caption(card, cards.utm_link(rashi, lang, "2026-10-04", BASE))
        assert not cards.unsafe(text), f"{lang}/{rashi}: {cards.unsafe(text)}"
    highlight = cards.highlight_card(lang, NOW)
    if highlight:
        text = cards.caption(highlight, cards.utm_link(highlight["rashi"], lang, "2026-10-04", BASE))
        assert not cards.unsafe(text), cards.unsafe(text)


def test_the_filter_would_actually_catch_something():
    """A refusal list that matches nothing is a comment. This is the test that makes it a control."""
    assert cards.unsafe("a death in the family") == ["death"]
    assert cards.unsafe("आज दुर्घटना का योग") == ["दुर्घटना"]
    assert cards.unsafe("अपघात होऊ शकतो") == ["अपघात"]
    # ...and that the rashi is not mistaken for the disease: every English Cancer card carries the word.
    assert cards.unsafe("Moon enters Cancer (Karka) - house 1 from your rashi") == []


@pytest.mark.parametrize("lang", cards.LANGS)
def test_a_card_carries_no_sentence_the_engine_did_not_produce(lang):
    """Every line on a card has to be traceable to a transit event, and every fact to a brief field. The way
    an interpretive sentence would arrive here is somebody adding a nice phrase to the template, so the
    template is checked for the shapes that would carry one."""
    source = (cards.__file__.replace("cards.py", "templates/card.html"))
    import pathlib

    html = pathlib.Path(source).read_text()
    for forbidden in ("lucky", "remedy", "will bring", "शुभ", "उपाय", "भाग्य"):
        assert forbidden not in html, f"the card template carries an interpretive word: {forbidden}"


def test_the_highlight_is_the_rashi_the_biggest_transit_lands_on():
    """Today's events are usually ONE transit seen from twelve rashis, so the choice is which rashi it lands
    on hardest. The 1st house wins, which is the rashi the graha is actually in."""
    chosen = cards.pick_highlight(NOW)
    assert chosen, "no highlight at all on a day with transits"
    rashi, event = chosen
    assert event["house"] == 1, f"the highlight is {rashi} with the event in house {event['house']}"


def test_the_highlight_is_the_same_answer_twice():
    """It runs once a day and gets posted. Two runs must not disagree."""
    assert cards.pick_highlight(NOW)[0] == cards.pick_highlight(NOW)[0]


@pytest.mark.parametrize("lang", cards.LANGS)
def test_every_caption_carries_the_link_the_hashtags_and_the_calculation(lang):
    card = cards.card_for("tula", lang, NOW)
    link = cards.utm_link("tula", lang, "2026-10-04", BASE)
    text = cards.caption(card, link)
    assert link in text
    assert cards.HASHTAGS[lang].split()[0] in text
    assert card["calc"] in text, "a card that does not name the engine behind it"


@pytest.mark.parametrize("lang", cards.LANGS)
def test_the_link_points_at_that_rashis_own_page_in_that_language(lang):
    for rashi in i18n.RASHI_KEYS:
        link = cards.utm_link(rashi, lang, "2026-10-04", BASE)
        assert link.startswith(BASE + i18n.url_for("rashifal-reading", lang, rashi=rashi, period="today"))
        assert "utm_source=instagram" in link and f"utm_content=2026-10-04-{rashi}" in link


def test_building_a_card_makes_no_ai_call(monkeypatch):
    """The whole claim of these cards. Enforced by breaking the client rather than by reading the code."""
    import app.ai.client as client

    def refuse(*args, **kwargs):
        raise AssertionError("a social card tried to call the AI")

    for name in ("ClaudeClient", "complete", "chat"):
        if hasattr(client, name):
            monkeypatch.setattr(client, name, refuse, raising=False)
    for lang in cards.LANGS:
        cards.card_for("mesha", lang, NOW)
        cards.highlight_card(lang, NOW)


def test_a_caption_is_never_written_with_a_link_nobody_can_open():
    """BASE_URL falls back to localhost when it is unset, which is right for a dev server and useless in a
    caption: the cards would generate, look perfect, and carry http://localhost:8000 into Instagram. The
    whole run stops instead, with the other refusals."""
    import datetime as dt
    from pathlib import Path

    from scripts.social_cards import build

    when = dt.datetime(2026, 10, 4, 6, 30, tzinfo=dt.timezone.utc)
    for bad in ("http://localhost:8000", "http://127.0.0.1:8000", "", "http://rashikundli.com"):
        written, refused = build(when, ("en",), Path("var/social/_never"), bad)
        assert written == 0 and refused, f"{bad!r} was accepted as a base URL"
        assert any("BASE_URL" in line for line in refused)
    assert not Path("var/social/_never").exists(), "a refused run still created its output directory"
