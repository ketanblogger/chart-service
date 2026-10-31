"""Significance ranking for the highlights page - its top three strengths and top three cautions.

Picks THIS chart's top three strengths and top three cautions from computed facts only, and hands the
AI the reason data for each so it can write one line without inventing anything.

HOW THE RANKING WORKS. Every candidate below contributes a factor with an integer score. Scores are
fixed constants in `WEIGHTS`, the modifiers are listed on each factor in `evidence.modifiers`, and
the final order is `(-score, key)` - `key` is unique per factor, so the sort is total and the same
chart always yields the same three. Nothing is random, nothing is "chosen by feel", and
`all_factors` carries every candidate that scored, so a longer report can go deeper without a second
ranking pass.

WHAT COUNTS AS A STRENGTH
  benefic yogas (graded by the yoga's own strength and category)
  a graha exalted, in moolatrikona or in its own sign - more when it also sits in a kendra/trikona
  a vargottama graha (same sign in D1 and D9)
  the lagna lord well placed and undamaged
  Guru or Shukra in a kendra or trikona
  the mahadasha lord running NOW being well placed (this is the "dasha relevance" term - a strength
  the native can act on this year outranks one that is dormant)

WHAT COUNTS AS A CAUTION
  challenging yogas (Kaal Sarp, Pitra dosha, Kemadruma, Shakata, Dainya/Khala parivartana)
  a debilitated graha whose debilitation is NOT cancelled (a cancelled one is a strength instead)
  a combust graha, more when it is the lagna lord or the running dasha lord
  Mangal dosha, graded by intensity and softened by its cancellations
  sade-sati or dhaiya running now, graded by phase
  the lagna lord, Chandra, or the 2nd/11th/7th lord in a dusthana
  the running mahadasha or antardasha lord damaged (debilitated, combust or in a dusthana)

SAFETY, ENFORCED IN THE DATA. Every caution carries `safety` and a `frame`. No caution is ever about
death or illness: the health-related ones are flagged `health_related: true` and carry an explicit
`framing` string telling the writer to treat them as TIMING AND LIFESTYLE - rest, routine, ordinary
prudence - never as a condition, a diagnosis or a severity. A caution with no constructive reading
available is not emitted at all.
"""

from datetime import date

from .constants import sign_info
from .dignity import DIGNITY_SCORE
from .timeline import HOUSE_AREAS, areas_for, date_range, graha_facts

KENDRA = (1, 4, 7, 10)
TRIKONA = (1, 5, 9)
DUSTHANA = (6, 8, 12)
TOP_N = 3

WEIGHTS = {
    "yoga_strength": {"strong": 9, "moderate": 6, "mild": 4},
    "yoga_category_bonus": {"mahapurusha": 2, "raj": 2, "dhana": 1, "vipreeta": 1,
                            "benefic_combination": 1, "parivartana": 0, "lunar": 0, "dosha": 0},
    "dignity": {"exalted": 7, "moolatrikona": 6, "own_sign": 5},
    "dignified_in_kendra_trikona": 2,
    "dignified_combust": -2,
    "dignified_in_dusthana": -1,
    "vargottama": 3,
    "lagna_lord_well_placed": 6,
    "benefic_in_kendra_trikona": 4,
    "dasha_lord_strong": 5,
    # cautions
    "debilitated": 7,
    "combust": 4,
    "combust_deep": 2,
    "combust_key_graha": 2,
    "mangal_dosha": {"high": 8, "medium": 6, "low": 5, "none": 0},
    "mangal_dosha_cancelled": -2,
    "sade_sati": {"peak": 8, "rising": 6, "setting": 5},
    "sade_sati_upcoming": 4,
    "dhaiya": 5,
    "lord_in_dusthana": {1: 6, 2: 5, 7: 5, 11: 5},
    "moon_in_dusthana": 5,
    "dasha_lord_damaged": 6,
}

SAFETY = ("Constructive framing only. Never death, never serious illness, never a diagnosis or a "
          "prognosis. Write it as a caution to prepare for, or an opportunity to handle with care.")
HEALTH_FRAMING = ("Health-related: write it strictly as TIMING AND LIFESTYLE - rest, routine, regular "
                  "checkups, not overcommitting in this window. Never name a condition, never imply "
                  "severity, never suggest anything medical.")

_CHALLENGING_KEYS = ("kaal_sarp", "pitra_dosha", "kemadruma", "shakata",
                     "parivartana_dainya", "parivartana_khala")
_HEALTH_HOUSES = (1, 6, 8)


def _areas(houses) -> list[str]:
    out = []
    for house in sorted(set(houses)):
        for area in HOUSE_AREAS[house]:
            if area not in out:
                out.append(area)
    return out


def _areas(factor_houses) -> list[str]:
    """Just the area keys - the factor already names its houses, so the weights add nothing here."""
    return [entry["area"] for entry in areas_for(factor_houses)]


def _factor(key, kind, score, title, reason, houses, grahas, facts, *, modifiers=(),
            health_related=False, frame="opportunity", **evidence) -> dict:
    houses = sorted({h for h in houses if h})
    out = {
        "key": key,
        "kind": kind,
        "score": score,
        "title": title,
        "reason": reason,
        "houses": houses,
        "life_areas": _areas(houses),
        "areas": _areas(houses),
        "pillars": _areas(houses),  # deprecated alias, read by app/ai/compact.py; see timeline.PILLARS
        "grahas": [facts[g] for g in grahas],
        "frame": frame,
        "evidence": {"modifiers": list(modifiers), **evidence},
    }
    if kind == "caution":
        out["safety"] = SAFETY
        out["health_related"] = health_related
        if health_related:
            out["framing"] = HEALTH_FRAMING
    return out


def _strength_factors(chart, dignities, navamsa, yoga_list, facts, current) -> list[dict]:
    out = []
    lagna_sign = chart["lagna"]["sign"]["index"]
    lagna_lord = sign_info(lagna_sign - 1)["lord"]

    for yoga in yoga_list:
        if yoga["nature"] != "benefic":
            continue
        score = WEIGHTS["yoga_strength"][yoga["strength"]] + WEIGHTS["yoga_category_bonus"].get(yoga["category"], 0)
        grahas = [g["key"] for g in yoga["grahas"]]
        out.append(_factor(
            f"yoga:{yoga['key']}:{'+'.join(grahas)}", "strength", score,
            yoga["name"], yoga["combination"], yoga["houses"], grahas, facts,
            modifiers=[f"yoga strength {yoga['strength']}", f"category {yoga['category']}"],
            yoga_key=yoga["key"], devanagari=yoga["devanagari"], rule=yoga["rule"],
        ))

    for key, entry in dignities.items():
        label = entry["dignity"]["label"]
        if label not in WEIGHTS["dignity"]:
            continue
        score = WEIGHTS["dignity"][label]
        modifiers = []
        house = entry["house_from_lagna"]
        if house in KENDRA or house in TRIKONA:
            score += WEIGHTS["dignified_in_kendra_trikona"]
            modifiers.append(f"in house {house}, a kendra/trikona")
        if house in DUSTHANA:
            score += WEIGHTS["dignified_in_dusthana"]
            modifiers.append(f"in house {house}, a difficult house")
        if entry["combustion"]["combust"]:
            score += WEIGHTS["dignified_combust"]
            modifiers.append("combust (close to Surya)")
        out.append(_factor(
            f"dignity:{key}", "strength", score,
            f"{entry['graha']['name']} is {label.replace('_', ' ')}",
            f"{entry['graha']['name']} is {entry['dignity']['reason']}, in house {house} from the lagna, "
            f"and rules house(s) {entry['rules_houses']}",
            [house, *entry["rules_houses"]], [key], facts, modifiers=modifiers, dignity=label,
        ))

    for key in navamsa["vargottama"]:
        entry = dignities[key]
        score = WEIGHTS["vargottama"] + (1 if entry["dignity"]["label"] in WEIGHTS["dignity"] else 0)
        out.append(_factor(
            f"vargottama:{key}", "strength", score,
            f"{entry['graha']['name']} is vargottama",
            f"{entry['graha']['name']} holds the same sign ({entry['sign']['name']}) in the birth chart "
            "and in the navamsa, which tradition reads as a placement that keeps its promise",
            [entry["house_from_lagna"], *entry["rules_houses"]], [key], facts,
            modifiers=["same sign in D1 and D9"],
        ))

    lord_entry = dignities[lagna_lord]
    lord_house = lord_entry["house_from_lagna"]
    if (lord_house in KENDRA or lord_house in TRIKONA) and not lord_entry["combustion"]["combust"] \
            and DIGNITY_SCORE.get(lord_entry["dignity"]["label"], 0) >= 0:
        out.append(_factor(
            f"lagna_lord:{lagna_lord}", "strength", WEIGHTS["lagna_lord_well_placed"],
            f"The lagna lord {lord_entry['graha']['name']} is well placed",
            f"{lord_entry['graha']['name']} rules the lagna ({sign_info(lagna_sign - 1)['name']}) and sits "
            f"in house {lord_house} from the lagna, {lord_entry['dignity']['reason']}, and is not combust",
            [1, lord_house, *lord_entry["rules_houses"]], [lagna_lord], facts,
            modifiers=[f"house {lord_house}", lord_entry["dignity"]["label"] or "no dignity label"],
        ))

    for key in ("Jupiter", "Venus"):
        house = dignities[key]["house_from_lagna"]
        if house not in KENDRA and house not in TRIKONA:
            continue
        out.append(_factor(
            f"benefic_angle:{key}", "strength", WEIGHTS["benefic_in_kendra_trikona"],
            f"{dignities[key]['graha']['name']} occupies a strong house",
            f"{dignities[key]['graha']['name']}, a natural benefic, is in house {house} from the lagna "
            f"({'a kendra' if house in KENDRA else 'a trikona'}) and rules house(s) {dignities[key]['rules_houses']}",
            [house, *dignities[key]["rules_houses"]], [key], facts, modifiers=[f"house {house}"],
        ))

    if current:
        key = current["mahadasha"]["lord"]["key"]
        entry = dignities[key]
        house = entry["house_from_lagna"]
        if (DIGNITY_SCORE.get(entry["dignity"]["label"], 0) >= 3 or house in KENDRA or house in TRIKONA) \
                and not entry["combustion"]["combust"] and entry["dignity"]["label"] != "debilitated":
            out.append(_factor(
                f"dasha_lord_strong:{key}", "strength", WEIGHTS["dasha_lord_strong"],
                f"The mahadasha running now belongs to {entry['graha']['name']}, and it is well placed",
                f"the {entry['graha']['name']} mahadasha runs {current['mahadasha']['start']} to "
                f"{current['mahadasha']['end']}; {entry['graha']['name']} is in house {house} from the lagna, "
                f"{entry['dignity']['reason']}, and rules house(s) {entry['rules_houses']}",
                [house, *entry["rules_houses"]], [key], facts, frame="timing",
                modifiers=["currently running mahadasha"],
                period=date_range(*_dates(current["mahadasha"])),
            ))
    return out


def _dates(period):
    return date.fromisoformat(period["start"]), date.fromisoformat(period["end"])


def _caution_factors(chart, dignities, navamsa, yoga_list, facts, current, sade_sati, dhaiya) -> list[dict]:
    out = []
    lagna_sign = chart["lagna"]["sign"]["index"]
    lord_of = {h["house"]: h["sign"]["lord"] for h in chart["houses"]}
    cancelled = {g["key"] for y in yoga_list if y["key"] == "neecha_bhanga_raja_yoga" for g in y["grahas"]}

    for yoga in yoga_list:
        if yoga["key"] not in _CHALLENGING_KEYS:
            continue
        score = WEIGHTS["yoga_strength"][yoga["strength"]]
        grahas = [g["key"] for g in yoga["grahas"]]
        health = bool(set(yoga["houses"]) & set(_HEALTH_HOUSES))
        out.append(_factor(
            f"yoga:{yoga['key']}", "caution", score, yoga["name"], yoga["combination"],
            yoga["houses"], grahas, facts, modifiers=[f"yoga strength {yoga['strength']}"],
            health_related=health, frame="effort", yoga_key=yoga["key"],
            devanagari=yoga["devanagari"], rule=yoga["rule"], framing_from_engine=yoga.get("framing"),
        ))

    for key, entry in dignities.items():
        if entry["dignity"]["label"] == "debilitated" and key not in cancelled:
            house = entry["house_from_lagna"]
            out.append(_factor(
                f"debilitated:{key}", "caution", WEIGHTS["debilitated"],
                f"{entry['graha']['name']} is debilitated",
                f"{entry['graha']['name']} is {entry['dignity']['reason']}, sits in house {house} from the "
                f"lagna and rules house(s) {entry['rules_houses']}; none of the classical cancellation "
                "conditions apply, so its matters need extra effort rather than luck",
                [house, *entry["rules_houses"]], [key], facts, frame="effort",
                modifiers=["no neecha bhanga"],
                health_related=bool({house, *entry["rules_houses"]} & set(_HEALTH_HOUSES)),
            ))
        if entry["combustion"]["combust"]:
            house = entry["house_from_lagna"]
            score = WEIGHTS["combust"]
            modifiers = [f"within {entry['combustion']['separation_degrees']}° of Surya, "
                         f"orb {entry['combustion']['orb_degrees']}°"]
            if entry["combustion"].get("deeply_combust"):
                score += WEIGHTS["combust_deep"]
                modifiers.append("within 1° of Surya")
            key_roles = [role for role, graha in
                         (("lagna lord", lord_of[1]),
                          ("running mahadasha lord", current["mahadasha"]["lord"]["key"] if current else None))
                         if graha == key]
            if key_roles:
                score += WEIGHTS["combust_key_graha"]
                modifiers.append("it is the " + " and the ".join(key_roles))
            out.append(_factor(
                f"combust:{key}", "caution", score,
                f"{entry['graha']['name']} is combust",
                f"{entry['graha']['name']} is within {entry['combustion']['separation_degrees']}° of Surya "
                f"(the classical orb is {entry['combustion']['orb_degrees']}°), in house {house} from the "
                f"lagna, ruling house(s) {entry['rules_houses']}; tradition reads a combust graha as one "
                "whose results come late or need pushing",
                [house, *entry["rules_houses"]], [key], facts, frame="effort", modifiers=modifiers,
                health_related=bool({house, *entry["rules_houses"]} & set(_HEALTH_HOUSES)),
            ))

    mangal = chart["mangal_dosha"]
    if mangal["present"]:
        score = WEIGHTS["mangal_dosha"][mangal["intensity"]]
        modifiers = [f"intensity {mangal['intensity']}"]
        if mangal["cancellation_applies"]:
            score += WEIGHTS["mangal_dosha_cancelled"]
            modifiers.append("mitigating factors apply")
        out.append(_factor(
            "mangal_dosha", "caution", score, "Mangal dosha is present",
            "Mangal falls in a dosha house counted from "
            + ", ".join(ref for ref in ("lagna", "moon", "venus") if mangal[f"from_{ref}"]["dosha"])
            + f"; intensity {mangal['intensity']}"
            + (", with classical mitigating factors" if mangal["cancellation_applies"] else ""),
            [7, dignities["Mars"]["house_from_lagna"]], ["Mars"], facts, frame="effort",
            modifiers=modifiers, intensity=mangal["intensity"],
            mitigated=mangal["cancellation_applies"],
        ))

    if sade_sati.get("active"):
        phase = sade_sati["phase"]
        out.append(_factor(
            f"sade_sati:{phase}", "caution", WEIGHTS["sade_sati"][phase],
            f"Sade Sati is running - {phase} phase",
            f"Shani is in {sade_sati['saturn_sign']['name']}, house {sade_sati['saturn_house_from_moon']} "
            f"from the Moon sign; the cycle runs {sade_sati['cycle']['start']} to {sade_sati['cycle']['end']}",
            [1, 12, 2], ["Saturn", "Moon"], facts, frame="timing", health_related=True,
            modifiers=[f"phase {phase}"], period=date_range(*_dates(sade_sati["cycle"])),
            phase=phase, phases=sade_sati["cycle"]["periods"],
        ))
    elif sade_sati.get("cycle", {}).get("which") == "next":
        out.append(_factor(
            "sade_sati:upcoming", "caution", WEIGHTS["sade_sati_upcoming"],
            "Sade Sati has not started yet",
            f"the next Sade Sati cycle runs {sade_sati['cycle']['start']} to {sade_sati['cycle']['end']}; "
            "there is time to prepare for it",
            [1, 12, 2], ["Saturn", "Moon"], facts, frame="timing", health_related=False,
            modifiers=["cycle is in the future"], period=date_range(*_dates(sade_sati["cycle"])),
        ))

    if dhaiya and dhaiya.get("active"):
        out.append(_factor(
            f"dhaiya:{dhaiya['kind']}", "caution", WEIGHTS["dhaiya"],
            f"Shani dhaiya is running ({dhaiya['kind']} from the Moon sign)",
            f"Shani is in {dhaiya['saturn_sign']['name']}, house {dhaiya['saturn_house_from_moon']} from "
            f"the Moon sign, from {dhaiya['period']['start']} to {dhaiya['period']['end']}",
            [4 if dhaiya["kind"] == "fourth" else 8], ["Saturn", "Moon"], facts, frame="timing",
            health_related=True, modifiers=[f"dhaiya {dhaiya['kind']}"],
            period=date_range(*_dates(dhaiya["period"])),
        ))

    for house, weight in WEIGHTS["lord_in_dusthana"].items():
        lord = lord_of[house]
        placed = dignities[lord]["house_from_lagna"]
        if placed not in DUSTHANA:
            continue
        out.append(_factor(
            f"lord_in_dusthana:{house}:{lord}", "caution", weight,
            f"The {house}th lord {dignities[lord]['graha']['name']} sits in a difficult house",
            f"{dignities[lord]['graha']['name']} rules house {house} and is placed in house {placed} from "
            f"the lagna, so that area asks for steady effort rather than easy gains",
            [house, placed], [lord], facts, frame="effort", modifiers=[f"house {house} lord in house {placed}"],
            # flagged on the house RULED, not on where the lord landed: the 11th lord sitting in the
            # 6th is a money-and-effort matter, not a health one.
            health_related=house in _HEALTH_HOUSES,
        ))

    moon_house = dignities["Moon"]["house_from_lagna"]
    if moon_house in DUSTHANA:
        out.append(_factor(
            "moon_in_dusthana", "caution", WEIGHTS["moon_in_dusthana"],
            "Chandra occupies a difficult house",
            f"Chandra is in house {moon_house} from the lagna; tradition reads this as a mind that carries "
            "more than it shows, and asks for rest and routine",
            [moon_house], ["Moon"], facts, frame="lifestyle", health_related=True,
            modifiers=[f"house {moon_house}"],
        ))

    if current:
        for level in ("mahadasha", "antardasha"):
            key = current[level]["lord"]["key"]
            entry = dignities[key]
            house = entry["house_from_lagna"]
            damage = []
            if entry["dignity"]["label"] == "debilitated" and key not in cancelled:
                damage.append("debilitated")
            if entry["combustion"]["combust"]:
                damage.append("combust")
            if house in DUSTHANA:
                damage.append(f"in house {house}, a difficult house")
            if not damage:
                continue
            out.append(_factor(
                f"dasha_lord_damaged:{level}:{key}", "caution", WEIGHTS["dasha_lord_damaged"],
                f"The {level} running now belongs to {entry['graha']['name']}, which is under pressure",
                f"the {entry['graha']['name']} {level} runs {current[level]['start']} to "
                f"{current[level]['end']}; {entry['graha']['name']} is " + ", ".join(damage)
                + f", and rules house(s) {entry['rules_houses']}",
                [house, *entry["rules_houses"]], [key], facts, frame="timing",
                modifiers=damage, health_related=bool({house, *entry["rules_houses"]} & set(_HEALTH_HOUSES)),
                period=date_range(*_dates(current[level])),
            ))
    return out


def highlights(chart: dict, dignities: dict, navamsa: dict, yoga_list: list,
               dhaiya: dict | None = None) -> dict:
    """Top strengths and cautions for the highlights page, plus every candidate that scored."""
    facts = graha_facts(chart, dignities, navamsa)
    current = chart["dasha"].get("current")
    strengths = _strength_factors(chart, dignities, navamsa, yoga_list, facts, current)
    cautions = _caution_factors(chart, dignities, navamsa, yoga_list, facts, current,
                                chart["sade_sati"], dhaiya)
    order = lambda factor: (-factor["score"], factor["key"])  # noqa: E731 - total, so deterministic
    strengths.sort(key=order)
    cautions.sort(key=order)
    return {
        "method": ("Deterministic scoring over computed facts only; see app/engine/highlights.py. "
                   "Ties break on the factor key, so the same chart always yields the same three."),
        "weights": WEIGHTS,
        "safety": SAFETY,
        "health_framing": HEALTH_FRAMING,
        "top_strengths": strengths[:TOP_N],
        "top_cautions": cautions[:TOP_N],
        "all_strengths": strengths,
        "all_cautions": cautions,
    }
