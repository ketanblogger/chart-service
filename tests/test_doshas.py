from datetime import date, datetime, time, timezone

from app.engine.dosha import mangal_dosha
from app.engine.sadesati import sade_sati
from tests.reference_charts import KALAM, NEHRU

ARIES, TAURUS, GEMINI, CANCER, LEO, VIRGO, LIBRA, SCORPIO, SAGITTARIUS, CAPRICORN, AQUARIUS, PISCES = range(1, 13)


def _signs(**overrides):
    return {"Lagna": ARIES, "Moon": ARIES, "Venus": ARIES, "Mars": GEMINI, "Jupiter": TAURUS, **overrides}


def test_no_dosha_when_mars_in_neutral_houses():
    result = mangal_dosha(_signs())  # Mars in 3rd from all three references
    assert result["present"] is False
    assert result["intensity"] == "none"
    assert result["cancellation_applies"] is False


def test_dosha_counted_separately_from_lagna_moon_and_venus():
    # Mars in Libra: 7th from Aries lagna, 3rd from Leo moon, 6th from Taurus venus
    result = mangal_dosha(_signs(Mars=LIBRA, Moon=LEO, Venus=TAURUS))
    assert result["from_lagna"] == {"mars_house": 7, "dosha": True}
    assert result["from_moon"] == {"mars_house": 3, "dosha": False}
    assert result["from_venus"] == {"mars_house": 6, "dosha": False}
    assert result["present"] is True
    assert result["intensity"] == "low"


def test_every_dosha_house_triggers():
    for house in range(1, 13):
        mars = (ARIES - 1 + house - 1) % 12 + 1
        result = mangal_dosha(_signs(Mars=mars))
        assert result["from_lagna"]["dosha"] is (house in (1, 2, 4, 7, 8, 12))


def test_cancellations_are_reported_as_data():
    # Mars exalted in Capricorn, 7th from Cancer lagna: all four cancellation rules apply.
    result = mangal_dosha(_signs(Lagna=CANCER, Moon=CANCER, Venus=CANCER, Mars=CAPRICORN, Jupiter=CANCER))
    applies = {item["key"]: item["applies"] for item in result["cancellations"]}
    assert applies == {
        "mars_in_own_or_exaltation_sign": True,
        "jupiter_conjunct_or_aspecting_mars": True,
        "house_sign_exception": True,
        "cancer_or_leo_lagna": True,
    }
    assert result["present"] is True  # cancellations never flip the raw rule
    assert result["cancellation_applies"] is True


def test_published_chart_is_manglik_from_all_three():
    """A. P. J. Abdul Kalam: Mangal in Tula, which is the 4th from the Karka lagna, the 12th from the
    Vrishchika Moon and the 1st from Shukra - a dosha house on all three counts."""
    dosha = KALAM.chart()["mangal_dosha"]
    assert (dosha["from_lagna"]["mars_house"], dosha["from_moon"]["mars_house"],
            dosha["from_venus"]["mars_house"]) == (4, 12, 1)
    assert dosha["intensity"] == "high"
    assert dosha["cancellation_applies"] is True


def test_published_chart_is_manglik_from_one_of_three():
    """Jawaharlal Nehru: Mangal in Kanya is the 12th from Shukra - a dosha house - but the 3rd from
    both the Karka lagna and the Karka Moon, which are not. One count out of three, so "low"."""
    dosha = NEHRU.chart()["mangal_dosha"]
    assert (dosha["from_lagna"]["mars_house"], dosha["from_moon"]["mars_house"],
            dosha["from_venus"]["mars_house"]) == (3, 3, 12)
    assert dosha["intensity"] == "low"
    assert dosha["present"] is True


def test_sade_sati_for_dhanu_matches_published_dates():
    # Saturn: Vrishchika 2 Nov 2014, Dhanu 26 Jan 2017, Makara 24 Jan 2020, finally Kumbha 17 Jan 2023.
    result = sade_sati(SAGITTARIUS, datetime(2018, 6, 1, tzinfo=timezone.utc))
    assert result["active"] is True
    assert result["phase"] == "peak"
    assert result["cycle"]["which"] == "current"
    assert result["cycle"]["start"] == "2014-11-02"
    assert result["cycle"]["end"] == "2023-01-17"
    phases = [period["phase"] for period in result["cycle"]["periods"]]
    assert phases == ["rising", "peak", "rising", "peak", "setting", "setting"]  # retrograde re-entries


def test_sade_sati_reports_next_cycle_when_inactive():
    result = sade_sati(SAGITTARIUS, datetime(2026, 9, 21, tzinfo=timezone.utc))
    assert result["active"] is False
    assert result["phase"] is None
    assert result["saturn_sign"]["name"] == "Meena"
    assert result["cycle"]["which"] == "next"
    assert result["cycle"]["start"] > "2026-09-21"
    assert result["cycle"]["periods"][0]["phase"] == "rising"


def test_sade_sati_phases_by_moon_sign_today():
    as_of = datetime(2026, 9, 21, tzinfo=timezone.utc)  # Saturn in Meena
    assert sade_sati(ARIES, as_of)["phase"] == "rising"
    assert sade_sati(PISCES, as_of)["phase"] == "peak"
    assert sade_sati(AQUARIUS, as_of)["phase"] == "setting"
    for moon_sign in (TAURUS, GEMINI, CANCER, LEO, VIRGO, LIBRA, SCORPIO, SAGITTARIUS, CAPRICORN):
        assert sade_sati(moon_sign, as_of)["active"] is False
