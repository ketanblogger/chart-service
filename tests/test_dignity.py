"""Combustion orbs and dignity labels."""

import pytest

from app.engine.dignity import (
    COMBUSTION_ORBS,
    EXALTATION,
    MOOLATRIKONA,
    OWN_SIGNS,
    combustion,
    dignity,
    graha_dignities,
    natural_friendship,
    separation,
)
from tests import synthetic
from tests.reference_charts import KALAM


@pytest.fixture(scope="module")
def reference():
    return KALAM.chart()


# --- combustion ------------------------------------------------------------------------------

def test_separation_wraps_around_zero():
    assert separation(1.0, 359.0) == pytest.approx(2.0)
    assert separation(359.0, 1.0) == pytest.approx(2.0)
    assert separation(0.0, 180.0) == pytest.approx(180.0)


@pytest.mark.parametrize("graha,orb", [("Moon", 12.0), ("Mars", 17.0), ("Mercury", 14.0),
                                       ("Jupiter", 11.0), ("Venus", 10.0), ("Saturn", 15.0)])
def test_combustion_orb_boundary_is_exact(graha, orb):
    """Inside the orb is combust, exactly on it is not."""
    assert combustion(graha, 100.0 + orb - 0.01, 100.0, False)["combust"] is True
    assert combustion(graha, 100.0 + orb, 100.0, False)["combust"] is False
    assert combustion(graha, 100.0 - orb + 0.01, 100.0, False)["combust"] is True


def test_retrograde_orbs_are_narrower_only_for_mercury_and_venus():
    narrower = {g for g, (direct, retro) in COMBUSTION_ORBS.items() if retro != direct}
    assert narrower == {"Mercury", "Venus"}
    assert combustion("Mercury", 113.0, 100.0, True)["combust"] is False   # 13° > 12° retro orb
    assert combustion("Mercury", 113.0, 100.0, False)["combust"] is True   # 13° < 14° direct orb
    assert combustion("Mercury", 113.0, 100.0, True)["retrograde_orb_used"] is True
    assert combustion("Mars", 113.0, 100.0, True)["retrograde_orb_used"] is False


def test_the_sun_and_the_nodes_are_never_combust():
    for graha in ("Sun", "Rahu", "Ketu"):
        result = combustion(graha, 100.5, 100.0, False)
        assert result["applicable"] is False
        assert result["combust"] is None
    assert combustion("Sun", 100.0, 100.0, False)["separation_degrees"] is None
    assert combustion("Rahu", 100.5, 100.0, False)["separation_degrees"] == pytest.approx(0.5)


def test_deep_combustion_is_within_one_degree():
    assert combustion("Venus", 100.5, 100.0, False)["deeply_combust"] is True
    assert combustion("Venus", 101.5, 100.0, False)["deeply_combust"] is False
    assert combustion("Venus", 101.5, 100.0, False)["combust"] is True


# --- dignity ---------------------------------------------------------------------------------

def test_debilitation_is_the_seventh_sign_from_exaltation():
    for graha, (exalt_sign, degree) in EXALTATION.items():
        debilitation = (exalt_sign + 5) % 12 + 1
        assert dignity(graha, exalt_sign, degree)["label"] == "exalted"
        assert dignity(graha, debilitation, degree)["label"] == "debilitated"
        assert dignity(graha, debilitation, degree)["exact_exaltation_degrees_away"] == 0


def test_moolatrikona_wins_inside_an_exaltation_or_own_sign():
    """Chandra's and Budha's moolatrikona arcs sit inside their exaltation sign - see dignity.py."""
    assert dignity("Moon", 2, 1.0)["label"] == "exalted"        # Vrishabha 0°-4°
    assert dignity("Moon", 2, 4.0)["label"] == "moolatrikona"   # Vrishabha 4°-30°
    assert dignity("Mercury", 6, 15.0)["label"] == "exalted"    # Kanya, below the arc
    assert dignity("Mercury", 6, 16.0)["label"] == "moolatrikona"
    assert dignity("Mercury", 6, 20.0)["label"] == "exalted"    # past the arc, still Kanya
    assert dignity("Sun", 5, 19.9)["label"] == "moolatrikona"
    assert dignity("Sun", 5, 20.0)["label"] == "own_sign"


def test_own_signs_and_friendship_labels():
    for graha, signs in OWN_SIGNS.items():
        for sign in signs:
            label = dignity(graha, sign, 25.0)["label"]
            assert label in ("own_sign", "moolatrikona", "exalted"), (graha, sign, label)
    assert dignity("Sun", 10, 5.0)["label"] == "enemy_sign"      # Makara, Shani's sign
    assert dignity("Sun", 4, 5.0)["label"] == "friendly_sign"    # Karka, Chandra's sign
    assert dignity("Sun", 3, 5.0)["label"] == "neutral_sign"     # Mithuna, Budha's sign


def test_natural_friendship_is_not_symmetric_and_skips_the_nodes():
    assert natural_friendship("Sun", "Venus") == "enemy"
    assert natural_friendship("Venus", "Sun") == "enemy"
    assert natural_friendship("Moon", "Mercury") == "friend"
    assert natural_friendship("Mercury", "Moon") == "enemy"  # the classic asymmetry
    assert natural_friendship("Rahu", "Sun") == "unrated"
    assert natural_friendship("Sun", "Sun") == "unrated"


def test_the_nodes_get_no_dignity_label():
    for node in ("Rahu", "Ketu"):
        result = dignity(node, 2, 10.0)
        assert result["label"] is None
        assert result["score"] == 0
        assert "disputed" in result["reason"]
        assert result["dispositor"] == "Venus"  # Vrishabha's lord, which IS asserted


def test_moolatrikona_arcs_are_inside_their_signs():
    for graha, (sign, low, high) in MOOLATRIKONA.items():
        assert 0 <= low < high <= 30
        assert sign in OWN_SIGNS[graha] or sign == EXALTATION[graha][0]


# --- on charts --------------------------------------------------------------------------------

def test_reference_chart_dignities(reference):
    """A. P. J. Abdul Kalam. Two of these are externally corroborated: the published analysis of this
    chart states that Chandra is debilitated and that Budha and Guru are both exalted."""
    table = graha_dignities(reference)
    assert {key: entry["dignity"]["label"] for key, entry in table.items()} == {
        "Sun": "neutral_sign",      # Kanya, Budha's sign, and Budha is neutral to Surya
        "Moon": "debilitated",      # Vrishchika - as the published analysis says
        "Mars": "neutral_sign",     # Tula, Shukra's sign
        "Mercury": "exalted",       # Kanya - as the published analysis says
        "Jupiter": "exalted",       # Karka - as the published analysis says
        "Venus": "moolatrikona",    # Tula at 7°18', inside the 0°-15° arc
        "Saturn": "neutral_sign",   # Dhanu, Guru's sign
        "Rahu": None,
        "Ketu": None,
    }
    assert table["Venus"]["degree"] == pytest.approx(7.305, abs=0.01)
    # Budha is 2°46' from Surya (orb 14°) and Shukra 9°43' (orb 10°) - both burnt, Shukra only just.
    assert [key for key, e in table.items() if e["combustion"]["combust"]] == ["Mercury", "Venus"]
    assert table["Mercury"]["combustion"]["separation_degrees"] == pytest.approx(2.775, abs=0.01)
    assert table["Venus"]["combustion"]["separation_degrees"] == pytest.approx(9.711, abs=0.01)
    assert table["Venus"]["combustion"]["orb_degrees"] == 10.0
    assert table["Mars"]["rules_houses"] == [5, 10]   # Karka lagna: Vrishchika and Mesha
    assert table["Jupiter"]["rules_houses"] == [6, 9]  # Dhanu and Meena - as the analysis says
    assert table["Rahu"]["rules_houses"] == []
    assert table["Mercury"]["natural_class"]["class"] == "variable"


def test_a_moolatrikona_venus_is_not_reported_as_merely_own_sign(reference):
    """Shukra at Tula 7°18' is inside the 0°-15° moolatrikona arc; at 15° or beyond it would be
    plain own_sign. The arc boundary is what the Malavya yoga in this chart turns on."""
    entry = graha_dignities(reference)["Venus"]
    assert entry["dignity"]["label"] == "moolatrikona"
    assert "moolatrikona arc Tula 0°-15°" in entry["dignity"]["reason"]


def test_moon_is_benefic_only_while_it_is_bright():
    def moon_class(sun, moon):
        return graha_dignities(synthetic.chart(5, {"Sun": sun, "Moon": moon}))["Moon"]["natural_class"]["class"]

    assert moon_class((1, 10.0), (1, 20.0)) == "malefic"    # 10° ahead - new moon, dark
    assert moon_class((1, 10.0), (2, 20.0)) == "benefic"    # 40° ahead - past the 3rd tithi
    assert moon_class((1, 10.0), (7, 10.0)) == "benefic"    # 180° ahead - full moon
    assert moon_class((1, 10.0), (8, 20.0)) == "malefic"    # 220° ahead - waning past the 3rd tithi
    # Directed, not shortest distance: 40° ahead is bright, 40° behind is dark.
    assert moon_class((2, 20.0), (1, 10.0)) == "malefic"


def test_dignities_are_json_serialisable(reference):
    import json
    json.dumps(graha_dignities(reference))
