"""The `accuracy` block: how much to trust a chart, given the place and the clock behind it.

Both caveats have to be TRUE, not merely cautious. A warning on a chart where the birthplace could
not have changed anything is noise that teaches people to skip the one that matters, so the tests
below pin the silence as firmly as the warning.
"""

import json
from datetime import date, time, timedelta

import pytest

from app.engine import compute_chart, find_city
from app.engine.accuracy import PLACE_UNCERTAINTY_KM, lagna_boundary
from app.engine.core import julian_day, to_utc
from tests.reference_charts import CHARTS, GANDHI, KALAM, NEHRU, VIVEKANANDA

MUMBAI = find_city("Mumbai")


def chart_at(when: date, at: time, city=MUMBAI):
    return compute_chart(when, at, city["lat"], city["lon"], city["tz"])


# --- shape ---------------------------------------------------------------------------------------

def test_every_chart_carries_accuracy_including_the_free_pages():
    """It is on the BASIC chart, not behind detail=full: the free kundali page shows a lagna and so
    needs the caveat as much as the paid book does."""
    chart = KALAM.chart()
    assert set(chart["accuracy"]) == {"lagna_boundary", "clock"}
    assert set(chart["accuracy"]["lagna_boundary"]) == {
        "degrees_into_sign", "arcminutes_to_boundary", "nearer_boundary", "adjacent_sign",
        "km_to_change_sign", "threshold_km", "sensitive", "basis"}
    assert set(chart["accuracy"]["clock"]) == {
        "timezone", "timezone_kind", "offset", "offset_seconds", "zone_offset_today",
        "differs_from_zone_today", "non_standard", "era", "era_label", "basis"}


def test_accuracy_is_json_serialisable_and_deterministic():
    one = json.dumps(KALAM.chart()["accuracy"], sort_keys=True)
    assert one == json.dumps(compute_chart(*KALAM.args)["accuracy"], sort_keys=True)


# --- the place caveat ------------------------------------------------------------------------------

@pytest.mark.parametrize("reference", CHARTS, ids=lambda r: r.key)
def test_arcminutes_to_boundary_is_the_distance_to_the_nearer_cusp(reference):
    chart = reference.chart()
    boundary = chart["accuracy"]["lagna_boundary"]
    degree = chart["lagna"]["degree"]
    assert boundary["degrees_into_sign"] == pytest.approx(degree, abs=1e-5)
    assert boundary["arcminutes_to_boundary"] == pytest.approx(min(degree, 30 - degree) * 60, abs=0.02)
    assert boundary["nearer_boundary"] == ("next" if 30 - degree <= degree else "previous")


@pytest.mark.parametrize("reference", CHARTS, ids=lambda r: r.key)
def test_the_adjacent_sign_is_the_one_the_lagna_would_become(reference):
    chart = reference.chart()
    boundary = chart["accuracy"]["lagna_boundary"]
    here = chart["lagna"]["sign"]["index"]
    step = 1 if boundary["nearer_boundary"] == "next" else -1
    assert boundary["adjacent_sign"]["index"] == (here - 1 + step) % 12 + 1


@pytest.mark.parametrize("when,at", [
    (date(1990, 6, 1), time(0, 7)),     # nearer cusp is the PREVIOUS sign - move west
    (date(1990, 6, 1), time(3, 16)),    # nearer cusp is the NEXT sign - move east
    (date(1975, 3, 20), time(14, 30)),  # far from any cusp: 741 km
])
def test_the_distance_actually_predicts_where_the_sign_changes(when, at):
    """The number has to mean something, so: move the birthplace that far in the direction of the
    nearer cusp and the rising sign changes; move half that far and it does not.

    This is what makes the figure measured rather than a rule of thumb. The ascendant's rate of
    change varies with latitude and with which sign is rising - 0.87 to 1.0 degrees per degree of
    longitude across the reference charts - so a fixed conversion would be wrong by a sixth on some
    charts and would point the wrong way on half of them.
    """
    import math
    chart = chart_at(when, at)
    boundary = chart["accuracy"]["lagna_boundary"]
    here = chart["lagna"]["sign"]["name"]
    step = 1 if boundary["nearer_boundary"] == "next" else -1   # east advances the ascendant
    km_per_degree = 111.32 * math.cos(math.radians(MUMBAI["lat"]))

    def sign_after(factor):
        east = step * boundary["km_to_change_sign"] * factor / km_per_degree
        return compute_chart(when, at, MUMBAI["lat"], MUMBAI["lon"] + east, MUMBAI["tz"])["lagna"]["sign"]["name"]

    assert sign_after(0.5) == here, "half the distance must not be enough"
    assert sign_after(1.3) == boundary["adjacent_sign"]["name"], "and it must land in the named sign"


def test_a_chart_far_from_a_cusp_says_nothing():
    """The silence is the feature. Kalam's lagna is 15.7 degrees into Karka - the birthplace would
    have to be most of the way across India for the rising sign to change."""
    boundary = KALAM.chart()["accuracy"]["lagna_boundary"]
    assert boundary["sensitive"] is False
    assert boundary["km_to_change_sign"] > 1000


def test_the_warning_fires_when_it_should_and_says_how_far():
    """00:07 on 1 June 1990 in Mumbai: the lagna is 20 arc-minutes from the Kumbha/Makara cusp, so a
    birthplace under 30 km away would have given a different rising sign - well inside the distance
    a visitor's real birthplace might sit from the city they picked."""
    boundary = chart_at(date(1990, 6, 1), time(0, 7))["accuracy"]["lagna_boundary"]
    assert boundary["sensitive"] is True
    assert boundary["km_to_change_sign"] < 40
    assert boundary["adjacent_sign"]["name"] == "Makara"


def test_it_stays_silent_on_the_overwhelming_majority_of_charts():
    """The property the caveat lives or dies by. Swept across a day of births, the warning should
    fire on a few per cent - if it fired on a third of charts nobody would read it."""
    fired = sum(chart_at(date(1990, 6, 1), time(m // 60, m % 60))["accuracy"]["lagna_boundary"]["sensitive"]
                for m in range(0, 60 * 24, 7))
    total = len(range(0, 60 * 24, 7))
    assert 0.02 < fired / total < 0.12, f"fired on {fired}/{total}"


def test_the_threshold_is_the_documented_one_and_is_reported():
    boundary = KALAM.chart()["accuracy"]["lagna_boundary"]
    assert boundary["threshold_km"] == PLACE_UNCERTAINTY_KM == 100.0
    assert "city" in boundary["basis"]


def test_sensitive_is_exactly_the_threshold_comparison():
    for minutes in range(0, 60 * 6, 11):
        boundary = chart_at(date(1990, 6, 1), time(minutes // 60, minutes % 60))["accuracy"]["lagna_boundary"]
        assert boundary["sensitive"] is (boundary["km_to_change_sign"] <= boundary["threshold_km"])


def test_the_threshold_is_configurable_without_touching_the_measurement():
    chart = chart_at(date(1990, 6, 1), time(0, 7))
    jd = julian_day(to_utc(date(1990, 6, 1), time(0, 7), MUMBAI["tz"]))
    tight = lagna_boundary(jd, MUMBAI["lat"], MUMBAI["lon"], chart["lagna"]["longitude"], threshold_km=1)
    assert tight["km_to_change_sign"] == chart["accuracy"]["lagna_boundary"]["km_to_change_sign"]
    assert tight["sensitive"] is False   # same measurement, stricter threshold


# --- the clock caveat -------------------------------------------------------------------------------

@pytest.mark.parametrize("when,offset,era,flagged", [
    (date(1889, 11, 14), "+05:21:10", "madras_time", True),
    (date(1944, 6, 1), "+06:30:00", "wartime", True),
    (date(1943, 1, 15), "+06:30:00", "wartime", True),
    (date(1990, 6, 1), "+05:30:00", "ist", False),
    (date(2026, 6, 1), "+05:30:00", "ist", False),
])
def test_the_clock_block_names_the_era_a_birth_was_recorded_on(when, offset, era, flagged):
    """This is the path a real visitor takes: they pick a city, the city carries a zone name, and
    zoneinfo resolves the era. The wartime rows are the ones with living customers."""
    clock = chart_at(when, time(9, 0))["accuracy"]["clock"]
    assert clock["offset"] == offset
    assert clock["era"] == era
    assert clock["non_standard"] is flagged
    assert clock["differs_from_zone_today"] is flagged
    assert clock["timezone_kind"] == "zone"
    assert clock["zone_offset_today"] == "+05:30:00"
    if flagged:
        assert clock["era_label"]


def test_a_pre_1870_birth_outside_bengal_is_flagged_through_its_explicit_offset():
    """Gandhi's chart is stored at +04:38 - Porbandar's own local mean time - because before 1870
    the zone name is Calcutta's LMT and would be 75 minutes wrong there. A fixed offset carries no
    history of its own, so the flag falls back to "is this India's current offset?", which it is
    not."""
    clock = GANDHI.chart()["accuracy"]["clock"]
    assert clock["timezone_kind"] == "fixed_offset"
    assert clock["offset"] == "+04:38:00"
    assert clock["differs_from_zone_today"] is None   # unknowable for a fixed offset
    assert clock["non_standard"] is True
    assert clock["era"] is None   # not one of the four recognised Indian offsets, and we do not guess


def test_an_unrecognised_offset_gets_no_era_rather_than_a_guess():
    clock = VIVEKANANDA.chart()["accuracy"]["clock"]
    assert clock["offset"] == "+05:53:00"   # the published value; zoneinfo's Calcutta LMT is 05:53:20
    assert clock["non_standard"] is True
    assert clock["era"] is None


def test_an_ordinary_modern_birth_is_not_flagged_at_all():
    accuracy = chart_at(date(1990, 6, 1), time(9, 0))["accuracy"]
    assert accuracy["clock"]["non_standard"] is False
    assert accuracy["lagna_boundary"]["sensitive"] is False


def test_the_reference_pinned_to_the_sources_convention_is_not_mistaken_for_history():
    """NEHRU stores +05:30 to match its publisher's (anachronistic) convention, so it reports as
    ordinary IST. A visitor entering the same birth through a city gets the historical offset and
    IS flagged - which is the honest difference between a fixture and a user's chart."""
    assert NEHRU.chart()["accuracy"]["clock"]["non_standard"] is False
    as_a_visitor = chart_at(NEHRU.born, NEHRU.at, find_city("Allahabad"))
    assert as_a_visitor["accuracy"]["clock"]["non_standard"] is True
    assert as_a_visitor["accuracy"]["clock"]["era"] == "madras_time"


def test_offset_seconds_agrees_with_the_printed_offset():
    for reference in (*CHARTS, GANDHI):
        clock = reference.chart()["accuracy"]["clock"]
        hours, minutes, seconds = (int(part) for part in clock["offset"].lstrip("+-").split(":"))
        signed = (1 if clock["offset"][0] == "+" else -1) * (hours * 3600 + minutes * 60 + seconds)
        assert clock["offset_seconds"] == signed
        assert timedelta(seconds=clock["offset_seconds"])
