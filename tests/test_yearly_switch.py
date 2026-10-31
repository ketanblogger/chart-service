"""When the rolling yearly page becomes next year's, and what it says while the reading catches up.

THE SWITCH IS A DATE; THE READING IS A BATCH JOB. Those are different things, and the gap between
them is the whole subject of this file. Turning the page over on 5 November does not write twelve
rashis in three languages - that run can fail for one of them, or finish English and not Marathi -
and a page titled 2027 over 2026 text is worse than one that is a few days late, because a reader
cannot tell and neither can a crawler.

Invented people only; `tests/` is published.
"""

import datetime as dt

import pytest

from app.rashifal.periods import YEARLY_SWITCH, window_for

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _on(date: str):
    return dt.datetime.fromisoformat(date + "T12:00:00+05:30")


def test_the_switch_is_the_fifth_of_november():
    """Moved from the 20th so the rolling page turns over on the day the dated 2027 pages go live.
    With the old date the site would have contradicted itself for a fortnight."""
    assert YEARLY_SWITCH == (11, 5)


@pytest.mark.parametrize("date,year", [
    ("2026-11-04", 2026),       # the day before
    ("2026-11-05", 2027),       # the day itself
    ("2026-12-31", 2027),
    ("2027-01-01", 2027),
    ("2027-11-04", 2027),
    ("2027-11-05", 2028),
])
def test_the_window_turns_over_on_the_day(date, year):
    assert window_for("yearly", _on(date)).year == year


def test_the_window_is_a_calendar_year_either_side_of_the_switch():
    """Nobody searches for a rolling twelve months. "rashifal 2027" is a calendar year or it is
    nothing, which is why this period is not rolling like the others."""
    window = window_for("yearly", _on("2026-11-06"))
    assert window.start_date.isoformat() == "2027-01-01"
    assert window.end_date.isoformat() == "2027-12-31"


def test_the_title_year_follows_the_reading_rather_than_the_calendar():
    """THE FALLBACK. A rashi whose 2027 reading has not been written yet keeps a 2026 title over its
    2026 text, per rashi and per language, and catches up by itself when the content lands."""
    import inspect

    from app.web import rashifal as web_rashifal

    source = inspect.getsource(web_rashifal.reading_page)
    assert "shown_year" in source
    assert "year=shown_year" in source, "the title must use the fallback year, not window.year"
    assert "not is_current" in source


def test_the_fallback_only_applies_to_the_yearly_page():
    """A weekly page showing last week's reading is a stale page and should look like one; the
    yearly page is the only one whose window change is a deliberate, dated turnover."""
    import inspect

    from app.web import rashifal as web_rashifal

    source = inspect.getsource(web_rashifal.reading_page)
    assert 'period == "yearly"' in source


def test_a_page_with_no_reading_at_all_still_says_the_new_year():
    """The fallback is for a page showing LAST year's text. A page with no reading yet shows the
    dated facts and the year it is about - there is nothing stale to be honest about."""
    import inspect

    from app.web import rashifal as web_rashifal

    source = inspect.getsource(web_rashifal.reading_page)
    assert "stored and reading and not is_current" in source
