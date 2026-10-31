"""Yoga detection - only combinations that can be stated crisply, tested, and shown to the reader
with the exact placement that triggered them.

Every yoga this module emits carries:
    key / name / devanagari   what to call it
    rule                      the definition this engine uses, in words
    combination               the placement in THIS chart that satisfied the rule
    strength                  "strong" | "moderate" | "mild", from documented modifiers only
    nature                    "benefic" | "challenging"
    grahas / houses           everything the reader must be told about

Nothing is invented. Where authorities disagree the chosen definition is named in `rule` and the
reason is in this docstring. No yoga is ever triggered by a nodal aspect (see aspects.py).

House groups used throughout: kendra 1/4/7/10, trikona 1/5/9, dusthana 6/8/12,
"association" = conjunction, exchange (parivartana) or mutual aspect (aspects.association).

DEFINITIONS AND THE CHOICES BEHIND THEM
---------------------------------------
Raj yoga (kendra-trikona). BPHS: a lord of a kendra and a lord of a trikona in association give a
  raja yoga. Implemented exactly so, for pairs of DIFFERENT grahas; one graha owning both a kendra
  and a trikona is not a "pair" but a yogakaraka and is emitted separately. Aspect must be MUTUAL -
  the looser "either aspects the other" version would fire on almost every chart.

Yogakaraka. A single graha lording one of the kendras 4/7/10 AND one of the trikonas 5/9. House 1 is
  excluded from both sides here because the lagna lord trivially "lords a kendra and a trikona" in
  every chart, which would make the label meaningless. On this definition only Mars (Karka, Simha
  lagna), Venus (Makara, Kumbha lagna) and Saturn (Vrishabha, Tula lagna) can be yogakaraka.

Dhana yoga. Association between a lord of the wealth houses (2nd, 11th) and a lord of 1st/5th/9th,
  or between the 2nd and 11th lords themselves. This is the common Parashari reading; wider lists
  (adding the 3rd, or single-lord placements) are in circulation and are NOT used, because they fire
  on most charts and would make the claim worthless.

Gajakesari. Guru in a kendra (1/4/7/10) FROM THE MOON. Strength is graded by Guru's own dignity and
  combustion - the strict versions that demand an undebilitated, uncombust Guru are represented by
  that grading rather than by suppressing the yoga.

Budhaditya. Surya and Budha in the same sign. Because Budha is nearly always within 14° of Surya
  when they share a sign, combustion is the norm rather than the exception; it is reported as a
  strength modifier, never silently ignored.

Chandra-Mangal. Chandra and Mangal in the same sign. Conjunction only - the "or mutual aspect"
  variant is not used.

Pancha Mahapurusha. Mangal/Budha/Guru/Shukra/Shani in its OWN sign (including its moolatrikona) or
  its EXALTATION sign, AND in a kendra from the lagna: Ruchaka / Bhadra / Hamsa / Malavya / Sasa.
  Kendra from the lagna is the standard requirement; whether it is also a kendra from the Moon is
  reported as an extra, not required.

Neecha Bhanga Raja Yoga. A debilitated graha whose debilitation is cancelled. The five classical
  cancellation conditions are tested and the ones that fired are listed, so the report can say WHY:
    a) the lord of the sign of debilitation is in a kendra from the lagna or from the Moon
    b) the graha exalted in that sign is in a kendra from the lagna or from the Moon
    c) the debilitated graha is joined by, or aspected by, its dispositor
    d) the debilitated graha is aspected by the graha exalted in that sign
    e) the debilitated graha occupies its own exaltation sign in navamsa
  In (a) and (b), "kendra from the Moon" is not counted when the graha in question IS the Moon: it is
  always in the 1st from itself, and counting that would make the yoga automatic for every chart with
  Mangal in Karka or Shani in Mesha.
  With no condition satisfied, no yoga is emitted (the debilitation itself is reported by
  dignity.py and picked up as a caution by highlights.py).

Vipreeta Raja Yoga. A lord of the 6th, 8th or 12th placed in the 6th, 8th or 12th: Harsha (6th
  lord), Sarala (8th lord), Vimala (12th lord). Some authorities require the lord to be in a
  dusthana OTHER than its own; that is reported as `in_own_dusthana` and used to grade strength
  rather than to suppress the yoga. When the same graha also rules a kendra or trikona, that is
  listed in `also_rules` with a caution, because the yoga then cuts both ways.

Kemadruma. No graha in the 2nd or the 12th from the Moon, and none with the Moon. Surya, Rahu and
  Ketu do not count as company for this purpose - that is the usual modern reading and it is the
  stricter one (it makes the yoga MORE likely, so the cancellations below carry the weight).
  Cancellations (kemadruma bhanga) tested: Chandra in a kendra from the lagna; any graha in a kendra
  from the Moon; Chandra joined or aspected by a natural benefic; Chandra in its own or exaltation
  sign. Emitted with `cancellations`; strength drops to "mild" when any applies.

Shakata. Chandra in the 6th, 8th or 12th from Guru. Cancellation: Chandra in a kendra from the
  lagna. Emitted with the cancellation flagged; strength "mild" when cancelled.

Kaal Sarp. All seven grahas (Surya, Chandra, Mangal, Budha, Guru, Shukra, Shani) inside one half of
  the zodiac bounded by the Rahu-Ketu axis. "full" when every one of the seven lies strictly inside
  the arc; "partial" when they all lie in the arc but at least one is within 1° of Rahu or of Ketu,
  i.e. sitting on the axis itself. The 12 traditional names follow Rahu's house from the lagna.
  When the seven are hemmed on the KETU-to-Rahu side instead, `arc` says so - several traditions
  call that arrangement Kaal Amrit rather than Kaal Sarp, so the name is reported as
  "Kaal Sarp (reverse arc)" and the dispute is stated on the yoga itself.

Pitra dosha. Definitions vary widely; ONE is used here and named on the yoga:
  Surya conjunct Rahu or Ketu in the same sign, OR Rahu or Ketu placed in the 9th house from the
  lagna, OR the 9th lord conjunct Rahu or Ketu. (The Surya/Rahu-and-9th-house reading, which is the
  most commonly published one.) Conditions that fired are listed. Variants that add Shani's
  affliction of Surya or the 9th, or that require a specific navamsa, are NOT used.

Parivartana (exchange). Two grahas each occupying a sign owned by the other. Classified by the two
  houses involved: Dainya when either is a dusthana, Khala when either is the 3rd, otherwise Maha.
"""

from .aspects import ASSOCIATION_TEXT, aspects_sign, association, chart_graha_signs, conjunct
from .constants import GRAHA_KEYS, graha_name, sign_info
from .core import house_from
from .dignity import EXALTATION, NODES

KENDRA = (1, 4, 7, 10)
TRIKONA = (1, 5, 9)
DUSTHANA = (6, 8, 12)
WEALTH_HOUSES = (2, 11)
NON_NODES = tuple(k for k in GRAHA_KEYS if k not in NODES)
SEVEN = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")

MAHAPURUSHA = {
    "Mars": ("ruchaka", "Ruchaka Yoga", "रुचक योग"),
    "Mercury": ("bhadra", "Bhadra Yoga", "भद्र योग"),
    "Jupiter": ("hamsa", "Hamsa Yoga", "हंस योग"),
    "Venus": ("malavya", "Malavya Yoga", "मालव्य योग"),
    "Saturn": ("sasa", "Sasa Yoga", "शश योग"),
}
VIPREETA = {6: ("harsha", "Harsha Yoga", "हर्ष योग"), 8: ("sarala", "Sarala Yoga", "सरल योग"),
            12: ("vimala", "Vimala Yoga", "विमल योग")}
KAAL_SARP_TYPES = {
    1: ("Ananta", "अनंत"), 2: ("Kulika", "कुलिक"), 3: ("Vasuki", "वासुकि"), 4: ("Shankhapala", "शंखपाल"),
    5: ("Padma", "पद्म"), 6: ("Mahapadma", "महापद्म"), 7: ("Takshaka", "तक्षक"), 8: ("Karkotaka", "कर्कोटक"),
    9: ("Shankhachuda", "शंखचूड"), 10: ("Ghataka", "घातक"), 11: ("Vishdhara", "विषधर"), 12: ("Sheshnag", "शेषनाग"),
}
PARIVARTANA_KINDS = {"maha": ("Maha Parivartana Yoga", "महा परिवर्तन योग"),
                     "khala": ("Khala Parivartana Yoga", "खल परिवर्तन योग"),
                     "dainya": ("Dainya Parivartana Yoga", "दैन्य परिवर्तन योग")}

AXIS_ORB_DEGREES = 1.0  # a graha this close to Rahu/Ketu counts as sitting on the axis


class _Chart:
    """Everything the rules below need, looked up once."""

    def __init__(self, chart: dict, navamsa: dict, dignities: dict):
        self.chart = chart
        self.navamsa = navamsa
        self.dignities = dignities
        self.signs = chart_graha_signs(chart)
        self.lagna_sign = chart["lagna"]["sign"]["index"]
        self.moon_sign = self.signs["Moon"]
        self.house = {key: chart["grahas"][key]["house"] for key in GRAHA_KEYS}
        self.house_from_moon = {key: house_from(self.moon_sign, self.signs[key]) for key in GRAHA_KEYS}
        self.rules = {key: dignities[key]["rules_houses"] for key in GRAHA_KEYS}
        self.lord_of = {h["house"]: h["sign"]["lord"] for h in chart["houses"]}

    def label(self, key: str) -> str | None:
        return self.dignities[key]["dignity"]["label"]

    def combust(self, key: str) -> bool:
        return bool(self.dignities[key]["combustion"]["combust"])

    def placement(self, key: str) -> str:
        return (f"{graha_name(key)['name']} in {sign_info(self.signs[key] - 1)['name']} "
                f"(house {self.house[key]} from the lagna, house {self.house_from_moon[key]} from the Moon)")


def _graha_ref(engine: _Chart, key: str) -> dict:
    """The block every yoga uses to name a graha - both house counts, always, both labelled."""
    return {
        **graha_name(key),
        "sign": sign_info(engine.signs[key] - 1),
        "house_from_lagna": engine.house[key],
        "house_from_moon": engine.house_from_moon[key],
        "rules_houses": engine.rules[key],
        "dignity": engine.label(key),
        "combust": engine.combust(key),
    }


def _yoga(key, name, devanagari, category, nature, rule, combination, strength, engine, grahas, houses, **extra) -> dict:
    return {
        "key": key,
        "name": name,
        "devanagari": devanagari,
        "category": category,
        "nature": nature,
        "strength": strength,
        "rule": rule,
        "combination": combination,
        "grahas": [_graha_ref(engine, g) for g in grahas],
        "houses": sorted(set(houses)),
        **extra,
    }


def _grade(engine: _Chart, keys, base: str = "strong") -> str:
    """Documented downgrade: any participating graha debilitated or combust drops one step."""
    order = ["mild", "moderate", "strong"]
    level = order.index(base)
    for key in keys:
        if engine.label(key) == "debilitated" or engine.combust(key):
            level -= 1
    return order[max(level, 0)]


# --- individual rules ---------------------------------------------------------------------------

def _raj_yogas(engine: _Chart) -> list[dict]:
    out = []
    for i, a in enumerate(NON_NODES):
        for b in NON_NODES[i + 1:]:
            kendra_a = [h for h in engine.rules[a] if h in KENDRA]
            trikona_b = [h for h in engine.rules[b] if h in TRIKONA]
            kendra_b = [h for h in engine.rules[b] if h in KENDRA]
            trikona_a = [h for h in engine.rules[a] if h in TRIKONA]
            if not ((kendra_a and trikona_b) or (kendra_b and trikona_a)):
                continue
            how = association(engine.signs, a, b)
            if how is None:
                continue
            kendra_houses = kendra_a if (kendra_a and trikona_b) else kendra_b
            trikona_houses = trikona_b if (kendra_a and trikona_b) else trikona_a
            out.append(_yoga(
                "raj_yoga", "Raj Yoga", "राज योग", "raj", "benefic",
                "A lord of a kendra (1/4/7/10) and a lord of a trikona (1/5/9) in association "
                "(conjunction, exchange or mutual aspect)",
                f"{graha_name(a)['name']} (rules {engine.rules[a]}) and {graha_name(b)['name']} "
                f"(rules {engine.rules[b]}) {ASSOCIATION_TEXT[how]}",
                _grade(engine, (a, b), "strong" if how in ("conjunction", "exchange") else "moderate"),
                engine, (a, b), kendra_houses + trikona_houses + [engine.house[a], engine.house[b]],
                association=how, kendra_houses=sorted(kendra_houses), trikona_houses=sorted(trikona_houses),
            ))
    return out


def _yogakaraka(engine: _Chart) -> list[dict]:
    out = []
    for key in NON_NODES:
        kendras = [h for h in engine.rules[key] if h in (4, 7, 10)]
        trikonas = [h for h in engine.rules[key] if h in (5, 9)]
        if not (kendras and trikonas):
            continue
        out.append(_yoga(
            "yogakaraka", "Yogakaraka", "योगकारक", "raj", "benefic",
            "One graha lords both a kendra (4/7/10) and a trikona (5/9) for this lagna "
            "(house 1 excluded, since the lagna lord would qualify in every chart)",
            f"{graha_name(key)['name']} rules the {kendras} and {trikonas} houses; it is placed in "
            f"house {engine.house[key]} from the lagna",
            _grade(engine, (key,)), engine, (key,), kendras + trikonas + [engine.house[key]],
        ))
    return out


def _dhana_yogas(engine: _Chart) -> list[dict]:
    out = []
    for i, a in enumerate(NON_NODES):
        for b in NON_NODES[i + 1:]:
            wealth_a = [h for h in engine.rules[a] if h in WEALTH_HOUSES]
            wealth_b = [h for h in engine.rules[b] if h in WEALTH_HOUSES]
            trikona_a = [h for h in engine.rules[a] if h in TRIKONA]
            trikona_b = [h for h in engine.rules[b] if h in TRIKONA]
            if not ((wealth_a and (trikona_b or wealth_b)) or (wealth_b and (trikona_a or wealth_a))):
                continue
            how = association(engine.signs, a, b)
            if how is None:
                continue
            houses = sorted(set(wealth_a + wealth_b + trikona_a + trikona_b))
            out.append(_yoga(
                "dhana_yoga", "Dhana Yoga", "धन योग", "dhana", "benefic",
                "A lord of the wealth houses (2nd, 11th) in association with a lord of the 1st, 5th or 9th, "
                "or the 2nd and 11th lords in association",
                f"{graha_name(a)['name']} (rules {engine.rules[a]}) and {graha_name(b)['name']} "
                f"(rules {engine.rules[b]}) {ASSOCIATION_TEXT[how]}",
                _grade(engine, (a, b), "strong" if how in ("conjunction", "exchange") else "moderate"),
                engine, (a, b), houses + [engine.house[a], engine.house[b]], association=how,
            ))
    return out


def _gajakesari(engine: _Chart) -> list[dict]:
    house = engine.house_from_moon["Jupiter"]
    if house not in KENDRA:
        return []
    return [_yoga(
        "gajakesari", "Gajakesari Yoga", "गजकेसरी योग", "benefic_combination", "benefic",
        "Guru in a kendra (1st, 4th, 7th or 10th) counted FROM THE MOON",
        f"Guru is in house {house} from the Moon ({sign_info(engine.signs['Jupiter'] - 1)['name']}); "
        f"from the lagna that is house {engine.house['Jupiter']}",
        _grade(engine, ("Jupiter",)), engine, ("Jupiter", "Moon"),
        [engine.house["Jupiter"], engine.house["Moon"]], house_from_moon=house,
    )]


def _budhaditya(engine: _Chart) -> list[dict]:
    if not conjunct(engine.signs, "Sun", "Mercury"):
        return []
    return [_yoga(
        "budhaditya", "Budhaditya Yoga", "बुधादित्य योग", "benefic_combination", "benefic",
        "Surya and Budha in the same sign",
        f"Surya and Budha are together in {sign_info(engine.signs['Sun'] - 1)['name']}, "
        f"house {engine.house['Sun']} from the lagna",
        _grade(engine, ("Sun", "Mercury")), engine, ("Sun", "Mercury"), [engine.house["Sun"]],
        mercury_combust=engine.combust("Mercury"),
    )]


def _chandra_mangal(engine: _Chart) -> list[dict]:
    if not conjunct(engine.signs, "Moon", "Mars"):
        return []
    return [_yoga(
        "chandra_mangal", "Chandra-Mangal Yoga", "चंद्र-मंगल योग", "dhana", "benefic",
        "Chandra and Mangal in the same sign (conjunction only)",
        f"Chandra and Mangal are together in {sign_info(engine.signs['Moon'] - 1)['name']}, "
        f"house {engine.house['Moon']} from the lagna",
        _grade(engine, ("Moon", "Mars")), engine, ("Moon", "Mars"), [engine.house["Moon"]],
    )]


def _mahapurusha(engine: _Chart) -> list[dict]:
    out = []
    for key, (slug, name, devanagari) in MAHAPURUSHA.items():
        label = engine.label(key)
        if label not in ("own_sign", "moolatrikona", "exalted") or engine.house[key] not in KENDRA:
            continue
        out.append(_yoga(
            f"mahapurusha_{slug}", name, devanagari, "mahapurusha", "benefic",
            "One of the Pancha Mahapurusha yogas: the graha is in its own sign (or moolatrikona) or "
            "exaltation sign AND in a kendra (1/4/7/10) from the lagna",
            f"{graha_name(key)['name']} is {label.replace('_', ' ')} in "
            f"{sign_info(engine.signs[key] - 1)['name']}, in house {engine.house[key]} from the lagna",
            _grade(engine, (key,)), engine, (key,), [engine.house[key]],
            dignity=label, also_kendra_from_moon=engine.house_from_moon[key] in KENDRA,
        ))
    return out


def _neecha_bhanga(engine: _Chart) -> list[dict]:
    out = []
    for key in NON_NODES:
        if engine.label(key) != "debilitated":
            continue
        sign = engine.signs[key]
        dispositor = sign_info(sign - 1)["lord"]
        exalted_here = next((g for g, (s, _) in EXALTATION.items() if s == sign), None)

        def in_kendra(other: str) -> bool:
            """From the lagna, or from the Moon. The Moon is always in the 1st from itself, so for the
            Moon only the lagna count is used - otherwise the condition would fire automatically on
            every chart where the Moon happens to be the dispositor or the exalted graha."""
            if engine.house[other] in KENDRA:
                return True
            return other != "Moon" and engine.house_from_moon[other] in KENDRA

        conditions = [
            {"key": "dispositor_in_kendra",
             "description": f"the lord of the sign of debilitation ({dispositor}) is in a kendra from the lagna or the Moon",
             "applies": in_kendra(dispositor)},
            {"key": "exalted_graha_in_kendra",
             "description": (f"the graha exalted in that sign ({exalted_here}) is in a kendra from the lagna or the Moon"
                             if exalted_here else "no graha is exalted in that sign, so this condition cannot apply"),
             "applies": bool(exalted_here) and in_kendra(exalted_here)},
            {"key": "joined_or_aspected_by_dispositor",
             "description": f"the debilitated graha is joined by or aspected by its dispositor ({dispositor})",
             "applies": engine.signs[dispositor] == sign or aspects_sign(dispositor, engine.signs[dispositor], sign)},
            {"key": "aspected_by_exalted_graha",
             "description": (f"the debilitated graha is aspected by {exalted_here}, which is exalted in that sign"
                             if exalted_here else "no graha is exalted in that sign, so this condition cannot apply"),
             "applies": bool(exalted_here) and aspects_sign(exalted_here, engine.signs[exalted_here], sign)},
            {"key": "exalted_in_navamsa",
             "description": "the debilitated graha occupies its own exaltation sign in the navamsa (D9)",
             "applies": engine.navamsa["grahas"][key]["sign"]["index"] == EXALTATION[key][0]},
        ]
        fired = [c for c in conditions if c["applies"]]
        if not fired:
            continue
        out.append(_yoga(
            "neecha_bhanga_raja_yoga", "Neecha Bhanga Raja Yoga", "नीच भंग राज योग", "raj", "benefic",
            "A debilitated graha whose debilitation is cancelled by at least one of the five classical "
            "conditions (dispositor or the sign's exalted graha in a kendra; the debilitated graha joined "
            "or aspected by either; or the debilitated graha exalted in navamsa)",
            f"{graha_name(key)['name']} is debilitated in {sign_info(sign - 1)['name']} "
            f"(house {engine.house[key]} from the lagna); " + "; ".join(c["description"] for c in fired),
            "strong" if len(fired) >= 2 else "moderate", engine, (key,), [engine.house[key]],
            cancellation_conditions=conditions, conditions_met=[c["key"] for c in fired],
        ))
    return out


def _vipreeta(engine: _Chart) -> list[dict]:
    out = []
    for house, (slug, name, devanagari) in VIPREETA.items():
        lord = engine.lord_of[house]
        if lord in NODES or engine.house[lord] not in DUSTHANA:
            continue
        also = [h for h in engine.rules[lord] if h not in DUSTHANA]
        out.append(_yoga(
            f"vipreeta_{slug}", f"Vipreeta Raja Yoga - {name}", f"विपरीत राज योग - {devanagari}",
            "vipreeta", "benefic",
            "The lord of the 6th, 8th or 12th placed in the 6th, 8th or 12th (Harsha / Sarala / Vimala)",
            f"the {house}th lord {graha_name(lord)['name']} is in house {engine.house[lord]} from the lagna",
            "moderate" if engine.house[lord] == house else _grade(engine, (lord,)),
            engine, (lord,), [house, engine.house[lord]],
            dusthana_ruled=house, in_own_dusthana=engine.house[lord] == house, also_rules=also,
            caution=(f"{graha_name(lord)['name']} also rules house(s) {also}, whose matters are weakened by the "
                     "same placement" if also else None),
        ))
    return out


def _kemadruma(engine: _Chart) -> list[dict]:
    neighbours = {(engine.moon_sign - 2) % 12 + 1, engine.moon_sign, engine.moon_sign % 12 + 1}
    company = [k for k in NON_NODES if k not in ("Moon", "Sun") and engine.signs[k] in neighbours]
    if company:
        return []
    benefic_touch = [k for k in ("Jupiter", "Venus")
                     if engine.signs[k] == engine.moon_sign or aspects_sign(k, engine.signs[k], engine.moon_sign)]
    cancellations = [
        {"key": "moon_in_kendra_from_lagna", "description": "Chandra is in a kendra from the lagna",
         "applies": engine.house["Moon"] in KENDRA},
        {"key": "graha_in_kendra_from_moon", "description": "a graha occupies a kendra from Chandra",
         "applies": any(engine.house_from_moon[k] in KENDRA for k in NON_NODES if k != "Moon")},
        {"key": "benefic_joins_or_aspects_moon", "description": "Guru or Shukra joins or aspects Chandra",
         "applies": bool(benefic_touch)},
        {"key": "moon_dignified", "description": "Chandra is in its own sign, moolatrikona or exaltation sign",
         "applies": engine.label("Moon") in ("own_sign", "moolatrikona", "exalted")},
    ]
    fired = [c for c in cancellations if c["applies"]]
    return [_yoga(
        "kemadruma", "Kemadruma Yoga", "केमद्रुम योग", "lunar", "challenging",
        "No graha (other than Surya, Rahu and Ketu) in the 2nd or the 12th from Chandra, and none with Chandra",
        f"Chandra is alone in {sign_info(engine.moon_sign - 1)['name']}: the signs on either side "
        f"({sign_info((engine.moon_sign - 2) % 12)['name']} and {sign_info(engine.moon_sign % 12)['name']}) "
        "are empty of grahas as well",
        "mild" if fired else "moderate", engine, ("Moon",), [engine.house["Moon"]],
        cancellations=cancellations, cancellations_met=[c["key"] for c in fired],
        framing="A quiet, self-reliant placement. Report it as a tendency to carry things alone, never as misfortune.",
    )]


def _shakata(engine: _Chart) -> list[dict]:
    house = house_from(engine.signs["Jupiter"], engine.moon_sign)
    if house not in DUSTHANA:
        return []
    cancelled = engine.house["Moon"] in KENDRA
    return [_yoga(
        "shakata", "Shakata Yoga", "शकट योग", "lunar", "challenging",
        "Chandra in the 6th, 8th or 12th from Guru; cancelled when Chandra is in a kendra from the lagna",
        f"Chandra is in house {house} counted from Guru "
        f"({sign_info(engine.moon_sign - 1)['name']} against Guru in {sign_info(engine.signs['Jupiter'] - 1)['name']})",
        "mild" if cancelled else "moderate", engine, ("Moon", "Jupiter"),
        [engine.house["Moon"], engine.house["Jupiter"]],
        moon_house_from_jupiter=house, cancelled_by_moon_in_kendra=cancelled,
        framing="Read as fortunes that rise and dip in cycles, and as a reason to plan for the dips - never as failure.",
    )]


def _kaal_sarp(engine: _Chart) -> list[dict]:
    longitudes = {k: engine.chart["grahas"][k]["longitude"] for k in GRAHA_KEYS}
    rahu, ketu = longitudes["Rahu"], longitudes["Ketu"]

    def inside(start: float) -> bool:
        return all((longitudes[k] - start) % 360 < 180 for k in SEVEN)

    if inside(rahu):
        arc, arc_text = "rahu_to_ketu", "from Rahu forward to Ketu"
    elif inside(ketu):
        arc, arc_text = "ketu_to_rahu", "from Ketu forward to Rahu"
    else:
        return []
    on_axis = [k for k in SEVEN
               if min((longitudes[k] - rahu) % 360, (rahu - longitudes[k]) % 360,
                      (longitudes[k] - ketu) % 360, (ketu - longitudes[k]) % 360) <= AXIS_ORB_DEGREES]
    kind = "partial" if on_axis else "full"
    rahu_house = engine.house["Rahu"]
    type_name, type_devanagari = KAAL_SARP_TYPES[rahu_house]
    reverse = arc == "ketu_to_rahu"
    return [_yoga(
        "kaal_sarp", "Kaal Sarp Yoga" + (" (reverse arc)" if reverse else ""),
        "काल सर्प योग", "dosha", "challenging",
        "All seven grahas (Surya to Shani) inside the half of the zodiac bounded by the Rahu-Ketu axis; "
        "\"full\" when all seven are strictly inside, \"partial\" when one or more sits within 1° of the axis",
        f"all seven grahas lie in the arc {arc_text}; Rahu is in house {rahu_house} from the lagna "
        f"({sign_info(engine.signs['Rahu'] - 1)['name']}), which is the {type_name} type"
        + (f"; {', '.join(graha_name(k)['name'] for k in on_axis)} sits on the axis itself" if on_axis else ""),
        "moderate" if kind == "full" else "mild", engine, ("Rahu", "Ketu"),
        [rahu_house, engine.house["Ketu"]],
        kind=kind, arc=arc, type=type_name, type_devanagari=type_devanagari,
        grahas_on_axis=on_axis,
        disputed=("Several traditions call the Ketu-to-Rahu arrangement Kaal Amrit rather than Kaal Sarp; "
                  "the arc is reported so the text can say which it is." if reverse else None),
        framing="Report as a chart that concentrates its energy in one half of life's areas - focus and "
                "intensity, plus the remedies tradition attaches. Never as a curse, never as danger.",
    )]


def _pitra_dosha(engine: _Chart) -> list[dict]:
    ninth_lord = engine.lord_of[9]
    conditions = [
        {"key": "sun_with_node",
         "description": "Surya is in the same sign as Rahu or Ketu",
         "applies": engine.signs["Sun"] in (engine.signs["Rahu"], engine.signs["Ketu"])},
        {"key": "node_in_ninth",
         "description": "Rahu or Ketu occupies the 9th house from the lagna",
         "applies": 9 in (engine.house["Rahu"], engine.house["Ketu"])},
        {"key": "ninth_lord_with_node",
         "description": f"the 9th lord ({ninth_lord}) is in the same sign as Rahu or Ketu",
         "applies": ninth_lord not in NODES
                    and engine.signs[ninth_lord] in (engine.signs["Rahu"], engine.signs["Ketu"])},
    ]
    fired = [c for c in conditions if c["applies"]]
    if not fired:
        return []
    return [_yoga(
        "pitra_dosha", "Pitra Dosha", "पितृ दोष", "dosha", "challenging",
        "ONE definition is used, of the several in circulation: Surya with Rahu or Ketu, or a node in the "
        "9th house, or the 9th lord with a node. Variants involving Shani's affliction of Surya or of the "
        "9th, or navamsa conditions, are not applied.",
        "; ".join(c["description"] for c in fired),
        "moderate" if len(fired) >= 2 else "mild", engine, ("Sun", "Rahu", "Ketu"),
        [9, engine.house["Sun"], engine.house["Rahu"]],
        conditions=conditions, conditions_met=[c["key"] for c in fired],
        definition_note="Definitions of Pitra dosha differ between authorities; this is the commonly published "
                        "Surya/Rahu-and-9th-house reading, and the report must present it as such.",
        framing="Frame entirely as remedy and remembrance of ancestors (shraddha, daan, tarpan). "
                "No blame, no fear, never a claim about any living relative.",
    )]


def _parivartana(engine: _Chart) -> list[dict]:
    out = []
    for i, a in enumerate(NON_NODES):
        for b in NON_NODES[i + 1:]:
            if association(engine.signs, a, b) != "exchange":
                continue
            house_a, house_b = engine.house[a], engine.house[b]
            if house_a in DUSTHANA or house_b in DUSTHANA:
                kind = "dainya"
            elif 3 in (house_a, house_b):
                kind = "khala"
            else:
                kind = "maha"
            name, devanagari = PARIVARTANA_KINDS[kind]
            out.append(_yoga(
                f"parivartana_{kind}", name, devanagari, "parivartana",
                "benefic" if kind == "maha" else "challenging",
                "Two grahas each occupying a sign owned by the other. Dainya when either of the two houses "
                "is a dusthana (6/8/12), Khala when either is the 3rd, otherwise Maha.",
                f"{graha_name(a)['name']} is in house {house_a} and {graha_name(b)['name']} in house {house_b}; "
                "each sits in a sign the other rules",
                _grade(engine, (a, b), "strong" if kind == "maha" else "moderate"),
                engine, (a, b), [house_a, house_b], kind=kind,
            ))
    return out


_RULES = (_raj_yogas, _yogakaraka, _dhana_yogas, _gajakesari, _budhaditya, _chandra_mangal,
          _mahapurusha, _neecha_bhanga, _vipreeta, _kemadruma, _shakata, _kaal_sarp,
          _pitra_dosha, _parivartana)

_STRENGTH_RANK = {"strong": 0, "moderate": 1, "mild": 2}
_CATEGORY_RANK = {"mahapurusha": 0, "raj": 1, "dhana": 2, "benefic_combination": 3, "vipreeta": 4,
                  "parivartana": 5, "lunar": 6, "dosha": 7}


def yogas(chart: dict, navamsa: dict, dignities: dict) -> list[dict]:
    """All detected yogas for a chart, sorted strongest-and-most-auspicious first. Empty when none apply.

    `navamsa` is varga.navamsa_chart(chart); `dignities` is dignity.graha_dignities(chart).
    """
    engine = _Chart(chart, navamsa, dignities)
    found = [yoga for rule in _RULES for yoga in rule(engine)]
    found.sort(key=lambda y: (_STRENGTH_RANK[y["strength"]], _CATEGORY_RANK.get(y["category"], 9),
                              y["key"], y["combination"]))
    return found
