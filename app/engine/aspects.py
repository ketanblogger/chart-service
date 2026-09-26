"""Graha drishti (aspects) and the three ways two grahas can be "associated".

Whole-sign (rashi) drishti, the convention this platform uses everywhere:

    every graha aspects the 7th sign from itself (full aspect)
    Mangal additionally the 4th and the 8th
    Guru additionally the 5th and the 9th
    Shani additionally the 3rd and the 10th

That is the special-aspect set of Brihat Parashara Hora Shastra. Graded/partial drishti (the
1/4, 1/2, 3/4 values used in Ashtakavarga and Bhava Bala) is NOT computed: nothing in the report
needs a fraction, and a fraction would only invite the AI to editorialise about it.

Rahu and Ketu: the texts disagree. BPHS gives the nodes no drishti of their own; later authorities
give them the 5th, 7th and 9th, and a few give the 3rd and 10th. `aspects()` returns the 5/7/9 set
for the nodes but flags it `disputed: true`, and no yoga rule in this engine is allowed to depend on
a nodal aspect - a yoga that would only exist because of one is simply not emitted.

"Association" (sambandha), which is what the Raj/Dhana yoga rules test for, is one of:
  - conjunction (yuti): both grahas in the same sign;
  - mutual aspect (paraspara drishti): each aspects the other's sign;
  - exchange (parivartana): each sits in a sign owned by the other.
One-sided aspect alone is not an association here - that is the stricter, more defensible reading,
and it is stated on every yoga this engine emits.
"""

from .constants import GRAHA_KEYS, graha_name, sign_info
from .core import house_from
from .dignity import NODES, OWN_SIGNS

# graha -> the houses it aspects counted from its own sign (1 = its own sign, never aspected).
SPECIAL_ASPECTS = {
    "Mars": (4, 7, 8),
    "Jupiter": (5, 7, 9),
    "Saturn": (3, 7, 10),
}
DEFAULT_ASPECTS = (7,)
NODE_ASPECTS = (5, 7, 9)
NODE_ASPECT_NOTE = ("The nodes' drishti is disputed: BPHS gives Rahu and Ketu no aspect of their own, "
                    "later authorities give them the 5th, 7th and 9th. The 5/7/9 set is reported, but no "
                    "yoga in this engine is triggered by a nodal aspect alone.")

ASPECT_RULE = ("Whole-sign drishti: every graha aspects the 7th sign from itself; "
               "Mangal also the 4th and 8th, Guru the 5th and 9th, Shani the 3rd and 10th")


def aspected_houses(graha: str) -> tuple[int, ...]:
    """Houses aspected, counted from the graha's own sign."""
    if graha in NODES:
        return NODE_ASPECTS
    return SPECIAL_ASPECTS.get(graha, DEFAULT_ASPECTS)


def aspects_sign(graha: str, graha_sign: int, target_sign: int) -> bool:
    """Does `graha` (sitting in `graha_sign`, 1-12) cast drishti on `target_sign` (1-12)?"""
    return house_from(graha_sign, target_sign) in aspected_houses(graha)


def graha_aspects(chart: dict) -> dict:
    """Per graha: the signs and houses it aspects, and which other grahas fall under that drishti."""
    signs = {key: chart["grahas"][key]["sign"]["index"] for key in GRAHA_KEYS}
    lagna_sign = chart["lagna"]["sign"]["index"]
    table = {}
    for key in GRAHA_KEYS:
        targets = sorted(
            {(signs[key] - 1 + offset - 1) % 12 + 1 for offset in aspected_houses(key)}
        )
        table[key] = {
            "graha": graha_name(key),
            "aspects_from_own_sign": list(aspected_houses(key)),
            "aspected_signs": [sign_info(s - 1) for s in targets],
            "aspected_houses_from_lagna": sorted(house_from(lagna_sign, s) for s in targets),
            "aspects_grahas": sorted(other for other in GRAHA_KEYS
                                     if other != key and signs[other] in targets),
            "disputed": key in NODES,
        }
        if key in NODES:
            table[key]["note"] = NODE_ASPECT_NOTE
    table["rule"] = ASPECT_RULE
    return table


# --- association (sambandha) ------------------------------------------------------------------

def conjunct(signs: dict[str, int], a: str, b: str) -> bool:
    return signs[a] == signs[b]


def mutual_aspect(signs: dict[str, int], a: str, b: str) -> bool:
    """Both aspect each other. Never true through a node - see NODE_ASPECT_NOTE."""
    if a in NODES or b in NODES:
        return False
    return aspects_sign(a, signs[a], signs[b]) and aspects_sign(b, signs[b], signs[a])


def exchange(signs: dict[str, int], a: str, b: str) -> bool:
    """Parivartana: each graha sits in a sign owned by the other. Nodes own nothing, so never true."""
    if a in NODES or b in NODES:
        return False
    return signs[a] in OWN_SIGNS[b] and signs[b] in OWN_SIGNS[a]


def association(signs: dict[str, int], a: str, b: str) -> str | None:
    """"conjunction" | "mutual_aspect" | "exchange" | None, in that order of precedence."""
    if a == b:
        return None
    if conjunct(signs, a, b):
        return "conjunction"
    if exchange(signs, a, b):
        return "exchange"
    if mutual_aspect(signs, a, b):
        return "mutual_aspect"
    return None


ASSOCIATION_TEXT = {
    "conjunction": "are together in the same sign",
    "exchange": "sit in each other's signs (parivartana)",
    "mutual_aspect": "aspect each other",
}


def chart_graha_signs(chart: dict) -> dict[str, int]:
    return {key: chart["grahas"][key]["sign"]["index"] for key in GRAHA_KEYS}
