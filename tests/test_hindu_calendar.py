"""A year of the Hindu calendar, checked against the tradition's own internal structure.

NO DATE HERE IS COMPARED WITH A LIST COPIED FROM SOMEWHERE. The festivals have fixed relationships
to each other - Holika Dahan is the night before Holi, Ram Navami is eight days after Gudi Padwa,
Dussehra is nine days after Navratri begins - and those relationships are what this file asserts.
They caught five wrong dates that each looked perfectly reasonable on its own: the Sun's sign on the
day of a tithi is NOT the sign the lunar month is named for, because a shukla paksha ends at purnima
by which time the Sun has usually moved on, and five festivals were pinned a month late.

A pinned list of dates would have been less work and would have tested that I had copied it
correctly, which is not the thing in doubt.
"""
import datetime as dt

import pytest

from app.engine import hindu_calendar as hc

YEAR = 2027


@pytest.fixture(scope="module")
def dates():
    return {item["key"]: item["date"] for item in hc.festivals(YEAR)}


@pytest.fixture(scope="module")
def listed():
    return hc.festivals(YEAR)


def test_every_festival_in_the_list_gets_a_date(listed):
    """A festival that cannot be dated vanishes from the calendar silently, which is the kind of gap
    nobody notices until a reader does. Dhanteras, Lakshmi puja and Makar Sankranti are the three
    that do not come from the tithi table."""
    assert len(listed) == len(hc.FESTIVALS) + 3
    assert {item["key"] for item in listed} >= {key for key, *_ in hc.FESTIVALS}
    for item in listed:
        assert isinstance(item["date"], dt.date) and item["date"].year == YEAR, item["key"]


def test_they_are_in_date_order(listed):
    assert [item["date"] for item in listed] == sorted(item["date"] for item in listed)


@pytest.mark.parametrize("earlier, later, gap", [
    ("holika-dahan", "holi", 1),                      # the dahan is the night before the colours
    ("gudi-padwa", "ram-navami", 8),                  # Chaitra shukla 1 to shukla 9
    ("ganesh-chaturthi", "anant-chaturdashi", 10),    # shukla 4 to shukla 14
    ("dhanteras", "lakshmi-puja", 2),                 # trayodashi to amavasya
])
def test_the_fixed_gaps_between_festivals_hold(dates, earlier, later, gap):
    assert (dates[later] - dates[earlier]).days == gap


def test_the_order_within_the_year_is_the_order_the_tradition_has(dates):
    assert dates["navratri-start"] < dates["dussehra"] < dates["kojagiri"]
    assert (dates["dussehra"] - dates["navratri-start"]).days in (9, 10)
    assert dates["kojagiri"] < dates["karva-chauth"] < dates["dhanteras"]
    assert dates["lakshmi-puja"] < dates["tulsi-vivah"] < dates["kartik-purnima"]
    assert (dates["tulsi-vivah"] - dates["lakshmi-puja"]).days <= 21
    assert dates["vat-purnima"] < dates["guru-purnima"] < dates["raksha-bandhan"]
    assert dates["raksha-bandhan"] < dates["janmashtami"] < dates["ganesh-chaturthi"]


def test_makar_sankranti_is_the_day_the_sun_enters_makara():
    """Solar, so no tithi is involved at all - and it is the one festival whose Gregorian date
    barely moves, which makes it a check on the Sun calculation itself."""
    day = hc.makar_sankranti(YEAR)
    assert day is not None and day.month == 1 and 13 <= day.day <= 16
    assert hc._sun_sign_on(day, hc.DEFAULT_CITY) == "Makara"
    assert hc._sun_sign_on(day - dt.timedelta(days=1), hc.DEFAULT_CITY) == "Dhanu"


def test_a_tithi_that_never_catches_a_sunrise_still_gets_its_festival(listed):
    """A tithi runs about 23 hours 37 minutes, so some have no sunrise in them at all and no day is
    NAMED for them. In 2027 Phalguna Purnima is one. The festival does not stop existing."""
    by_basis = {}
    for item in listed:
        by_basis.setdefault(item["basis"], []).append(item["key"])
    # WHICH festival needs it is a property of the year, not of the code: in 2027 it is Navratri's
    # first day, and correcting an unrelated sun-sign moved Holika Dahan off this branch and onto
    # the sunrise one. So the assertion is that the branch is REACHED, not which name reaches it.
    assert "tithi-start" in by_basis, (
        "no festival needed the kshaya-tithi fallback this year - if that is really so the branch "
        "is untested, and if it is not, the fallback has stopped working")
    assert by_basis["tithi-start"]
    assert all(key in {k for k, *_ in hc.FESTIVALS} for key in by_basis["tithi-start"])


def test_the_evening_observances_come_from_the_module_that_decides_them(listed):
    """Dhanteras and Lakshmi puja are decided by the tithi at pradosh, not at sunrise, by
    app/engine/festivals.py. The calendar imports that answer so the two can never print different
    dates for the same evening."""
    from app.engine import festivals

    by_key = {item["key"]: item for item in listed}
    assert by_key["dhanteras"]["basis"] == "pradosh"
    assert by_key["lakshmi-puja"]["basis"] == "pradosh"
    assert by_key["lakshmi-puja"]["date"] == festivals.windows("lakshmi-puja", YEAR, "Ujjain")["date"]


def test_the_ekadashis_amavasyas_and_purnimas_are_the_right_shape_of_year():
    """Two ekadashis a lunar month, one amavasya and one purnima - so twenty-four or twenty-five,
    and twelve or thirteen, in a Gregorian year. A count outside that means the walk is broken."""
    ekadashis = hc.ekadashis(YEAR)
    assert 23 <= len(ekadashis) <= 26
    assert {e["paksha"]["key"] for e in ekadashis} == {"shukla", "krishna"}
    assert 12 <= len(hc.amavasyas(YEAR)) <= 13
    assert 12 <= len(hc.purnimas(YEAR)) <= 13
    for group in (ekadashis, hc.amavasyas(YEAR), hc.purnimas(YEAR)):
        assert [item["date"] for item in group] == sorted(item["date"] for item in group)
        assert all(item["date"].year == YEAR for item in group)


def test_an_amavasya_is_never_a_purnima():
    assert not ({a["date"] for a in hc.amavasyas(YEAR)} & {p["date"] for p in hc.purnimas(YEAR)})


def test_every_festival_is_named_in_all_three_languages(listed):
    for item in listed:
        assert set(item["names"]) == {"en", "hi", "mr"}, item["key"]
        assert all(item["names"].values()), item["key"]
        # Marathi is not the Hindi name with a different font: several of these genuinely differ
        # (धुलिवंदन for Holi, कोजागिरी पौर्णिमा for Sharad Purnima, त्रिपुरारी for Kartik Purnima).
    differing = [i["key"] for i in listed if i["names"]["hi"] != i["names"]["mr"]]
    assert len(differing) >= 8, f"only {len(differing)} names differ between Hindi and Marathi"
