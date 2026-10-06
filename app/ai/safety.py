"""Code-level safety screen for AI-written text: en / hi / mr.

The prompt already forbids these topics; this is the backstop. It screens only AI-written strings
(never our own disclaimer). A hit triggers a regeneration, and if the last attempt still has hits
the offending paragraph / bullet / remedy is removed (see report.py).

Devanagari note: Python's `\\b` breaks inside Devanagari words (matras are not `\\w`), so Devanagari
terms use an explicit "not preceded by a Devanagari letter" guard instead and allow any inflected ending.
That guard is also what keeps मरण from matching inside स्मरण / नामस्मरण.
"""

import re
from dataclasses import dataclass

# A commerce word within a few dozen characters of a stone, in either order. One sentence at a
# time: the `[^.;!?\n]` run never crosses a full stop, so two innocent sentences cannot combine.
_STONES = r"stones?|gem\w*|sapphires?|rub(?:y|ies)|emeralds?|corals?|pearls?|topaz|neelam|pukhraj|pushparaj|panna|moonga|mo[ot]i|mukta|gomed|lehsunia|manikya|manik|navratna|cat'?s eye"
_COMMERCE = r"buy|buying|bought|purchas\w+|order|price[sd]?|pricing|costs?|rupees|jeweller\w*|jewelr\w*|shop|store|supplier|website|online|discount|deal|energi[sz]\w+|consecrat\w+"
_NEAR_STONE = (rf"\b(?:{_COMMERCE})\b[^.;!?\n]{{0,45}}?\b(?:{_STONES})\b|"
               rf"\b(?:{_STONES})\b[^.;!?\n]{{0,45}}?\b(?:{_COMMERCE})\b")

_EN = {
    "death": r"\b(?:deaths?|die[sd]?|dying|demise|passing away|pass(?:es)? away|fatal(?:ly|ity)?|funeral|"
             r"suicid\w*|murder\w*|killed|life[- ]threatening|lifespan|life span|longevity|short life|"
             r"maraka|untimely end|end of (?:your|his|her|their) life|widow\w*)\b",
    "illness": r"\b(?:tumou?rs?|heart attacks?|cardiac arrest|strokes?(?! of (?:luck|fortune|genius|insight))|paralysis|paralys\w+|terminal(?:ly)? ill\w*|"
               r"incurable|chronic (?:illness|disease)\w*|serious (?:illness|disease|health)\w*|"
               r"severe (?:illness|disease)\w*|kidney failure|organ failure|surgery|surgeries|"
               r"hospitali[sz]\w+|miscarriage\w*|infertil\w+|diabet\w+|hiv|dementia|"
               r"cancerous|cancer (?:patient|disease|diagnos\w+|treatment|risk)|"
               r"(?:risk|chance|danger|diagnos\w+|signs?) of cancer|(?:get|gets|develop|develops) cancer)\b",
    "catastrophe": r"\b(?:accidents?|accidental|catastroph\w+|disasters?|calamit\w+|bankrupt\w*|imprison\w*|"
                   r"jail\w*|prison|divorc\w*|separation from (?:your )?spouse|litigation|lawsuits?|cursed?|doomed)\b",
    # Selling, of any kind. Blocked everywhere, INCLUDING in the gemstone chapter: a stone may be
    # named there, but never priced, sourced, "energised" for a fee, or turned into a purchase.
    # Carats and ratti are deliberately absent - the engine itself supplies a classical weight range.
    "hard_sell": r"\b(?:yantras?|paid puja|book a puja|paid homa|"
                 r"consult (?:a|an|your|another) (?:pandit|priest|astrologer|jyotish\w*))\b|"
                 + _NEAR_STONE,
    # Fear as a sales tool: "wear it or else". Blocked everywhere.
    "gem_fear": r"\b(?:without (?:this|the) (?:stone|gem\w*)|if you do not wear|unless you wear|"
                r"failing to wear|not wearing (?:this|it|the stone)|must wear|have to wear|compulsor\w+ to wear)\b",
}

# Gemstone talk itself. Allowed ONLY in the gemstone chapter of the flagship book, and only when the
# engine actually computed a recommendation (the book's Part F asks for a gemstone, which reverses the
# old blanket ban). Everywhere else - other chapters, the other three products, the consultation chat - it is a hit.
_EN_GEMSTONE = {
    "gemstone": r"\b(?:gemstones?|gem stones?|blue sapphires?|yellow sapphires?|neelam|pukhraj|pushparaj|"
                r"ruby|rubies|emeralds?|panna|red corals?|moonga|pearls?|moti|cat'?s eye|lehsunia|"
                r"hessonite|gomed|navratna)\b",
}

_D = r"(?<![ऀ-ॿ])"  # not preceded by a Devanagari character

_DEVANAGARI = {
    # shared by Hindi and Marathi, then language-specific spellings
    "death": _D + r"(?:मृत्यु|मृत्यू|मौत|मरण|निधन|देहांत|देहान्त|देहावसान|अपमृत्यू|अकाल मृत्यु|अल्पायु|आयुष्य कमी|"
                  r"आयु कम|मारक|जानलेवा|जीवघेण|प्राणघातक|आत्महत्या|विधवा|विधुर|वैधव्य)",
    "illness": _D + r"(?:कर्करोग|कैंसर|कॅन्सर|कँसर|ट्यूमर|हृदयाघात|दिल का दौरा|हार्ट अटैक|हार्ट अटॅक|"
                    r"हृदयविकाराचा झटका|हृदयविकार|पक्षाघात|अर्धांगवायू|लकवा|गंभीर बीमारी|गंभीर रोग|गंभीर आजार|"
                    r"दुर्धर आजार|असाध्य|लाइलाज|शस्त्रक्रिया|शल्यक्रिया|शल्य क्रिया|सर्जरी|ऑपरेशन|गर्भपात|"
                    r"वंध्यत्व|बांझपन|मधुमेह|डायबिटीज)",
    "catastrophe": _D + r"(?:दुर्घटना|एक्सीडेंट|हादसा|हादसे|अपघात|घटस्फोट|तलाक|दिवालिया|दिवाला|दिवाळखोर|दिवाळे|"
                        r"जेल|कारावास|तुरुंग|तुरुंगवास|मुकदमा|मुकदमे|खटला|खटले|शापित|अभागा|अभागी|कमनशिबी)",
    "hard_sell": _D + r"(?:यंत्र खरीद|यंत्र विकत|यंत्र घ्या|सशुल्क पूजा|पूजा बुक|"
                      r"(?:किंमत|किमत|कीमत|रुपये|रुपए|कॅरेट|कैरेट|रत्ती|सराफ|दुकान|विक्रेत|ऑनलाइन|ऑनलाईन)"
                      r"[^।.;!?\n]{0,30}(?:रत्न|नग|खडा|खडे)|"
                      r"(?:रत्न|नग|खडा|खडे)[^।.;!?\n]{0,30}"
                      r"(?:किंमत|किमत|कीमत|रुपये|रुपए|कॅरेट|कैरेट|रत्ती|सराफ|दुकान|विक्रेत|ऑनलाइन|ऑनलाईन|"
                      r"खरेदी|खरीद|विकत घ्या|अभिमंत्रित))",
    "gem_fear": _D + r"(?:(?:रत्न|नग|खडा)[^।.;!?\n]{0,25}(?:घातल्याशिवाय|पहने बिना|बिना पहने)|"
                     r"(?:घातलेच पाहिजे|धारण करावेच|पहनना ही होगा|पहनना अनिवार्य))",
}

_DEVANAGARI_GEMSTONE = {
    "gemstone": _D + r"(?:रत्न(?!ागिरी)|नीलम|पुखराज|पुष्कराज|माणिक|माणिक्य|पाचू|पन्ना|मूंगा|पोवळे|गोमेद|"
                     r"लहसुनिया|लसण्या|मोती)",
}

def _compiled(latin: dict, devanagari: dict) -> list:
    return [(category, re.compile(pattern, re.IGNORECASE)) for category, pattern in latin.items()] + [
        (category, re.compile(pattern)) for category, pattern in devanagari.items()
    ]


_PATTERNS = _compiled(_EN, _DEVANAGARI)
_GEMSTONE_PATTERNS = _compiled(_EN_GEMSTONE, _DEVANAGARI_GEMSTONE)


@dataclass(frozen=True)
class SafetyHit:
    category: str  # death | illness | catastrophe | hard_sell | gem_fear | gemstone
    term: str


# ---- negation: a deliberate four-way asymmetry, not an oversight ----------------------------------
#
# "…as an optional practice rather than a purchase, and the engine has identified three stones…" is
# the opposite of a sale, and the commerce/stone proximity rule read it as one - the second time a
# negation blind spot cost a paid regeneration. It is handled here the way `check_own_sign` handles
# it in app/ai/validator.py.
#
# The asymmetry below looks like an inconsistency and is not. Before "fixing" it, read this:
#
#   hard_sell                  NEGATED. It is a rule about intent, and "not a purchase" inverts the
#                              intent completely.
#   death / illness /          NOT negated, on purpose. These are forbidden as TOPICS, not as
#   catastrophe                claims. "There is no danger of an accident in this period" still
#                              puts the idea in front of an anxious reader, which is exactly what
#                              the book forbids: no fear, no death, no illness. Both must stay hits.
#   gem_fear                   CANNOT be negated: its own patterns ARE negative constructions
#                              ("without this stone", "if you do not wear"). Exempting negation
#                              would switch the rule off entirely.
#   sign / house / date        Left alone in the validator, deliberately. A negation somewhere in a
#   (app/ai/validator.py)      sentence does not negate THIS claim - "Guru is not in the 9th, it is
#                              in the 10th" would sail through with a wrong second half.
#
# Pinned by tests/test_historical_defects.py, which asserts the negated forms of death, illness and
# catastrophe still fire.
_RE_NOT_A_SALE = re.compile(
    r"\b(?:not|never|rather than|instead of|without)\b[^.;!?\n]{0,40}$|"
    r"\b(?:no|not|never)\b\s+(?:a\s+|an\s+|any\s+)?$", re.IGNORECASE)


def _negated_sale(text: str, start: int) -> bool:
    """True when a negation sits just before the matched commerce phrase, in the same clause."""
    window = text[max(0, start - 60):start]
    clause = re.split(r"[.;!?\n]", window)[-1]
    return bool(_RE_NOT_A_SALE.search(clause))


def screen_text(text: str, allow_gemstone: bool = False) -> list[SafetyHit]:
    """All forbidden-topic hits in one string, in any of the three languages.

    `allow_gemstone=True` only for the gemstone chapter of the flagship Kundali book, where the engine
    supplied the recommendation for the book's gemstone chapter. It lifts the ban on naming stones and
    nothing else:
    a price, a weight, a shop, a supplier, "must be energised" and every "wear it or else" line stay
    blocked, as do paid pujas, yantras and "consult an astrologer".
    """
    patterns = _PATTERNS if allow_gemstone else _PATTERNS + _GEMSTONE_PATTERNS
    hits = []
    for category, pattern in patterns:
        for match in pattern.finditer(text or ""):
            if category == "hard_sell" and _negated_sale(text or "", match.start()):
                continue
            hits.append(SafetyHit(category, match.group(0)))
    return hits
