"""Mangal (Kuja) dosha.

Rule used: Mars in house 1, 2, 4, 7, 8 or 12, whole-sign, counted from the Lagna, from the
Moon and from Venus. (The 2nd house is included, as in the South Indian / Maharashtrian
tradition; some North Indian schools omit it.) `present` is the raw rule. The classical
cancellation (parihara) conditions are evaluated and returned as data - they do not flip
`present`; interpretation decides how much weight to give them.
"""

from .core import house_from

DOSHA_HOUSES = (1, 2, 4, 7, 8, 12)
RULE = "Mars in house 1, 2, 4, 7, 8 or 12 (whole-sign) counted from Lagna, Moon and Venus"

_ARIES, _TAURUS, _GEMINI, _CANCER, _LEO, _VIRGO, _LIBRA, _SCORPIO, _SAGITTARIUS, _CAPRICORN, _AQUARIUS, _PISCES = range(1, 13)

# From the lagna: Mars in this house does not cause dosha when it sits in these signs.
_HOUSE_SIGN_EXCEPTIONS = {
    2: (_GEMINI, _VIRGO),
    4: (_ARIES, _SCORPIO),
    7: (_CANCER, _CAPRICORN),
    8: (_SAGITTARIUS, _PISCES),
    12: (_TAURUS, _LIBRA),
}

NOTES = [
    "When both partners have Mangal dosha, the doshas are traditionally considered to cancel each other.",
    "Tradition holds that the effect of Mangal dosha weakens after the age of 28, when Mars matures.",
    "Dosha counted from the Lagna is considered the strongest, then from the Moon, then from Venus.",
]


def mangal_dosha(signs: dict[str, int]) -> dict:
    """`signs` maps "Lagna", "Moon", "Venus", "Mars", "Jupiter" to sign numbers 1-12."""
    mars = signs["Mars"]
    result = {"rule": RULE}
    for reference in ("Lagna", "Moon", "Venus"):
        house = house_from(signs[reference], mars)
        result[f"from_{reference.lower()}"] = {"mars_house": house, "dosha": house in DOSHA_HOUSES}
    count = sum(result[f"from_{ref}"]["dosha"] for ref in ("lagna", "moon", "venus"))
    lagna_house = result["from_lagna"]["mars_house"]

    cancellations = [
        {
            "key": "mars_in_own_or_exaltation_sign",
            "description": "Mars in its own sign (Aries, Scorpio) or exaltation sign (Capricorn)",
            "applies": mars in (_ARIES, _SCORPIO, _CAPRICORN),
        },
        {
            "key": "jupiter_conjunct_or_aspecting_mars",
            "description": "Jupiter in the same sign as Mars, or aspecting it (5th, 7th or 9th from Jupiter)",
            "applies": house_from(signs["Jupiter"], mars) in (1, 5, 7, 9),
        },
        {
            "key": "house_sign_exception",
            "description": "Mars in the 2nd in Gemini/Virgo, 4th in Aries/Scorpio, 7th in Cancer/Capricorn, "
                           "8th in Sagittarius/Pisces or 12th in Taurus/Libra (from Lagna)",
            "applies": mars in _HOUSE_SIGN_EXCEPTIONS.get(lagna_house, ()),
        },
        {
            "key": "cancer_or_leo_lagna",
            "description": "For Cancer and Leo lagna Mars is a yogakaraka, so its dosha is considered ineffective",
            "applies": signs["Lagna"] in (_CANCER, _LEO),
        },
    ]
    present = count > 0
    result.update({
        "present": present,
        "intensity": ("none", "low", "medium", "high")[count],
        "cancellations": cancellations,
        "cancellation_applies": present and any(item["applies"] for item in cancellations),
        "notes": NOTES,
    })
    return result


def chart_signs(chart: dict) -> dict[str, int]:
    signs = {key: chart["grahas"][key]["sign"]["index"] for key in ("Moon", "Venus", "Mars", "Jupiter")}
    signs["Lagna"] = chart["lagna"]["sign"]["index"]
    return signs
