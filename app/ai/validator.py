"""Post-generation fact check: the AI interprets, it never calculates.

Every date, month-year, year, degree, graha-in-sign, graha-in-house and lagna statement found in the
AI's text is compared with the engine data that was put in the prompt. Anything that is not in the
data is an Issue. report.py regenerates on issues and, on the last attempt, removes the offending
paragraph (kinds in REDACT_KINDS) or records a warning (bare years).

This is a pragmatic pattern check, not a parser: it only judges statements it recognises with high
confidence, in en / hi / mr, and stays silent otherwise.
"""

import datetime as dt
import re
from dataclasses import dataclass, field, replace

REDACT_KINDS = {"date", "month", "degree", "sign", "house", "lagna", "house_sign", "untraceable",
                "filler", "date_range", "dignity"}
# Worth a regeneration, never worth removing text: bare years, dosha wording, and stock phrasing.
SOFT_KINDS = {"year", "wording", "boilerplate", "heading_length", "duplicate_heading"}
# `dignity` was soft until 2026-09-22, because the own-sign check was heuristic and its false alarms
# cost whole regenerations. It is blocking now, and the order of those two facts matters: the rule was
# promoted only AFTER the false positives were measured and their cause removed. Every one of them
# turned out to be "your own sign" - a claim about the reader's lagna - being read as a claim about a
# graha; see `_RE_READER_OWNS_EN`. With that fixed the measured false-positive count was zero and the
# true positives were four, one of which had already shipped to a delivered book: "Guru ... in Karka,
# its own sign of exaltation", where Karka is Chandra's sign. Do not soften this without repeating the
# measurement on REJECTED DRAFTS - accepted output cannot contain false positives, because a false
# positive is exactly what forces the regeneration that replaces it.
# `untranslated` is blocking but never redacted: blanking a heading leaves the contents page
# with a hole. It fails the part and is regenerated instead (see book_report.run_call).
REGENERATE_ONLY_KINDS = {"untranslated"}

_DEV = "ऀ-ॿ"
_NOT_DEV_BEFORE = f"(?<![{_DEV}])"
_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# ---- names ---------------------------------------------------------------------------------------

_SIGN_ALIASES = [  # index 1..12; first three are the engine's key / name / devanagari
    ["Aries", "Mesha", "Mesh", "मेष"],
    ["Taurus", "Vrishabha", "Vrishabh", "Vrushabh", "वृषभ", "वृष"],
    ["Gemini", "Mithuna", "Mithun", "मिथुन"],
    ["Cancer", "Karka", "Kark", "कर्क"],
    ["Leo", "Simha", "Sinh", "Singh", "सिंह"],
    ["Virgo", "Kanya", "कन्या"],
    ["Libra", "Tula", "तुला", "तूळ", "तुळ"],
    ["Scorpio", "Vrishchika", "Vrishchik", "Vruschik", "वृश्चिक"],
    ["Sagittarius", "Dhanu", "Dhanus", "धनु", "धनू"],
    ["Capricorn", "Makara", "Makar", "मकर"],
    ["Aquarius", "Kumbha", "Kumbh", "कुंभ", "कुम्भ"],
    ["Pisces", "Meena", "Meen", "Mina", "मीन"],
]

_GRAHA_ALIASES = {
    "Sun": ["Sun", "Surya", "Ravi", "सूर्य", "रवि", "रवी"],
    "Moon": ["Moon", "Chandra", "Chandrama", "चंद्र", "चन्द्र", "चंद्रमा", "चन्द्रमा"],
    "Mars": ["Mars", "Mangal", "Mangala", "Kuja", "मंगल", "मंगळ"],
    "Mercury": ["Mercury", "Budha", "Budh", "बुध"],
    "Jupiter": ["Jupiter", "Guru", "Brihaspati", "गुरु", "गुरू", "बृहस्पति"],
    "Venus": ["Venus", "Shukra", "शुक्र"],
    "Saturn": ["Saturn", "Shani", "शनि", "शनी"],
    "Rahu": ["Rahu", "राहु", "राहू"],
    "Ketu": ["Ketu", "केतु", "केतू"],
}


def _is_latin(word: str) -> bool:
    return word.isascii()


def _alternation(words, latin: bool) -> str:
    chosen = sorted((w for w in words if _is_latin(w) == latin), key=len, reverse=True)
    return "|".join(re.escape(w) for w in chosen)


_SIGN_BY_ALIAS = {alias.lower(): index for index, aliases in enumerate(_SIGN_ALIASES, 1) for alias in aliases}
_GRAHA_BY_ALIAS = {alias.lower(): key for key, aliases in _GRAHA_ALIASES.items() for alias in aliases}
_ALL_SIGNS = [a for aliases in _SIGN_ALIASES for a in aliases]
_ALL_GRAHAS = [a for aliases in _GRAHA_ALIASES.values() for a in aliases]
_S_EN, _S_DEV = _alternation(_ALL_SIGNS, True), _alternation(_ALL_SIGNS, False)
_G_EN, _G_DEV = _alternation(_ALL_GRAHAS, True), _alternation(_ALL_GRAHAS, False)

_SIGN_LORDS = ["Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"]
# Grahas slow enough that "which sign it is in" is informative over a window. The rest sweep the whole
# zodiac within a year, so their transit signs cannot support or refute an own-sign claim.
SLOW_FOR_DIGNITY = frozenset({"Mars", "Jupiter", "Saturn", "Rahu", "Ketu"})

_ORDINALS_EN = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth",
                "tenth", "eleventh", "twelfth"]
_ORDINALS_DEV = [  # Sanskrit (both languages), Marathi oblique, Hindi oblique
    ["प्रथम", "पहिल्या", "पहले", "पहला"],
    ["द्वितीय", "दुसऱ्या", "दुसर्‍या", "दूसरे", "दूसरा"],
    ["तृतीय", "तिसऱ्या", "तिसर्‍या", "तीसरे", "तीसरा"],
    ["चतुर्थ", "चौथ्या", "चौथे", "चौथा"],
    ["पंचम", "पाचव्या", "पांचवें", "पाँचवें", "पांचवां"],
    ["षष्ठ", "षष्ठम", "सहाव्या", "छठे", "छठा"],
    ["सप्तम", "सातव्या", "सातवें", "सातवां"],
    ["अष्टम", "आठव्या", "आठवें", "आठवां"],
    ["नवम", "नवव्या", "नौवें", "नवें", "नौवां"],
    ["दशम", "दहाव्या", "दसवें", "दसवां"],
    ["एकादश", "अकराव्या", "ग्यारहवें", "ग्यारहवां"],
    ["द्वादश", "बाराव्या", "बारहवें", "बारहवां"],
]
_ORD_EN = {word: n for n, word in enumerate(_ORDINALS_EN, 1)}
_ORD_DEV = {word: n for n, words in enumerate(_ORDINALS_DEV, 1) for word in words}
_ORD_DEV_ALT = "|".join(re.escape(w) for w in sorted(_ORD_DEV, key=len, reverse=True))

_MONTHS = {
    1: ["january", "jan", "जनवरी", "जानेवारी"],
    2: ["february", "feb", "फरवरी", "फ़रवरी", "फेब्रुवारी"],
    3: ["march", "mar", "मार्च"],
    4: ["april", "apr", "अप्रैल", "एप्रिल"],
    5: ["may", "मई", "मे"],
    6: ["june", "jun", "जून"],
    7: ["july", "jul", "जुलाई", "जुलै"],
    8: ["august", "aug", "अगस्त", "ऑगस्ट"],
    9: ["september", "sept", "sep", "सितंबर", "सितम्बर", "सप्टेंबर"],
    10: ["october", "oct", "अक्टूबर", "अक्तूबर", "ऑक्टोबर"],
    11: ["november", "nov", "नवंबर", "नवम्बर", "नोव्हेंबर"],
    12: ["december", "dec", "दिसंबर", "दिसम्बर", "डिसेंबर"],
}
_MONTH_BY_NAME = {name: number for number, names in _MONTHS.items() for name in names}
_ALL_MONTHS = list(_MONTH_BY_NAME)
_MONTH = (
    rf"(?:\b(?:{_alternation(_ALL_MONTHS, True)})\b\.?|{_NOT_DEV_BEFORE}(?:{_alternation(_ALL_MONTHS, False)})(?![{_DEV}]))"
)

# ---- patterns ------------------------------------------------------------------------------------

_I = re.IGNORECASE
_RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_RE_NUMERIC = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b")
_RE_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH}),?\s+(\d{{4}})\b", _I)
_RE_MDY = re.compile(rf"({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", _I)
_RE_MONTH_YEAR = re.compile(rf"({_MONTH}),?\s+(\d{{4}})\b", _I)
_RE_YEAR = re.compile(r"(?<![\d.,])(1[89]\d\d|2[01]\d\d)(?![\d°]|\s*(?:rupees|rs\b|₹))", _I)
_RE_DEGREE = re.compile(r"(\d{1,3})\s*°(?:\s*(\d{1,2})\s*['′’])?")
_RE_DEGREE_WORD = re.compile(rf"(\d{{1,3}})(?:\.\d+)?\s*(?:degrees?\b|अंश(?![{_DEV}])|डिग्री)", _I)

_PLACED = r"(?:\s+(?:is|sits|resides|rests|stands|falls|lies|placed|posited|situated|located|is\s+(?:placed|posited|situated|located|found)))?"
_RE_SIGN_EN = re.compile(
    rf"\b({_G_EN})\b{_PLACED}\s+in\s+(?:the\s+sign\s+of\s+|the\s+sign\s+|the\s+rashi\s+of\s+|your\s+)?({_S_EN})\b", _I)
_RE_HOUSE_EN = re.compile(
    rf"\b({_G_EN})\b{_PLACED}\s+in\s+(?:the|your)\s+(?:(\d{{1,2}})(?:st|nd|rd|th)|({'|'.join(_ORDINALS_EN)}))\s+(?:house|bhava)\b", _I)
# "Guru enters Simha", "Shani moves into Mesha" - the movement form. Without this the sign check only
# fired on "in <sign>", so a wrong sign slipped through whenever the sentence used a verb of motion.
_RE_SIGN_MOVE_EN = re.compile(
    rf"\b({_G_EN})\b(?:\s+(?:also|then|now|again|will|finally))*\s+"
    r"(?:enters?|entering|enters\s+into|moves?\s+(?:in)?to|shifts?\s+(?:in)?to|transits?\s+(?:through|into)|"
    r"returns?\s+to|crosses\s+into|settles\s+into|steps\s+(?:in)?to)\s+"
    rf"(?:the\s+sign\s+(?:of\s+)?)?({_S_EN})\b", _I)

_RE_LAGNA_EN = [
    re.compile(rf"\b(?:your|the)\s+(?:lagna|ascendant)\s+(?:is|falls\s+in|is\s+in|in)\s+({_S_EN})\b", _I),
    re.compile(rf"\b(?:your|with|a|an)\s+({_S_EN})\s+(?:lagna|ascendant|rising)\b", _I),
]

_G_D = rf"{_NOT_DEV_BEFORE}({_G_DEV})"
_S_D = rf"{_NOT_DEV_BEFORE}({_S_DEV})"
_IN_SIGN = r"(?:राशीत|राशीमध्ये|राशीतील|राशीतला|राशीमधील|राशिमध्ये|राशि\s+में|राशी\s+में|मध्ये|में)"
_RE_SIGN_DEV = [
    (re.compile(rf"{_G_D}\s+(?:हा\s+|ग्रह\s+)?{_S_D}\s+{_IN_SIGN}"), ("g", "s")),
    (re.compile(rf"{_S_D}\s+{_IN_SIGN}\s+(?:असलेला\s+|असलेल्या\s+|स्थित\s+|विराजमान\s+|बैठा\s+|बैठे\s+)?{_G_D}(?![{_DEV}])"),
     ("s", "g")),
]
_RE_HOUSE_DEV = re.compile(
    rf"{_G_D}\s+(?:हा\s+|ग्रह\s+)?(?:तुमच्या\s+|आपल्या\s+|आपके\s+|आपकी\s+)?(?:कुंडलीच्या\s+|कुंडलीतील\s+|कुंडली\s+के\s+)?"
    rf"(?:(\d{{1,2}})\s*(?:व्या|वे|वें|वां|वा|th)?|({_ORD_DEV_ALT}))\s+"
    r"(?:स्थानात|स्थानी|स्थानामध्ये|भावात|भावामध्ये|घरात|भाव\s+में|घर\s+में|स्थान\s+में)"
)
_RE_LAGNA_DEV = [
    re.compile(rf"(?:तुमचे|तुमचं|तुमच्या|आपले|आपका|आपकी|आपके)\s+{_S_D}\s+लग्न"),
    re.compile(rf"लग्न\s+{_S_D}\s+(?:राशीत|राशीचे|राशीमध्ये|राशि\s+में|राशि\s+का|आहे|है)"),
]


_N_EN = rf"(?:(\d{{1,2}})(?:st|nd|rd|th)|({'|'.join(_ORDINALS_EN)}))"
_N_DEV = rf"(?:(\d{{1,2}})\s*(?:व्या|वे|वें|वां|वा|th)?|({_ORD_DEV_ALT}))"
_HOUSE_DEV = r"(?:भावात|भावामध्ये|भाव|स्थानात|स्थानी|स्थान|घरात|घर)"
# "Guru enters your 9th house", "Guru aapke 9th house mein pravesh karega" (the plain "in the Nth house" form is _RE_HOUSE_EN)
_RE_HOUSE_MOVE_EN = re.compile(
    rf"\b({_G_EN})\b(?:\s+(?:also|then|now|again|bhi|will|transit\w*|se))*\s+"
    rf"(?:(?:enters?|entering|moves?\s+(?:in)?to|shifts?\s+(?:in)?to|transits?(?:\s+through)?|crosses\s+into|returns?\s+to)\s+(?:the|your)|aapke|aapka|tumchya)\s+"
    rf"{_N_EN}\s+(?:house|bhava|bhav)\b", _I)
# house <-> sign pairings, tightly adjacent only: "9th house (Simha)", "10th house is Vrishabha", "Vrishabha, your 10th house"
_RE_HOUSE_THEN_SIGN_EN = re.compile(
    rf"\b{_N_EN}\s+(?:house|bhava|bhav)\s*(?:\(\s*|,\s*|-\s*|:\s*|is\s+|falls\s+in\s+|in\s+|of\s+)(?:the\s+sign\s+(?:of\s+)?)?({_S_EN})\b", _I)
_RE_SIGN_THEN_HOUSE_EN = re.compile(
    rf"\b({_S_EN})\b(?:\s*\([^)]{{0,20}}\))?\s*(?:,|-|–|—|\()?\s*(?:which\s+is\s+|that\s+is\s+|i\.e\.\s+|yaani\s+|jo\s+|is\s+)?"
    rf"(?:your|the|aapka|aapke|aapki|tumchya|tumche)\s+{_N_EN}\s+(?:house|bhava|bhav)\b", _I)
_RE_SIGN_THEN_HOUSE_DEV = re.compile(
    rf"{_S_D}\s+(?:राशीत|राशीमध्ये|राशि\s+में|राशी\s+में|राशी|राशि)?\s*(?:,|\(|-|–|—)?\s*(?:म्हणजे|म्हणजेच|यानी|अर्थात|जो|जे)?\s*"
    rf"(चंद्रापासून\s+|चंद्राच्या\s+|चंद्र\s+से\s+|चन्द्र\s+से\s+)?(?:तुमच्या\s+|आपके\s+|आपल्या\s+|लग्नापासून\s+|लग्न\s+से\s+)?{_N_DEV}\s+{_HOUSE_DEV}")
_RE_HOUSE_THEN_SIGN_DEV = re.compile(rf"{_NOT_DEV_BEFORE}{_N_DEV}\s+{_HOUSE_DEV}\s*(?:\(\s*|,\s*|म्हणजे\s+|यानी\s+)?{_S_D}(?![{_DEV}])")
_RE_FROM_MOON = re.compile(
    r"\bfrom\s+(?:your\s+|the\s+|natal\s+)*(?:moon|chandra|rashi|rasi|janma\s+rashi)\b|\b(?:chandra|moon|rashi)\s+se\b|"
    r"\bchandrapasun\b|\bchandra\s+lagna\b|चंद्रापासून|चंद्राच्या|चंद्र\s+से|चन्द्र\s+से|चंद्रराशी|चंद्र\s+राशि\s+से|राशीपासून|राशि\s+से", _I)
# Mangal dosha that is present is "mitigated", never "cancelled": the engine's cancellations do not flip `present`.
_RE_DOSHA_CANCELLED = re.compile(
    r"\b(?:dosha|dosh)\b[^.;!?\n]{0,60}?\b(?:cancel\w*|nullif\w+|ineffective|void|does\s+not\s+apply|no\s+longer\s+applies|"
    r"nishprabhav|prabhavheen|radd|khatam)\b|\b(?:cancel\w*|nullif\w+)\b[^.;!?\n]{0,40}?\b(?:dosha|dosh)\b|"
    r"दोष[^।.;!?\n]{0,50}?(?:प्रभावहीन|निष्प्रभ|निष्प्रभावी|रद्द|निरस्त|समाप्त|संपतो|संपुष्टात|नाहीसा|लागू\s+होत\s+नाही|लागू\s+नहीं)", _I)

_RE_NEGATION = re.compile(r"\b(?:not|never|no)\b|n't|नाही(?![\u0900-\u097Fा-ौ])|नहीं|नसतो|नसते|न\s+कि", re.IGNORECASE)

_SENTENCE_ENDS = (".", "।", "!", "?", "\n", ";")
_RE_TRANSIT_CUE = re.compile(
    r"(?<!\d)(?:1[89]|2[01])\d\d(?!\d)|\b(?:transit\w*|ingress\w*|enter\w*|re-enter\w*|mov(?:es|ed|ing)|shift\w*|return\w*|"
    r"cross\w*|pass\w*|current(?:ly)?|now|at present|these days|this (?:month|year|week)|gochar|sadhya|abhi|filhal)\b|"
    r"गोचर|प्रवेश|भ्रमण|संक्रमण|सध्या|आत्ता|आता|अभी|इस समय|फिलहाल|वर्तमान|जातो|जाईल|येतो|येईल|जाएगा|आएगा|जाएंगे|आएंगे", re.IGNORECASE)

_RE_MOTION_CUE = re.compile(r"\b(?:transit\w*|ingress\w*|enter\w*|re-enter\w*|gochar)\b|गोचर|प्रवेश|भ्रमण|संक्रमण", re.IGNORECASE)

# "own sign" claims. Sign lordship is a fixed table, so these can be judged exactly:
#   sign named next to the phrase -> that sign's lord must be the graha; no sign named -> the graha's birth sign.
_RE_OWN_EN = re.compile(
    rf"(?:\b({_S_EN})\b(?:\s*\([^)]*\))?,?\s+(?:which\s+is\s+|is\s+)?)?"          # 1: sign before ("Kumbha, Saturn's own sign")
    rf"(?:\b({_G_EN})(?:'s|’s)\s+)?"                                                # 2: possessive graha
    r"\b(?:own[\s-]+(?:sign|rashi|rasi|house)|apni\s+(?:hi\s+)?(?:rashi|rasi)|swa-?rashi|sva-?rashi|"
    r"swatah?chya(?:ch)?\s+(?:rashi|rashit|rashimadhe))\b"
    rf"(?:\s+(?:of|in))?,?\s*(?:\(?\b({_S_EN})\b)?", _I)                             # 3: sign after ("its own sign Makara", "own sign in Vrishchika")
_RE_OWN_DEV = re.compile(
    rf"(?:स्वतःच्याच|स्वतःच्या|स्वत:च्याच|स्वत:च्या|आपल्याच|अपनी\s+ही|अपनी|स्वयं\s+की)\s*(?:{_NOT_DEV_BEFORE}({_S_DEV})\s+)?"
    r"(?:राशीत|राशीमध्ये|राशि|राशी|घरात|घर)|स्वराशी|स्वगृही")
# "your own sign" is a claim about the READER's lagna sign, not about any graha - ordinary Jyotish
# phrasing ("Guru returns to your own sign" = Guru transits the native's lagna rashi). Reading the
# second-person possessive as if it were "its own" and checking it against the graha's `in_own_sign`
# rejected three true sentences across two live runs, at the cost of a regeneration each. Marathi
# `आपल्या` / `तुमच्या` and Hindi `आपकी` are second-person the same way; Hindi `अपनी` is NOT - it is
# reflexive ("its own sign") and stays with the graha.
# Both patterns are anchored to the END of the text preceding the phrase, so they test the words
# ATTACHED to "own sign" rather than anything that happens to appear earlier in the sentence. That
# distinction is the whole correctness argument: the one sentence known to have reached a finished
# book is "Guru ... sits in YOUR first house itself, in Karka, ITS own sign of exaltation", where an
# unbounded search for "your" finds the one belonging to "first house", routes the phrase to the
# lagna branch, and passes it - because Karka really is that chart's lagna.
#
# `_RE_THIRD_PERSON_OWNS` is deliberately redundant with the `$` anchor on `_RE_READER_OWNS_EN`.
# The anchor alone is correct but invisible: delete one character and the rule silently inverts on
# exactly that sentence. An explicit "its/his/her/their means the graha, full stop" survives that
# edit, and states the intent in words instead of punctuation.
_RE_READER_OWNS_EN = re.compile(r"\byour\s+(?:very\s+|own\s+)?$", _I)
_RE_THIRD_PERSON_OWNS = re.compile(r"\b(?:its|it's|his|her|their|the\s+graha's)\s+(?:very\s+|own\s+)?$", _I)
_RE_READER_OWNS_DEV = re.compile(r"^(?:तुमच्याच?|आपल्याच?|आपकी|आपके|आपका)")
_RE_OWN_WORD_EN = re.compile(r"own[\s-]+(?:sign|rashi|rasi|house)", _I)
_RE_ANY_GRAHA = re.compile(rf"\b(?:{_G_EN})\b|{_NOT_DEV_BEFORE}(?:{_G_DEV})", _I)


def _reader_owns_en(original: str, match) -> bool:
    """True when the English "own sign" phrase is owned by "your", not by a graha.

    Judged on the words immediately before the phrase only. A "your" elsewhere in the sentence is
    somebody else's - most often "your Nth house" - and must not transfer.
    """
    inner = _RE_OWN_WORD_EN.search(match.group(0))
    if not inner:
        return False
    before = original[:match.start() + inner.start()]
    if _RE_THIRD_PERSON_OWNS.search(before):
        return False  # "its own sign" is about the graha, whatever appears earlier
    return bool(_RE_READER_OWNS_EN.search(before))


_RE_ANY_SIGN = re.compile(rf"\b(?:{_S_EN})\b|{_NOT_DEV_BEFORE}(?:{_S_DEV})", _I)


# ---- facts from the engine data ------------------------------------------------------------------


@dataclass
class Facts:
    dates: set = field(default_factory=set)  # dt.date
    months: set = field(default_factory=set)  # (year, month)
    years: set = field(default_factory=set)
    degrees: set = field(default_factory=set)  # int degree
    degree_minutes: set = field(default_factory=set)  # (degree, minute)
    graha_signs: dict = field(default_factory=dict)  # graha key -> {sign index}
    graha_houses: dict = field(default_factory=dict)  # graha key -> {house}
    lagna_signs: set = field(default_factory=set)
    # Birth-chart placements only. A sign/house that is merely a transit of that graha (graha_signs / graha_houses)
    # is accepted only in a sentence that reads as a transit statement (a year, "enters", "currently", प्रवेश ...).
    natal_signs: dict = field(default_factory=dict)
    natal_houses: dict = field(default_factory=dict)
    mangal_present: bool = False  # engine: cancellations never flip `present`, so the text may not say "cancelled"
    # Fact types calc-engine-2 may start supplying. While false, the book may not assert them at all
    # (see `untraceable_issues`); each flips to true as soon as the data actually carries that fact.
    has_aspects: bool = False   # whole-sign drishti per graha
    has_dignity: bool = False   # per-graha exaltation / debilitation / combustion
    has_navamsa: bool = False   # the D9 chart
    has_yogas: bool = False     # a computed yoga list


def facts_to_json(facts: Facts) -> dict:
    return {
        "dates": sorted(d.isoformat() for d in facts.dates),
        "years": sorted(facts.years),
        "degrees": sorted(facts.degrees),
        "degree_minutes": sorted(list(pair) for pair in facts.degree_minutes),
        "graha_signs": {k: sorted(v) for k, v in facts.graha_signs.items()},
        "graha_houses": {k: sorted(v) for k, v in facts.graha_houses.items()},
        "lagna_signs": sorted(facts.lagna_signs),
        "natal_signs": {k: sorted(v) for k, v in facts.natal_signs.items()},
        "natal_houses": {k: sorted(v) for k, v in facts.natal_houses.items()},
        "mangal_present": facts.mangal_present,
        "has_aspects": facts.has_aspects,
        "has_dignity": facts.has_dignity,
        "has_navamsa": facts.has_navamsa,
        "has_yogas": facts.has_yogas,
    }


def facts_from_json(data: dict) -> Facts:
    dates = {dt.date.fromisoformat(d) for d in data.get("dates", [])}
    return Facts(
        dates=dates,
        months={(d.year, d.month) for d in dates},
        years=set(data.get("years", [])) | {d.year for d in dates},
        degrees=set(data.get("degrees", [])),
        degree_minutes={tuple(pair) for pair in data.get("degree_minutes", [])},
        graha_signs={k: set(v) for k, v in data.get("graha_signs", {}).items()},
        graha_houses={k: set(v) for k, v in data.get("graha_houses", {}).items()},
        lagna_signs=set(data.get("lagna_signs", [])),
        natal_signs={k: set(v) for k, v in data.get("natal_signs", {}).items()},
        natal_houses={k: set(v) for k, v in data.get("natal_houses", {}).items()},
        mangal_present=bool(data.get("mangal_present", False)),
        has_aspects=bool(data.get("has_aspects", False)),
        has_dignity=bool(data.get("has_dignity", False)),
        has_navamsa=bool(data.get("has_navamsa", False)),
        has_yogas=bool(data.get("has_yogas", False)),
    )


_RE_DATA_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_RE_DATA_DMS = re.compile(r"^(\d{1,3})°(\d{1,2})'")


def collect_facts(data) -> Facts:
    """Walk the prompt data (chart / matching / outlook windows) and index every checkable fact."""
    facts = Facts()

    def add_date(text: str):
        for y, m, d in _RE_DATA_DATE.findall(text):
            try:
                facts.dates.add(dt.date(int(y), int(m), int(d)))
            except ValueError:
                pass

    def sign_index(value):
        return value.get("index") if isinstance(value, dict) else None

    def walk(node, key=None):
        if isinstance(node, str):
            add_date(node)
            dms = _RE_DATA_DMS.match(node)
            if key == "degree_dms" and dms:
                facts.degrees.add(int(dms.group(1)))
                facts.degree_minutes.add((int(dms.group(1)), int(dms.group(2))))
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            if key == "year":
                facts.years.add(int(node))
            elif key in ("degrees", "degree"):
                facts.degrees.add(int(node))
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif isinstance(node, dict):
            graha = node.get("graha")
            graha_key = graha.get("key") if isinstance(graha, dict) else None
            if graha_key in _GRAHA_ALIASES:
                for sign_key in ("sign", "to_sign", "from_sign"):
                    if sign_index(node.get(sign_key)):
                        facts.graha_signs.setdefault(graha_key, set()).add(sign_index(node[sign_key]))
                for house_key in ("house", "house_from_moon", "house_from_lagna"):
                    if isinstance(node.get(house_key), int):
                        facts.graha_houses.setdefault(graha_key, set()).add(node[house_key])
            for name, graha_key in (("saturn_sign", "Saturn"), ("moon_sign", "Moon"), ("moon_rashi", "Moon")):
                if sign_index(node.get(name)):
                    facts.graha_signs.setdefault(graha_key, set()).add(sign_index(node[name]))
            if isinstance(node.get("saturn_house_from_moon"), int):
                facts.graha_houses.setdefault("Saturn", set()).add(node["saturn_house_from_moon"])
            if isinstance(node.get("mars_house"), int):  # Mars's house from lagna / Moon / Venus: a birth-chart fact
                facts.graha_houses.setdefault("Mars", set()).add(node["mars_house"])
                facts.natal_houses.setdefault("Mars", set()).add(node["mars_house"])
            if isinstance(node.get("mangal_dosha"), dict) and node["mangal_dosha"].get("present") is True:
                facts.mangal_present = True
            for key, flag in (("navamsa", "has_navamsa"), ("yogas", "has_yogas"),
                              ("aspects", "has_aspects"), ("dignity", "has_dignity")):
                if node.get(key):
                    setattr(facts, flag, True)
            # A birth chart. The navamsa block has the same two keys, so it is excluded by `division`:
            # a D9 sign is not a natal placement and must never be accepted as one.
            if (isinstance(node.get("lagna"), dict) and isinstance(node.get("grahas"), dict)
                    and "division" not in node):
                for natal_key, position in node["grahas"].items():
                    if natal_key in _GRAHA_ALIASES and isinstance(position, dict):
                        if sign_index(position.get("sign")):
                            facts.natal_signs.setdefault(natal_key, set()).add(sign_index(position["sign"]))
                        if isinstance(position.get("house"), int):
                            facts.natal_houses.setdefault(natal_key, set()).add(position["house"])
            lagna = node.get("lagna")
            # `division` again: the navamsa lagna is a D9 sign, not the birth lagna. Letting it in
            # would give `lagna_signs` two members and silently switch off every house<->sign check.
            if isinstance(lagna, dict) and sign_index(lagna.get("sign")) and "division" not in node:
                facts.lagna_signs.add(sign_index(lagna["sign"]))
            for child_key, child in node.items():
                walk(child, child_key)

    walk(data)
    facts.months = {(d.year, d.month) for d in facts.dates}
    facts.years |= {d.year for d in facts.dates}
    return facts


# ---- checking ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Issue:
    kind: str  # date | month | year | degree | sign | house | lagna
    found: str
    message: str


def _blank(text: str, match: re.Match) -> str:
    return text[: match.start()] + " " * (match.end() - match.start()) + text[match.end():]


def _month_number(name: str) -> int:
    return _MONTH_BY_NAME[name.lower().rstrip(".")]


def check_text(text: str, facts: Facts) -> list[Issue]:
    """Issues in one string. Deterministic; no network."""
    if not text:
        return []
    issues: list[Issue] = []
    work = text.translate(_DEV_DIGITS)

    def check_date(match, year, month, day):
        nonlocal work
        found = match.group(0)
        work = _blank(work, match)
        try:
            value = dt.date(int(year), int(month), int(day))
        except ValueError:
            issues.append(Issue("date", found, f"'{found}' is not a valid calendar date"))
            return
        if value not in facts.dates:
            issues.append(Issue("date", found, f"the date '{found}' does not appear anywhere in the data"))

    for match in list(_RE_ISO.finditer(work)):
        check_date(match, match.group(1), match.group(2), match.group(3))
    for match in list(_RE_NUMERIC.finditer(work)):
        check_date(match, match.group(3), match.group(2), match.group(1))
    for match in list(_RE_DMY.finditer(work)):
        check_date(match, match.group(3), _month_number(match.group(2)), match.group(1))
    for match in list(_RE_MDY.finditer(work)):
        check_date(match, match.group(3), _month_number(match.group(1)), match.group(2))

    for match in list(_RE_MONTH_YEAR.finditer(work)):
        found = match.group(0)
        work = _blank(work, match)
        if (int(match.group(2)), _month_number(match.group(1))) not in facts.months:
            issues.append(Issue("month", found, f"no date in '{found}' appears in the data"))

    for match in _RE_YEAR.finditer(work):
        if int(match.group(1)) not in facts.years:
            issues.append(Issue("year", match.group(1), f"the year {match.group(1)} does not appear in the data"))

    for match in _RE_DEGREE.finditer(work):
        degree, minute = int(match.group(1)), match.group(2)
        ok = (degree, int(minute)) in facts.degree_minutes if minute is not None else degree in facts.degrees
        if not ok:
            issues.append(Issue("degree", match.group(0), f"the degree '{match.group(0)}' is not in the data"))
    for match in _RE_DEGREE_WORD.finditer(work):
        if int(match.group(1)) not in facts.degrees:
            issues.append(Issue("degree", match.group(0), f"the degree '{match.group(0)}' is not in the data"))

    original = text.translate(_DEV_DIGITS)  # same length as `work`, but with the dates still in it

    def sentence_bounds(position_start, position_end):
        begin = max((original.rfind(mark, 0, position_start) for mark in _SENTENCE_ENDS), default=-1) + 1
        ends = [i for i in (original.find(mark, position_end) for mark in _SENTENCE_ENDS) if i != -1]
        return begin, (min(ends) if ends else len(original))

    def is_transit_statement(match) -> bool:
        start = max((original.rfind(mark, 0, match.start()) for mark in _SENTENCE_ENDS), default=-1) + 1
        ends = [i for i in (original.find(mark, match.end()) for mark in _SENTENCE_ENDS) if i != -1]
        return bool(_RE_TRANSIT_CUE.search(original[start:min(ends) if ends else len(original)]))

    def check_placement(kind, match, graha_alias, value, natal, anywhere, what):
        graha, found = _GRAHA_BY_ALIAS[graha_alias.lower()], match.group(0)
        in_birth_chart, in_data = natal.get(graha), anywhere.get(graha)
        if not in_data or (value in (in_birth_chart or in_data)):
            return
        if in_birth_chart and value in in_data:
            if not is_transit_statement(match):
                issues.append(Issue(kind, found, f"'{found}': in the birth chart {graha} is not in {what}; the data has "
                                    "it there only as a transit, so say when (give the date from the data)"))
            return
        issues.append(Issue(kind, found, f"'{found}': the data does not place {graha} in {what}"))

    def check_sign(match, graha_alias, sign_alias):
        check_placement("sign", match, graha_alias, _SIGN_BY_ALIAS[sign_alias.lower()], facts.natal_signs,
                        facts.graha_signs, "that sign")

    lagna_sign = next(iter(facts.lagna_signs)) if len(facts.lagna_signs) == 1 else None
    moon_signs = facts.natal_signs.get("Moon") or set()
    moon_sign = next(iter(moon_signs)) if len(moon_signs) == 1 else None

    def says_from_moon(match) -> bool:
        return bool(_RE_FROM_MOON.search(original[slice(*sentence_bounds(match.start(), match.end()))]))

    def check_house(match, graha_alias, house):
        """Birth-chart house, or - in a transit sentence - the whole-sign house of a transit sign in the data,
        counted from the lagna. Counted from the Moon only if the sentence says so ("9th from your Moon")."""
        graha, found = _GRAHA_BY_ALIAS[graha_alias.lower()], match.group(0)
        natal = facts.natal_houses.get(graha)
        if lagna_sign is None or not natal:  # pair reports / old stored facts: keep the permissive check
            return check_placement("house", match, graha_alias, house, facts.natal_houses, facts.graha_houses, f"house {house}")
        if house in natal:
            return
        signs = facts.graha_signs.get(graha, set())
        from_lagna = {(sign - lagna_sign) % 12 + 1 for sign in signs}
        from_moon = {(sign - moon_sign) % 12 + 1 for sign in signs} if moon_sign else set()
        if is_transit_statement(match):
            if house in from_lagna or (house in from_moon and says_from_moon(match)):
                return
            if house in from_moon:
                issues.append(Issue("house", found, f"'{found}': house {house} is counted from the Moon sign. \"Your Nth house\" "
                                    "always means counted from the lagna - use house_from_lagna, or say \"Nth from your Moon sign\""))
                return
        issues.append(Issue("house", found, f"'{found}': the data does not place {graha} in house {house} (counted from the lagna)"))

    def check_house_sign(match, house, sign_alias, moon_marked=False):
        if lagna_sign is None:
            return
        sign, found = _SIGN_BY_ALIAS[sign_alias.lower()], match.group(0)
        expected = (sign - lagna_sign) % 12 + 1
        expected_moon = (sign - moon_sign) % 12 + 1 if moon_sign else None
        if house == expected or (house == expected_moon and (moon_marked or says_from_moon(match))):
            return
        hint = f" (it is the {expected_moon}th counted from the Moon sign - say so explicitly if you mean that)" \
            if house == expected_moon else ""
        issues.append(Issue("house_sign", found, f"'{found}': {_SIGN_ALIASES[sign - 1][1]} is house {expected} from the lagna, "
                            f"not house {house}{hint}"))

    def number(digits, word, table):
        return int(digits) if digits else table[word.lower() if word.isascii() else word]

    for match in _RE_SIGN_EN.finditer(work):
        check_sign(match, match.group(1), match.group(2))
    for match in _RE_SIGN_MOVE_EN.finditer(work):
        check_sign(match, match.group(1), match.group(2))
    for pattern, order in _RE_SIGN_DEV:
        for match in pattern.finditer(work):
            groups = dict(zip(order, match.groups()))
            check_sign(match, groups["g"], groups["s"])

    for match in _RE_HOUSE_EN.finditer(work):
        check_house(match, match.group(1), int(match.group(2)) if match.group(2) else _ORD_EN[match.group(3).lower()])
    for match in _RE_HOUSE_DEV.finditer(work):
        check_house(match, match.group(1), int(match.group(2)) if match.group(2) else _ORD_DEV[match.group(3)])
    for match in _RE_HOUSE_MOVE_EN.finditer(work):
        check_house(match, match.group(1), number(match.group(2), match.group(3), _ORD_EN))

    for match in _RE_HOUSE_THEN_SIGN_EN.finditer(work):
        check_house_sign(match, number(match.group(1), match.group(2), _ORD_EN), match.group(3))
    for match in _RE_SIGN_THEN_HOUSE_EN.finditer(work):
        check_house_sign(match, number(match.group(2), match.group(3), _ORD_EN), match.group(1))
    for match in _RE_SIGN_THEN_HOUSE_DEV.finditer(work):
        check_house_sign(match, number(match.group(3), match.group(4), _ORD_DEV), match.group(1), bool(match.group(2)))
    for match in _RE_HOUSE_THEN_SIGN_DEV.finditer(work):
        check_house_sign(match, number(match.group(1), match.group(2), _ORD_DEV), match.group(3))

    if facts.mangal_present:
        for match in _RE_DOSHA_CANCELLED.finditer(original):
            tail = original[match.start():match.end() + 25]
            if _RE_NEGATION.search(tail):  # "the dosha is not cancelled", "दोष नाहीसा होत नाही"
                continue
            issues.append(Issue("wording", match.group(0), f"'{match.group(0)}': the dosha is present in the data; its mitigating "
                                "factors soften it (mitigated / सौम्य होतो / कम होता है) - never say cancelled, nullified or ineffective"))

    def _where_it_can_be(graha: str) -> set:
        """Signs a graha may truthfully be said to occupy, in this scope.

        Natal placements, plus the in-scope transits of SLOW grahas only. Inside a 2031 window Guru
        really is transiting Dhanu, its own sign, and saying so is true. Budha, Shukra, Surya and
        Chandra are excluded because they visit all twelve signs within a year, so "Budha is in its
        own sign" would be unfalsifiable in any scope wider than a month. Shared by both branches of
        `check_own_sign` so the "its own sign" and "your own sign" readings cannot drift apart.
        """
        return set(facts.natal_signs.get(graha, ())) | (
            set(facts.graha_signs.get(graha, ())) if graha in SLOW_FOR_DIGNITY else set())

    def check_own_sign(match, adjacent_sign, possessive_graha, about_the_reader=False):
        """Precision first (a false alarm costs a whole regeneration). Judged per sentence:
        a sign named right at the phrase -> its lord must be mentioned in the sentence;
        other signs in the sentence -> one of them must belong to a graha mentioned in the sentence;
        no sign at all -> one of the grahas mentioned must be in its own sign in the birth chart."""
        if possessive_graha and _GRAHA_BY_ALIAS[possessive_graha.lower()] == "Moon" and not adjacent_sign:
            return  # "the Moon's own sign" is also how people say "your Moon sign"
        begin, finish = sentence_bounds(match.start(), match.end())
        sentence = original[begin:finish]
        # "Mangal is NOT in its own sign" is a true statement about this chart, and flagging it cost
        # two real regenerations of a paid part before this guard existed. Safe here because the
        # whole sentence is ONE claim - unlike `sign` / `house` / `date` below, which are left
        # un-negated on purpose: "Guru is not in the 9th, it is in the 10th" carries two claims and
        # a blanket negation guard would wave the wrong one through. The full four-way reasoning
        # lives above `_RE_NOT_A_SALE` in app/ai/safety.py.
        if _RE_NEGATION.search(sentence):
            return
        grahas = {_GRAHA_BY_ALIAS[g.lower()] for g in _RE_ANY_GRAHA.findall(sentence)}
        if about_the_reader:
            # "your own sign" names the NATIVE's lagna rashi, so the claim is checked against the
            # lagna and never against the graha's `in_own_sign`.
            #
            # Returning early here - "nothing to verify" - was wrong, and the first version of this
            # branch did exactly that. "Shani sits in your own sign" IS a placement claim: it says
            # Shani is in the lagna rashi, and on a Karka chart with Shani in Dhanu it is false. That
            # early return silently switched off a check the old rule got right, which is the shape
            # of bug this whole file exists to avoid.
            named = _SIGN_BY_ALIAS[adjacent_sign.lower()] if adjacent_sign else None
            if not facts.lagna_signs:
                return
            if named is not None:
                if named in facts.lagna_signs:
                    return
                found = match.group(0).strip()
                issues.append(Issue("dignity", found, f"'{found}' in \"{sentence.strip()[:120]}\": "
                                    f"\"your own sign\" is the lagna rashi, and {_SIGN_ALIASES[named - 1][1]} "
                                    "is not the lagna in the data"))
                return
            if not grahas or any(facts.lagna_signs & _where_it_can_be(g) for g in grahas):
                return
            found = match.group(0).strip()
            lagna = _SIGN_ALIASES[next(iter(facts.lagna_signs)) - 1][1]
            issues.append(Issue("dignity", found, f"'{found}' in \"{sentence.strip()[:120]}\": "
                                f"\"your own sign\" is your lagna rashi, {lagna}, and the data does not "
                                f"place {'/'.join(sorted(grahas))} there"))
            return
        if not grahas:
            return
        # Only a sign sitting AT the phrase names what the claim is about. A sign mentioned elsewhere
        # in the sentence usually is not: "Simha lagna with Shani seated firmly in its own sign" is a
        # true statement about Shani, and reading Simha as the subject rejected it - a false positive
        # that failed a whole part on a live run. With no sign at the phrase, judge the grahas named.
        signs = {_SIGN_BY_ALIAS[adjacent_sign.lower()]} if adjacent_sign else set()
        if signs:
            ok = any(_SIGN_LORDS[sign - 1] in grahas for sign in signs)
        elif not any(facts.natal_signs.get(g) or facts.graha_signs.get(g) for g in grahas):
            return
        else:
            ok = any(_SIGN_LORDS[sign - 1] == g for g in grahas for sign in _where_it_can_be(g))
        if not ok:
            found = match.group(0).strip()
            detail = ", ".join(f"{_SIGN_ALIASES[sign - 1][1]} belongs to {_SIGN_LORDS[sign - 1]}" for sign in sorted(signs)) \
                or "none of the grahas named here is in its own sign in the birth chart"
            issues.append(Issue("dignity", found, f"'{found}' in \"{sentence.strip()[:120]}\": check `in_own_sign` in the data - {detail}"))

    for match in _RE_OWN_EN.finditer(original):
        check_own_sign(match, match.group(3) or match.group(1), match.group(2),
                       about_the_reader=_reader_owns_en(original, match))
    for match in _RE_OWN_DEV.finditer(original):
        check_own_sign(match, match.group(1), None,
                       about_the_reader=bool(_RE_READER_OWNS_DEV.match(match.group(0))))

    if facts.lagna_signs:
        for pattern in _RE_LAGNA_EN + _RE_LAGNA_DEV:
            for match in pattern.finditer(work):
                if _SIGN_BY_ALIAS[match.group(1).lower()] not in facts.lagna_signs:
                    issues.append(Issue("lagna", match.group(0), f"'{match.group(0)}': that is not the lagna in the data"))
    return issues


def allow_mentions(facts: Facts, text: str) -> None:
    """Chat: a date, month or year the *user* typed may be echoed back by the AI ("how is November 2026?").
    Adds them to `facts` in place. Placements and degrees are never widened this way."""
    work = (text or "").translate(_DEV_DIGITS)

    def add(year, month, day=None):
        try:
            if day is not None:
                facts.dates.add(dt.date(int(year), int(month), int(day)))
            facts.months.add((int(year), int(month)))
            facts.years.add(int(year))
        except ValueError:
            pass

    for m in _RE_ISO.finditer(work):
        add(m.group(1), m.group(2), m.group(3))
    for m in _RE_NUMERIC.finditer(work):
        add(m.group(3), m.group(2), m.group(1))
    for m in _RE_DMY.finditer(work):
        add(m.group(3), _month_number(m.group(2)), m.group(1))
    for m in _RE_MDY.finditer(work):
        add(m.group(3), _month_number(m.group(1)), m.group(2))
    for m in _RE_MONTH_YEAR.finditer(work):
        add(m.group(2), _month_number(m.group(1)))
    for m in _RE_YEAR.finditer(work):
        facts.years.add(int(m.group(1)))


# =====================================================================================================
# "Kuch bhi chipkana nahi" - nothing generic may be pasted in to fill space. Two checks the book adds.
#
# 1. `filler`      - a paragraph that names nothing from this chart. The reader paid to be told about
#                    themselves; a long paragraph with no graha, sign, house, period or date in it would
#                    read the same in anyone's book, so it is removed.
# 2. `untraceable` - a statement about something the engine never computed (aspects, exaltation,
#                    combustion, ashtakavarga, a divisional chart we did not send, a named yoga when the
#                    data lists no yogas). The AI interprets; it does not get to invent a new fact type.
#
# Both are deliberately built for precision: a false positive costs a real regeneration.
# =====================================================================================================

FILLER_MIN_WORDS = 30  # shorter than this is a linking sentence, not padding

# Anything that ties a sentence to THIS chart. Broad on purpose: one hit is enough to pass.
_RE_CHART_ANCHOR = re.compile(
    rf"\b(?:{_G_EN})\b|{_NOT_DEV_BEFORE}(?:{_G_DEV})|\b(?:{_S_EN})\b|{_NOT_DEV_BEFORE}(?:{_S_DEV})|"
    rf"\b(?:{'|'.join(_ORDINALS_EN)})\s+(?:house|bhava|bhav)\b|\b\d{{1,2}}(?:st|nd|rd|th)\s+(?:house|bhava|bhav)\b|"
    rf"{_NOT_DEV_BEFORE}(?:{_ORD_DEV_ALT})\s+{_HOUSE_DEV}|(?<!\d)(?:1[89]|2[01])\d\d(?!\d)|{_MONTH}|"
    r"\b(?:lagna|ascendant|rising sign|nakshatra|pada|dasha|dasa|antardasha|pratyantardasha|mahadasha|"
    r"yoga|dosha|dosh|sade[- ]sati|navamsa|rashi|rasi|transit\w*|retrograde|house\b|bhava)|"
    # Part F's gemstone chapter is grounded in the engine's stone table rather than in a placement,
    # so its vocabulary anchors it just as well; without these the whole chapter read as filler.
    r"\b(?:ruby|manikya|pearl|mukta|moti|coral|moonga|emerald|panna|sapphire|neelam|pukhraj|topaz|"
    r"gomed|hessonite|lehsunia|cat'?s eye|silver|gold|copper|finger|ratti|carats?|"
    r"sunday|monday|tuesday|wednesday|thursday|friday|saturday|mantra|beej)|"
    r"माणिक|मोती|पोवळे|मूंगा|पाचू|पन्ना|नीलम|पुखराज|पुष्कराज|गोमेद|चांदी|सोन|सोना|तांब|बोट|अंगुली|"
    r"रविवार|सोमवार|मंगळवार|मंगलवार|बुधवार|गुरुवार|शुक्रवार|शनिवार|मंत्र|रत्न|"
    r"लग्न|नक्षत्र|चरण|दशा|अंतर्दशा|महादशा|प्रत्यंतर|योग|दोष|साडेसाती|साढ़ेसाती|नवमांश|राशी|राशि|गोचर|वक्री|भाव|स्थान",
    _I)

# Throat-clearing and stock phrases. Never worth cutting a paragraph over; they drive one rewrite.
_RE_BOILERPLATE = re.compile(
    r"\b(?:in conclusion|to (?:sum up|summari[sz]e)|as (?:mentioned|stated|noted|discussed) (?:above|earlier|before)|"
    r"this (?:chapter|section|part) (?:will|aims to|covers)|it is (?:important|worth) (?:to note|noting|remembering)|"
    r"at the end of the day|the journey of life|life is a journey|remember that life|"
    r"every (?:individual|person) is unique|as with (?:any|every) chart)\b|"
    r"निष्कर्ष\s*(?:में|म्हणून|तः)|सारांश\s*(?:में|म्हणून)|जैसा कि (?:ऊपर|पहले)|जसे की (?:वर|आधी)|"
    r"जीवन (?:एक )?(?:यात्रा|प्रवास)|प्रत्येक व्यक्ती (?:वेगळी|अद्वितीय)|हर व्यक्ति (?:अलग|अद्वितीय)", _I)

# Fact types the engine does not compute, so the AI may not assert them. `optional` names the Facts flag
# that switches a rule off once calc-engine-2 starts supplying that fact.
_UNTRACEABLE = (
    ("aspect", "has_aspects",
     r"\b(?:aspect(?:s|ed|ing)?|drishti|drsti|full aspect|special aspect)\b|"
     r"{D}(?:दृष्टी|दृष्टि|दृष्टीत|दृष्टिमें|प्रतियोग)"),
    # The engine's `dignity` block computes exaltation, debilitation, moolatrikona, own sign,
    # natural friendship and combustion - all fair game once it is in the data.
    ("dignity", "has_dignity",
     r"\b(?:exalt\w+|debilitat\w+|neecha|neech(?!\w)|uchcha|uccha|combust\w*|astangata|"
     r"mool ?trikona|moolatrikona|friendly sign|enemy sign|sign of (?:a )?(?:friend|enemy))\b|"
     r"{D}(?:उच्च(?:स्थ|चा|ची)?|नीच(?:स्थ|चा|ची)?|उच्चीचा|नीचीचा|अस्त(?:ंगत|ंगती)|मूलत्रिकोण|"
     r"मित्र राशी|मित्र राशि|शत्रू राशी|शत्रु राशि)"),
    # Planetary war is not computed by anything in the engine, at any time.
    ("war", None, r"\b(?:planetary war|graha ?yuddha)\b|{D}ग्रहयुद्ध"),
    ("varga", "has_navamsa",
     r"\bnavamsa|navamsha|navansh|d-?9\b|{D}नवमांश"),
    ("varga", None,
     r"\b(?:dashamsha|dasamsa|d-?10|saptamsha|saptamsa|d-?7|drekkana|dreshkana|d-?3|chaturthamsa|d-?4|"
     r"trimsamsa|d-?30|shodasavarga|ashtakavarga|ashtaka ?varga|bindus?|sarvashtakavarga)\b|"
     r"{D}(?:दशमांश|सप्तमांश|द्रेष्काण|त्रिंशांश|अष्टकवर्ग|बिंदू)"),
    ("yoga", "has_yogas",
     r"\b(?:gaja ?kesari|raj(?:a)? ?yoga|dhana ?yoga|kaal ?sarp\w*|kal ?sarp\w*|pitra ?dosh\w*|"
     r"pancha ?mahapurusha|ruchaka yoga|bhadra yoga|hamsa yoga|malavya yoga|shasha yoga|"
     r"neecha ?bhanga|vipreet\w* raj\w*|budhaditya|chandra ?mangal(?:a)? yoga)\b|"
     r"{D}(?:गजकेसरी|राजयोग|धनयोग|कालसर्प|काळसर्प|पितृदोष|पंचमहापुरुष|रुचक योग|भद्र योग|हंस योग|"
     r"मालव्य योग|शश योग|नीचभंग|विपरीत राजयोग|बुधादित्य|चंद्रमंगल योग)"),
)

_UNTRACEABLE_WHY = {
    "aspect": "aspects are not in the data - the engine does not compute drishti, so do not assert one",
    "dignity": "exaltation, debilitation, combustion, mool trikona, friendship and planetary war are not in "
               "the data - use `in_own_sign`, `rules_houses` and `sign_lord`, which are",
    "varga": "that divisional chart is not in the data - only the charts the data actually contains may be read",
    "yoga": "the data lists no yogas for this chart, so no yoga may be named",
    "war": "planetary war (graha yuddha) is not computed by the engine, so it may not be asserted",
}

_UNTRACEABLE_PATTERNS = [(kind, flag, re.compile(pattern.replace("{D}", _NOT_DEV_BEFORE), _I))
                         for kind, flag, pattern in _UNTRACEABLE]


def untraceable_issues(text: str, facts: Facts) -> list[Issue]:
    """Claims about fact types the engine never supplied. Blocking: they are invented facts - the AI
    interprets, it never calculates."""
    issues = []
    for kind, flag, pattern in _UNTRACEABLE_PATTERNS:
        if flag and getattr(facts, flag, False):
            continue
        for match in pattern.finditer(text or ""):
            found = match.group(0)
            issues.append(Issue("untraceable", found, f"'{found}': {_UNTRACEABLE_WHY[kind]}"))
    return issues


def filler_issues(text: str) -> list[Issue]:
    """Paragraph-level padding: prose that names nothing from this chart, and stock phrases."""
    issues = []
    for match in _RE_BOILERPLATE.finditer(text or ""):
        issues.append(Issue("boilerplate", match.group(0),
                            f"'{match.group(0)}': stock phrasing - the reader paid for their chart, "
                            "not for filler. Say the thing itself or drop the sentence"))
    if len((text or "").split()) >= FILLER_MIN_WORDS and not _RE_CHART_ANCHOR.search(text):
        issues.append(Issue("filler", (text or "")[:60],
                            "this paragraph names no graha, sign, house, period, nakshatra or date from "
                            "this chart, so it would read the same in anyone's book. Ground it in a "
                            "placement or leave it out"))
    return issues


def allow_range(facts: Facts, start: str, end: str) -> None:
    """Widen `facts` to every month and year a supplied window spans, in place.

    The engine hands the book dated windows ("Sep 2026 - Nov 2026"). Writing "in October" inside that
    window is true and useful, but October has no engine event in it, so the month check would cut the
    sentence. Specific *days* are deliberately not widened: a named date must still be an engine date.
    """
    try:
        first, last = dt.date.fromisoformat(start[:10]), dt.date.fromisoformat(end[:10])
    except ValueError:
        return
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        facts.months.add((year, month))
        facts.years.add(year)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


# A date range the model wrote itself, e.g. "Jan 2028 - May 2028" or "जानेवारी 2028 ते मे 2028". Inside a
# timeline window this is always wrong: the engine's own label is printed above the text, so a second,
# model-written range can only duplicate it or contradict it (team-lead contract with the PDF layer).
_RE_WRITTEN_RANGE = re.compile(
    rf"{_MONTH},?\s*\d{{4}}\s*(?:-|–|—|to\b|till\b|until\b|through\b|ते|पर्यंत|तक|से)\s*{_MONTH},?\s*\d{{4}}|"
    rf"{_MONTH}\s*(?:-|–|—|to\b|ते|तक)\s*{_MONTH},?\s*\d{{4}}", _I)


def written_range_issues(text: str) -> list[Issue]:
    """A date range the model typed out. Only ever called on text inside a timeline window."""
    return [Issue("date_range", match.group(0),
                  f"'{match.group(0)}': the window's date range is printed from the engine above this "
                  "text - never write it yourself. Say what happens, not when")
            for match in _RE_WRITTEN_RANGE.finditer(text or "")]


def narrow_to_window(facts: Facts, window) -> Facts:
    """`facts` with the transit placements cut down to the ones inside ONE timeline window, or - when
    `window` is a list of windows - inside that set of them.

    The book covers about twenty years, and over twenty years a slow graha visits every sign. Checking
    a window's prose against the whole span would accept "Guru enters your 9th house" in a window where
    Guru enters the 1st - which is exactly the defect the house convention exists to stop. Each window's
    text is therefore checked against that window's own transits (plus, always, the birth chart).

    Months and years are narrowed the same way and for the same reason: the whole book covers about
    twenty years, so an unscoped month check accepts any month at all. Inside a window, a month is
    allowed when the window spans it. Specific days stay as they are - a named day must still be an
    engine date somewhere in the data.

    Degrees, the lagna and the natal chart are untouched.
    """
    windows = window if isinstance(window, list) else [window]
    local = collect_facts(windows)
    grahas = set(facts.natal_signs) | set(facts.natal_houses) | set(local.graha_signs) | set(local.graha_houses)
    signs = {g: set(facts.natal_signs.get(g, ())) | set(local.graha_signs.get(g, ())) for g in grahas}
    houses = {g: set(facts.natal_houses.get(g, ())) | set(local.graha_houses.get(g, ())) for g in grahas}
    scoped = replace(facts,
                     graha_signs={g: v for g, v in signs.items() if v},
                     graha_houses={g: v for g, v in houses.items() if v},
                     months=set(), years=set())
    for entry in windows:
        engine_range = entry.get("range") or {}
        if engine_range.get("start") and engine_range.get("end"):
            allow_range(scoped, engine_range["start"], engine_range["end"])
    scoped.years |= {d.year for d in local.dates}
    scoped.months |= {(d.year, d.month) for d in local.dates}
    return scoped


def near_horizon(facts: Facts, timeline: dict) -> Facts:
    """`facts` for book prose that is NOT inside a timeline window - Parts A, B, C, E, F, H.

    Why this exists. The book covers about twenty years, so the whole-book fact set has every slow
    graha in every sign, and a transit claim checked against it passes whatever house it names. That
    is fine inside a timeline window, where the text is scoped to that window's own transits. It is
    NOT fine in a personality or dosha chapter, where a from-Moon house written as a from-lagna house
    is exactly as wrong as it was in the live transcript that started all this - and would sail
    through.

    So non-window prose is checked against the birth chart plus the CURRENT YEAR's transits only: the
    same near horizon the consultation chat uses, which is why the chat layer never lost this check.
    A chapter may say "Shani is currently moving through Meena"; it may not invent where Guru will be
    in 2044, because prose that wants to talk about 2044 belongs in a window.

    Only the PLACEMENTS are narrowed. Dates, months and years stay whole-book, because Part G's table
    legitimately names every year in the book and Part E names periods years out; those are checked
    against the engine's own dates, which is the right universe for them. It is the sign and house
    claims that need a horizon.

    KNOWN LIMIT, pinned in tests/test_historical_defects.py: because the two are checked
    independently, a date and a placement that are each valid on their own pass together even when
    the pairing is wrong - "Shani enters Mesha in 2031" survives, since Shani does enter Mesha (in
    2027) and 2031 is a year in the report. Narrowing dates here would reject Part G's year table,
    so the containment is a prompt rule instead: outside the timeline chapters a period is named by
    what it is, not by a date. Dated claims belong in windows, where both halves are scoped together.
    """
    from .engine_facts import current_year_windows

    scoped = narrow_to_window(facts, list(current_year_windows(timeline)))
    return replace(scoped, dates=facts.dates, months=facts.months, years=facts.years)


# A heading that never made it out of English. In a Hindi or Marathi book these are what the
# auto-generated contents page prints, so one English chapter title is visible on page two of a paid
# book. Latin *words* are the signal; Latin digits are fine and required (years stay 2028), and a
# bracketed English gloss after Devanagari ("मीन (Pisces)") is normal practice, so a heading only fails
# when it carries Latin letters and no Devanagari at all.
_RE_DEVANAGARI = re.compile(rf"[{_DEV}]")
_RE_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
DEVANAGARI_LANGUAGES = ("hi", "mr")


def untranslated_heading(text: str, language: str) -> Issue | None:
    """A heading left in English in a Devanagari book, or None."""
    if language not in DEVANAGARI_LANGUAGES or not (text or "").strip():
        return None
    if _RE_DEVANAGARI.search(text) or not _RE_LATIN_WORD.search(text):
        return None
    return Issue("untranslated", text.strip()[:60],
                 f"'{text.strip()[:60]}': this heading is still in English. Every heading in a "
                 "Hindi or Marathi book is written in Devanagari - only numerals stay in Latin "
                 "digits. Chapter ids like `year_2028` are internal labels, never headings")
