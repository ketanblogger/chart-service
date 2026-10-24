"""The birth-time window on the kundli form: no new page, no new URL.

WHY IT IS HERE AND NOT ON A PAGE OF ITS OWN. "I do not know the exact time" is one question, and the
form already asks it - there is a disclosure with three-hour presets behind it. A preset gets a result
with a caveat covering everything the hour decides; a window somebody actually remembers is often forty
minutes, and that usually settles the lagna outright. Two answers to one question belong together.

THE WINDOW TAKES A DIFFERENT ENDPOINT, because it is a different kind of answer. /api/chart returns a
chart - a lagna, twelve houses, dasha dates - and folding "it is one of these two lagnas" into that
shape would let the page read a lagna off it that nobody established.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n, pages

client = TestClient(app)
FORM = Path("app/web/templates/_person_fields.html").read_text(encoding="utf-8")
APP_JS = Path("app/static/js/app.js").read_text(encoding="utf-8")
RENDER_JS = Path("app/static/js/render.js").read_text(encoding="utf-8")

SINGLE = ["/birth-chart", "/kundli", "/hi/kundli", "/mr/kundali", "/sidereal-birth-chart"]


@pytest.mark.parametrize("path", SINGLE)
def test_the_window_is_offered_on_the_single_birth_forms(path):
    html = client.get(path).text
    assert "data-window-from" in html and "data-window-to" in html, path


@pytest.mark.parametrize("path", ["/horoscope-matching", "/hi/kundali-matching", "/mr/patrika-matching"])
def test_it_is_not_offered_where_there_are_two_births(path):
    """A window on each of two births multiplies into possibilities nobody can read."""
    assert "data-window-from" not in client.get(path).text, path


def test_it_lives_inside_the_disclosure_that_already_asks_the_question():
    """Not behind a second toggle. The presets and the window are two answers to one question."""
    assert FORM.index("data-preset-toggle") < FORM.index("data-window-from")
    assert FORM.index("data-window-from") < FORM.index("</div>\n  </div>\n</div>\n{% endmacro %}")


def test_no_new_url_and_nothing_new_in_the_sitemap():
    """THE CONSTRAINT THIS WAS BUILT UNDER. The feature is a field on a form that already exists."""
    assert "birth-time" not in str(sorted(i18n.PAGES))
    assert sum(len(ref.langs) for ref in i18n.all_pages()) == 514


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_language_has_the_window_copy(lang):
    words = pages.ui(lang)
    for key in ("time_window_lead", "time_window_from", "time_window_to", "time_window_note"):
        assert words.get(key, "").strip(), f"{lang} is missing {key}"
    if lang != "en":
        assert words["time_window_lead"] != pages.ui("en")["time_window_lead"]


def test_the_window_goes_to_the_endpoint_built_for_it():
    block = APP_JS[APP_JS.index("var windowFrom"):]
    block = block[:block.index("setBusy(true)")]
    assert "/api/chart/without-time" in block
    assert "from_time" in block and "to_time" in block


def test_half_a_window_is_not_a_window():
    """One end alone would be a guess about the other, which is the failure this whole feature avoids."""
    block = APP_JS[APP_JS.index("var usingWindow"):]
    block = block[:block.index("var postTo")]
    assert "windowFrom.value && windowTo.value" in block


def test_a_window_answer_is_never_drawn_as_a_chart():
    """The page's own renderer draws a lagna and twelve houses. A window answer may have neither."""
    assert "ctx.window ? R.timeWindow(response, ctx)" in APP_JS


def test_the_renderer_sets_its_own_language():
    """It is called directly by app.js rather than through the entry point that assigns LANG - without
    this the Hindi and Marathi pages rendered the whole block in English, which only a browser showed."""
    block = RENDER_JS[RENDER_JS.index("function timeWindow(data, ctx)"):]
    block = block[:block.index("function _timeWindow")]
    assert "withLang(" in block


def test_a_split_window_shows_no_single_lagna():
    """Printing one lagna for a window that crosses a boundary - the nearest, the longest, the middle -
    would be a guess wearing the clothes of a calculation."""
    answer = client.post("/api/chart/without-time", json={
        "date": "1990-05-14", "city": "Pune", "from_time": "06:00", "to_time": "09:00"}).json()
    assert answer["window"]["lagna"] is None
    assert len(answer["window"]["possibilities"]) >= 2


def test_the_refusal_says_what_it_would_take():
    """A refusal with no number reads as a limitation of the site rather than of the arithmetic."""
    answer = client.post("/api/chart/without-time", json={
        "date": "1990-05-14", "city": "Pune", "from_time": "07:00", "to_time": "07:40"}).json()
    assert answer["window"]["dasha"]["available"] is False
    assert answer["window"]["dasha"]["needs_minutes"] == 10
    # All three languages name the threshold. Counted rather than sliced per language - the three
    # label tables are indented differently in that file, and a slice that assumed otherwise failed on
    # copy that was sitting there correctly (the same trap as the paywall copy test).
    phrases = re.findall(r"windowNoDasha: ([^\n]*(?:\n[^\n]*\+[^\n]*)*)", RENDER_JS)
    assert len(phrases) == 3, f"windowNoDasha in {len(phrases)} languages, expected 3"
    for phrase in phrases:
        assert "{minutes}" in phrase, "a language does not say how tight the window must be"
