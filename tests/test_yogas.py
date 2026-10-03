"""Yoga detection. Every rule is tested both ways: a chart that triggers it, and a near-miss that
must NOT. The reference chart is hand-verified at the bottom."""

import pytest

from app.engine.aspects import association, aspects_sign, exchange, mutual_aspect
from app.engine.varga import navamsa_chart
from app.engine.dignity import graha_dignities
from app.engine.yogas import KAAL_SARP_TYPES, yogas
from tests import synthetic
from tests.reference_charts import KALAM

ARIES, TAURUS, GEMINI, CANCER, LEO, VIRGO = 1, 2, 3, 4, 5, 6
LIBRA, SCORPIO, SAGITTARIUS, CAPRICORN, AQUARIUS, PISCES = 7, 8, 9, 10, 11, 12


@pytest.fixture(scope="module")
def reference():
    return KALAM.chart()


def detect(lagna, placements, retrograde=()):
    """All yogas of a synthetic chart, as a list - a chart can hold several Raj yogas at once."""
    chart = synthetic.chart(lagna, placements, retrograde)
    navamsa, dignities = synthetic.facts(chart)
    return yogas(chart, navamsa, dignities)


def pick(found, key, *grahas):
    """The one yoga with this key (and, when given, exactly these grahas), or None.

    Naming the grahas matters: the filler placements can raise a Raj or Dhana yoga of their own for
    some lagnas, so "this yoga is absent" only means anything about a named pair.
    """
    matches = [y for y in found if y["key"] == key
               and (not grahas or sorted(g["key"] for g in y["grahas"]) == sorted(grahas))]
    assert len(matches) <= 1, matches
    return matches[0] if matches else None


# --- aspects, the primitive everything else rests on -------------------------------------------

def test_whole_sign_drishti():
    assert aspects_sign("Sun", ARIES, LIBRA) is True        # the 7th, which every graha casts
    assert aspects_sign("Sun", ARIES, CANCER) is False
    assert aspects_sign("Mars", ARIES, CANCER) is True      # Mangal's 4th
    assert aspects_sign("Mars", ARIES, SCORPIO) is True     # Mangal's 8th
    assert aspects_sign("Jupiter", ARIES, LEO) is True      # Guru's 5th
    assert aspects_sign("Jupiter", ARIES, SAGITTARIUS) is True   # Guru's 9th
    assert aspects_sign("Saturn", ARIES, GEMINI) is True    # Shani's 3rd
    assert aspects_sign("Saturn", ARIES, CAPRICORN) is True  # Shani's 10th
    assert aspects_sign("Saturn", ARIES, LEO) is False


def test_association_kinds_and_node_exclusion():
    signs = {"Sun": ARIES, "Moon": ARIES, "Mars": LIBRA, "Jupiter": CANCER, "Venus": TAURUS,
             "Mercury": GEMINI, "Saturn": CAPRICORN, "Rahu": ARIES, "Ketu": LIBRA}
    assert association(signs, "Sun", "Moon") == "conjunction"
    assert association(signs, "Sun", "Mars") == "mutual_aspect"   # 1st and 7th
    assert association(signs, "Sun", "Jupiter") is None
    # Guru in Karka (Chandra's sign) and Chandra in Mesha (Mangal's) is not an exchange.
    assert exchange({"Moon": CANCER, "Jupiter": PISCES}, "Moon", "Jupiter") is False
    assert exchange({"Moon": SAGITTARIUS, "Jupiter": CANCER}, "Moon", "Jupiter") is True
    assert mutual_aspect(signs, "Sun", "Rahu") is False       # never through a node
    assert association(signs, "Sun", "Rahu") == "conjunction"  # conjunction still counts


# --- one rule at a time -------------------------------------------------------------------------

def test_raj_yoga_needs_a_kendra_lord_and_a_trikona_lord_in_association():
    # Mesha lagna: Chandra rules the 4th (Karka), Guru rules the 9th (Dhanu). Put them together.
    yoga = pick(detect(ARIES, {"Moon": LEO, "Jupiter": LEO}), "raj_yoga", "Jupiter", "Moon")
    assert yoga["association"] == "conjunction"
    assert yoga["kendra_houses"] == [4] and yoga["trikona_houses"] == [9]
    # Same two lords, no association at all -> no yoga for that pair.
    assert pick(detect(ARIES, {"Moon": LEO, "Jupiter": VIRGO}), "raj_yoga", "Jupiter", "Moon") is None


def test_raj_yoga_by_mutual_aspect_but_not_by_one_sided_aspect():
    # 4th lord Chandra in Mesha, 9th lord Guru in Tula: 1st/7th, mutual.
    yoga = pick(detect(ARIES, {"Moon": ARIES, "Jupiter": LIBRA}), "raj_yoga", "Jupiter", "Moon")
    assert yoga["association"] == "mutual_aspect"
    # Guru in Mesha aspects Simha (its 5th); Chandra in Simha aspects only Kumbha. One-sided.
    assert pick(detect(ARIES, {"Jupiter": ARIES, "Moon": LEO}), "raj_yoga", "Jupiter", "Moon") is None


def test_yogakaraka_only_for_the_four_lagnas_that_can_have_one():
    # Simha lagna: Mangal rules the 4th (Vrishchika) and the 9th (Mesha).
    yoga = pick(detect(LEO, {"Mars": LEO}), "yogakaraka", "Mars")
    assert yoga["houses"] == [1, 4, 9]
    # Mesha lagna: no graha rules both a 4/7/10 and a 5/9.
    assert [y for y in detect(ARIES, {}) if y["key"] == "yogakaraka"] == []
    # Makara lagna: Shukra rules the 5th (Vrishabha) and the 10th (Tula).
    assert pick(detect(CAPRICORN, {}), "yogakaraka", "Venus") is not None


def test_dhana_yoga():
    # Mesha lagna: Shukra rules the 2nd (Vrishabha), Guru the 9th (Dhanu). Together in Mithuna.
    assert pick(detect(ARIES, {"Venus": GEMINI, "Jupiter": GEMINI}), "dhana_yoga", "Jupiter", "Venus")
    assert pick(detect(ARIES, {"Venus": GEMINI, "Jupiter": VIRGO}), "dhana_yoga", "Jupiter", "Venus") is None


def test_gajakesari_is_counted_from_the_moon_not_the_lagna():
    # Chandra in Mesha, Guru in Karka: the 4th FROM THE MOON.
    assert pick(detect(LIBRA, {"Moon": ARIES, "Jupiter": CANCER}), "gajakesari")["house_from_moon"] == 4
    # Guru in a kendra from the LAGNA but the 3rd from the Moon -> no yoga.
    assert pick(detect(LIBRA, {"Moon": ARIES, "Jupiter": GEMINI}), "gajakesari") is None


def test_budhaditya_and_its_combustion_qualifier():
    close = pick(detect(ARIES, {"Sun": (LEO, 10.0), "Mercury": (LEO, 12.0)}), "budhaditya")
    assert close["mercury_combust"] is True
    assert close["strength"] == "moderate"   # downgraded once, for the combustion
    wide = pick(detect(ARIES, {"Sun": (LEO, 1.0), "Mercury": (LEO, 29.0)}), "budhaditya")
    assert wide["mercury_combust"] is False
    assert wide["strength"] == "strong"
    assert pick(detect(ARIES, {"Sun": LEO, "Mercury": VIRGO}), "budhaditya") is None


def test_chandra_mangal_is_conjunction_only():
    assert pick(detect(ARIES, {"Moon": TAURUS, "Mars": TAURUS}), "chandra_mangal")
    assert pick(detect(ARIES, {"Moon": TAURUS, "Mars": SCORPIO}), "chandra_mangal") is None  # opposition


@pytest.mark.parametrize("graha,sign,key", [
    ("Mars", ARIES, "mahapurusha_ruchaka"),
    ("Mercury", GEMINI, "mahapurusha_bhadra"),
    ("Jupiter", SAGITTARIUS, "mahapurusha_hamsa"),
    ("Venus", LIBRA, "mahapurusha_malavya"),
    ("Saturn", AQUARIUS, "mahapurusha_sasa"),
])
def test_pancha_mahapurusha_needs_own_or_exaltation_sign_in_a_kendra(graha, sign, key):
    # lagna = the graha's own sign, so it sits in the 1st, a kendra.
    assert pick(detect(sign, {graha: sign}), key) is not None
    # same sign, but now the 3rd from the lagna - not a kendra.
    lagna = (sign - 3) % 12 + 1
    assert pick(detect(lagna, {graha: sign}), key) is None


def test_mahapurusha_accepts_exaltation_too():
    found = detect(CAPRICORN, {"Mars": (CAPRICORN, 28.0)})   # Mangal exalted in Makara, in the 1st
    assert pick(found, "mahapurusha_ruchaka")["dignity"] == "exalted"


# Guru debilitated in Makara. Its dispositor is Shani; the graha exalted in Makara is Mangal.
# Keeping both, and Chandra, out of every kendra from the lagna AND from the Moon leaves no
# cancellation - so the debilitation stands and no yoga is emitted.
_NO_CANCELLATION = {"Jupiter": (CAPRICORN, 5.0), "Saturn": TAURUS, "Mars": TAURUS,
                    "Moon": VIRGO, "Sun": VIRGO, "Mercury": VIRGO, "Venus": VIRGO,
                    "Rahu": AQUARIUS, "Ketu": LEO}


def test_neecha_bhanga_needs_at_least_one_cancellation():
    plain = synthetic.chart(ARIES, _NO_CANCELLATION)
    navamsa, dignities = synthetic.facts(plain)
    assert dignities["Jupiter"]["dignity"]["label"] == "debilitated"
    assert pick(yogas(plain, navamsa, dignities), "neecha_bhanga_raja_yoga", "Jupiter") is None
    # Now move the dispositor Shani into a kendra from the lagna.
    yoga = pick(detect(ARIES, {**_NO_CANCELLATION, "Saturn": CANCER}),
                "neecha_bhanga_raja_yoga", "Jupiter")
    assert "dispositor_in_kendra" in yoga["conditions_met"]
    assert len(yoga["cancellation_conditions"]) == 5


def test_neecha_bhanga_does_not_fire_just_because_the_moon_is_the_dispositor():
    """Mangal debilitated in Karka: the dispositor is Chandra, which is always in the 1st from
    itself. Counting that would make the yoga automatic - see yogas.py. Guru (exalted in Karka) and
    Chandra are both kept out of every kendra here, so nothing legitimate can fire either."""
    found = detect(ARIES, {"Mars": (CANCER, 5.0), "Moon": GEMINI, "Jupiter": TAURUS, "Saturn": VIRGO,
                           "Venus": VIRGO, "Mercury": VIRGO, "Sun": VIRGO,
                           "Rahu": AQUARIUS, "Ketu": LEO})
    assert pick(found, "neecha_bhanga_raja_yoga", "Mars") is None


def test_vipreeta_raja_yoga_names_the_right_variant():
    # Mesha lagna: 6th = Kanya (Budha), 8th = Vrishchika (Mangal), 12th = Meena (Guru).
    yoga = pick(detect(ARIES, {"Mercury": SCORPIO}), "vipreeta_harsha")   # 6th lord in the 8th
    assert yoga["dusthana_ruled"] == 6
    assert yoga["in_own_dusthana"] is False
    yoga = pick(detect(ARIES, {"Mars": SCORPIO}), "vipreeta_sarala")      # 8th lord in its own 8th
    assert yoga["in_own_dusthana"] is True
    assert yoga["strength"] == "moderate"
    assert yoga["caution"] is not None   # Mangal also rules the 1st
    assert pick(detect(ARIES, {"Jupiter": LEO}), "vipreeta_vimala") is None   # 12th lord in the 5th


def test_kemadruma_and_its_cancellations():
    # Chandra alone in Karka; Simha, Karka and Mithuna all empty of other grahas.
    found = detect(CANCER, {"Moon": CANCER, "Sun": CANCER, "Mars": SCORPIO, "Mercury": SAGITTARIUS,
                            "Jupiter": CAPRICORN, "Venus": AQUARIUS, "Saturn": PISCES,
                            "Rahu": ARIES, "Ketu": LIBRA})
    yoga = pick(found, "kemadruma")
    # Surya in the Moon's own sign does not count as company, by the definition used.
    assert yoga is not None
    assert yoga["strength"] == "mild"   # Chandra is in the 1st, a kendra -> cancelled
    assert "moon_in_kendra_from_lagna" in yoga["cancellations_met"]
    # One graha in the 2nd from Chandra kills the yoga outright.
    assert pick(detect(CANCER, {"Moon": CANCER, "Mars": LEO}), "kemadruma") is None


def test_shakata():
    # Chandra in the 6th from Guru: Guru in Mesha, Chandra in Kanya.
    yoga = pick(detect(ARIES, {"Jupiter": ARIES, "Moon": VIRGO}), "shakata")
    assert yoga["moon_house_from_jupiter"] == 6
    assert yoga["cancelled_by_moon_in_kendra"] is False
    assert pick(detect(ARIES, {"Jupiter": ARIES, "Moon": LEO}), "shakata") is None  # the 5th, not 6/8/12


def test_kaal_sarp_full_partial_and_absent():
    """All seven between Rahu and Ketu. Rahu at Mesha 0°, Ketu at Tula 0°."""
    hemmed = {g: (TAURUS, 10.0) for g in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")}
    hemmed.update({"Rahu": (ARIES, 0.0), "Ketu": (LIBRA, 0.0)})
    yoga = pick(detect(ARIES, hemmed), "kaal_sarp")
    assert yoga["kind"] == "full"
    assert yoga["arc"] == "rahu_to_ketu"
    assert yoga["type"] == KAAL_SARP_TYPES[1][0] == "Ananta"   # Rahu in the 1st
    assert yoga["grahas_on_axis"] == []
    # One graha sitting on the axis -> partial.
    partial = pick(detect(ARIES, dict(hemmed, Sun=(ARIES, 0.5))), "kaal_sarp")
    assert partial["kind"] == "partial"
    assert partial["grahas_on_axis"] == ["Sun"]
    # One graha outside the arc -> nothing.
    assert pick(detect(ARIES, dict(hemmed, Sun=(SCORPIO, 10.0))), "kaal_sarp") is None


def test_kaal_sarp_reverse_arc_is_named_and_flagged():
    hemmed = {g: (SCORPIO, 10.0) for g in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")}
    hemmed.update({"Rahu": (ARIES, 0.0), "Ketu": (LIBRA, 0.0)})
    yoga = pick(detect(ARIES, hemmed), "kaal_sarp")
    assert yoga["arc"] == "ketu_to_rahu"
    assert yoga["name"].endswith("(reverse arc)")
    assert "Kaal Amrit" in yoga["disputed"]


def test_pitra_dosha_conditions():
    # Surya with Rahu.
    assert pick(detect(ARIES, {"Sun": TAURUS, "Rahu": TAURUS, "Ketu": SCORPIO}),
                "pitra_dosha")["conditions_met"] == ["sun_with_node"]
    # A node in the 9th from the lagna.
    assert "node_in_ninth" in pick(detect(ARIES, {"Rahu": SAGITTARIUS, "Ketu": GEMINI}),
                                   "pitra_dosha")["conditions_met"]
    # The 9th lord with a node: Mesha lagna, 9th = Dhanu, lord Guru.
    assert "ninth_lord_with_node" in pick(detect(ARIES, {"Jupiter": TAURUS, "Rahu": TAURUS,
                                                         "Ketu": SCORPIO}), "pitra_dosha")["conditions_met"]
    # Nodes away from Surya, away from the 9th, away from the 9th lord.
    assert pick(detect(ARIES, {"Sun": ARIES, "Jupiter": LEO, "Rahu": TAURUS, "Ketu": SCORPIO}),
                "pitra_dosha") is None


def test_parivartana_kinds():
    # Mesha lagna, Chandra in Dhanu (Guru's), Guru in Karka (Chandra's): houses 9 and 4 -> Maha.
    yoga = pick(detect(ARIES, {"Moon": SAGITTARIUS, "Jupiter": CANCER}),
                "parivartana_maha", "Jupiter", "Moon")
    assert yoga["kind"] == "maha"
    assert yoga["houses"] == [4, 9]
    # Involving a dusthana -> Dainya. Shani in Kanya (6th, Budha's), Budha in Kumbha (11th, Shani's).
    assert pick(detect(ARIES, {"Saturn": VIRGO, "Mercury": AQUARIUS}),
                "parivartana_dainya", "Mercury", "Saturn") is not None
    # Involving the 3rd -> Khala. Mesha lagna 3rd = Mithuna (Budha); Budha in Vrishabha (2nd, Shukra),
    # Shukra in Mithuna (3rd, Budha).
    assert pick(detect(ARIES, {"Mercury": TAURUS, "Venus": GEMINI}),
                "parivartana_khala", "Mercury", "Venus")["kind"] == "khala"


def test_the_filler_placements_alone_raise_no_dignity_or_dosha_yoga():
    """Guards the test fixture itself: whatever the fillers do, it must not be a yoga that a rule
    test would then mistake for its own result."""
    found = detect(ARIES, {})
    keys = {y["key"] for y in found}
    assert not keys & {"neecha_bhanga_raja_yoga", "kaal_sarp", "kemadruma", "shakata",
                       "budhaditya", "chandra_mangal", "gajakesari",
                       "parivartana_maha", "parivartana_khala", "parivartana_dainya"}
    assert not any(k.startswith("mahapurusha_") for k in keys)


def test_every_yoga_carries_its_rule_and_both_house_counts():
    found = detect(LEO, {"Mars": LEO, "Moon": ARIES, "Jupiter": CANCER})
    assert found
    for yoga in found:
        assert yoga["rule"] and yoga["combination"]
        assert yoga["strength"] in ("strong", "moderate", "mild")
        assert yoga["nature"] in ("benefic", "challenging")
        for graha in yoga["grahas"]:
            assert set(graha) >= {"key", "name", "devanagari", "sign",
                                  "house_from_lagna", "house_from_moon", "rules_houses"}


# --- the reference chart, hand-verified ----------------------------------------------------------

def test_reference_chart_yogas(reference):
    """A. P. J. Abdul Kalam, Karka lagna, so the house lords are
    1 Chandra, 2 Surya, 3 Budha, 4 Shukra, 5 Mangal, 6 Guru, 7 Shani, 8 Shani, 9 Guru, 10 Mangal,
    11 Shukra, 12 Budha.

    Expected, worked by hand - and four of the nine rest on placements the published analysis of this
    chart states independently (Guru exalted in the 1st, Budha exalted in the 3rd with Surya, Chandra
    debilitated, Shani in the 6th ruling the 7th and 8th):
      Hamsa           Guru exalted in Karka, in house 1 - a kendra. One of the Pancha Mahapurusha.
      Yogakaraka      Mangal rules the 5th and the 10th, a trikona and a kendra, for Karka lagna.
      Sarala          the 8th lord Shani sits in the 6th - a Vipreeta Raja yoga, in another dusthana.
      Malavya         Shukra in its moolatrikona Tula, in house 4 - a kendra. Moderate: it is combust.
      Neecha Bhanga   Chandra is debilitated in Vrishchika and the debilitation is cancelled.
      Raj yoga        Mangal (5th and 10th lord) with Shukra (4th and 11th lord) in Tula: a trikona
                      lord and a kendra lord in conjunction.
      Dhana yoga      the same pair - Shukra also rules the 11th, a wealth house.
      Budhaditya      Surya and Budha together in Kanya, house 3.
      Pitra dosha     two conditions: Surya shares a sign with Ketu, AND Rahu is in the 9th house.
    Not present: Gajakesari (Guru is the 3rd from the Moon), Chandra-Mangal, Kemadruma (Shukra and
    Mangal sit in the 12th from Chandra), Shakata, Kaal Sarp (Guru is outside the Rahu-Ketu arc),
    Ruchaka/Bhadra/Sasa, Harsha, Vimala, and any Parivartana.
    """
    found = {y["key"]: y for y in yogas(reference, navamsa_chart(reference), graha_dignities(reference))}
    assert set(found) == {"mahapurusha_hamsa", "yogakaraka", "vipreeta_sarala", "mahapurusha_malavya",
                          "neecha_bhanga_raja_yoga", "raj_yoga", "dhana_yoga", "budhaditya",
                          "pitra_dosha"}

    assert found["mahapurusha_hamsa"]["dignity"] == "exalted"
    assert found["mahapurusha_hamsa"]["strength"] == "strong"
    assert found["mahapurusha_hamsa"]["grahas"][0]["house_from_lagna"] == 1

    assert found["mahapurusha_malavya"]["dignity"] == "moolatrikona"
    assert found["mahapurusha_malavya"]["strength"] == "moderate"   # Shukra is combust
    assert found["mahapurusha_malavya"]["grahas"][0]["combust"] is True

    assert found["yogakaraka"]["grahas"][0]["key"] == "Mars"
    assert found["yogakaraka"]["grahas"][0]["rules_houses"] == [5, 10]

    assert found["vipreeta_sarala"]["dusthana_ruled"] == 8
    assert found["vipreeta_sarala"]["in_own_dusthana"] is False      # the 8th lord sits in the 6th
    assert found["vipreeta_sarala"]["strength"] == "strong"

    assert found["neecha_bhanga_raja_yoga"]["grahas"][0]["key"] == "Moon"
    assert found["neecha_bhanga_raja_yoga"]["conditions_met"]

    assert sorted(g["key"] for g in found["raj_yoga"]["grahas"]) == ["Mars", "Venus"]
    assert found["raj_yoga"]["association"] == "conjunction"
    assert sorted(g["key"] for g in found["dhana_yoga"]["grahas"]) == ["Mars", "Venus"]

    assert found["budhaditya"]["mercury_combust"] is True
    assert found["budhaditya"]["grahas"][0]["house_from_lagna"] == 3

    assert found["pitra_dosha"]["conditions_met"] == ["sun_with_node", "node_in_ninth"]
    assert "commonly published" in found["pitra_dosha"]["definition_note"]
    assert found["pitra_dosha"]["framing"]


def test_reference_chart_yoga_order_is_deterministic(reference):
    navamsa, dignities = navamsa_chart(reference), graha_dignities(reference)
    first = yogas(reference, navamsa, dignities)
    assert [y["key"] for y in first] == [y["key"] for y in yogas(reference, navamsa, dignities)]
    assert [y["strength"] for y in first] == sorted(
        (y["strength"] for y in first), key=["strong", "moderate", "mild"].index)


def test_yogas_are_json_serialisable(reference):
    import json
    json.dumps(yogas(reference, navamsa_chart(reference), graha_dignities(reference)))
