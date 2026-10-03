"""Phase 7: period windows and the engine-only transit brief."""

import datetime as dt
import json

import pytest

from app import engine
from app.rashifal.brief import BRIEF_VERSION, brief_hash, build_brief
from app.rashifal.periods import IST, PERIOD_SLUGS, RASHI_SLUGS, rashi_index, window_for

NOW = dt.datetime(2026, 9, 21, 10, 0, tzinfo=IST)  # a Monday


def ist(*args):
    return dt.datetime(*args, tzinfo=IST)


def test_slugs_are_exactly_the_spec():
    assert RASHI_SLUGS == ["mesha", "vrishabha", "mithuna", "karka", "simha", "kanya", "tula", "vrishchika", "dhanu",
                           "makara", "kumbha", "meena"]
    assert PERIOD_SLUGS == ["today", "weekly", "monthly", "6-months", "yearly"]
    assert [rashi_index(slug) for slug in RASHI_SLUGS] == list(range(1, 13))
    for bad in ("Mesha", "aries", "", "mesha "):
        with pytest.raises(ValueError):
            rashi_index(bad)


def test_today_is_the_ist_calendar_day():
    late, midnight = window_for("today", ist(2026, 9, 21, 23, 59, 59)), window_for("today", ist(2026, 9, 22, 0, 0))
    assert (late.start, late.end) == (ist(2026, 9, 21), ist(2026, 9, 22))
    assert midnight.start == ist(2026, 9, 22) and late.key == "2026-09-21" and midnight.key == "2026-09-22"
    assert late.start_date == late.end_date == dt.date(2026, 9, 21) and late.days == 1
    # IST midnight is 18:30 UTC: the UTC date is not the IST date
    utc = dt.timezone.utc
    assert window_for("today", dt.datetime(2026, 9, 21, 18, 29, tzinfo=utc)).key == "2026-09-21"
    assert window_for("today", dt.datetime(2026, 9, 21, 18, 30, tzinfo=utc)).key == "2026-09-22"
    assert window_for("today", dt.datetime(2026, 9, 21, 23, 0)).key == "2026-09-21"  # naive = IST


def test_weekly_is_monday_to_sunday():
    for moment in (ist(2026, 9, 21, 0, 0), ist(2026, 9, 24, 12, 0), ist(2026, 9, 27, 23, 59)):
        window = window_for("weekly", moment)
        assert (window.start, window.end) == (ist(2026, 9, 21), ist(2026, 9, 28))
        assert window.start.weekday() == 0 and window.end_date == dt.date(2026, 9, 27) and window.days == 7
    assert window_for("weekly", ist(2026, 9, 20, 23, 59)).key == "2026-09-14"
    assert window_for("weekly", ist(2026, 9, 28, 0, 0)).key == "2026-09-28"
    year_end = window_for("weekly", ist(2027, 1, 1, 9, 0))  # a week that spans the new year
    assert (year_end.start_date, year_end.end_date) == (dt.date(2026, 12, 28), dt.date(2027, 1, 3))


@pytest.mark.parametrize("period, moment, start, end", [
    ("monthly", ist(2026, 9, 21), dt.date(2026, 9, 1), dt.date(2026, 9, 30)),
    ("6-months", ist(2026, 9, 30, 23, 59), dt.date(2026, 9, 1), dt.date(2027, 2, 28)),
    ("monthly", ist(2026, 12, 31, 23, 59), dt.date(2026, 12, 1), dt.date(2026, 12, 31)),  # last minute of the year
    ("monthly", ist(2028, 2, 10), dt.date(2028, 2, 1), dt.date(2028, 2, 29)),   # leap February
    ("monthly", ist(2027, 1, 1, 0, 0), dt.date(2027, 1, 1), dt.date(2027, 1, 31)),
    ("6-months", ist(2027, 9, 15), dt.date(2027, 9, 1), dt.date(2028, 2, 29)),  # ends on a leap day
    ("6-months", ist(2026, 10, 1, 0, 0), dt.date(2026, 10, 1), dt.date(2027, 3, 31)),
])
def test_long_periods_roll_from_the_first_of_the_month(period, moment, start, end):
    window = window_for(period, moment)
    assert (window.start_date, window.end_date) == (start, end)
    assert window.start == ist(start.year, start.month, 1)


def test_same_window_for_every_moment_in_it_and_unknown_period():
    assert window_for("6-months", ist(2026, 9, 1)).key == window_for("6-months", ist(2026, 9, 30, 23, 59)).key
    assert window_for("6-months", ist(2026, 10, 1)).key == "2026-10-01"
    with pytest.raises(ValueError):
        window_for("3-months", NOW)


def test_yearly_is_the_calendar_year_and_turns_over_in_november():
    """Yearly stopped rolling monthly on 2026-09-26. Nobody searches for "the next twelve months" - they
    search "dhanu rashifal 2027", and they start in November. So the page is a calendar year, and it turns
    to the next one on 20 November, which is when that demand appears rather than when the year begins.

    The 6-month page deliberately kept the rolling window: no one searches for a calendar half-year."""
    for moment, year in ((ist(2026, 1, 1), 2026), (ist(2026, 9, 26), 2026), (ist(2026, 11, 19, 23, 59), 2026),
                         (ist(2026, 11, 20, 0, 0), 2027), (ist(2026, 12, 31, 23, 59), 2027),
                         (ist(2027, 1, 1, 0, 0), 2027), (ist(2027, 11, 19), 2027), (ist(2027, 11, 20), 2028)):
        window = window_for("yearly", moment)
        assert window.year == year, moment
        assert (window.start_date, window.end_date) == (dt.date(year, 1, 1), dt.date(year, 12, 31)), moment

    # One turnover a year, so the refresh job regenerates it once a year: every moment between two
    # 20 Novembers is the same window key, which is what makes the refresh idempotent.
    keys = {window_for("yearly", ist(2027, month, 5)).key for month in range(1, 12)}
    assert keys == {"2027-01-01"}
    assert window_for("yearly", ist(2026, 11, 20)).key == window_for("yearly", ist(2027, 6, 1)).key


# ---- brief ---------------------------------------------------------------------------------------


def _saturn_house(brief):
    return next(p["house"] for p in brief["positions_at_start"] if p["graha"]["key"] == "Saturn")


@pytest.mark.parametrize("period", PERIOD_SLUGS)
def test_brief_is_rashi_specific(period):
    briefs = {rashi: build_brief(rashi, period, NOW) for rashi in RASHI_SLUGS}
    assert sorted(_saturn_house(b) for b in briefs.values()) == list(range(1, 13))  # same graha, 12 different houses
    assert len({brief_hash(b) for b in briefs.values()}) == 12
    for rashi, brief in briefs.items():
        assert brief["rashi"]["index"] == rashi_index(rashi) and brief["saturn"]["saturn_house_from_moon"] == _saturn_house(brief)
    first, second = briefs["mesha"]["events"], briefs["vrishabha"]["events"]
    assert [e["date"] for e in first] == [e["date"] for e in second]  # same sky ...
    assert all((a["house"] - b["house"]) % 12 == 1 for a, b in zip(first, second))  # ... one house apart


def test_brief_matches_the_engine_and_needs_no_arithmetic():
    brief = build_brief("dhanu", "weekly", NOW)
    assert brief["version"] == BRIEF_VERSION and brief["period"] == {
        "slug": "weekly", "start_date": "2026-09-21", "end_date": "2026-09-27", "days": 7, "timezone": "Asia/Kolkata (IST)"}
    raw = engine.transit_events(ist(2026, 9, 21), ist(2026, 9, 28), rashi="dhanu")
    assert [(e["date"], e["graha"]["key"], e["house"]) for e in brief["events"]] == \
           [(r["datetime"][:10], r["graha"]["key"], r["house"]) for r in raw]
    assert [e["id"] for e in brief["events"]] == [f"e{n}" for n in range(1, len(raw) + 1)]
    transits = engine.current_transits(ist(2026, 9, 21), rashi="dhanu")["grahas"]
    for position in brief["positions_at_start"]:
        source = transits[position["graha"]["key"]]
        assert (position["sign"]["index"], position["house"], position["retrograde"]) == \
               (source["sign"]["index"], source["house"], source["retrograde"])
    moon_events = [e for e in brief["events"] if e["graha"]["key"] == "Moon"]
    assert len(moon_events) >= 2 and all(e["chandra_bala"]["moon_house_from_rashi"] == e["house"] for e in moon_events)
    text = json.dumps(brief)
    for forbidden in ('"longitude"', '"degree"', '"degree_dms"', '"speed"', '"datetime_utc"'):
        assert forbidden not in text  # nothing that invites the AI to do arithmetic
    assert brief["saturn"]["dhaiya"]["active"] is True and brief["saturn"]["dhaiya"]["kind"] == "fourth"


def test_today_brief_has_panchang_moon_and_a_deterministic_lucky_pair():
    brief = build_brief("mesha", "today", NOW)
    assert brief["panchang"]["vara"]["key"] == "Monday" and brief["panchang"]["tithi"]["name"] == "Dashami"
    bala = brief["moon_at_sunrise"]["chandra_bala"]
    assert bala == {"moon_house_from_rashi": 9, "favourable": False}
    assert brief["lucky"]["basis"] == "rashi_lord" and brief["lucky"]["graha"]["key"] == "Mars"  # Mesha's lord
    assert (brief["lucky"]["colour"]["key"], brief["lucky"]["number"]) == ("red", 9)
    mithuna = build_brief("mithuna", "today", NOW)  # Moon in Dhanu = 7th from Mithuna: favourable -> Monday's lord
    assert mithuna["moon_at_sunrise"]["chandra_bala"]["favourable"] is True
    assert mithuna["lucky"]["basis"] == "day_lord" and mithuna["lucky"]["graha"]["key"] == "Moon"
    assert set(mithuna["lucky"]["colour"]) == {"key", "en", "mr", "hi"}
    assert build_brief("mesha", "today", NOW) == brief  # deterministic
    assert "panchang" not in build_brief("mesha", "weekly", NOW) and "lucky" not in build_brief("mesha", "weekly", NOW)


@pytest.mark.parametrize("period", ["monthly", "6-months", "yearly"])
def test_long_briefs_cover_slow_grahas_without_the_moon(period):
    brief = build_brief("karka", period, NOW)
    assert all(p["graha"]["key"] != "Moon" for p in brief["positions_at_start"]) and "moon_at_start" not in brief
    assert all(e["graha"]["key"] != "Moon" for e in brief["events"]) and brief["events"]
    by_graha = {}
    for stay in brief["slow_graha_stays"]:
        by_graha.setdefault(stay["graha"]["key"], []).append(stay)
    assert set(by_graha) == {"Jupiter", "Saturn", "Rahu", "Ketu"}
    for stays in by_graha.values():
        assert stays[0]["from"] == brief["period"]["start_date"] and stays[-1]["to"] == brief["period"]["end_date"]
        assert all(a["to"] == b["from"] for a, b in zip(stays, stays[1:]))  # contiguous
        assert all(1 <= s["house"] <= 12 for s in stays)
    ingresses = [e for e in brief["events"] if e["type"] == "ingress" and e["graha"]["key"] in by_graha]
    assert sum(len(s) - 1 for s in by_graha.values()) == len(ingresses)
    assert "periods" in brief["saturn"]["sade_sati"]["cycle"]


def test_brief_is_a_fresh_copy_each_time():
    brief = build_brief("mesha", "today", NOW)
    brief["events"].append("junk")
    assert "junk" not in build_brief("mesha", "today", NOW)["events"]
