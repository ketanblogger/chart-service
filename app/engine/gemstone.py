"""Gemstone (ratna) recommendation, computed from the chart - data only.

RULE SET (lagna-lord / "jeevan ratna" school, the one standard Indian gem-astrology practice follows,
as set out in the navaratna chapters of Jataka Parijata and reproduced in every modern ratna manual):

  1. Life stone (jeevan / janma ratna) = the gemstone of the LAGNA LORD. The lagna lord is held never
     to harm the native whatever else it rules, so its stone is the one safe lifelong stone.
  2. Fortune stone (bhagya ratna) = the gemstone of the 9TH LORD.
  3. Benefic/wisdom stone (ishta ratna) = the gemstone of the 5TH LORD.
     Where two of those lordships fall on the same graha, the stone is listed once, at the highest role.
  4. Stones to avoid = the gemstones of the lords of the 6TH, 8TH and 12TH houses - EXCEPT any graha
     that also lords the 1st, 5th or 9th, because rule 1/2/3 takes precedence over rule 4 for a graha
     that serves both roles. (This precedence is why, for a Simha lagna, Guru - who rules the 5th and
     the 8th - is recommended rather than avoided.)
  5. Rahu and Ketu own no sign, so they can never be selected by lordship. Their stones (gomed,
     lehsunia) are therefore never recommended by this engine; they are listed under
     `not_selected_by_this_rule` so the report can explain why they are absent instead of the reader
     wondering.

Only the rule and its output are computed here. The report must present all of it as TRADITIONAL
PRACTICE - faith-based, optional, and to be taken up with a practitioner - never as an instruction to
buy anything. `presentation` carries that wording so it cannot be dropped by accident.

Weight guidance is in ratti (the traditional unit, ~0.91 carat / ~0.1215 g) as the classical ranges
give it, with the carat equivalent alongside. Wearing day, metal and finger are the conventional
assignments that accompany each stone in the same literature.
"""

from .constants import graha_name, sign_info

RATTI_IN_CARATS = 0.91

# graha -> stone, in the traditional accompaniment: metal, finger, weekday, ratti range, beej mantra.
STONES = {
    "Sun": {
        "stone": "Ruby", "sanskrit": "Manikya", "devanagari": "माणिक्य",
        "metal": "gold or copper", "finger": "ring finger", "day": "Sunday",
        "ratti": (3, 5), "mantra": "ॐ ह्रां ह्रीं ह्रौं सः सूर्याय नमः",
    },
    "Moon": {
        "stone": "Pearl", "sanskrit": "Mukta / Moti", "devanagari": "मोती",
        "metal": "silver", "finger": "little finger", "day": "Monday",
        "ratti": (4, 6), "mantra": "ॐ श्रां श्रीं श्रौं सः चन्द्राय नमः",
    },
    "Mars": {
        "stone": "Red Coral", "sanskrit": "Moonga / Praval", "devanagari": "मूंगा",
        "metal": "gold or copper", "finger": "ring finger", "day": "Tuesday",
        "ratti": (6, 9), "mantra": "ॐ क्रां क्रीं क्रौं सः भौमाय नमः",
    },
    "Mercury": {
        "stone": "Emerald", "sanskrit": "Panna / Marakata", "devanagari": "पन्ना",
        "metal": "gold", "finger": "little finger", "day": "Wednesday",
        "ratti": (3, 6), "mantra": "ॐ ब्रां ब्रीं ब्रौं सः बुधाय नमः",
    },
    "Jupiter": {
        "stone": "Yellow Sapphire", "sanskrit": "Pushparaga / Pukhraj", "devanagari": "पुखराज",
        "metal": "gold", "finger": "index finger", "day": "Thursday",
        "ratti": (5, 7), "mantra": "ॐ ग्रां ग्रीं ग्रौं सः गुरवे नमः",
    },
    "Venus": {
        "stone": "Diamond", "sanskrit": "Vajra / Heera", "devanagari": "हीरा",
        "metal": "silver or platinum", "finger": "middle finger", "day": "Friday",
        "ratti": (1, 2), "mantra": "ॐ द्रां द्रीं द्रौं सः शुक्राय नमः",
        "substitute": "white sapphire (safed pukhraj) or white zircon, where a diamond is out of reach",
    },
    "Saturn": {
        "stone": "Blue Sapphire", "sanskrit": "Neelam", "devanagari": "नीलम",
        "metal": "silver, iron or panchdhatu", "finger": "middle finger", "day": "Saturday",
        "ratti": (4, 7), "mantra": "ॐ प्रां प्रीं प्रौं सः शनैश्चराय नमः",
    },
    "Rahu": {
        "stone": "Hessonite", "sanskrit": "Gomed", "devanagari": "गोमेद",
        "metal": "silver", "finger": "middle finger", "day": "Saturday",
        "ratti": (6, 9), "mantra": "ॐ भ्रां भ्रीं भ्रौं सः राहवे नमः",
    },
    "Ketu": {
        "stone": "Cat's Eye", "sanskrit": "Vaidurya / Lehsunia", "devanagari": "लहसुनिया",
        "metal": "silver", "finger": "ring finger", "day": "Wednesday",
        "ratti": (5, 7), "mantra": "ॐ स्रां स्रीं स्रौं सः केतवे नमः",
    },
}

ROLES = {
    1: ("life_stone", "Life stone (jeevan ratna) - the lagna lord's gemstone"),
    9: ("fortune_stone", "Fortune stone (bhagya ratna) - the 9th lord's gemstone"),
    5: ("benefic_stone", "Benefic stone (ishta ratna) - the 5th lord's gemstone"),
}
AVOID_HOUSES = (6, 8, 12)
FAVOURED_HOUSES = (1, 5, 9)

RULE_SET = ("Lagna-lord ratna rule: life stone from the lagna lord, fortune stone from the 9th lord, "
            "benefic stone from the 5th lord; the stones of the 6th, 8th and 12th lords are avoided "
            "unless the same graha also rules the 1st, 5th or 9th, in which case the favourable "
            "lordship takes precedence")

PRESENTATION = ("Traditional faith-based practice. Present as what tradition suggests, always optional, "
                "and to be taken up with a practitioner - never as a purchase instruction, never as a "
                "promise of a result, and never as a substitute for medical, legal or financial advice.")

WEARING_NOTE = ("Tradition has a stone set in the named metal and first worn on the named weekday, in the "
                "morning of the bright fortnight (shukla paksha), after the graha's beej mantra is recited.")


def _entry(graha: str, role_key: str, role_text: str, house: int, sign: dict) -> dict:
    stone = STONES[graha]
    low, high = stone["ratti"]
    return {
        "role": role_key,
        "role_description": role_text,
        "graha": graha_name(graha),
        "stone": stone["stone"],
        "sanskrit": stone["sanskrit"],
        "devanagari": stone["devanagari"],
        "metal": stone["metal"],
        "finger": stone["finger"],
        "day": stone["day"],
        "weight": {
            "ratti": [low, high],
            "carats": [round(low * RATTI_IN_CARATS, 2), round(high * RATTI_IN_CARATS, 2)],
            "guidance": f"{low}-{high} ratti ({low * RATTI_IN_CARATS:.2f}-{high * RATTI_IN_CARATS:.2f} carats), "
                        "the classical range; a practitioner fixes the exact weight",
        },
        "mantra": stone["mantra"],
        "substitute": stone.get("substitute"),
        "because": f"{graha_name(graha)['name']} rules house {house} ({sign['name']}) in this chart",
    }


def gemstones(chart: dict) -> dict:
    """The gemstone block for a computed chart. Deterministic - the same chart always gives the same list."""
    lord_of = {h["house"]: h["sign"]["lord"] for h in chart["houses"]}
    sign_of = {h["house"]: h["sign"] for h in chart["houses"]}

    recommended, taken = [], set()
    for house, (role_key, role_text) in ROLES.items():
        lord = lord_of[house]
        if lord in taken:
            continue
        taken.add(lord)
        recommended.append(_entry(lord, role_key, role_text, house, sign_of[house]))

    avoid = []
    for house in AVOID_HOUSES:
        lord = lord_of[house]
        if lord in taken:
            continue  # rule 4: a favourable lordship takes precedence
        taken.add(lord)
        stone = STONES[lord]
        avoid.append({
            "graha": graha_name(lord),
            "stone": stone["stone"],
            "sanskrit": stone["sanskrit"],
            "devanagari": stone["devanagari"],
            "because": f"{graha_name(lord)['name']} rules house {house} ({sign_of[house]['name']}), "
                       "one of the difficult houses, and rules none of the 1st, 5th or 9th",
        })

    overridden = [
        {"graha": graha_name(lord_of[house]), "dusthana": house,
         "also_rules": sorted(h for h in FAVOURED_HOUSES if lord_of[h] == lord_of[house]),
         "note": f"{graha_name(lord_of[house])['name']} rules the {house}th but also a favourable house, "
                 "so its stone is recommended rather than avoided"}
        for house in AVOID_HOUSES
        if any(lord_of[h] == lord_of[house] for h in FAVOURED_HOUSES)
    ]

    return {
        "rule_set": RULE_SET,
        "presentation": PRESENTATION,
        "wearing_note": WEARING_NOTE,
        "lagna": chart["lagna"]["sign"],
        "primary": recommended[0],
        "recommended": recommended,
        "avoid": avoid,
        "precedence_applied": overridden,
        "not_selected_by_this_rule": {
            "grahas": ["Rahu", "Ketu"],
            "reason": "Rahu and Ketu own no sign, so no house lordship can select their stones "
                      "(gomed, lehsunia) under this rule set",
        },
    }
