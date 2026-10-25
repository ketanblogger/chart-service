"""Month by month on the yearly page: twelve short paragraphs built from dated events.

WHY IT IS IN THE BRIEF RATHER THAN LEFT TO THE WRITER. The prompt forbids inventing timing - "around
mid-March" is the exact phrase it names - and a model with a year of prose to fill and a flat list of
dates is a model that reaches for exactly that. Twelve buckets, each holding only its own month's
events, means walking the year in order requires no arithmetic and no guessing.

Invented people only; `tests/` is published.
"""

import datetime as dt

import pytest

from app.rashifal.brief import build_brief
from app.rashifal.prompts import rashifal_schema

MOMENT = dt.datetime(2027, 3, 1, tzinfo=dt.timezone.utc)


@pytest.fixture(scope="module")
def yearly():
    return build_brief("mesha", "yearly", MOMENT)


def test_the_yearly_brief_has_twelve_months_in_order(yearly):
    months = yearly["months"]
    assert len(months) == 12
    assert [m["number"] for m in months] == list(range(1, 13))
    assert months[0]["month"] == "January" and months[-1]["month"] == "December"


def test_every_dated_event_lands_in_its_own_month(yearly):
    """A month holds only its own events, so the writer never has to work out which month a date is
    in - which is where invented timing comes from."""
    for bucket in yearly["months"]:
        for event in bucket["events"]:
            stamp = event.get("date") or event.get("datetime") or ""
            assert int(str(stamp)[5:7]) == bucket["number"], (bucket["month"], stamp)


def test_a_month_with_no_events_is_present_and_empty():
    """ALL TWELVE ARE ALWAYS THERE, whether or not anything happens in them - the prompt tells the
    writer to say the slow grahas do not move that month, which is true and better than filler.

    Tested on a constructed list rather than on a real year: 2027 happens to have something in every
    month for Mesha, and a test that depends on a quiet month would pass or fail according to which
    year and rashi it was pointed at."""
    from app.rashifal.brief import _months

    class _W:
        pass

    buckets = _months([{"id": "e1", "date": "2027-06-03"}], _W())
    assert len(buckets) == 12
    assert [m["number"] for m in buckets] == list(range(1, 13))
    assert len(buckets[5]["events"]) == 1                 # June
    assert all(buckets[n]["events"] == [] for n in range(12) if n != 5)


def test_every_month_of_a_real_year_is_present(yearly):
    assert len(yearly["months"]) == 12
    assert all("events" in m for m in yearly["months"])


def test_no_event_is_lost_or_duplicated_by_the_bucketing(yearly):
    bucketed = sum(len(m["events"]) for m in yearly["months"])
    dated = [e for e in yearly["events"] if (e.get("date") or e.get("datetime"))]
    assert bucketed == len(dated)
    ids = [e.get("id") for m in yearly["months"] for e in m["events"]]
    assert len(ids) == len(set(ids))


def test_the_eclipses_are_in_the_yearly_brief_with_their_house(yearly):
    eclipses = yearly["eclipses"]
    assert len(eclipses) == 5
    for one in eclipses:
        assert 1 <= one["house_from_rashi"] <= 12
        assert one["date"].startswith("2027")
        assert isinstance(one["visible_in_india"], bool)
        assert isinstance(one["observed_as_grahan"], bool)


def test_the_eclipse_facts_carry_no_meaning(yearly):
    """The brief gives a date and a position. "An eclipse in your sign brings..." is the sentence the
    site's own checker refuses, and it is not in the data handed to the writer."""
    from app.blog import safety

    text = " ".join(str(v) for one in yearly["eclipses"] for v in one.values() if isinstance(v, str))
    assert not safety.blocking_terms(text)


def test_only_the_yearly_period_gets_months():
    """Structured outputs require every key, so a daily page handed the months schema would write
    twelve months for one day."""
    assert "months" in rashifal_schema(("en",), "yearly")["properties"]["en"]["properties"]
    for period in ("today", "weekly", "monthly", "6-months"):
        assert "months" not in rashifal_schema(("en",), period)["properties"]["en"]["properties"]


def test_a_brief_for_another_period_has_no_months():
    for period in ("today", "weekly", "monthly", "6-months"):
        assert "months" not in build_brief("mesha", period, MOMENT)


def test_the_prompt_tells_the_writer_what_to_do_with_an_empty_month():
    from app.rashifal.prompts import _PERIOD_GUIDE

    guide = " ".join(_PERIOD_GUIDE["yearly"])
    assert "months" in guide
    assert "empty" in guide and "invented" in guide


def test_the_prompt_forbids_making_an_eclipse_happen_to_anybody():
    from app.rashifal.prompts import SYSTEM_PROMPT

    assert "ECLIPSES ARE DATES AND POSITIONS" in SYSTEM_PROMPT
    assert "sutak is not observed" in SYSTEM_PROMPT


def test_an_older_stored_reading_without_months_still_renders():
    """Every yearly page written before the schema asked for months has none, and must not 500."""
    import inspect

    from app.web import rashifal as web_rashifal

    source = inspect.getsource(web_rashifal._reading)
    assert 'content.get("months")' in source, "a missing key must not raise"
