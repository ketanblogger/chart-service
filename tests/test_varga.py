"""Navamsa (D9). The algorithm is checked three ways: against its own literal rule, against two
independently published charts, and by hand for the reference chart."""

import pytest

from app.engine.varga import (
    NAVAMSA_SPAN,
    _navamsa_sign_by_rule,
    navamsa_chart,
    navamsa_sign,
    sign_nature,
)
from tests.reference_charts import GANDHI, KALAM, NEHRU


@pytest.fixture(scope="module")
def reference():
    return KALAM.chart()


def test_shortcut_matches_the_literal_movable_fixed_dual_rule():
    """Every arc-minute of the zodiac: the one-line formula must equal the classical rule."""
    for minute in range(360 * 30):  # 10,800 points, one per 2 arc-minutes
        longitude = minute * 360 / (360 * 30)
        assert navamsa_sign(longitude) == _navamsa_sign_by_rule(longitude), longitude


def test_sign_natures():
    assert [sign_nature(i) for i in range(12)] == [
        "movable", "fixed", "dual", "movable", "fixed", "dual",
        "movable", "fixed", "dual", "movable", "fixed", "dual"]


def test_navamsa_starting_points():
    """Movable starts from the sign itself, fixed from the 9th, dual from the 5th."""
    assert navamsa_sign(0.0) == 0            # Mesha (movable) -> Mesha
    assert navamsa_sign(30.0) == 9           # Vrishabha (fixed) -> Makara, the 9th from it
    assert navamsa_sign(60.0) == 6           # Mithuna (dual) -> Tula, the 5th from it
    assert navamsa_sign(90.0) == 3           # Karka (movable) -> Karka
    # The published worked example: Surya at 15° Simha (fixed, so counting starts at Mesha) falls in
    # the 5th navamsa, 13°20'-16°40', and lands back in Simha.
    assert navamsa_sign(4 * 30 + 15) == 4


def test_vargottama_can_only_happen_at_one_navamsa_per_sign():
    """1st navamsa of a movable sign, 5th of a fixed sign, 9th of a dual sign - and nowhere else."""
    expected = {"movable": 1, "fixed": 5, "dual": 9}
    for sign0 in range(12):
        hits = [part + 1 for part in range(9)
                if navamsa_sign(sign0 * 30 + part * NAVAMSA_SPAN + 0.5) == sign0]
        assert hits == [expected[sign_nature(sign0)]], sign0


def test_published_navamsa_mahatma_gandhi():
    """External proof. Sithars Astrology publishes a whole D9 - rare, most sources only print the
    rashi chart - and this engine reproduces all nine grahas. That source's D9 ascendant is Makara
    against our Vrishchika; Gandhi's minute of birth is disputed and the ascendant is the only
    quantity sensitive to it, so only the grahas are asserted. See tests/reference_charts.py."""
    d9 = navamsa_chart(GANDHI.chart())["grahas"]
    assert {key: entry["sign"]["name"] for key, entry in d9.items()} == GANDHI.published["navamsa"]
    assert "Makara" in GANDHI.lagna_dispute


def test_the_rule_applied_by_hand_to_independently_published_degrees_jawaharlal_nehru():
    """A second, independent path to the same answer. AstroSage publishes Nehru's D1 sign and degree
    (rated "Accurate (A)"); applying the classical movable/fixed/dual rule to THOSE degrees by hand
    gives the signs below, and this engine's D9 agrees - so the division is verified against numbers
    this codebase did not produce. Worked longhand:

        Surya    Vrishchika  0°17'  fixed   -> count from Karka;   0.29/3°20' = 1st  -> Karka
        Chandra  Karka      18°05'  movable -> from Karka;        18.09/3°20' = 6th  -> Dhanu
        Mangal   Kanya       9°59'  dual    -> from Makara;        9.99/3°20' = 3rd  -> Meena
        Budha    Tula       17°10'  movable -> from Tula;         17.18/3°20' = 6th  -> Meena
        Guru     Dhanu      15°10'  dual    -> from Mesha;        15.18/3°20' = 5th  -> Simha
        Shukra   Tula        7°23'  movable -> from Tula;          7.39/3°20' = 3rd  -> Dhanu
        Shani    Simha      10°46'  fixed   -> from Mesha;        10.78/3°20' = 4th  -> Karka
    """
    chart = NEHRU.chart()
    for key, (sign, degree) in NEHRU.published.items():
        assert chart["grahas"][key]["sign"]["name"] == sign
        assert chart["grahas"][key]["degree"] == pytest.approx(degree, abs=0.07)

    d9 = navamsa_chart(chart)["grahas"]
    assert {key: d9[key]["sign"]["name"] for key in NEHRU.published} == {
        "Sun": "Karka", "Moon": "Dhanu", "Mars": "Meena", "Mercury": "Meena",
        "Jupiter": "Simha", "Venus": "Dhanu", "Saturn": "Karka",
    }


def test_reference_chart_navamsa_hand_worked(reference):
    """A. P. J. Abdul Kalam, 15 Oct 1931, 01:15 IST, Rameswaram - every position worked longhand
    from the engine's sidereal longitudes, so the whole D9 can be checked by eye:

        lagna    105°41' Karka      movable -> count from Karka;  15.69/3°20' = 5th -> Vrishchika
        Surya    177°35' Kanya      dual    -> from Makara;       27.59/3°20' = 9th -> Kanya (vargottama)
        Chandra  223°01' Vrishchika fixed   -> from Karka;        13.03/3°20' = 4th -> Tula
        Mangal   205°56' Tula       movable -> from Tula;         25.94/3°20' = 8th -> Vrishabha
        Budha    174°49' Kanya      dual    -> from Makara;       24.82/3°20' = 8th -> Simha
        Guru     115°07' Karka      movable -> from Karka;        25.13/3°20' = 8th -> Kumbha
        Shukra   187°18' Tula       movable -> from Tula;          7.30/3°20' = 3rd -> Dhanu
        Shani    264°10' Dhanu      dual    -> from Mesha;        24.18/3°20' = 8th -> Vrishchika
        Rahu     341°31' Meena      dual    -> from Karka;        11.52/3°20' = 4th -> Tula
        Ketu     161°31' Kanya      dual    -> from Makara;       11.52/3°20' = 4th -> Mesha

    Surya is vargottama: Kanya in the rashi chart and Kanya again in the navamsa, which can only
    happen in the 9th navamsa of a dual sign.
    """
    d9 = navamsa_chart(reference)
    assert d9["lagna"]["sign"]["name"] == "Vrishchika"
    assert {key: g["sign"]["name"] for key, g in d9["grahas"].items()} == {
        "Sun": "Kanya", "Moon": "Tula", "Mars": "Vrishabha", "Mercury": "Simha",
        "Jupiter": "Kumbha", "Venus": "Dhanu", "Saturn": "Vrishchika",
        "Rahu": "Tula", "Ketu": "Mesha",
    }
    # Houses counted from the navamsa lagna (Vrishchika = 8), never from the D1 lagna.
    assert {key: g["house"] for key, g in d9["grahas"].items()} == {
        "Sun": 11, "Moon": 12, "Mars": 7, "Mercury": 10, "Jupiter": 4,
        "Venus": 2, "Saturn": 1, "Rahu": 12, "Ketu": 6,
    }
    assert d9["vargottama"] == ["Sun"]
    assert d9["grahas"]["Sun"]["navamsa"] == 9
    assert d9["grahas"]["Sun"]["d1_sign_nature"] == "dual"
    assert d9["lagna_vargottama"] is False
    assert all(g["house"] == g["house_from_navamsa_lagna"] for g in d9["grahas"].values())


def test_navamsa_houses_table_is_complete(reference):
    d9 = navamsa_chart(reference)
    assert [h["house"] for h in d9["houses"]] == list(range(1, 13))
    assert d9["houses"][0]["sign"]["name"] == d9["lagna"]["sign"]["name"]
    placed = sorted(key for house in d9["houses"] for key in house["grahas"])
    assert placed == sorted(d9["grahas"])


def test_navamsa_is_json_serialisable(reference):
    import json
    json.dumps(navamsa_chart(reference))
