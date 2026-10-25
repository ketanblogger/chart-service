"""The numerology arithmetic, against examples worked by hand.

EVERY EXPECTED VALUE IN THIS FILE WAS ADDED UP BY HAND and the working is in the test, because a
numerology test that calls the same function twice proves only that the function is consistent with
itself. If the Chaldean table is ever mistyped, these fail; if they were generated from the code,
they would not.

CHALDEAN ONLY. Pythagorean runs 1-9 straight across the alphabet and gives different answers for the
same name; a site that silently mixed them would be one nobody could check.

Invented people only; `tests/` is published.
"""

import datetime as dt

import pytest

from app.numerology import core


# ---- the table itself ----------------------------------------------------------------------------------


def test_every_letter_has_exactly_one_value():
    letters = "".join(core.CHALDEAN.values())
    assert len(letters) == 26, letters
    assert sorted(letters) == sorted("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def test_no_letter_is_worth_nine():
    """The 9 was held sacred and left out of the Chaldean letter table. A table with a 9 in it is a
    Pythagorean one that has been mislabelled."""
    assert 9 not in core.CHALDEAN
    assert max(core.CHALDEAN) == 8


# ---- reduction -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("total,expected", [
    (1, 1), (9, 9), (10, 1), (11, 2), (22, 4), (27, 9), (29, 2), (48, 3), (99, 9), (1999, 1),
])
def test_a_total_reduces_to_one_digit(total, expected):
    assert core.reduce_to_digit(total) == expected


# ---- name number ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("name,total,number,working", [
    # K=2 E=5 S=3 H=5 A=1 V=6
    ("Keshav", 22, 4, "2+5+3+5+1+6 = 22 -> 4"),
    # T=4 I=1 N=5 A=1
    ("Tina", 11, 2, "4+1+5+1 = 11 -> 2"),
    # A=1 M=4 I=1 T=4
    ("Amit", 10, 1, "1+4+1+4 = 10 -> 1"),
    # R=2 A=1 D=4 H=5 A=1
    ("Radha", 13, 4, "2+1+4+5+1 = 13 -> 4"),
])
def test_the_chaldean_name_number_is_what_it_adds_up_to(name, total, number, working):
    result = core.name_number(name)
    assert result["total"] == total, working
    assert result["number"] == number, working


def test_spaces_and_punctuation_are_ignored_but_the_letters_are_not():
    """"Keshav Prabhu" is the same letters as "KeshavPrabhu"."""
    assert core.name_number("Keshav Prabhu")["total"] == core.name_number("KeshavPrabhu")["total"]
    assert core.name_number("D'Souza")["total"] == core.name_number("DSouza")["total"]


def test_case_does_not_matter():
    assert core.name_number("keshav")["total"] == core.name_number("KESHAV")["total"] == 22


def test_a_name_with_no_latin_letters_is_unusable_rather_than_zero():
    """Devanagari has no Chaldean value - the table is for the Latin alphabet. Printing a 0 would be
    a wrong answer; saying it cannot be read is a true one."""
    result = core.name_number("केशव")
    assert result["usable"] is False
    assert result["number"] == 0


# ---- mulank and bhagyank -------------------------------------------------------------------------------


@pytest.mark.parametrize("day,expected,working", [
    (1, 1, "born on the 1st"),
    (9, 9, "born on the 9th"),
    (10, 1, "1+0 = 1"),
    (19, 1, "1+9 = 10 -> 1"),
    (29, 2, "2+9 = 11 -> 2"),
    (31, 4, "3+1 = 4"),
])
def test_mulank_is_the_day_reduced(day, expected, working):
    assert core.mulank(dt.date(1990, 1, day)) == expected, working


@pytest.mark.parametrize("date,expected,working", [
    ((1991, 4, 3), 9, "0+3+0+4+1+9+9+1 = 27 -> 9"),
    ((2000, 1, 1), 4, "0+1+0+1+2+0+0+0 = 4"),
    ((1987, 12, 25), 8, "2+5+1+2+1+9+8+7 = 35 -> 8"),
    ((1975, 6, 18), 1, "1+8+0+6+1+9+7+5 = 37 -> 10 -> 1"),
])
def test_bhagyank_is_the_whole_date_reduced(date, expected, working):
    assert core.bhagyank(dt.date(*date)) == expected, working


def test_mulank_and_bhagyank_are_different_questions():
    """One is the day, the other the whole date. A page that confused them would be wrong for
    everybody not born on a day that happens to match."""
    born = dt.date(1991, 4, 3)
    assert core.mulank(born) == 3 and core.bhagyank(born) == 9


# ---- the Lo Shu grid -----------------------------------------------------------------------------------


def test_the_square_is_the_one_every_source_uses():
    assert core.LO_SHU_ROWS == ((4, 9, 2), (3, 5, 7), (8, 1, 6))
    flat = [n for row in core.LO_SHU_ROWS for n in row]
    assert sorted(flat) == list(range(1, 10))
    for row in core.LO_SHU_ROWS:
        assert sum(row) == 15, row          # it is a magic square; every line sums to 15


def test_every_row_column_and_diagonal_sums_to_fifteen():
    rows = core.LO_SHU_ROWS
    for n in range(3):
        assert sum(rows[r][n] for r in range(3)) == 15
    assert rows[0][0] + rows[1][1] + rows[2][2] == 15
    assert rows[0][2] + rows[1][1] + rows[2][0] == 15


def test_the_grid_counts_the_dates_digits_plus_mulank_and_bhagyank():
    """3 April 1991: the non-zero digits are 3,4,1,9,9,1, and the convention adds mulank 3 and
    bhagyank 9 - so 1 appears twice, 3 twice, 4 once and 9 three times."""
    grid = core.lo_shu(dt.date(1991, 4, 3))
    assert grid["counts"] == {1: 2, 2: 0, 3: 2, 4: 1, 5: 0, 6: 0, 7: 0, 8: 0, 9: 3}
    assert grid["repeated"] == [1, 3, 9]
    assert grid["missing"] == [2, 5, 6, 7, 8]


def test_zeroes_are_not_placed():
    """There is no 0 cell in the grid, so the zeroes of a date simply have nowhere to go."""
    grid = core.lo_shu(dt.date(2000, 10, 10))
    assert 0 not in grid["digits"]


def test_the_convention_is_a_named_constant_the_page_can_state():
    """Schools differ on whether the mulank and bhagyank go in. The page says which this site uses,
    and this is the one place to change it."""
    assert core.LO_SHU_INCLUDES_MULANK_AND_BHAGYANK is True


def test_a_plane_is_complete_only_when_all_three_of_its_numbers_are_present():
    grid = core.lo_shu(dt.date(1991, 4, 3))
    # the mental row is 4,9,2 and this date has no 2
    assert grid["planes"]["mental"] is False
    # thought is 4,3,8 and this date has no 8
    assert grid["planes"]["thought"] is False


def test_all_eight_planes_are_reported():
    grid = core.lo_shu(dt.date(1991, 4, 3))
    assert set(grid["planes"]) == {"mental", "emotional", "practical", "thought", "will",
                                   "action", "golden", "silver"}


def test_the_profile_carries_everything_the_page_shows():
    p = core.profile("Keshav", dt.date(1991, 4, 3))
    assert p["mulank"] == 3 and p["bhagyank"] == 9
    assert p["name_number"]["number"] == 4
    assert p["lo_shu"]["repeated"] == [1, 3, 9]


def test_nothing_this_module_RETURNS_says_what_a_number_MEANS():
    """What a 7 is like belongs in the copy, where it is written once and reviewed. This module
    answers what the number IS - the same split app/engine keeps between a position and a reading.

    CHECKED ON THE OUTPUT, NOT THE SOURCE. The first version read the file as text and failed on the
    comment explaining why there is no "unlucky" level - which is the opposite of a violation. What
    matters is that no verdict reaches a reader, and a reader reads the returned values."""
    import datetime as _dt

    returned = core.profile("Keshav", _dt.date(1991, 4, 3))
    returned["check"] = core.check_number("98765 43210", mulank=3, bhagyank=9)

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from strings(item)

    for text in strings(returned):
        lowered = text.lower()
        for word in ("lucky", "unlucky", "bad", "dosh", "danger", "warn"):
            assert word not in lowered, (word, text)


# ---- how one number sits with another ------------------------------------------------------------------


def test_there_is_no_level_worse_than_neutral():
    """THE RULE THIS WHOLE FEATURE IS BUILT UNDER. A person cannot change their date of birth, and
    telling them their own number is unlucky is a charge they can do nothing about. The tradition's
    "enemy" pairs come back as NEUTRAL - honest about there being no special affinity, and silent
    about anybody's worth."""
    levels = {core.fit(a, b) for a in range(1, 10) for b in range(1, 10)}
    assert levels <= set(core.FIT_LEVELS)
    assert "bad" not in levels and "unlucky" not in levels
    assert core.FIT_LEVELS == ("strong", "good", "neutral")


def test_a_number_is_strongest_with_itself():
    for n in range(1, 10):
        assert core.fit(n, n) == "strong"


def test_the_friendships_come_from_the_planets():
    """1 and 9 are Sun and Mars, which the tradition reads as friends; 1 and 8 are Sun and Saturn,
    which it does not. That is why this table is not arbitrary."""
    assert core.RULERS[1] == "Sun" and core.RULERS[9] == "Mars" and core.RULERS[8] == "Saturn"
    assert core.fit(1, 9) == "good"
    assert core.fit(1, 8) == "neutral"


def test_every_number_one_to_nine_has_a_ruler_and_friends():
    assert set(core.RULERS) == set(range(1, 10))
    assert set(core.FRIENDS) == set(range(1, 10))
    for n, friends in core.FRIENDS.items():
        assert n in friends, f"{n} should be its own friend"
        assert all(1 <= f <= 9 for f in friends)


@pytest.mark.parametrize("value,digits,total,number,working", [
    ("+91 98765 43210", "919876543210", 55, 1, "9+1+9+8+7+6+5+4+3+2+1+0 = 55 -> 10 -> 1"),
    ("MH-12-AB-3456", "12" + "3456", 21, 3, "1+2+3+4+5+6 = 21 -> 3"),
    ("Flat 402", "402", 6, 6, "4+0+2 = 6"),
])
def test_a_number_is_read_from_its_digits_only(value, digits, total, number, working):
    """A phone number's spaces, plus sign and country code are not part of it in any school - and a
    reader pasting "+91 98765 43210" must get the same answer as one typing the ten digits."""
    result = core.check_number(value)
    assert result["digits"] == digits, working
    assert result["total"] == total and result["number"] == number, working


def test_punctuation_alone_is_unusable():
    assert core.check_number("---")["usable"] is False
    assert core.check_number("")["usable"] is False


def test_the_fit_is_reported_against_both_numbers_when_both_are_given():
    result = core.check_number("98765 43210", mulank=3, bhagyank=9)
    assert set(result["fits"]) == {"mulank", "bhagyank"}
    for entry in result["fits"].values():
        assert entry["level"] in core.FIT_LEVELS


def test_no_fit_is_reported_against_a_number_that_was_not_given():
    """A reader who has not entered their date of birth gets the number and nothing about fit,
    rather than a fit against a zero."""
    result = core.check_number("98765 43210")
    assert result["fits"] == {}
