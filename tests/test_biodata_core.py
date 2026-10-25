"""The six kundli rows a biodata prints, and the ones a date alone cannot settle.

Every expected value here was checked by hand from the Moon's sidereal longitude, not copied out of a
run: 216.7345 degrees puts the Moon 6.73 degrees into Vrishchika (which begins at 210), and Anuradha
spans 213.3333 to 226.6667, so the Moon is 0.2551 of the way through it - the second charan of four.
Gan and nadi follow from nakshatra 16, not from a second computation.

The people are invented. A biodata is the one document on this site made entirely of personal
details, which makes it the one place where a real name in a fixture would be worst.
"""
import datetime as dt

import pytest

from app.biodata import core

# An invented person: 3 April 1991, 14:25, at Pune's coordinates.
BORN = dt.date(1991, 4, 3)
AT = dt.time(14, 25)
PUNE = (18.52, 73.86)


def test_with_a_birth_time_all_six_rows_are_settled():
    k = core.from_birth(BORN, birth_time=AT, lat=PUNE[0], lon=PUNE[1], language="en")
    assert k["from_time"] is True and k["charan_index"] == 2
    assert [k["rows"][row]["known"] for row in core.ROWS] == [True] * 6
    assert k["rows"]["rashi"]["text"] == "Vrishchika"
    assert k["rows"]["nakshatra"]["text"] == "Anuradha"
    assert k["rows"]["charan"]["text"] == "2"
    assert k["rows"]["gan"]["text"] == "Deva"          # Anuradha is a Deva gan nakshatra
    assert k["rows"]["nadi"]["text"] == "Madhya"        # 16 % 6 == 4 -> the cycle's Madhya
    # Mars is in a dosha house AND a classical cancellation applies, so neither "Yes" nor "No" alone.
    assert k["rows"]["manglik"]["text"] == "Yes, with parihar (cancellation)"


def test_marathi_is_not_the_hindi_labels():
    """The whole point of this tool for a Marathi family is that it reads like their own paperwork."""
    mr, hi = core.LABELS["mr"], core.LABELS["hi"]
    assert mr["rashi"] == "रास" and hi["rashi"] == "राशि"      # रास, not राशि
    assert mr["nadi"] == "नाडी" and hi["nadi"] == "नाड़ी"        # no nukta in Marathi
    assert mr["manglik"] == "मंगळ" and hi["manglik"] == "मांगलिक"
    for lang in ("en", "hi", "mr"):
        assert set(core.LABELS[lang]) >= set(core.ROWS) | {"devak", "gotra"}


@pytest.mark.parametrize("language, expected", [
    ("mr", "वृश्चिक"), ("hi", "वृश्चिक"), ("en", "Vrishchika")])
def test_the_rashi_is_written_in_the_readers_script(language, expected):
    k = core.from_birth(BORN, birth_time=AT, lat=PUNE[0], lon=PUNE[1], language=language)
    assert k["rows"]["rashi"]["text"] == expected


def test_a_date_alone_names_both_possibilities_and_never_guesses():
    """The Moon crosses about thirteen degrees in a day - a whole nakshatra's width - so on this date
    it is in Tula at midnight and Vrishchika by the evening. A biodata that printed one of them would
    be showing a prospective family a guess with no mark on it."""
    k = core.from_birth(BORN, language="mr")
    assert k["from_time"] is False and k["charan_index"] is None
    assert k["rows"]["rashi"]["known"] is False
    assert k["rows"]["rashi"]["either"] == ["तुला", "वृश्चिक"]
    assert k["rows"]["nakshatra"]["either"] == ["विशाखा", "अनुराधा"]
    assert k["rows"]["gan"]["either"] == ["राक्षस", "देव"]        # Vishakha is Rakshasa, Anuradha Deva
    assert k["rows"]["nadi"]["either"] == ["अंत्य", "मध्य"]


def test_charan_and_manglik_ask_for_the_time_rather_than_answer():
    """Four charans pass in a day, and manglik needs the lagna. Both say what is needed instead of
    printing an answer - a blank manglik line is honest, and a "No" on the strength of a date is a
    claim the family may act on."""
    for language in ("en", "hi", "mr"):
        k = core.from_birth(BORN, language=language)
        for row in ("charan", "manglik"):
            assert k["rows"][row]["known"] is False
            assert k["rows"][row]["text"] == core.NEEDS_TIME[language]
            assert "either" not in k["rows"][row]


def test_a_date_whose_day_settles_the_nakshatra_reports_it_plainly():
    """Not every date is ambiguous: where the Moon stays inside one nakshatra from midnight to
    midnight, the row is settled and says so. A test that only ever saw the ambiguous case would not
    notice the settled branch breaking."""
    settled = [d for d in (dt.date(1991, 4, day) for day in range(1, 29))
               if core.from_birth(d)["rows"]["nakshatra"]["known"]]
    assert settled, "no date in a whole month settled its nakshatra - is both-ends checking broken?"
    k = core.from_birth(settled[0], language="en")
    assert k["rows"]["nakshatra"]["known"] and "either" not in k["rows"]["nakshatra"]
    assert k["rows"]["gan"]["known"] and k["rows"]["nadi"]["known"]


def test_an_unknown_language_is_refused():
    with pytest.raises(ValueError):
        core.from_birth(BORN, language="ta")
