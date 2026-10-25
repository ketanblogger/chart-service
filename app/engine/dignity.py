"""Combustion (asta) and dignity (exaltation / debilitation / moolatrikona / own sign / friendship).

This is DATA for the interpretation layer. The AI is forbidden to assert a dignity it was not given,
so everything a report might want to say about a graha's strength is computed and labelled here.

COMBUSTION (asta) - a graha too close to the Sun is "burnt" and traditionally loses its ability to
give its results. Orbs are measured in degrees of longitude difference from the Sun and differ per
graha; the set below is the one given in Brihat Parashara Hora Shastra and reproduced in B.V. Raman,
*Graha and Bhava Balas*, and it is the set almost every Indian ephemeris program ships with:

    Moon 12°, Mars 17°, Mercury 14° (12° when retrograde), Jupiter 11°,
    Venus 10° (8° when retrograde), Saturn 15°

Two documented variants we deliberately do NOT apply, so that the numbers here are reproducible:
  - some texts give Mars 8° when retrograde (we keep 17°, which is the wider, more conservative orb
    and therefore flags combustion more readily, never less);
  - Western "cazimi" (within 17' of the Sun, held to be a strengthening rather than a burning) has no
    classical Parashari equivalent and is not used. We do expose `deeply_combust` (within 1°) as a
    plain qualifier, without claiming it reverses the effect.
Rahu and Ketu are shadow points and are never treated as combust. The Sun is never combust.

DIGNITY - exaltation (uchcha) degrees, debilitation (neecha) at the opposite point, moolatrikona arcs
and own signs are the standard BPHS values:

    graha    exalted          debilitated      moolatrikona          own signs
    Sun      Mesha 10°        Tula 10°         Simha 0°-20°          Simha
    Moon     Vrishabha 3°     Vrishchika 3°    Vrishabha 4°-30°      Karka
    Mars     Makara 28°       Karka 28°        Mesha 0°-12°          Mesha, Vrishchika
    Mercury  Kanya 15°        Meena 15°        Kanya 16°-20°         Mithuna, Kanya
    Jupiter  Karka 5°         Makara 5°        Dhanu 0°-10°          Dhanu, Meena
    Venus    Meena 27°        Kanya 27°        Tula 0°-15°           Vrishabha, Tula
    Saturn   Tula 20°         Mesha 20°        Kumbha 0°-20°         Makara, Kumbha

Rahu/Ketu exaltation is disputed (Vrishabha/Mithuna and Vrishchika/Dhanu are all claimed by different
authorities), so this module returns `dignity: null` for the nodes and says why in `note` rather than
picking a side. The nodes also own no sign, so they have no lordship-based dignity either.

FRIENDSHIP is the naisargika (natural, permanent) table of BPHS only. Tatkalika (temporary, from the
houses the grahas occupy at the moment) and the panchadha (five-fold compound) friendship that some
schools derive from it are NOT computed - they would change the label without any way for the report
to explain the change, and no rule in this codebase depends on them.
"""

from .constants import GRAHA_KEYS, graha_name, sign_info

# graha -> orb in degrees from the Sun; (direct, retrograde) where the two differ.
COMBUSTION_ORBS = {
    "Moon": (12.0, 12.0),
    "Mars": (17.0, 17.0),
    "Mercury": (14.0, 12.0),
    "Jupiter": (11.0, 11.0),
    "Venus": (10.0, 8.0),
    "Saturn": (15.0, 15.0),
}
COMBUSTION_RULE = ("Longitude difference from the Sun below the classical per-graha orb "
                   "(Moon 12°, Mars 17°, Mercury 14°/12° retrograde, Jupiter 11°, Venus 10°/8° retrograde, "
                   "Saturn 15°); Rahu and Ketu are never counted as combust")
DEEP_COMBUSTION_DEGREES = 1.0

# graha -> (exaltation sign 1-12, exaltation degree). Debilitation is the 7th sign at the same degree.
EXALTATION = {
    "Sun": (1, 10.0), "Moon": (2, 3.0), "Mars": (10, 28.0), "Mercury": (6, 15.0),
    "Jupiter": (4, 5.0), "Venus": (12, 27.0), "Saturn": (7, 20.0),
}
# graha -> (sign 1-12, from degree, to degree)
MOOLATRIKONA = {
    "Sun": (5, 0.0, 20.0), "Moon": (2, 4.0, 30.0), "Mars": (1, 0.0, 12.0), "Mercury": (6, 16.0, 20.0),
    "Jupiter": (9, 0.0, 10.0), "Venus": (7, 0.0, 15.0), "Saturn": (11, 0.0, 20.0),
}
OWN_SIGNS = {
    "Sun": (5,), "Moon": (4,), "Mars": (1, 8), "Mercury": (3, 6),
    "Jupiter": (9, 12), "Venus": (2, 7), "Saturn": (10, 11),
}
NODES = ("Rahu", "Ketu")
NODE_NOTE = ("Rahu and Ketu own no sign and their exaltation is disputed between authorities, "
             "so no dignity label is asserted for them")

# Naisargika (natural) friendship, BPHS. Anything not listed as friend or enemy is neutral (sama).
_FRIENDS = {
    "Sun": ("Moon", "Mars", "Jupiter"),
    "Moon": ("Sun", "Mercury"),
    "Mars": ("Sun", "Moon", "Jupiter"),
    "Mercury": ("Sun", "Venus"),
    "Jupiter": ("Sun", "Moon", "Mars"),
    "Venus": ("Mercury", "Saturn"),
    "Saturn": ("Mercury", "Venus"),
}
_ENEMIES = {
    "Sun": ("Venus", "Saturn"),
    "Moon": (),
    "Mars": ("Mercury",),
    "Mercury": ("Moon",),
    "Jupiter": ("Mercury", "Venus"),
    "Venus": ("Sun", "Moon"),
    "Saturn": ("Sun", "Moon", "Mars"),
}

# Used for ordering/scoring only; the label itself is what the report prints.
DIGNITY_SCORE = {"exalted": 5, "moolatrikona": 4, "own_sign": 3, "friendly_sign": 1,
                 "neutral_sign": 0, "enemy_sign": -1, "debilitated": -3}

BENEFICS = ("Jupiter", "Venus")  # natural benefics; Mercury and the Moon are conditional (see below)
MALEFICS = ("Saturn", "Mars", "Sun", "Rahu", "Ketu")


def natural_friendship(graha: str, other: str) -> str:
    """"friend" | "neutral" | "enemy" for two non-node grahas; "unrated" when a node is involved."""
    if graha in NODES or other in NODES or graha == other:
        return "unrated"
    if other in _FRIENDS[graha]:
        return "friend"
    if other in _ENEMIES[graha]:
        return "enemy"
    return "neutral"


def separation(a: float, b: float) -> float:
    """Shortest angular distance between two longitudes, 0-180."""
    return abs((a - b + 180) % 360 - 180)


def elongation(moon_longitude: float, sun_longitude: float) -> float:
    """How far the Moon has travelled ahead of the Sun, 0-360. 0 = amavasya, 180 = purnima.
    Unlike `separation` this is directed, so it tells waxing from waning."""
    return (moon_longitude - sun_longitude) % 360


# The Moon counts as bright (paksha bala, benefic) from the 4th tithi of the waxing fortnight to the
# 4th of the waning one. A tithi is 12° of elongation, so those limits are 36° and 180° + 36°.
BRIGHT_MOON_ELONGATION = (36.0, 216.0)


def combustion(graha: str, longitude: float, sun_longitude: float, retrograde: bool) -> dict:
    """Combustion of one graha. `combust` is null for the Sun and the nodes (the rule does not apply)."""
    if graha == "Sun" or graha in NODES:
        return {"applicable": False, "combust": None, "orb_degrees": None,
                "separation_degrees": None if graha == "Sun" else round(separation(longitude, sun_longitude), 4),
                "rule": COMBUSTION_RULE}
    orb = COMBUSTION_ORBS[graha][1 if retrograde else 0]
    gap = separation(longitude, sun_longitude)
    return {
        "applicable": True,
        "combust": gap < orb,
        "deeply_combust": gap < DEEP_COMBUSTION_DEGREES,
        "separation_degrees": round(gap, 4),
        "orb_degrees": orb,
        "retrograde_orb_used": retrograde and COMBUSTION_ORBS[graha][0] != COMBUSTION_ORBS[graha][1],
        "rule": COMBUSTION_RULE,
    }


def _dignity_label(graha: str, sign: int, degree: float) -> tuple[str, str]:
    """(label, the exact condition that produced it).

    Precedence, fixed here because two of the arcs overlap: MOOLATRIKONA arc first, then exaltation
    sign, then debilitation sign, then own sign, then natural friendship with the sign's lord.
    Checking moolatrikona first is what keeps Chandra's (Vrishabha 4°-30°) and Budha's
    (Kanya 16°-20°) moolatrikona arcs reachable at all - both sit inside those grahas' exaltation
    signs, and sign-wide exaltation would otherwise swallow them. Everywhere else exaltation is
    sign-wide, which is what Indian software conventionally does; the distance from the deep
    exaltation degree is returned separately as `exact_exaltation_degrees_away`.
    """
    exalt_sign, exalt_degree = EXALTATION[graha]
    mt_sign, mt_from, mt_to = MOOLATRIKONA[graha]
    if sign == mt_sign and mt_from <= degree < mt_to:
        return "moolatrikona", f"in its moolatrikona arc {sign_info(sign - 1)['name']} {mt_from:g}°-{mt_to:g}°"
    if sign == exalt_sign:
        return "exalted", f"in its exaltation sign {sign_info(sign - 1)['name']} (deep exaltation {exalt_degree:g}°)"
    if sign == (exalt_sign + 5) % 12 + 1:
        return "debilitated", f"in its debilitation sign {sign_info(sign - 1)['name']} (deep debilitation {exalt_degree:g}°)"
    if sign in OWN_SIGNS[graha]:
        return "own_sign", f"in its own sign {sign_info(sign - 1)['name']}"
    relation = natural_friendship(graha, sign_info(sign - 1)["lord"])
    label = {"friend": "friendly_sign", "enemy": "enemy_sign"}.get(relation, "neutral_sign")
    return label, (f"in {sign_info(sign - 1)['name']}, a sign of {sign_info(sign - 1)['lord']}, "
                   f"who is its natural {relation if relation != 'unrated' else 'neutral'}")


def dignity(graha: str, sign: int, degree: float) -> dict:
    """Dignity of one graha. `label` is null for Rahu/Ketu - see NODE_NOTE."""
    if graha in NODES:
        return {"label": None, "score": 0, "reason": NODE_NOTE, "dispositor": sign_info(sign - 1)["lord"],
                "exact_exaltation_degrees_away": None}
    label, reason = _dignity_label(graha, sign, degree)
    exalt_sign, exalt_degree = EXALTATION[graha]
    exact = None
    if label in ("exalted", "debilitated"):
        exact = round(abs(degree - exalt_degree), 4)
    return {
        "label": label,
        "score": DIGNITY_SCORE[label],
        "reason": reason,
        "dispositor": sign_info(sign - 1)["lord"],  # the lord of the sign it sits in
        "exact_exaltation_degrees_away": exact,  # how far from the deep point, when exalted/debilitated
    }


def graha_dignities(chart: dict) -> dict:
    """Per-graha combustion + dignity + lordship for a computed chart, keyed by graha.

    Extends (does not duplicate) the `lordships` block app/ai/compact.py already builds: the same
    `rules_houses` / `in_own_sign` / `sign_lord` fields are here under the same meaning, plus the
    dignity label, combustion and the natural benefic/malefic class.
    """
    sun_longitude = chart["grahas"]["Sun"]["longitude"]
    moon_elongation = elongation(chart["grahas"]["Moon"]["longitude"], sun_longitude)
    table = {}
    for key in GRAHA_KEYS:
        position = chart["grahas"][key]
        sign = position["sign"]["index"]
        rules = [] if key in NODES else [h["house"] for h in chart["houses"] if h["sign"]["lord"] == key]
        table[key] = {
            "graha": graha_name(key),
            "sign": position["sign"],
            "degree": position["degree"],
            "house_from_lagna": position["house"],
            "retrograde": position["retrograde"],
            "rules_houses": rules,
            "in_own_sign": sign in OWN_SIGNS.get(key, ()),
            "sign_lord": position["sign"]["lord"],
            "dignity": dignity(key, sign, position["degree"]),
            "combustion": combustion(key, position["longitude"], sun_longitude, position["retrograde"]),
            "natural_class": _natural_class(key, moon_elongation),
        }
    return table


def _natural_class(graha: str, moon_elongation: float) -> dict:
    """Natural benefic/malefic. Jupiter and Venus are benefic, Saturn/Mars/Sun/Rahu/Ketu malefic.
    The Moon is benefic while it is BRIGHT - classically from the 4th tithi of the waxing fortnight to
    the 4th of the waning one, i.e. 36° to 216° of elongation from the Sun - and malefic while it is
    dark. Elongation is directed, so a Moon 50° BEFORE the Sun (waning, near amavasya) is correctly
    read as dark even though it is the same 50° away as a waxing Moon would be. Mercury takes the
    nature of what it joins, so it is reported as "variable" rather than guessed at.
    """
    if graha == "Moon":
        low, high = BRIGHT_MOON_ELONGATION
        bright = low <= moon_elongation < high
        return {"class": "benefic" if bright else "malefic",
                "reason": f"Chandra is {moon_elongation:.1f}° ahead of Surya; tradition treats "
                          f"{low:g}°-{high:g}° (the bright fortnight) as benefic"}
    if graha == "Mercury":
        return {"class": "variable", "reason": "Budha takes the nature of the grahas it is joined with or aspected by"}
    if graha in BENEFICS:
        return {"class": "benefic", "reason": "natural benefic"}
    return {"class": "malefic", "reason": "natural malefic"}
