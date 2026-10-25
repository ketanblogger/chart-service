"""The muhurta engine, against values taken from a published panchang rather than from itself.

A golden test whose expected values came out of the thing under test proves only that it is consistent.
These come from Drik Panchang for Pune, which is the cross-check that was agreed: a mismatch is a question
first - whose sunrise, whose ayanamsa - and a verdict only after that question has an answer. The tolerance
is +/-5 minutes on sunrise and on the day's divisions, which is about what two sunrise conventions differ
by; the tithi and nakshatra NAMES are exact, because those are not a matter of convention.
"""

import datetime as dt

import pytest

from app.engine import muhurta

PUNE = {"name": "Pune", "lat": 18.5204, "lon": 73.8567, "tz": "Asia/Kolkata"}
TOLERANCE = dt.timedelta(minutes=5)


def _at(stamp: str) -> dt.datetime:
    return dt.datetime.fromisoformat(stamp)


def _close(got: str, want: str, what: str) -> None:
    a, b = _at(got), _at(want)
    assert abs(a - b) <= TOLERANCE, f"{what}: {got} vs the published {want} - more than 5 minutes apart"


# ---- the anchor ------------------------------------------------------------------------------------
# Thursday 11 March 2027 at Pune. Drik Panchang: Shukla Tritiya, Revati ending about 11:20,
# Rahu Kaal about 14:13 to 15:42.

def test_the_published_day_for_pune_comes_out_the_same_here():
    facts = muhurta.day_facts(dt.date(2027, 3, 11), PUNE)
    assert facts["tithi"]["paksha"]["name"] == "Shukla"
    assert facts["tithi"]["name"] == "Tritiya"
    assert facts["nakshatra"]["name"] == "Revati"
    _close(facts["nakshatra"]["ends_at"], "2027-03-11T11:20+05:30", "Revati ending")
    _close(facts["rahu_kaal"]["from"], "2027-03-11T14:13+05:30", "Rahu Kaal start")
    _close(facts["rahu_kaal"]["to"], "2027-03-11T15:42+05:30", "Rahu Kaal end")
    assert facts["vara"]["key"] == "Thursday"


def test_rahu_kaal_is_an_eighth_of_the_daylight_and_the_right_eighth():
    """Not a fixed ninety minutes and not measured over a civil day: sunrise to sunset, divided by eight.
    In March at Pune the difference between that and a noon-based split is about forty minutes."""
    facts = muhurta.day_facts(dt.date(2027, 3, 11), PUNE)
    rise, sets = _at(facts["sunrise"]), _at(facts["sunset"])
    part = (sets - rise) / 8
    assert facts["rahu_kaal"]["part"] == 6, "Thursday takes the sixth part"
    expected_from = rise + part * 5
    assert abs(_at(facts["rahu_kaal"]["from"]) - expected_from) <= dt.timedelta(minutes=1)
    assert abs((_at(facts["rahu_kaal"]["to"]) - _at(facts["rahu_kaal"]["from"])) - part) \
        <= dt.timedelta(minutes=1)


@pytest.mark.parametrize("day, part", [
    (dt.date(2027, 3, 8), 2),    # Monday
    (dt.date(2027, 3, 9), 7),    # Tuesday
    (dt.date(2027, 3, 10), 5),   # Wednesday
    (dt.date(2027, 3, 11), 6),   # Thursday
    (dt.date(2027, 3, 12), 4),   # Friday
    (dt.date(2027, 3, 13), 3),   # Saturday
    (dt.date(2027, 3, 14), 8),   # Sunday
])
def test_each_weekday_takes_its_own_part_of_the_day(day, part):
    """The whole sequence, not the one day that was checked against a panchang. An off-by-one here would
    be invisible on a Thursday and wrong on the other six days."""
    assert muhurta.day_facts(day, PUNE)["rahu_kaal"]["part"] == part


def test_sunrise_and_sunset_are_taken_the_same_way():
    """Both from core, both by the panchang convention. Mixing one convention with another puts the error
    straight into the day's divisions, where it is hardest to see."""
    facts = muhurta.day_facts(dt.date(2027, 3, 11), PUNE)
    _close(facts["sunrise"], "2027-03-11T06:50+05:30", "sunrise")
    assert _at(facts["sunset"]) > _at(facts["sunrise"])
    assert dt.timedelta(hours=10) < (_at(facts["sunset"]) - _at(facts["sunrise"])) < dt.timedelta(hours=14)


def test_the_place_actually_changes_the_answer():
    """A finder that ignored its place would pass every test above, since they are all at one place."""
    pune = muhurta.day_facts(dt.date(2027, 3, 11), PUNE)
    kolkata = muhurta.day_facts(dt.date(2027, 3, 11),
                                {"name": "Kolkata", "lat": 22.5726, "lon": 88.3639, "tz": "Asia/Kolkata"})
    # Kolkata is about 14.5 degrees east of Pune, so the Sun rises there the better part of an hour earlier.
    assert _at(kolkata["sunrise"]) < _at(pune["sunrise"]) - dt.timedelta(minutes=30)
    assert kolkata["rahu_kaal"]["from"] != pune["rahu_kaal"]["from"]


# ---- the rules -------------------------------------------------------------------------------------


def test_every_purpose_names_nakshatras_that_exist():
    """A typo in the rule file would otherwise read as 'no good days' for ever, which looks like an answer."""
    from app.engine.constants import nakshatra_info

    known = {nakshatra_info(index)["name"] for index in range(27)}
    for key, rule in muhurta.purposes().items():
        unknown = [name for name in rule["nakshatras"] if name not in known]
        assert not unknown, f"{key}: {unknown} are not nakshatras this engine knows"
        assert rule["nakshatras"], f"{key}: no nakshatra would ever pass"
        for lang in ("en", "hi", "mr"):
            assert rule.get(lang), f"{key}: no {lang} label"


def test_a_day_that_fails_says_which_rule_it_failed():
    """The reason is the product. 'No' without it cannot be checked by the reader or by us."""
    facts = muhurta.day_facts(dt.date(2027, 3, 11), PUNE)      # Revati, Shukla Tritiya, a Thursday
    verdict = muhurta.judge(facts, "griha-pravesh")
    assert verdict["passes"], verdict["failed"]

    # Shukla Chaturthi is rikta, and every purpose sets the rikta tithis aside.
    rikta = muhurta.day_facts(dt.date(2027, 3, 12), PUNE)
    assert rikta["tithi"]["day"] == 4, rikta["tithi"]
    assert not muhurta.judge(rikta, "griha-pravesh")["passes"]
    assert any("Chaturthi" in reason for reason in muhurta.judge(rikta, "griha-pravesh")["failed"])


def test_the_search_returns_only_days_that_pass_and_counts_what_it_searched():
    result = muhurta.find("griha-pravesh", dt.date(2027, 3, 1), dt.date(2027, 3, 31), PUNE)
    assert result["found"] == len(result["days"])
    assert result["searched_days"] >= result["found"]
    assert result["basis"] == "arithmetic, not a guarantee"
    for day in result["days"]:
        assert muhurta.judge(day, "griha-pravesh")["passes"], day["date"]


def test_an_empty_answer_stays_empty():
    """No padding. A near miss offered as a result is worth less than nothing, because the reader cannot
    see which rule it failed - and the whole value of this is that every answer has a reason."""
    # One day, chosen because it fails: Shukla Chaturthi is rikta.
    result = muhurta.find("griha-pravesh", dt.date(2027, 3, 12), dt.date(2027, 3, 12), PUNE)
    assert result["found"] == 0 and result["days"] == []
    assert result["searched_days"] == 1


def test_the_search_respects_its_limit_and_its_range():
    result = muhurta.find("business", dt.date(2027, 3, 1), dt.date(2027, 6, 30), PUNE, limit=3)
    assert result["found"] <= 3
    with pytest.raises(ValueError):
        muhurta.find("business", dt.date(2027, 3, 2), dt.date(2027, 3, 1), PUNE)
    with pytest.raises(ValueError):
        muhurta.find("business", dt.date(2027, 1, 1), dt.date(2029, 1, 1), PUNE)
    with pytest.raises(KeyError):
        muhurta.find("no-such-purpose", dt.date(2027, 3, 1), dt.date(2027, 3, 2), PUNE)


# ---- what it will not answer -----------------------------------------------------------------------


@pytest.mark.parametrize("asked", [
    "best day for my surgery", "muhurta for an operation next month", "when should the treatment start",
    "ऑपरेशन के लिए शुभ दिन", "शस्त्रक्रियेसाठी चांगला दिवस", "good date for the court case verdict",
])
def test_health_and_outcomes_are_refused_by_name(asked):
    """Refused, not answered emptily: 'no good days' is a worse answer than 'we do not do this'."""
    with pytest.raises(muhurta.Refused):
        muhurta.check_allowed(asked)


@pytest.mark.parametrize("asked", [
    "good day to move into the new flat", "muhurta for buying a car", "when to start the shop",
    "गृह प्रवेश के लिए शुभ दिन", "वाहन खरेदीसाठी मुहूर्त",
])
def test_ordinary_requests_are_not_refused(asked):
    """The other half of the gate. A refusal list that refuses everything would pass the test above."""
    muhurta.check_allowed(asked)
