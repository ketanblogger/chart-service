"""The eclipses of a year, computed from Swiss Ephemeris rather than typed from a table.

EVERY ASSERTION BELOW IS A BUG THIS FILE FOUND. The first version of the module reported all five
eclipses of 2027 as invisible from India - including one at 21:33 IST with the Moon thirty degrees
above the horizon, and the total solar eclipse of 2 August, which is a partial across the whole
country. It would have shipped on a grahan page as a plain statement of fact.

Three separate mistakes produced that, and each one has a test here:
  - the argument order is (jd, geopos, flags), not (jd, flags, geopos) as in several neighbouring
    Swiss Ephemeris calls. It raised a TypeError that a bare `except` turned into "no".
  - the magnitude at the instant of GREATEST ECLIPSE is zero for a place that sees a partial phase an
    hour earlier. The local search is what answers "can I see it from here".
  - `attributes[0]` is the UMBRAL magnitude, which is zero for a penumbral lunar eclipse.

Invented people only; `tests/` is published.
"""

import datetime as dt

import pytest

from app.engine import eclipses as ec


@pytest.fixture(scope="module")
def year_2027():
    return ec.eclipses(2027)


def test_the_year_has_the_eclipses_it_actually_has(year_2027):
    """Five in 2027: two solar, three lunar. A year has between four and seven, and a count outside
    that means the search loop is wrong rather than the sky being unusual."""
    assert len(year_2027) == 5
    assert [e["what"] for e in year_2027].count("solar") == 2
    assert [e["what"] for e in year_2027].count("lunar") == 3


def test_they_are_in_time_order_and_inside_the_year(year_2027):
    dates = [e["date"] for e in year_2027]
    assert dates == sorted(dates)
    assert all(date.startswith("2027") for date in dates)


def test_the_august_total_solar_eclipse_is_visible_from_india(year_2027):
    """THE ONE THAT WOULD HAVE BEEN WRONG ON THE PAGE. 2 August 2027 is total over Egypt and a
    partial across India - 0.43 at Dwarka, 0.30 at Ujjain, 0.17 at Delhi. Reading the magnitude at
    the instant of greatest eclipse gave zero, because India's partial phase is at a different time."""
    august = next(e for e in year_2027 if e["date"] == "2027-08-02")
    assert august["what"] == "solar" and august["kind"] == "total"
    assert august["visible_in_india"] is True
    assert august["india_magnitude"] > 0.2
    assert august["india_time_ist"], "a visible eclipse must say when to look"


def test_an_eclipse_india_cannot_see_says_so(year_2027):
    """The annular eclipse of 6 February 2027 is over the southern hemisphere."""
    february = next(e for e in year_2027 if e["date"] == "2027-02-06")
    assert february["visible_in_india"] is False
    assert february["india_magnitude"] == 0.0
    assert february["india_time_ist"] == ""


def test_a_penumbral_lunar_eclipse_with_the_moon_up_is_reported_as_visible(year_2027):
    """`attributes[0]` is the UMBRAL magnitude and is zero for a penumbral eclipse, so reading only
    that said these were invisible while the Moon was 30 degrees up at Ujjain."""
    february = next(e for e in year_2027 if e["date"] == "2027-02-21")
    assert february["kind"] == "penumbral" and february["what"] == "lunar"
    assert february["visible_in_india"] is True
    assert february["india_magnitude"] > 0.9


def test_a_penumbral_eclipse_is_not_called_a_grahan(year_2027):
    """A STATEMENT ABOUT PRACTICE, NOT ABOUT THE SKY. The Moon passes through the outer shadow and
    dims very slightly; most people looking up would see an ordinary full Moon, and the tradition
    does not observe sutak for one. The event is reported because it is real and overhead, and this
    flag says whether it is the thing somebody searching for "grahan" means."""
    for one in year_2027:
        if one["what"] == "lunar" and one["kind"] == "penumbral":
            assert one["observed_as_grahan"] is False, one["date"]
    august = next(e for e in year_2027 if e["date"] == "2027-08-02")
    assert august["observed_as_grahan"] is True


def test_a_lunar_eclipse_below_the_horizon_is_not_visible(year_2027):
    """17 August 2027 peaks at 12:43 IST, with the Moon under India."""
    august = next(e for e in year_2027 if e["date"] == "2027-08-17")
    assert august["visible_in_india"] is False


def test_each_eclipse_names_the_sign_and_nakshatra_it_falls_in(year_2027):
    for one in year_2027:
        assert 1 <= one["sign"]["index"] <= 12
        assert 1 <= one["nakshatra"]["index"] <= 27
        assert one["sign"]["devanagari"] and one["nakshatra"]["name"]
        assert 0 <= one["longitude"] < 360


def test_the_house_is_counted_from_the_readers_rashi():
    """The eclipse is the same sky for everybody; the house is the part that differs."""
    from_mesha = ec.for_rashi(2027, 1)
    from_tula = ec.for_rashi(2027, 7)
    assert len(from_mesha) == len(from_tula) == 5
    for one, other in zip(from_mesha, from_tula):
        assert one["date"] == other["date"]
        assert 1 <= one["house"] <= 12
        assert (one["house"] - other["house"]) % 12 == 6, "Tula is six signs from Mesha"


def test_the_swiss_ephemeris_argument_order_is_the_one_this_module_uses():
    """THE SIGNATURE TRAP. `sol_eclipse_how(jd, geopos, flags)` - not (jd, flags, geopos), which is
    what `calc_ut` and several neighbours take. The wrong order raises TypeError, and this module no
    longer wraps the call in a bare except, so it would fail loudly rather than answer "no"."""
    import swisseph as swe

    from app.engine.core import julian_day

    jd = julian_day(dt.datetime(2027, 8, 2, 10, 6, tzinfo=dt.timezone.utc))
    attributes = swe.sol_eclipse_how(jd, list(ec.UJJAIN), swe.FLG_SWIEPH)[1]
    assert attributes[0] >= 0
    with pytest.raises(TypeError):
        swe.sol_eclipse_how(jd, swe.FLG_SWIEPH, list(ec.UJJAIN))


def test_nothing_here_says_what_an_eclipse_MEANS():
    """The module returns dates, a sign, a nakshatra and a visibility. "An eclipse in your sign
    brings..." is the exact sentence app/blog/safety.py refuses, and it is not written here."""
    from app.blog import safety

    for one in ec.eclipses(2027):
        text = " ".join(str(value) for value in one.values() if isinstance(value, str))
        assert not safety.blocking_terms(text), (one["date"], text)


def test_a_year_is_computed_once(year_2027):
    assert ec.eclipses(2027) is year_2027, "the sky is the same for every reader"


# ---- what the copy is allowed to say ------------------------------------------------------------------


def test_the_august_eclipse_has_times_for_several_cities(year_2027):
    """"16:37 IST at Ujjain" answers the question for nobody. The partial is 0.43 at one end of the
    country and 0.17 at the other, starting and ending at different clock times."""
    august = next(e for e in year_2027 if e["date"] == "2027-08-02")
    cities = august["cities"]
    assert len(cities) >= 5
    for city in cities:
        assert city["starts"] and city["maximum"] and city["ends"], city
        assert city["starts"] < city["maximum"] < city["ends"], city
        assert city["magnitude"] > 0
    assert len({c["magnitude"] for c in cities}) > 1, "the magnitude must differ across the country"


def test_an_eclipse_that_is_not_a_grahan_here_lists_no_cities(year_2027):
    """A list of six cities all saying "nothing to see" is noise on a page about an eclipse that is
    not happening here."""
    for one in year_2027:
        if not (one["visible_in_india"] and one["observed_as_grahan"]):
            assert one["cities"] == (), one["date"]


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_kind_is_named_in_every_tree(lang):
    """उपछाया चंद्र ग्रहण is what people search for; a year's list that quietly omits three of its five
    eclipses is one a reader cannot check anywhere else."""
    for one in ec.eclipses(2027):
        assert ec.KIND_NAMES[lang][one["kind"]], (lang, one["kind"])
    assert ec.PENUMBRAL_NOTE[lang]


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_penumbral_note_says_what_it_is_and_that_sutak_is_not_observed(lang):
    """The honest sentence is also the one that stops somebody worrying."""
    note = ec.PENUMBRAL_NOTE[lang]
    # Lower-cased: the English sentence opens with "Sutak", and the two Devanagari trees spell the
    # word with different vowel lengths - सूतक in Hindi, सुतक in Marathi - which is correct in each.
    assert any(word in note.lower() for word in ("sutak", "सूतक", "सुतक")), note
    from app.blog import safety

    # THE LANGUAGE HAS TO BE PASSED. blocking_terms defaults to English, and the English language
    # check on a Devanagari sentence reports "not in English" - so this assertion failed on the two
    # notes that were perfectly fine, for the same reason the blog's own checker blocked every Hindi
    # post until two days ago.
    assert not safety.blocking_terms(note, lang=lang), note
