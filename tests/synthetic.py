"""Build a minimal but complete chart dict from sign+degree placements, for rule tests.

The yoga/dignity/gemstone rules only ever read placements, houses and lordships - never the
ephemeris - so a hand-made chart is the cleanest way to test a rule in isolation and to prove a rule
does NOT fire. Anything produced here has the same shape app.engine.chart.compute_chart returns
(minus dasha/mangal/sade-sati, which these rules do not touch).
"""

from app.engine.constants import GRAHA_KEYS, graha_name, sign_info
from app.engine.core import _dms, house_from  # noqa: PLC2701 - same package, formatting only
from app.engine.constants import NAKSHATRA_SPAN, PADA_SPAN, nakshatra_info

DEFAULT_DEGREE = 15.0


def chart(lagna_sign: int, placements: dict[str, int | tuple[int, float]],
          retrograde: tuple[str, ...] = ()) -> dict:
    """`lagna_sign` and each placement are sign numbers 1-12, optionally (sign, degree).

    Grahas left out are parked in signs that keep them out of the way of the rule under test;
    Ketu is forced opposite Rahu, as it always is.
    """
    signs, degrees = {}, {}
    for key in GRAHA_KEYS:
        value = placements.get(key, _FILLER[key])
        sign, degree = value if isinstance(value, tuple) else (value, DEFAULT_DEGREE)
        signs[key], degrees[key] = sign, degree
    if "Ketu" not in placements:
        signs["Ketu"] = (signs["Rahu"] + 5) % 12 + 1
        degrees["Ketu"] = degrees["Rahu"]

    grahas = {}
    for key in GRAHA_KEYS:
        longitude = (signs[key] - 1) * 30 + degrees[key]
        grahas[key] = {
            "graha": graha_name(key),
            "longitude": round(longitude, 6),
            "sign": sign_info(signs[key] - 1),
            "degree": degrees[key],
            "degree_dms": _dms(degrees[key]),
            "nakshatra": nakshatra_info(int(longitude // NAKSHATRA_SPAN)),
            "pada": int(longitude % NAKSHATRA_SPAN // PADA_SPAN) + 1,
            "house": house_from(lagna_sign, signs[key]),
            "retrograde": key in retrograde,
            "speed": -1.0 if key in retrograde else 1.0,
        }
    lagna_longitude = (lagna_sign - 1) * 30 + DEFAULT_DEGREE
    return {
        "input": {"timezone": "Asia/Kolkata"},
        "lagna": {
            "longitude": lagna_longitude,
            "sign": sign_info(lagna_sign - 1),
            "degree": DEFAULT_DEGREE,
            "degree_dms": _dms(DEFAULT_DEGREE),
            "nakshatra": nakshatra_info(int(lagna_longitude // NAKSHATRA_SPAN)),
            "pada": int(lagna_longitude % NAKSHATRA_SPAN // PADA_SPAN) + 1,
        },
        "grahas": grahas,
        "moon_rashi": sign_info(signs["Moon"] - 1),
        "houses": [
            {
                "house": house,
                "sign": sign_info((lagna_sign - 1 + house - 1) % 12),
                "grahas": [k for k in GRAHA_KEYS if grahas[k]["house"] == house],
            }
            for house in range(1, 13)
        ],
    }


# Parking spots for grahas a test does not place itself. Chosen so the fillers alone produce NO
# dignity (nothing own/exalted/debilitated), NO combustion, and - because the "graha sits in the sign
# of" chain below is one long cycle with no two-cycle in it - no parivartana either:
#   Surya -> Vrishabha (Shukra) -> Makara (Shani) -> Mithuna (Budha) -> Karka (Chandra) -> Simha (Surya)
# with Mangal in Kanya and Guru in Tula hanging off it. Kemadruma, Shakata, Gajakesari,
# Chandra-Mangal, Budhaditya and Kaal Sarp are all absent for this set as well. What the fillers
# CANNOT avoid is lagna-dependent lordship yogas, so a test that asserts a yoga is absent must name
# the grahas it means - see tests/test_yogas.py:pick.
_FILLER = {"Sun": 2, "Moon": 5, "Mars": 6, "Mercury": 4, "Jupiter": 7, "Venus": 10,
           "Saturn": 3, "Rahu": 9, "Ketu": 3}


def facts(chart_dict: dict):
    """(navamsa, dignities) for a synthetic chart - the two inputs every rule module wants."""
    from app.engine.dignity import graha_dignities
    from app.engine.varga import navamsa_chart
    return navamsa_chart(chart_dict), graha_dignities(chart_dict)
