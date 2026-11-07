"""The wedding-season block: one computed transit, and silence the rest of the year.

WHY A TRANSIT AND NOT A FESTIVAL LIST. The Sun's sidereal ingress into Dhanu begins Dhanurmas, and its
ingress into Makara ends it; weddings are not solemnised in between. Both are degree crossings, computed
by the same ephemeris as every other date on this site, so they move correctly every year and nobody has
to remember to edit a list before December.

WHAT IT REFUSES TO SAY. The season also pauses through Chaturmas, which runs between two EKADASHI dates
- and in 2026 the Kartika shukla Ekadashi is kshaya: it is never the tithi at sunrise (20 Nov is
Dashami, 21 Nov is Dwadashi). Which day the vrata falls on is a question of observance that different
panchangs answer differently, so this module says nothing about it rather than printing one answer as
fact. A site that computes everything else exactly does not get to guess here.
"""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import wedding_season

PATHS = {"en": "/horoscope-matching", "hi": "/hi/kundali-matching", "mr": "/mr/patrika-matching"}

# Computed from the engine, pinned here so a change in the ephemeris wiring shows up as a failing test
# rather than as a wrong date on a page nobody checked in December.
PAUSE_2026 = dt.date(2026, 12, 16)
RESUME_2027 = dt.date(2027, 1, 14)


def test_the_boundaries_are_the_suns_own_ingress_dates():
    state = wedding_season.state(dt.date(2026, 11, 20))
    assert state["pause_on"] == PAUSE_2026 and state["resume_on"] == RESUME_2027


@pytest.mark.parametrize("today, phase", [
    (dt.date(2026, 10, 22), None),        # 55 days out: too far to be news
    (dt.date(2026, 11, 4), "closing"),    # the notice window opens
    (dt.date(2026, 12, 15), "closing"),   # the day before
    (dt.date(2026, 12, 16), "paused"),    # the ingress itself
    (dt.date(2027, 1, 13), "paused"),     # the day before Makara
    (dt.date(2027, 1, 14), None),         # resumed: nothing to announce
    (dt.date(2027, 6, 1), None),          # midsummer
])
def test_it_speaks_only_when_there_is_something_to_say(today, phase):
    state = wedding_season.state(today)
    assert (state or {}).get("phase") == phase if phase else state is None


def test_the_countdown_counts_the_right_thing():
    closing = wedding_season.state(dt.date(2026, 11, 20))
    assert closing["days"] == (PAUSE_2026 - dt.date(2026, 11, 20)).days
    paused = wedding_season.state(dt.date(2026, 12, 20))
    assert paused["days"] == (RESUME_2027 - dt.date(2026, 12, 20)).days


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
@pytest.mark.parametrize("today", [dt.date(2026, 11, 20), dt.date(2026, 12, 20)])
def test_every_language_renders_both_phases_with_real_dates(lang, today):
    block = wedding_season.block(lang, today)
    assert block and block["heading"].strip() and block["text"].strip() and block["cta"].strip()
    assert "{" not in block["heading"] and "{" not in block["text"], "an unfilled placeholder"
    assert "2026" in block["heading"] + block["text"] or "2027" in block["heading"] + block["text"]


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_the_translations_are_not_the_english_one(lang):
    for today in (dt.date(2026, 11, 20), dt.date(2026, 12, 20)):
        assert wedding_season.block(lang, today)["heading"] != wedding_season.block("en", today)["heading"]


def test_it_claims_nothing_about_auspiciousness():
    """A transit says when muhurats pause. It does not say a wedding is blessed, and this block must
    never read as though it does - that is the line the whole site's positioning rests on."""
    for lang in ("en", "hi", "mr"):
        for today in (dt.date(2026, 11, 20), dt.date(2026, 12, 20)):
            words = (wedding_season.block(lang, today)["text"]).lower()
            for banned in ("lucky", "guaranteed", "शुभ फल", "नशीब"):
                assert banned not in words, f"{lang} claims {banned}"


@pytest.mark.parametrize("lang, path", PATHS.items())
def test_the_live_page_agrees_with_the_module(lang, path):
    """The page carries the block exactly when the module says there is something to say.

    THIS TEST USED TO PIN THE ANSWER INSTEAD OF THE RULE. It read "today is outside the window, so
    the live page must not carry the block at all" - true on the day it was written, and false from
    IST midnight on 4 November 2026, when the 42-day notice window for the 16 December pause opened.
    It would then have stayed red for forty-two days, gone green over the pause for the wrong
    reason, and red again in January. The module's arithmetic was never wrong: 4 November to
    16 December is 42 days, which is what the page said.

    A seasonal block is a function of the date, so its test has to be one too.
    """
    html = TestClient(app).get(path).text
    expected = wedding_season.block(lang) is not None
    assert ('id="wedding-season"' in html) is expected, (
        f"the module says {'something' if expected else 'nothing'} and the page says the opposite")


def test_the_block_appears_and_disappears_on_the_right_days():
    """The dates it turns on and off, checked directly rather than through whatever today happens to
    be - this is the part the old test was reaching for and could only get right once."""
    opens = PAUSE_2026 - dt.timedelta(days=wedding_season.NOTICE_DAYS)
    assert wedding_season.state(opens - dt.timedelta(days=1)) is None, "it speaks too early"
    assert wedding_season.state(opens)["phase"] == "closing", "it is silent when the notice is due"
    assert wedding_season.state(PAUSE_2026 - dt.timedelta(days=1))["phase"] == "closing"
    assert wedding_season.state(PAUSE_2026)["phase"] == "paused", "the pause itself"
    assert wedding_season.state(RESUME_2027 - dt.timedelta(days=1))["phase"] == "paused"
    assert wedding_season.state(RESUME_2027) is None, "it is still talking after the season resumes"


def test_the_day_count_is_the_days_to_the_date_it_prints():
    """The number in the sentence and the date in the heading must agree - a reader can subtract."""
    for offset in (1, 7, 20, wedding_season.NOTICE_DAYS):
        today = PAUSE_2026 - dt.timedelta(days=offset)
        st = wedding_season.state(today)
        assert st["days"] == offset, (today, st)
        assert st["pause_on"] == PAUSE_2026


@pytest.mark.parametrize("lang, path", PATHS.items())
def test_the_page_renders_the_block_inside_the_season(monkeypatch, lang, path):
    monkeypatch.setattr(wedding_season, "block", lambda language, today=None:
                        wedding_season.COPY and _stub(language))
    html = TestClient(app).get(path).text
    assert 'id="wedding-season"' in html


def _stub(lang: str) -> dict:
    """A rendered block, so the template test is about the TEMPLATE and not about today's date."""
    return {"phase": "closing", "heading": f"heading-{lang}", "text": "text", "cta": "cta"}


def test_only_the_matching_page_gets_it(monkeypatch):
    """It is an offer about matching. On the kundli page it would be a non sequitur."""
    monkeypatch.setattr(wedding_season, "block", lambda language, today=None: _stub(language))
    assert 'id="wedding-season"' not in TestClient(app).get("/birth-chart").text
    assert 'id="wedding-season"' in TestClient(app).get("/horoscope-matching").text
