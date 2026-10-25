"""The saptahik hubs: this week's dates in the title, twelve signs with a teaser, refreshed every Monday.

WHAT WAS ALREADY THERE, checked before anything was written: the titles and headings already carried the
live week, all twelve signs already appeared with a teaser drawn from the generated reading (falling back
to the week's real planetary facts rather than to nothing), and the scheduler already regenerates the
weekly window on Mondays at 00:10 IST.

WHAT WAS WRONG. The hub titles were 74, 81 and 92 characters, because the hub templates still appended
" | RashiKundli" - fourteen characters of brand, in a sixty-character budget, spent on the one word the
reader already knows - and because a week inside one month spelled the month twice. 10A took the brand
suffix off the READING pages and shortened those sixty titles; the hubs kept theirs, and the title test it
added never looked at a hub. That is the gap this file closes.
"""
from __future__ import annotations

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rashifal import i18n as words
from app.web import i18n

client = TestClient(app)

HUBS = [(i18n.url_for(key, lang), key, lang)
        for key in ("rashifal-hub", "rashifal-weekly") for lang in i18n.LANGS]
WEEKLY = [row for row in HUBS if row[1] == "rashifal-weekly"]
TITLE_LIMIT = 60


def head(path: str) -> tuple[str, str]:
    html = client.get(path).text
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    meta = re.search(r'name="description" content="(.*?)"', html, re.S)
    return (title.group(1).strip() if title else ""), (meta.group(1).strip() if meta else "")


@pytest.mark.parametrize("path, key, lang", HUBS)
def test_the_hub_title_fits_in_what_a_search_result_shows(path, key, lang):
    title, _ = head(path)
    assert title, path
    assert len(title) <= TITLE_LIMIT, f"{path}: {len(title)} characters - {title!r}"


@pytest.mark.parametrize("path, key, lang", HUBS)
def test_the_hub_title_does_not_spend_its_budget_on_the_brand(path, key, lang):
    """A reader who is looking at our result does not need to be told whose site it is, and 10A already
    took these fourteen characters off the reading pages."""
    title, _ = head(path)
    assert "RashiKundli" not in title, (path, title)


@pytest.mark.parametrize("path, key, lang", WEEKLY)
def test_the_weekly_hub_titles_the_week_it_is_about(path, key, lang):
    """A weekly page that does not say WHICH week is indistinguishable, in a result list, from the same
    page six weeks stale."""
    title, _ = head(path)
    # THE WEEK COMES FROM THE SAME PLACE THE PAGE GETS IT: the engine's IST window, not this machine's
    # clock. `dt.date.today()` is the local date, and on a UTC box the IST date is already tomorrow from
    # 18:30 - so at Sunday 19:00 UTC the page's window starts 26 October and date.today() computes
    # 19 October, a week apart. The test failed for about five and a half hours every Sunday, for no
    # reason in the code at all. Asking periods for the window cannot drift from what the page used.
    from app.rashifal.periods import window_for

    window = window_for("weekly")
    expected = words.format_range(window.start_date.isoformat(), window.end_date.isoformat(),
                                  lang, compact=True)
    assert expected in title, (path, title, expected)


@pytest.mark.parametrize("path, key, lang", WEEKLY)
def test_a_week_inside_one_month_names_the_month_once(path, key, lang):
    """"19 अक्टूबर – 25 अक्टूबर 2026" spends nine characters saying अक्टूबर twice, and those are
    characters the phrase a searcher typed does not get."""
    same_month = words.format_range("2026-10-19", "2026-10-25", lang, compact=True)
    assert same_month.count("–") == 1
    # COUNTING MONTH NAMES, not whitespace tokens. The compact dash is unspaced - a date range takes
    # one, and the weekly title needs the two characters - so "28 September–4 October 2026" splits
    # into four tokens where the spaced form gave five. A test that counts tokens is measuring the
    # typography; what it means to check is that each month is named as often as it carries meaning.
    month = same_month.split("–")[1].strip().split()[1]
    assert same_month.count(month) == 1, same_month
    # across a month boundary both months are still named, because then they carry information
    across = words.format_range("2026-09-28", "2026-10-04", lang, compact=True)
    first_month = words._MONTHS[lang][8]          # September
    second_month = words._MONTHS[lang][9]         # October
    assert first_month in across and second_month in across, across
    assert across.count("–") == 1, across


@pytest.mark.parametrize("path, key, lang", HUBS)
def test_the_heading_and_the_title_date_the_same_week(path, key, lang):
    """One of them would be wrong, and a reader cannot tell which."""
    html = client.get(path).text
    title, _ = head(path)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    assert h1, path
    heading = re.sub(r"<[^>]+>", "", h1.group(1))
    if key == "rashifal-weekly":
        # The dash may be spaced or not; what must hold is that the title's date string is the
        # heading's date string, whichever shape the formatter is using.
        dates = re.search(r"(\d{1,2}\s*–\s*\d{1,2} \S+ \d{4}|\d{1,2} \S+\s*–\s*\d{1,2} \S+ \d{4})",
                          title)
        assert dates, (path, title)
        assert dates.group(1) in heading, (path, heading, dates.group(1))


@pytest.mark.parametrize("path, key, lang", HUBS)
def test_all_twelve_signs_are_on_the_hub_with_somewhere_to_go(path, key, lang):
    html = client.get(path).text
    period = "weekly" if key == "rashifal-weekly" else "today"
    missing = [rashi for rashi in i18n.RASHI_KEYS
               if i18n.url_for("rashifal-reading", lang, rashi=rashi, period=period) not in html]
    assert not missing, (path, missing)


@pytest.mark.parametrize("path, key, lang", HUBS)
def test_every_sign_carries_a_teaser_and_never_an_empty_card(path, key, lang):
    """A card with a heading and nothing under it is worse than no card. When the written reading has not
    been generated the teaser falls back to the week's real planetary facts - never to invented text, and
    never to blank."""
    html = client.get(path).text
    for rashi in i18n.RASHI_KEYS:
        link = i18n.url_for("rashifal-reading", lang, rashi=rashi, period=period_of(key))
        at = html.index(link)
        card = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html[max(0, at - 700):at]))
        assert len(card.strip()) > 60, (path, rashi, card[-80:])


def period_of(key: str) -> str:
    return "weekly" if key == "rashifal-weekly" else "today"


def test_the_weekly_window_is_refreshed_on_mondays():
    """The hub is only as good as the readings behind it. The cadence is the scheduler's, and this pins it
    so a change there has to be deliberate."""
    from app.rashifal import periods

    monday = dt.date(2026, 10, 19)   # a Monday, fixed: this test is about the rule, not about today
    window = periods.window_for("weekly", periods.to_ist(dt.datetime.combine(monday, dt.time(9))))
    assert window.start_date == monday, window
    assert window.end_date == monday + dt.timedelta(days=6), window
    # and a reading taken mid-week still belongs to the same Monday, which is what makes the window
    # stable enough to put in a title
    for offset in (2, 4, 6):
        midweek = periods.to_ist(dt.datetime.combine(monday + dt.timedelta(days=offset), dt.time(9)))
        assert periods.window_for("weekly", midweek).start_date == monday, offset
    # and the next Monday starts a new one
    next_monday = periods.to_ist(dt.datetime.combine(monday + dt.timedelta(days=7), dt.time(1)))
    assert periods.window_for("weekly", next_monday).start_date == monday + dt.timedelta(days=7)


def test_the_weekly_title_fits_in_EVERY_week_not_just_this_one():
    """THE TEST ABOVE ONLY EVER SEES THE WEEK IT IS RUN IN.

    That is how this shipped: the weekly hub's title carries the week's dates, so its length depends
    on the calendar, and the overflow only appears in particular weeks - the one spanning the new
    year, when neither year can be dropped, and the ones spanning two long month names. A suite run
    in March passes and the same code fails in December. It did pass, repeatedly, and then failed on
    a Sunday in October with nothing having changed but the date.

    So this sweeps every week of three years in all three trees. A title is generated, not written,
    and anything generated has to be checked over its whole range of inputs rather than at whatever
    point the clock happens to be at.
    """
    import datetime as dt

    from app.rashifal import i18n as words

    worst = {}
    day = dt.date(2026, 1, 5)                     # a Monday
    while day < dt.date(2029, 1, 1):
        end = day + dt.timedelta(days=6)
        for lang in ("en", "hi", "mr"):
            covers = words.format_range(day.isoformat(), end.isoformat(), lang, compact=True)
            title = words.hub_title("weekly", lang, covers)
            if len(title) > len(worst.get(lang, "")):
                worst[lang] = title
        day += dt.timedelta(days=7)

    assert set(worst) == {"en", "hi", "mr"}
    over = {lang: (len(title), title) for lang, title in worst.items() if len(title) > TITLE_LIMIT}
    assert not over, f"the longest week of the year overflows: {over}"


def test_the_weekly_title_still_carries_the_week_and_a_roman_phrase():
    """Trimming a title to fit is only right while it keeps the two things it is for: the dates that
    distinguish this week from every other week, and - in the Devanagari trees - a Roman phrase, so
    a reader scanning results in either script finds it."""
    import datetime as dt
    import re

    from app.rashifal import i18n as words

    start, end = dt.date(2027, 1, 25), dt.date(2027, 1, 31)
    for lang in ("en", "hi", "mr"):
        covers = words.format_range(start.isoformat(), end.isoformat(), lang, compact=True)
        title = words.hub_title("weekly", lang, covers)
        assert covers in title, (lang, title)
        assert "2027" in title, (lang, title)
        if lang != "en":
            assert re.search(r"[A-Za-z]{4,}", title), (lang, title)


def test_a_week_across_the_new_year_still_says_which_december():
    """The first year is dropped even across the turn, which is safe because the months say it:
    December comes before January, so "28 December - 3 January 2027" is 2026's December and a reader
    resolves that without being told. Dropping it is what buys the longest week its room."""
    import datetime as dt

    from app.rashifal import i18n as words

    covers = words.format_range("2026-12-28", "2027-01-03", "en", compact=True)
    assert covers == "28 December–3 January 2027"
    assert "2026" not in covers
    # The long form, which sits in prose rather than in a title, keeps both years.
    full = words.format_range("2026-12-28", "2027-01-03", "en")
    assert "2026" in full and "2027" in full
