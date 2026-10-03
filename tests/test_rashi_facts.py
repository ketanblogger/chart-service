"""Every astrological fact claim in the twelve sign-hub essays, checked against the engine.

These essays are STATIC prose - twelve signs in three languages, 36 bodies - and they make hard, checkable
claims: which houses the sign lord also owns, where each graha is exalted and debilitated and at what degree,
which nakshatras and padas the sign spans and who rules them, and which signs Saturn must be in for sade sati
and dhaiya. Prose like that is written once, translated twice, and then never recomputed. Two errors were
found by reading one page:

  "Venus, and the second house it owns for you" on Libra, over a body that correctly says Venus owns the 8th.
  "the sign lord of your 12th house is weak" about the Sun on Libra, which rules the 11th from Libra.

Both had been through review and were live in three languages. So the claims are not proofread here, they are
RECOMPUTED: tests/rashi_truth.py derives every fact from app/engine/constants.py and app/engine/dignity.py,
the same tables the chart is drawn from.

WHAT THIS DELIBERATELY DOES NOT DO is pass when it understands nothing. A regex that matches no sentences is
a green test over an empty population, which is the exact failure this file exists to catch - so every claim
kind asserts its own minimum yield across the twelve signs, and the parser reports any sentence that looks
like a claim and that it could not read.
"""

import pathlib
import re

import pytest

from app.engine import constants
from app.rashifal import i18n as rashifal_i18n
from app.web import i18n, pages

from . import rashi_truth as truth

LANGS = ("en", "hi", "mr")
RASHIS = tuple(i18n.RASHI_KEYS)


# ---- naming: the same graha and sign under every name the three trees use ---------------------------


def _sign_names(lang: str) -> dict[str, int]:
    """Every spelling of every sign in this tree -> its 1-12 index."""
    names: dict[str, int] = {}
    for index in range(1, 13):
        english, sanskrit, devanagari, _ = truth.SIGNS[index - 1]
        key = i18n.RASHI_KEYS[index - 1]
        for name in (english, sanskrit, devanagari, i18n.rashi_names(key, lang)["rashi"]):
            names[name] = index
        if lang == "en":
            # the essays use the short Latin forms ("Mesh", "Vrishabh") as well as the Sanskrit ones
            names[i18n.rashi_names(key, lang)["latin"]] = index
    return names


def _graha_names(lang: str) -> dict[str, str]:
    """Every spelling of every graha in this tree -> its English key."""
    names: dict[str, str] = {}
    for key, (sanskrit, devanagari) in constants._GRAHAS.items():
        for name in (key, sanskrit, devanagari):
            names[name] = key
        if lang in ("hi", "mr"):
            names[rashifal_i18n.graha_name({"key": key, "devanagari": devanagari}, lang)] = key
    return names


_NAK_TABLES: dict[str, dict] = {}


def _nakshatra_names(lang: str) -> dict[str, int]:
    if lang in _NAK_TABLES:
        return _NAK_TABLES[lang]
    names: dict[str, int] = {}
    for index, (name, devanagari) in enumerate(truth.NAKSHATRAS):
        for spelling in (name, devanagari):
            names[spelling] = index
        if lang in ("hi", "mr"):
            names[rashifal_i18n.nakshatra_name({"name": name, "devanagari": devanagari}, lang)] = index
    _NAK_TABLES[lang] = names
    return names


# Ordinals as the three trees write them. Hindi and Marathi inflect, so every form the essays use is listed.
ORDINALS = {
    "en": {str(n) + suffix: n for n, suffix in
           [(1, "st"), (2, "nd"), (3, "rd"), *((n, "th") for n in range(4, 13))]}
          | {w: n + 1 for n, w in enumerate(
              "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth".split())},
    "hi": {"पहले": 1, "पहला": 1, "पहली": 1, "दूसरे": 2, "दूसरा": 2, "दूसरी": 2, "तीसरे": 3, "तीसरा": 3,
           "चौथे": 4, "चौथा": 4, "पाँचवें": 5, "पांचवें": 5, "पाँचवाँ": 5, "छठे": 6, "छठा": 6, "छठवें": 6,
           "सातवें": 7, "सातवाँ": 7, "आठवें": 8, "आठवाँ": 8, "नवें": 9, "नौवें": 9, "नवाँ": 9,
           "दसवें": 10, "दसवाँ": 10, "ग्यारहवें": 11, "ग्यारहवाँ": 11, "बारहवें": 12, "बारहवाँ": 12},
    "mr": {"पहिल्या": 1, "पहिला": 1, "दुसऱ्या": 2, "दुसरा": 2, "तिसऱ्या": 3, "तिसरा": 3,
           "चौथ्या": 4, "चौथा": 4, "पाचव्या": 5, "पाचवा": 5, "सहाव्या": 6, "सहावा": 6,
           "सातव्या": 7, "सातवा": 7, "आठव्या": 8, "आठवा": 8, "नवव्या": 9, "नववा": 9,
           "दहाव्या": 10, "दहावा": 10, "अकराव्या": 11, "अकरावा": 11, "बाराव्या": 12, "बारावा": 12},
}
NAKSHATRA_WORD = {"en": r"nakshatra|pada|Ashwini|Bharani|Krittika|Rohini|Mrigashira|Ardra|Punarvasu|Pushya|"
                        r"Ashlesha|Magha|Phalguni|Hasta|Chitra|Swati|Vishakha|Anuradha|Jyeshtha|Mula|"
                        r"Purvashadha|Uttarashadha|Shravana|Dhanishta|Shatabhisha|Bhadrapada|Revati",
                  "hi": r"नक्षत्र|चरण", "mr": r"नक्षत्र|चरण"}
DEICTIC = {"en": r"\bhere\b|\bthis sign\b", "hi": r"यहाँ|इसी राशि|इस राशि", "mr": r"इथे|याच राशी|या राशी"}
DIGNITY_WORDS = {"en": r"exalt|debilitat|weakest|lowest point|strongest",
                 "hi": r"उच्च|नीच|कमज़ोर|सबसे नीचे",
                 "mr": r"उच्च|नीच|कमकुवत|सर्वात खाली"}
HOUSE_WORD = {"en": r"houses?", "hi": r"भाव", "mr": r"भाव|स्थान"}
OWNS_WORD = {"en": r"owns?", "hi": r"मालिक|स्वामी", "mr": r"मालक|स्वामी"}


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.:;।])\s+", text) if s.strip()]


def body_text(key: str, lang: str) -> list[tuple[str, str]]:
    """(where, sentence) for every sentence of a sign's hub body, with placeholders FILLED.

    Filled, because `{lord}` is what the file contains and "Venus (Shukra)" is what a reader sees, and the
    claim being checked is the one on the page."""
    copy = pages.get("rashifal-rashi", lang, **i18n.rashi_names(key, lang))
    out: list[tuple[str, str]] = []
    for sentence in sentences(copy.intro):
        out.append(("intro", sentence))
    for section in copy.sections:
        out.append(("heading", section.heading))
        for block in section.blocks:
            for piece in (block if isinstance(block, (list, tuple)) else [block]):
                if isinstance(piece, str):
                    for sentence in sentences(piece):
                        out.append((section.heading[:40], sentence))
    for question, answer in (copy.faqs or ()):
        for sentence in sentences(question) + sentences(answer):
            out.append(("faq", sentence))
    return out


# MATCHING A NAME IN HINDI AND MARATHI. The essays inflect: तूळ becomes तुळेच्या, कर्क becomes कर्केच्या,
# मेष becomes मेषेच्या - and the vowel LENGTH changes with the case ending, so an exact match finds nothing.
#
# What is compared is the word with vowel LENGTH normalised (ी->ि, ू->ु) and the name's own trailing vowel
# sign dropped, then matched as a prefix. Stripping every vowel mark instead - the first thing tried here -
# turns मूल (the nakshatra) into मल, which is a prefix of मालिक ("owner"), and the checker then reported Mula
# in sixty Hindi sentences that are about ownership. Normalising only the LENGTH keeps मुल and मालिक apart
# while still matching तुळ inside तुळेच्या, and it keeps धनु (the sign) out of धनिष्ठा (the nakshatra).
_LENGTH = str.maketrans({"ी": "ि", "ू": "ु", "ई": "इ", "ऊ": "उ"})
_TRAILING = re.compile(r"[\u093E-\u094D]+$")


def fold(text: str) -> str:
    return text.translate(_LENGTH)


def stem(name: str) -> str:
    return _TRAILING.sub("", fold(name))


_VOCAB_CACHE: dict[str, list] = {}


def _vocab(lang: str) -> list[tuple[str, str, object]]:
    """(stem, kind, value) for every sign, graha and nakshatra name in this tree, longest stem first.

    ONE vocabulary for all three kinds, because the collisions are BETWEEN kinds: धनु (the sign) is a prefix
    of धनिष्ठा (the nakshatra), and a matcher that only knows about signs when it is looking for signs finds
    Sagittarius inside Dhanishta. Longest stem wins, across kinds, one name per word."""
    if lang not in _VOCAB_CACHE:
        rows = []
        for name, value in _sign_names(lang).items():
            rows.append((stem(name), "sign", value))
        for name, value in _graha_names(lang).items():
            rows.append((stem(name), "graha", value))
        for name, value in _nakshatra_names(lang).items():
            rows.append((stem(name), "nakshatra", value))
        _VOCAB_CACHE[lang] = sorted((r for r in rows if len(r[0]) >= 2), key=lambda r: -len(r[0]))
    return _VOCAB_CACHE[lang]


def _match_kind(sentence: str, lang: str, kind: str) -> set:
    """Every value of `kind` named in the sentence."""
    found = set()
    for word in re.split(r"[\s,.।;:()\-]+", sentence):
        folded = fold(word)
        for name_stem, row_kind, value in _vocab(lang):
            if folded.startswith(name_stem):
                if row_kind == kind:
                    found.add(value)
                break                          # one name per word: the longest, whatever kind it is
    return found


def _match_names(sentence: str, names: dict[str, object], lang: str) -> set:
    """Signs, grahas or nakshatras in a sentence - the kind is inferred from the table handed in."""
    if lang == "en":
        return {value for name, value in names.items()
                if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", sentence)}
    sample = next(iter(names.values()))
    kind = ("graha" if isinstance(sample, str)
            else "nakshatra" if names is _NAK_TABLES.get(lang) else "sign")
    return _match_kind(sentence, lang, kind)


def grahas_in(sentence: str, names: dict[str, str], lang: str = "en") -> list[str]:
    """The graha keys named in a sentence."""
    return sorted(_match_names(sentence, names, lang))


def ordinals_in(sentence: str, lang: str) -> list[int]:
    out = []
    for word, value in sorted(ORDINALS[lang].items(), key=lambda kv: -len(kv[0])):
        pattern = (rf"(?<![\w]){re.escape(word)}(?![\w])" if lang == "en"
                   else rf"(?<![ऀ-ॿ]){re.escape(word)}(?![ऀ-ॿ])")
        if re.search(pattern, sentence):
            out.append(value)
    return out


# ---- the claims ------------------------------------------------------------------------------------


def context_grahas(rows: list[tuple[str, str]], i: int, names: dict[str, str], lang: str) -> list[str]:
    """Grahas named in this sentence, else in the one before it, else in the section heading.

    "the sign lord of your 12th house is weak" names no graha: its subject is the Sun, from the heading
    two sentences up. A claim whose subject is in the previous sentence is still a claim."""
    for candidate in (rows[i][1], rows[i - 1][1] if i else "", rows[i][0]):
        found = grahas_in(candidate, names, lang)
        if found:
            return found
    return []


@pytest.mark.parametrize("lang", LANGS)
def test_every_house_a_graha_is_said_to_own_is_a_house_it_owns(lang):
    """"<graha> also owns your 8th house from here" - recomputed, not proofread. The houses a graha owns
    from a rashi follow from OWN_SIGNS and whole-sign counting, and nothing else."""
    graha_names, checked, failures = _graha_names(lang), 0, []
    for key in RASHIS:
        rashi = i18n.RASHI_KEYS.index(key) + 1
        rows = body_text(key, lang)
        for i, (where, sentence) in enumerate(rows):
            if not re.search(OWNS_WORD[lang], sentence) or not re.search(HOUSE_WORD[lang], sentence):
                continue
            houses = ordinals_in(sentence, lang)
            if not houses:
                continue
            grahas = context_grahas(rows, i, graha_names, lang)
            if len(grahas) != 1:
                continue                      # two grahas in one sentence: not a claim this can attribute
            owned = truth.houses_owned_from(rashi, grahas[0])
            checked += 1
            for house in houses:
                if house not in owned:
                    failures.append(f"{lang}/{key} [{where}]: {grahas[0]} is said to own the {house}th house "
                                    f"from {key}, but it owns {owned} - {sentence[:110]}")
    assert not failures, "\n".join(failures)
    assert checked >= 12, f"only {checked} ownership claims parsed in {lang} - the parser has gone blind"


@pytest.mark.parametrize("lang", LANGS)
def test_every_house_lord_claim_names_the_right_graha(lang):
    """"the sign lord of your Nth house" - the lord of the Nth sign counted from the rashi."""
    patterns = {"en": r"sign lord of your (\w+) house",
                "hi": r"(\S+)\s+भाव का (?:स्वामी|मालिक)",
                "mr": r"(\S+)\s+(?:भाव|स्थान)(?:ाचा|चा)?\s*(?:स्वामी|मालक)"}
    graha_names, checked, failures = _graha_names(lang), 0, []
    for key in RASHIS:
        rashi = i18n.RASHI_KEYS.index(key) + 1
        rows = body_text(key, lang)
        for i, (where, sentence) in enumerate(rows):
            for word in re.findall(patterns[lang], sentence):
                house = ORDINALS[lang].get(word.strip("।,."))
                if house is None:
                    continue
                grahas = context_grahas(rows, i, graha_names, lang)
                if len(grahas) != 1:
                    continue
                checked += 1
                expected = truth.lord_of_house(rashi, house)
                if grahas[0] != expected:
                    failures.append(f"{lang}/{key} [{where}]: calls {grahas[0]} the lord of the {house}th "
                                    f"house from {key}; the {house}th is "
                                    f"{truth.SIGNS[truth.sign_at_house(rashi, house) - 1][0]}, ruled by "
                                    f"{expected} - {sentence[:110]}")
    assert not failures, "\n".join(failures)
    assert checked >= 1, f"only {checked} house-lord claims parsed in {lang}"


@pytest.mark.parametrize("lang", LANGS)
def test_every_exaltation_and_debilitation_sign_is_the_engines(lang):
    """Exaltation comes from dignity.EXALTATION; debilitation is the 7th sign from it, which is the rule
    that table itself states rather than a second list to keep in step."""
    # The dignity WORD, not the word plus a postposition: Marathi writes परमोच्च (sandhi, so a literal
    # "उच्च" does not appear in it) and Hindi "उच्च का होता है", and pinning the postposition found neither.
    strong = {"en": r"exalted", "hi": r"उच्च", "mr": r"परमोच्च|उच्च"}
    weak = {"en": r"weakest|debilitated|lowest point", "hi": r"नीच|सबसे कमज़ोर",
            "mr": r"परमनीच|नीच|सर्वात कमकुवत|सर्वात खाली"}
    sign_names, graha_names = _sign_names(lang), _graha_names(lang)
    checked, failures = 0, []
    for key in RASHIS:
        rows = body_text(key, lang)
        for i, (where, sentence) in enumerate(rows):
            for kind, pattern in (("exalted", strong[lang]), ("debilitated", weak[lang])):
                # ANCHORED AT A WORD START. नीच is a substring of शनीचा and शनीचे ("Saturn's"), which appear
                # in nearly every Saturn paragraph - unanchored, the checker read eight Marathi sentences
                # about Saturn's transit as claims that Saturn is debilitated in whatever sign they mention.
                if not re.search(rf"(?<![\u0900-\u097F])(?:{pattern})", sentence):
                    continue
                signs = _match_names(sentence, sign_names, lang)
                grahas = grahas_in(sentence, graha_names, lang)
                # "The Sun is debilitated HERE" names no sign - the sign is the page. Most of the Hindi and
                # Marathi dignity sentences are written that way, so without this the two Devanagari trees
                # would be checked on three claims each while English was checked on twelve.
                if not signs and re.search(DEICTIC[lang], sentence):
                    signs = {i18n.RASHI_KEYS.index(key) + 1}
                if len(grahas) != 1 or len(signs) != 1:
                    continue
                graha, sign = grahas[0], signs.pop()
                if graha not in truth.GRAHAS:
                    continue
                expected = (truth.exaltation(graha) if kind == "exalted" else truth.debilitation(graha))[0]
                checked += 1
                if sign != expected:
                    failures.append(f"{lang}/{key} [{where}]: says {graha} is {kind} in "
                                    f"{truth.SIGNS[sign - 1][0]}; it is {kind} in "
                                    f"{truth.SIGNS[expected - 1][0]} - {sentence[:110]}")
    assert not failures, "\n".join(failures)
    assert checked >= 10, f"only {checked} dignity claims parsed in {lang}"


@pytest.mark.parametrize("lang", LANGS)
def test_every_dignity_degree_is_the_engines(lang):
    """"at 20 degrees of Libra" - the degree in EXALTATION, which debilitation shares."""
    # Marathi writes "तुळेच्या 20 अंशांवर" and Hindi "तुला के 20 अंश": the postposition between the sign and
    # the number differs, so the pattern takes whatever word carries the sign and lets the stem matcher read it.
    patterns = {"en": r"(\d+)\s+degrees of\s+(\w+)",
                "hi": r"(\S+)\s+(?:के\s+)?(\d+)\s*अंश",
                "mr": r"(\S+)\s+(\d+)\s*अंश"}
    sign_names, graha_names = _sign_names(lang), _graha_names(lang)
    checked, failures = 0, []
    for key in RASHIS:
        rows = body_text(key, lang)
        for i, (where, sentence) in enumerate(rows):
            if not re.search(DIGNITY_WORDS[lang], sentence):
                continue                      # "a Moon near 26 degrees of Aries" is a position, not a dignity
            for a, b in re.findall(patterns[lang], sentence):
                degree, sign_word = (a, b) if lang == "en" else (b, a)
                matched = _match_names(sign_word, sign_names, lang) if lang != "en" else \
                    {sign_names[sign_word]} if sign_word in sign_names else set()
                sign = next(iter(matched)) if len(matched) == 1 else None
                grahas = context_grahas(rows, i, graha_names, lang)
                if sign is None or len(grahas) != 1 or grahas[0] not in truth.GRAHAS:
                    continue
                graha = grahas[0]
                options = {truth.exaltation(graha), truth.debilitation(graha)}
                checked += 1
                if (sign, float(degree)) not in options:
                    failures.append(f"{lang}/{key} [{where}]: puts {graha} at {degree} degrees of "
                                    f"{truth.SIGNS[sign - 1][0]}; the engine has exaltation "
                                    f"{truth.exaltation(graha)} and debilitation {truth.debilitation(graha)} "
                                    f"- {sentence[:110]}")
    assert not failures, "\n".join(failures)
    # The floor is what the corpus CONTAINS, measured, not a target: its job is to fail when the parser
    # stops reading a tree, which is how a checker like this dies quietly. Marathi states fewer degrees in
    # prose than Hindi does; English and Hindi state the same seven.
    assert checked >= {"en": 7, "hi": 7, "mr": 5}[lang], f"only {checked} degree claims parsed in {lang}"


@pytest.mark.parametrize("lang", LANGS)
def test_every_nakshatra_named_is_one_the_sign_spans_and_has_the_right_lord(lang):
    """The nakshatras a sign spans and their padas are computed from the spans, not listed - a sign is 30
    degrees and a nakshatra 13 degrees 20 minutes, so the boundaries fall inside nakshatras and every sign
    covers exactly nine padas. The Vimshottari lord follows from the nakshatra's index."""
    ruled = {"en": r"ruled by", "hi": r"स्वामी", "mr": r"स्वामी"}
    nak_names, graha_names = _nakshatra_names(lang), _graha_names(lang)
    checked, failures = 0, []
    for key in RASHIS:
        rashi = i18n.RASHI_KEYS.index(key) + 1
        spanned = {index for index, _ in truth.nakshatra_spans(rashi)}
        rows = body_text(key, lang)
        for where, sentence in rows:
            # NAKSHATRA CONTEXT REQUIRED. The stem matcher reads मुलांच्या ("children's") as मूळ, and a sign
            # body that mentions children is not making a claim about Mula. A real nakshatra claim says so.
            if not re.search(NAKSHATRA_WORD[lang], sentence + " " + where):
                continue
            named = _match_names(sentence, nak_names, lang)
            if not named:
                continue
            for index in named:
                if index not in spanned:
                    failures.append(f"{lang}/{key} [{where}]: names {truth.NAKSHATRAS[index][0]}, which "
                                    f"{key} does not span (it spans "
                                    f"{[truth.NAKSHATRAS[i][0] for i in sorted(spanned)]}) - {sentence[:100]}")
            if not re.search(ruled[lang], sentence) or len(named) != 1:
                continue
            grahas = grahas_in(sentence, graha_names, lang)
            if len(grahas) != 1:
                continue
            index = named.pop()
            checked += 1
            expected = truth.nakshatra_lord(index)
            if grahas[0] != expected:
                failures.append(f"{lang}/{key} [{where}]: gives {truth.NAKSHATRAS[index][0]} the lord "
                                f"{grahas[0]}; its Vimshottari lord is {expected} - {sentence[:110]}")
    assert not failures, "\n".join(failures)
    assert checked >= 12, f"only {checked} nakshatra-lord claims parsed in {lang}"


@pytest.mark.parametrize("lang", LANGS)
def test_sade_sati_and_dhaiya_name_the_right_signs(lang):
    """Sade sati is Saturn in the 12th, 1st or 2nd from the Moon sign; dhaiya the 4th or the 8th. These are
    the same definitions app/engine/sadesati.py computes the live dates from."""
    sade = {"en": r"sade sati", "hi": r"साढ़ेसाती", "mr": r"साडेसाती"}
    # Marathi calls it अडीचकी, not ढय्या. The first version of this test looked for ढय्या in the Marathi
    # tree, found it nowhere, and checked no Marathi dhaiya claim at all while reporting a pass.
    dhaiya = {"en": r"[Dd]haiya", "hi": r"ढैया|ढय्या", "mr": r"अडीचकी|ढय्या|ढैय्या"}
    sign_names = _sign_names(lang)
    checked, failures = 0, []
    for key in RASHIS:
        rashi = i18n.RASHI_KEYS.index(key) + 1
        for where, sentence in body_text(key, lang):
            signs = _match_names(sentence, sign_names, lang)
            for label, pattern, expected in (("sade sati", sade[lang], truth.sade_sati_signs(rashi)),
                                             ("dhaiya", dhaiya[lang], truth.dhaiya_signs(rashi))):
                if not re.search(pattern, sentence):
                    continue
                # the sign's own name appears in most of these sentences; the claim is the OTHER signs
                named = signs - ({rashi} if label == "dhaiya" else set())
                if len(named) != len(expected):
                    continue
                checked += 1
                if named != set(expected):
                    # The sentence may be about ANOTHER sign - the Aquarius FAQ explains Capricorn's sade
                    # sati to contrast it. If the claim is right for a sign the sentence itself names, it is
                    # a correct claim about that sign rather than a wrong one about this page's.
                    about = [other for other in range(1, 13)
                             if named == set(truth.sade_sati_signs(other) if label == "sade sati"
                                             else truth.dhaiya_signs(other)) and other in signs]
                    if about:
                        continue
                    failures.append(f"{lang}/{key} [{where}]: {label} signs given as "
                                    f"{sorted(truth.SIGNS[i - 1][0] for i in named)}; they are "
                                    f"{[truth.SIGNS[i - 1][0] for i in expected]} - {sentence[:110]}")
    assert not failures, "\n".join(failures)
    assert checked >= 12, f"only {checked} sade sati / dhaiya claims parsed in {lang}"


@pytest.mark.parametrize("lang", LANGS)
def test_the_one_date_claim_is_computed_and_not_written(lang):
    """"The Sun falls to its lowest point at 10 degrees of Libra, around the middle of October" - it does
    not; it gets there on the 27th, and by 2027 on the 28th. A sentence cannot track a date that drifts, so
    the copy carries a placeholder and app/web/pages.py fills it from the ephemeris.

    Asserted two ways: the rendered page must show the engine's date, and the SOURCE must not contain a
    month written by hand next to that claim - which is what would quietly come back."""
    from app.engine.core import from_julian_day
    from app.web.pages import _sun_low_jd, sun_low_date
    from zoneinfo import ZoneInfo

    expected = sun_low_date(lang)
    page = " ".join(sentence for _, sentence in body_text("tula", lang))
    assert expected in page, f"{lang}: the Libra hub does not carry the computed date {expected!r}"

    # the computed date really is the Sun at 10 degrees of sidereal Libra
    import datetime as dt
    jd = _sun_low_jd(dt.datetime.now(dt.timezone.utc).year)
    assert jd is not None
    from app.engine.core import longitude_and_speed
    longitude, _ = longitude_and_speed(jd, "Sun")
    assert abs(longitude - 190.0) < 0.05, longitude
    day = from_julian_day(jd).astimezone(ZoneInfo("Asia/Kolkata")).day
    assert str(day) in expected

    source = pathlib.Path(f"app/web/content/rashi_{lang}.py").read_text()
    assert "{sun_low_date}" in source, f"{lang}: the date is not a placeholder any more"
