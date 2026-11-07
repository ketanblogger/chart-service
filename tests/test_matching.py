from datetime import date, time

import pytest

from app.engine import ashtakoota, compute_chart, match_charts
from app.engine.constants import NAKSHATRA_SPAN
from app.engine.matching import _YONI_POINTS, MAX_POINTS
from tests.reference_charts import INDIRA, MATCH_PAIR, MATCH_PAIR_LOW

# One Moon longitude per nakshatra pada: covers every nakshatra/sign combination.
PADAS = [(i + 0.5) * NAKSHATRA_SPAN / 4 for i in range(108)]
SYMMETRIC_KOOTAS = ("tara", "yoni", "graha_maitri", "bhakoot", "nadi")


def _scores(result):
    return {k["koota"]: k["score"] for k in result["kootas"]}


def test_max_points_add_up_to_36():
    assert sum(MAX_POINTS.values()) == 36
    assert list(MAX_POINTS) == ["varna", "vashya", "tara", "yoni", "graha_maitri", "gana", "bhakoot", "nadi"]


def test_yoni_table_is_symmetric_with_full_marks_on_the_diagonal():
    for i, row in enumerate(_YONI_POINTS):
        assert row[i] == 4
        assert row == [_YONI_POINTS[j][i] for j in range(14)]


def test_every_combination_scores_within_bounds():
    for boy in PADAS:
        for girl in PADAS:
            result = ashtakoota(boy, girl)
            for koota in result["kootas"]:
                assert 0 <= koota["score"] <= koota["max"]
            assert result["total"] == sum(_scores(result).values())
            assert 0 <= result["total"] <= 36
            assert result["percentage"] == round(result["total"] / 36 * 100, 1)


def test_symmetric_kootas_do_not_depend_on_who_is_boy_or_girl():
    for boy in PADAS[::5]:
        for girl in PADAS[::7]:
            forward, backward = _scores(ashtakoota(boy, girl)), _scores(ashtakoota(girl, boy))
            for koota in SYMMETRIC_KOOTAS:
                assert forward[koota] == backward[koota]


def test_identical_moons_lose_only_nadi():
    for longitude in PADAS:
        result = ashtakoota(longitude, longitude)
        assert _scores(result) == {**MAX_POINTS, "nadi": 0}
        assert result["total"] == 28
        assert result["doshas"]["nadi_dosha"] == {"present": True, "cancellation_applies": False}


def test_a_perfect_score_exists():
    assert max(ashtakoota(boy, girl)["total"] for boy in PADAS for girl in PADAS) == 36


def test_known_pair():
    # Boy: Moon in Purvashadha/Dhanu. Girl: Moon in Rohini/Vrishabha (45°).
    result = ashtakoota(262.59, 45.0)
    scores = _scores(result)
    assert (result["boy"]["gana"], result["girl"]["gana"]) == ("Manushya", "Manushya")
    assert (result["boy"]["yoni"], result["girl"]["yoni"]) == ("Monkey", "Serpent")
    assert (result["boy"]["nadi"], result["girl"]["nadi"]) == ("Madhya", "Antya")
    assert scores["varna"] == 1  # Kshatriya groom, Vaishya bride
    assert scores["gana"] == 6
    assert scores["yoni"] == 2
    assert scores["nadi"] == 8
    assert scores["bhakoot"] == 0  # Vrishabha is 6th from Dhanu: shadashtaka
    assert scores["graha_maitri"] == 0.5  # Jupiter sees Venus as enemy, Venus sees Jupiter as neutral
    assert result["doshas"]["bhakoot_dosha"]["sign_distance"] == [6, 8]


def test_the_published_pair_scores_what_its_two_published_nakshatras_imply():
    """Guna milan on two charts whose Moon nakshatras AND padas are both independently published.

    WHAT IS EXTERNAL AND WHAT IS DERIVED. The external half is the two inputs: Hasta pada 3 for one
    chart and Uttarashadha pada 3 for the other, each printed by its own source (see
    tests/reference_charts.py). The 36 points are a deterministic consequence of those two verified
    inputs - derived, not invented, and not a self-confirming pin, which is the whole reason the
    pair is built from published charts rather than from two arbitrary births.

    The two people were NOT a couple and none is implied; guna milan is a function of two charts,
    and this pairing was chosen for what it exercises: a mid-range total, a koota scoring zero, a
    dosha present, and mangal dosha on both sides.
    """
    boy_ref, girl_ref = MATCH_PAIR
    boy, girl = boy_ref.chart(), girl_ref.chart()

    # the external half, asserted first and on its own
    assert boy["janma_nakshatra"]["name"] == boy_ref.published["janma_nakshatra"]
    assert boy["janma_nakshatra"]["pada"] == boy_ref.published["janma_pada"]
    assert girl["janma_nakshatra"]["name"] == girl_ref.published["Moon"][2]
    assert girl["janma_nakshatra"]["pada"] == girl_ref.published["Moon"][3]

    # the derived half
    result = match_charts(boy, girl)
    assert result["total"] == 25.0
    assert result["max_total"] == 36
    assert result["verdict"] == "good"
    assert {k["koota"]: k["score"] for k in result["kootas"]} == {
        "varna": 1, "vashya": 1, "tara": 3.0, "yoni": 2,
        "graha_maitri": 4, "gana": 6, "bhakoot": 0, "nadi": 8,
    }
    assert result["doshas"]["bhakoot_dosha"]["present"] is True     # Bhakoot scored zero
    assert result["doshas"]["nadi_dosha"]["present"] is False
    assert result["total"] == pytest.approx(result["percentage"] * 36 / 100, abs=0.02)


def test_the_low_scoring_published_pair_exercises_nadi_dosha():
    """The other documented pair, kept because it reaches code the first one does not: two kootas
    score zero (Gana and Nadi, the 6- and 8-pointers) and the nadi dosha - the most serious of the
    two - is present. Same provenance, same caveat: not a couple, nothing implied."""
    boy_ref, girl_ref = MATCH_PAIR_LOW
    result = match_charts(boy_ref.chart(), girl_ref.chart())
    assert result["total"] == 13.0
    assert result["verdict"] == "below_average"
    assert [k["koota"] for k in result["kootas"] if k["score"] == 0] == ["gana", "nadi"]
    assert result["doshas"]["nadi_dosha"]["present"] is True


def test_match_charts_adds_mangal_dosha_comparison():
    """Both of these charts carry mangal dosha, so the comparison block reports them as balancing
    each other - the classical reading when both sides have it."""
    boy, girl = (reference.chart() for reference in MATCH_PAIR)
    result = match_charts(boy, girl)
    assert result["mangal_dosha"]["boy"]["present"] is True
    assert result["mangal_dosha"]["girl"]["present"] is True
    assert result["mangal_dosha"]["compatible"] is True
    assert set(result["mangal_dosha"]) == {"boy", "girl", "compatible"}
