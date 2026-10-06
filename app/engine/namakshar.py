"""Namakshar (Avakahada chakra): first syllable of a name -> nakshatra pada -> rashi, for by-name matching.

Each of the 108 nakshatra padas owns one starting sound. A person whose birth details are unknown is
traditionally assigned the pada whose sound begins their name; guna milan then runs on those padas.
This is a convention, not astronomy: matching from birth details is always more accurate, and every
result says so.

Table - verified against two independently published tables, which agree on all 108 padas:
  [1] Drik Panchang, "Hindu Name Initials - List of 108 Pada Swars based on 27 Nakshatras"
      https://www.drikpanchang.com/swar-siddhanta/nakshatra/nakshatra-pada-swar-siddhanta.html
  [2] Bhrigu Pandit, "नक्षत्रों के चरण तथा इनके चरणाक्षर"  https://www.bhrigupandit.com/ (article of that title)
Differences between them are spelling only: short / long vowel signs (चु / चू, इ / ई - the chakra has five
vowel classes a i u e o, length is not distinguished); bare consonant vs. consonant + ा for the one-pada
consonants (ध / धा, फ / फा, ढ / ढ़); and Uttara Bhadrapada pada 4 printed as ञ in [1] and ण in [2] (a misprint
in [2]: ण is Hasta pada 3 in both). Neither affects any lookup.

Abhijit: [2] (and most Hindi sources) list जू जे जो खा for the intercalary 28th nakshatra, which the 27-fold
guna milan does not use. Abhijit spans 276°40'-280°53'20": its first three quarters lie inside Uttarashadha
pada 4 and its last quarter almost wholly inside Shravana pada 1, so जू जे जो -> Uttarashadha 4 and
खा -> Shravana 1 (all Makara either way). Marked `convention`.

Sounds that are not in the chakra (no source assigns them; these are the conventions in common use, marked
`convention` or `ambiguous` in the result):
  श -> स · ब -> व · conjuncts take their first consonant (क्ष -> क, त्र -> त, श्र -> श -> स, प्र -> प) ·
  ऐ -> ए, औ -> ओ · ज्ञ -> ज (as written) or ग (as pronounced "gya" in Hindi): ambiguous ·
  ऋ / ृ -> "ri" (Hindi, Sanskrit) or "ru" (Marathi): ambiguous in Devanagari, literal in Latin.
Latin script cannot show dental vs. retroflex: t = त / ट, th = थ / ठ, d = द / ड, dh = ध / ढ. The dental
reading is the default (far more common at the start of Indian names) and the result lists every candidate,
so the UI can ask. IAST letters (ṭ ḍ ṇ ṣ ś ṛ ā ī ū) are read exactly.
"""

import unicodedata

from .constants import NAKSHATRA_SPAN, PADA_SPAN, nakshatra_info, sign_info

# 27 nakshatras x 4 padas, in order from Ashwini pada 1.
_CHAKRA = """
चू चे चो ला | ली लू ले लो | अ ई उ ए | ओ वा वी वू | वे वो का की | कू घ ङ छ | के को हा ही | हू हे हो डा | डी डू डे डो |
मा मी मू मे | मो टा टी टू | टे टो पा पी | पू ष ण ठ | पे पो रा री | रू रे रो ता | ती तू ते तो | ना नी नू ने | नो या यी यू |
ये यो भा भी | भू धा फा ढा | भे भो जा जी | खी खू खे खो | गा गी गू गे | गो सा सी सू | से सो दा दी | दू थ झ ञ | दे दो चा ची
"""
_ABHIJIT = {("ज", "u"): (20, 3), ("ज", "e"): (20, 3), ("ज", "o"): (20, 3), ("ख", "a"): (21, 0)}  # (nakshatra, pada) 0-based
_ONE_PADA = set("घङछषणठधफढथझञ")  # consonants that own exactly one pada: any vowel lands there

_INDEPENDENT = {"अ": "a", "आ": "a", "ॲ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "e", "ऍ": "e",
                "ओ": "o", "औ": "o", "ऑ": "o", "ऋ": "ṛ", "ॠ": "ṛ"}
_MATRA = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "e", "ो": "o", "ौ": "o", "ॅ": "e", "ॉ": "o",
          "ृ": "ṛ", "ॄ": "ṛ"}
_CONSONANTS = set("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहळ")
_VIRAMA, _NUKTA = "्", "़"
_SKIP = {"‌", "‍", "ं", "ँ", "ः", _NUKTA}
_FOLD = {"श": "स", "ब": "व", "ळ": "ल"}  # not in the chakra -> the series conventionally used
_VOWEL_SIGN = {"a": "ा", "i": "ी", "u": "ू", "e": "े", "o": "ो"}
_VOWEL_LETTER = {"a": "अ", "i": "ई", "u": "उ", "e": "ए", "o": "ओ"}
_LATIN_OF = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ṅ", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ñ",
             "ट": "ṭ", "ठ": "ṭh", "ड": "ḍ", "ढ": "ḍh", "ण": "ṇ", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
             "प": "p", "फ": "ph", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "ष": "ṣ", "स": "s", "ह": "h"}

# Latin consonant tokens, longest first. Value: list of Devanagari readings, the default first.
_GYA = ["ज्ञ"]
_KSHA = ["क"]  # क्ष
_LATIN_CONSONANTS = {
    "dny": _GYA, "jny": _GYA, "gny": _GYA, "jñ": _GYA, "jn": _GYA, "gy": _GYA, "gn": _GYA,
    "ksh": _KSHA, "kṣ": _KSHA, "x": _KSHA, "chh": ["छ"], "ch": ["च"], "c": ["क"],
    "kh": ["ख"], "gh": ["घ"], "jh": ["झ"], "ṭh": ["ठ"], "ḍh": ["ढ"], "th": ["थ", "ठ"], "dh": ["ध"],  # ध / ढ share Purvashadha and its Dhanu half: never changes a score
   
    "ph": ["फ"], "bh": ["भ"], "sh": ["श"], "ś": ["श"], "ṣ": ["ष"], "ṭ": ["ट"], "ḍ": ["ड"], "ṇ": ["ण"], "ṅ": ["ङ"],
    "ñ": ["ञ"], "ng": ["ङ"],
    "k": ["क"], "q": ["क"], "g": ["ग"], "j": ["ज"], "z": ["ज"], "t": ["त", "ट"], "d": ["द", "ड"], "n": ["न"],
    "p": ["प"], "f": ["फ"], "b": ["ब"], "m": ["म"], "y": ["य"], "r": ["र"], "l": ["ल"], "ḷ": ["ल"], "v": ["व"],
    "w": ["व"], "s": ["स"], "h": ["ह"],
}
_LATIN_VOWELS = {"aa": "a", "ai": "e", "au": "o", "ou": "o", "ee": "i", "ii": "i", "ei": "e",
                 "oo": "u", "uu": "u", "ā": "a", "ī": "i", "ū": "u", "ē": "e", "ō": "o", "ṛ": "ṛ", "r̥": "ṛ",
                 "a": "a", "i": "i", "u": "u", "e": "e", "o": "o"}
_HONORIFICS = {"shri", "shree", "sri", "smt", "kum", "kumari", "mr", "mrs", "ms", "miss", "dr", "prof", "late", "ch",
               "श्री", "श्रीमती", "कु", "कुमारी", "डॉ", "सौ", "चि"}

NOTE = ("Derived from the first sound of each name (Avakahada chakra), not from a birth chart. If the date, time and "
        "place of birth are known, matching from birth details is more accurate.")


class NameError_(ValueError):
    """The name has no usable first syllable (empty, digits, another script)."""


def _build_chakra() -> dict:
    table = {}
    padas = [s for block in _CHAKRA.replace("\n", " ").split("|") for s in block.split()]
    assert len(padas) == 108
    for number, syllable in enumerate(padas):
        consonant, vowel = (None, _INDEPENDENT[syllable]) if syllable in _INDEPENDENT else (syllable[0], _MATRA.get(syllable[1:], "a"))
        slot = divmod(number, 4)
        if consonant in _ONE_PADA:
            for v in "aiueo":
                table[(consonant, v)] = slot
        else:
            table[(consonant, vowel)] = slot
    table.update(_ABHIJIT)
    return table


_TABLE = _build_chakra()
CANONICAL_SYLLABLES = [s for block in _CHAKRA.replace("\n", " ").split("|") for s in block.split()]  # index = nakshatra*4 + pada


def _syllable(consonant: str | None, vowel: str) -> str:
    if consonant is None:
        return _VOWEL_LETTER[vowel]
    return consonant if consonant in _ONE_PADA else consonant + _VOWEL_SIGN[vowel]


def _latin(consonant: str | None, vowel: str) -> str:
    return (_LATIN_OF[consonant] if consonant else "") + ("a" if consonant in _ONE_PADA else vowel)


def _first_token(name: str) -> str:
    text = unicodedata.normalize("NFC", name or "").strip()
    tokens = [t.strip(".,'\"()-") for t in text.replace(".", ". ").split()]
    tokens = [t for t in tokens if t]
    while len(tokens) > 1 and tokens[0].lower() in _HONORIFICS:
        tokens.pop(0)
    if not tokens:
        raise NameError_("name is empty")
    return tokens[0]


def _parse_devanagari(word: str) -> tuple[list[str | None], list[str], list[str]]:
    """(consonant readings, vowel readings, rules applied) for the first akshara."""
    rules = []
    first = word[0]
    if first in _INDEPENDENT:
        vowel = _INDEPENDENT[first]
        return [None if vowel != "ṛ" else "र"], _vowels(vowel, rules), rules  # ऋ = r + i / u
    if first not in _CONSONANTS:
        raise NameError_(f"cannot read a syllable from {word!r}")
    position, cluster = 1, [first]
    while position < len(word):  # conjunct: consonant (nukta)? virama consonant ...
        char = word[position]
        if char in _SKIP:
            position += 1
        elif char == _VIRAMA and position + 1 < len(word) and word[position + 1] in _CONSONANTS:
            cluster.append(word[position + 1])
            position += 2
        else:
            break
    vowel = _MATRA.get(word[position], "a") if position < len(word) else "a"
    if cluster[:2] == ["ज", "ञ"]:
        rules.append("ज्ञ is not in the chakra: read as ज (as written) or ग (as pronounced 'gya')")
        consonants = ["ज", "ग"]
    else:
        if len(cluster) > 1:
            rules.append(f"conjunct {'्'.join(cluster)}: the first consonant decides")
        consonants = [first]
    return consonants, _vowels(vowel, rules), rules


def _vowels(vowel: str, rules: list[str]) -> list[str]:
    if vowel != "ṛ":
        return [vowel]
    rules.append("ऋ is not in the chakra: read as 'ri' (Hindi / Sanskrit) or 'ru' (Marathi)")
    return ["i", "u"]


def _parse_latin(word: str) -> tuple[list[str | None], list[str], list[str]]:
    rules, text = [], word.lower()
    text = "".join(ch for ch in text if ch.isalpha() or unicodedata.combining(ch))
    if not text:
        raise NameError_(f"cannot read a syllable from {word!r}")

    def take(table: dict, start: int):
        for length in (3, 2, 1):
            chunk = text[start:start + length]
            if len(chunk) == length and chunk in table:
                return chunk, table[chunk]
        return None, None

    position, readings, cluster = 0, [None], 0
    while position < len(text):
        chunk, value = take(_LATIN_CONSONANTS, position)
        if chunk is None or (chunk == "y" and cluster and take(_LATIN_VOWELS, position + 1)[0] is None):
            break
        if cluster == 0:
            readings = list(value)
            if value is _GYA:
                rules.append("ज्ञ is not in the chakra: read as ज (as written) or ग (as pronounced 'gya')")
                readings = ["ग", "ज"] if chunk in ("gy", "gn", "gny") else ["ज", "ग"]
            elif value is _KSHA:
                rules.append("क्ष is not in the chakra: the first consonant, क, decides")
            elif len(value) > 1:
                rules.append(f"Latin '{chunk}' can be {' or '.join(value)}; {value[0]} (dental) is assumed")
        cluster += 1
        position += len(chunk)
    if cluster > 1 and readings[0] not in ("ज", "ग") and not rules:
        rules.append("consonant cluster: the first consonant decides")
    chunk, vowel = take(_LATIN_VOWELS, position)
    if chunk is None:
        if cluster == 0:
            raise NameError_(f"cannot read a syllable from {word!r}")
        vowel = "a"
    if cluster == 0 and vowel == "ṛ":
        readings = ["र"]
    return readings, _vowels(vowel, rules), rules


def _pada_entry(consonant: str | None, vowel: str) -> dict:
    folded = _FOLD.get(consonant, consonant)
    nakshatra, pada = _TABLE[(folded, vowel)]
    longitude = nakshatra * NAKSHATRA_SPAN + pada * PADA_SPAN + PADA_SPAN / 2  # midpoint of the pada
    return {
        "syllable": _syllable(folded, vowel),
        "latin": _latin(folded, vowel),
        "nakshatra": nakshatra_info(nakshatra),
        "pada": pada + 1,
        "moon_sign": sign_info(int(longitude // 30)),
        "longitude": round(longitude, 6),
    }


def syllable_entry(syllable: str) -> dict:
    """The pada for an explicitly chosen syllable (Devanagari, e.g. "टी"; the chakra's or Abhijit's)."""
    text = unicodedata.normalize("NFC", syllable or "").strip()
    if not text or not ("ऀ" <= text[0] <= "ॿ"):
        raise NameError_("syllable must be a Devanagari syllable such as 'टी'")
    consonants, vowels, _ = _parse_devanagari(text)
    if len(consonants) > 1 or len(vowels) > 1:
        raise NameError_(f"{syllable!r} is itself ambiguous; choose one of the chakra's syllables")
    return _pada_entry(consonants[0], vowels[0])


def from_name(name: str, syllable: str | None = None) -> dict:
    """Nakshatra pada for a name in Latin transliteration or Devanagari.

    `confidence`: "exact" (the sound is in the chakra), "convention" (a standard substitution was applied:
    श->स, ब->व, conjunct, Abhijit syllables) or "ambiguous" (several readings; `candidates` lists them, the
    first is used). `syllable` = the user's explicit choice; it overrides the reading of the name.
    """
    token = _first_token(name)
    devanagari = "ऀ" <= token[0] <= "ॿ"
    if not devanagari and not (token[0].isalpha() and unicodedata.name(token[0], "").startswith("LATIN")):
        raise NameError_(f"cannot read a syllable from {name!r}: write the name in Latin letters or in Devanagari")
    consonants, vowels, rules = _parse_devanagari(token) if devanagari else _parse_latin(token)

    candidates, seen = [], set()
    for consonant in consonants:
        for vowel in vowels:
            entry = _pada_entry(consonant, vowel)
            if entry["syllable"] not in seen:
                seen.add(entry["syllable"])
                candidates.append(entry)
    first_consonant = consonants[0]
    if first_consonant in _FOLD:
        rules.append(f"{first_consonant} is not in the chakra: the {_FOLD[first_consonant]} series is used")
    if (_FOLD.get(first_consonant, first_consonant), vowels[0]) in _ABHIJIT:
        rules.append("an Abhijit syllable, placed in the pada of the 27-nakshatra scheme that it overlaps")

    if syllable:
        chosen = syllable_entry(syllable)
        confidence = "chosen"
    else:
        chosen = candidates[0]
        confidence = "ambiguous" if len(candidates) > 1 else "convention" if rules else "exact"
    return {
        "name": name.strip(),
        "read_as": token,
        "script": "devanagari" if devanagari else "latin",
        **chosen,
        "confidence": confidence,
        "rules": rules,
        "candidates": candidates if len(candidates) > 1 else [],
    }
