"""The arithmetic: mulank, bhagyank, the Chaldean name number and the Lo Shu grid.

NO MEANINGS HERE, ONLY NUMBERS. What a 7 is like belongs in the copy, where it can be written once
and reviewed; this module answers what the number IS. The split is the same one app/engine keeps
between a position and a reading.

THE SCHOOL IS NAMED AND SINGLE. Chaldean, which maps letters to 1-8 and never to 9 - the 9 was held
sacred and left out of the letter table. Pythagorean runs 1-9 straight across the alphabet and gives
different answers for the same name. A site that silently mixed them would be one nobody could check
against anything, so the page says which it uses and this module implements only that one.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

#: THE CHALDEAN LETTER VALUES. 1-8 only: there is no letter worth 9.
#: Grouped the way the tradition states them, so the table can be read against any source.
CHALDEAN = {
    1: "AIJQY",
    2: "BKR",
    3: "CGLS",
    4: "DMT",
    5: "EHNX",
    6: "UVW",
    7: "OZ",
    8: "FP",
}

_LETTER_VALUE = {letter: value for value, letters in CHALDEAN.items() for letter in letters}

#: Master numbers are NOT reduced in most schools. This one does reduce them for the mulank and
#: bhagyank, because every Indian source the proprietor works from reads 11 as 2 and 22 as 4 for
#: those two, and a site that printed "your mulank is 11" would not match any of them. The compound
#: total is kept alongside, so nothing is thrown away and a reader who wants it can see it.
MASTER_NUMBERS = (11, 22, 33)

#: The Lo Shu square, read as rows. This is the arrangement every Indian source uses.
LO_SHU_ROWS = ((4, 9, 2), (3, 5, 7), (8, 1, 6))

#: WHICH DIGITS GO INTO THE GRID. The common Indian convention: every non-zero digit of the date of
#: birth written as DD-MM-YYYY, PLUS the mulank and the bhagyank. Schools differ - some place only
#: the date's own digits - so the page states this in words and this constant is the one place to
#: change it.
LO_SHU_INCLUDES_MULANK_AND_BHAGYANK = True

#: The planes the grid is read in. Rows, columns and the two diagonals, each with its own name.
PLANES = {
    "mental": (4, 9, 2),
    "emotional": (3, 5, 7),
    "practical": (8, 1, 6),
    "thought": (4, 3, 8),
    "will": (9, 5, 1),
    "action": (2, 7, 6),
    "golden": (4, 5, 6),
    "silver": (2, 5, 8),
}


def reduce_to_digit(total: int) -> int:
    """Add the digits until one is left. 29 -> 11 -> 2."""
    while total > 9:
        total = sum(int(digit) for digit in str(total))
    return total


def _letters(name: str) -> str:
    """The name as A-Z, with accents folded and everything else dropped.

    A NAME IS NOT ALWAYS TYPED IN LATIN LETTERS. Devanagari has no Chaldean value - the table is for
    the Latin alphabet - so a name in Devanagari yields nothing rather than a wrong number, and the
    caller is expected to say so rather than print a 0.
    """
    folded = unicodedata.normalize("NFKD", name or "")
    return re.sub(r"[^A-Z]", "", folded.upper())


def name_number(name: str) -> dict:
    """The Chaldean value of a name: the compound total and the single digit it reduces to."""
    letters = _letters(name)
    per_letter = [{"letter": letter, "value": _LETTER_VALUE[letter]} for letter in letters]
    total = sum(item["value"] for item in per_letter)
    return {
        "usable": bool(letters),
        "letters": per_letter,
        "total": total,
        "number": reduce_to_digit(total) if total else 0,
    }


def steps(total: int) -> list[str]:
    """The reduction, written out: 29 -> ["2+9=11", "1+1=2"]. Empty when nothing needed reducing.

    SO THE PAGE CAN SHOW ITS WORKING. The name card has always shown how its number was reached -
    the letters and their values - while the mulank and bhagyank cards showed a bare digit, which
    is the one part of this a reader cannot check and the part they most want to.
    """
    out: list[str] = []
    while total > 9:
        digits = [int(d) for d in str(total)]
        total = sum(digits)
        out.append("+".join(str(d) for d in digits) + f"={total}")
    return out


def mulank(born: dt.date) -> int:
    """The day of the month, reduced. Born on the 29th: 2+9 = 11 -> 2."""
    return reduce_to_digit(born.day)


def bhagyank(born: dt.date) -> int:
    """Every digit of the whole date, reduced."""
    digits = f"{born.day:02d}{born.month:02d}{born.year:04d}"
    return reduce_to_digit(sum(int(d) for d in digits))


def lo_shu(born: dt.date) -> dict:
    """The grid, with what is repeated, what is missing, and which planes are complete."""
    digits = [int(d) for d in f"{born.day:02d}{born.month:02d}{born.year:04d}" if d != "0"]
    if LO_SHU_INCLUDES_MULANK_AND_BHAGYANK:
        digits += [mulank(born), bhagyank(born)]
    counts = {n: digits.count(n) for n in range(1, 10)}
    return {
        "digits": digits,
        "counts": counts,
        "rows": [[{"number": n, "count": counts[n]} for n in row] for row in LO_SHU_ROWS],
        "repeated": sorted(n for n, c in counts.items() if c > 1),
        "missing": sorted(n for n, c in counts.items() if c == 0),
        "planes": {name: all(counts[n] > 0 for n in cells) for name, cells in PLANES.items()},
    }


def profile(name: str, born: dt.date) -> dict:
    """Everything the calculator page shows, from one name and one date."""
    digits = f"{born.day:02d}{born.month:02d}{born.year:04d}"
    return {
        "name": name,
        "born": born.isoformat(),
        "mulank": mulank(born),
        "bhagyank": bhagyank(born),
        # THE WORKING, so a reader can check the one part of this they cannot otherwise see - the
        # name card has always shown its letters and their values while these two showed a bare
        # digit. One complete chain each, ready to join with an arrow: the mulank starts from the
        # day of the month, the bhagyank from every digit of the whole date, and the FIRST step of
        # the bhagyank is that sum itself, or the chain would begin at a number nothing explains.
        "mulank_from": born.day,
        "mulank_working": steps(born.day),
        "bhagyank_from": "+".join(digits),
        "bhagyank_working": ([f"{'+'.join(digits)}={sum(int(d) for d in digits)}"]
                             + steps(sum(int(d) for d in digits))),
        "name_number": name_number(name),
        "lo_shu": lo_shu(born),
    }


# ---- how one number sits with another ------------------------------------------------------------------

#: THE PLANET BEHIND EACH NUMBER, which is where the relationships come from. Standard across Indian
#: numerology, and the reason this is not an arbitrary table.
RULERS = {1: "Sun", 2: "Moon", 3: "Jupiter", 4: "Rahu", 5: "Mercury",
          6: "Venus", 7: "Ketu", 8: "Saturn", 9: "Mars"}

#: WHICH NUMBERS THE TRADITION READS AS FRIENDLY. Taken from the planetary friendships, which is why
#: 1 and 9 (Sun and Mars) are friends and 1 and 8 (Sun and Saturn) are not.
#:
#: SYMMETRIC, DELIBERATELY, AND THE CLASSICAL FRIENDSHIPS ARE NOT. Mars counts the Moon a friend
#: while the Moon does not count Mars; the same holds for Jupiter and the Moon. Encoding that
#: faithfully gave two pairs with two answers - fit(9, 2) was "good" and fit(2, 9) "neutral" - and a
#: reader who looks up 2 and then 9 is told two different things about the same relationship. The
#: mulank-2 page said 9 was neutral while the mulank-9 page and the number checker called 2-9 a good
#: match, which is what the proprietor found on the live site.
#:
#: So the table is the UNION of the two directions: if either number counts the other a friend, the
#: pair is good for both. Union rather than intersection because this module never reports worse
#: than neutral by design, and taking the kinder reading of a genuinely two-sided tradition is
#: consistent with that. `test_the_fit_relation_is_symmetric` holds it.
FRIENDS = {
    1: (1, 2, 3, 9),
    2: (1, 2, 3, 4, 7, 9),   # 3 and 9 added: Jupiter and Mars both count the Moon a friend
    3: (1, 2, 3, 9),
    4: (2, 4, 6, 7, 8),
    5: (5, 6, 8),
    6: (4, 5, 6, 8),
    7: (2, 4, 7),
    8: (4, 5, 6, 8),
    9: (1, 2, 3, 9),
}


def fit_groups(number: int) -> dict:
    """THE SINGLE SOURCE every page and the checker read: {"strong": [...], "good": [...],
    "neutral": [...]} for one mulank, each list sorted.

    The nine mulank pages carry their compatibility as hand-written prose in three languages - 27
    paragraphs naming the numbers - and prose cannot be kept in step with a table by hand. It was
    not: the proprietor found mulank 2 calling 9 neutral while mulank 9 called 2 a good match.
    tests/test_numerology_compatibility.py reads the digits back out of every one of those 27
    paragraphs and holds them to this function.
    """
    return {level: sorted(other for other in range(1, 10) if fit(number, other) == level)
            for level in FIT_LEVELS}

#: THREE LEVELS, ALL OF THEM USABLE. There is no "bad" level and there will not be one: a person
#: cannot change their date of birth, and telling them their own number is unlucky is a charge they
#: can do nothing about. The tradition's "enemy" pairs are reported as NEUTRAL - which is honest
#: about there being no special affinity, and says nothing about anybody's worth or luck.
FIT_LEVELS = ("strong", "good", "neutral")


def fit(number: int, against: int) -> str:
    """How `number` sits with `against`: "strong", "good" or "neutral". Never worse than neutral."""
    if number == against:
        return "strong"
    if against in FRIENDS.get(number, ()):
        return "good"
    return "neutral"


def check_number(value: str, *, mulank: int | None = None, bhagyank: int | None = None) -> dict:
    """A mobile, vehicle, house or business number: its total, its single digit, and how it sits.

    THE DIGITS ARE ALL THAT IS READ. A phone number's letters, spaces, plus sign and country code are
    not part of it in any school - and a reader pasting "+91 98765 43210" should get the same answer
    as one typing the ten digits, rather than a different number because of the punctuation.
    """
    digits = [int(d) for d in re.sub(r"\D", "", value or "")]
    if not digits:
        return {"usable": False, "digits": "", "total": 0, "number": 0, "fits": {}}
    total = sum(digits)
    number = reduce_to_digit(total)
    fits = {}
    if mulank:
        fits["mulank"] = {"against": mulank, "level": fit(number, mulank)}
    if bhagyank:
        fits["bhagyank"] = {"against": bhagyank, "level": fit(number, bhagyank)}
    return {
        "usable": True,
        "digits": "".join(str(d) for d in digits),
        "total": total,
        "number": number,
        "ruler": RULERS[number],
        "fits": fits,
    }


def for_chat(born: dt.date, name: str = "") -> dict:
    """The numbers a numerology consultation needs, in the shape the chat's context block takes.

    THE NAME ITSELF NEVER GOES IN. The chat has always treated a reader's name as display-only and
    never sent it to the model (app/ai/chat_routes.py says so where the name is read), and a name
    number does not need the name - it needs the number the name adds up to. So the derived integer
    travels and the name stays here.

    NOTHING IS CARRIED THROUGH SIGN-IN. These are recomputed from the same birth date the chart is
    built from, which means the chat's numbers cannot drift from the calculator's: there is one
    implementation and it is this one.
    """
    grid = lo_shu(born)
    numbers = {
        "system": "Chaldean",
        "mulank": mulank(born),
        "bhagyank": bhagyank(born),
        "lo_shu_repeated": grid["repeated"],
        "lo_shu_missing": grid["missing"],
        "lo_shu_planes_complete": sorted(n for n, done in grid["planes"].items() if done),
    }
    if name:
        found = name_number(name)
        if found["usable"]:
            numbers["name_number"] = found["number"]
            numbers["name_number_total"] = found["total"]
    return numbers


def for_report(born: dt.date, name: str = "") -> dict:
    """for_chat(), plus the spelling alternatives a written report is sold on.

    A SEPARATE FUNCTION ON PURPOSE, and for two reasons.

    First, `for_chat` must not change. The digest stored on a paid order - and therefore the report
    id the customer bought - is computed from exactly what `for_chat` returns, so adding a field to
    it would change every future order's id and stop matching the ones already sold.

    Second, the chat deliberately never sends a reader's NAME to the model, and the spellings are
    the name. A written report is a different case: it is about that person, their name is printed
    on its cover, and the alternatives are the thing they paid for.
    """
    numbers = dict(for_chat(born, name))
    # THE GRID ITSELF, so the PDF can draw the same 3x3 the site draws rather than describing it in
    # words. Derived from the date alone, like the spellings - and kept out of the report id for
    # the same reason (app/ai/report.py, _DERIVED_FACTS).
    numbers["lo_shu_grid"] = lo_shu(born)["rows"]
    if name:
        numbers["name_spellings"] = spelling_variants(name)
    return numbers


# ---- spelling alternatives, computed rather than written -------------------------------------------
#
# WHY THIS IS CODE AND NOT THE MODEL'S JOB. The first real numerology report PROMISED spelling
# alternatives and then gave none: it said only that "adding or removing a letter can make 1, 6 or
# 5", which is a description of the exercise rather than the thing the reader paid for. A model
# asked to do this will also, sooner or later, produce a spelling whose total it has mis-added - and
# the one number on the page a reader can check themselves is exactly the one that must never be
# wrong. So the spellings and their totals are computed here, and the writer is handed the finished
# list to talk about.
#
# NATURAL, NOT INVENTED. Each candidate is ONE substitution from a table of spelling conventions
# that Indian names in Latin script actually vary by - VIJAY / VIJAI, SURESH / SURESHH,
# VIJAY / VIJAI. One edit at a time, because two edits stop looking like the same name.
#
# IT NEVER RECOMMENDS. The reader's own spelling is always in the list and marked as theirs. A
# number is not better than another number, and app/ai/products.py says the same thing to the writer.
_SPELLING_RULES: tuple[tuple[str, str], ...] = (
    # a long vowel written twice - the commonest Indian-English variation of all
    ("A", "AA"), ("I", "EE"), ("U", "OO"), ("E", "EE"), ("O", "OO"),
    # the aspirated consonants, written with or without the H
    ("K", "KH"), ("T", "TH"), ("D", "DH"), ("G", "GH"), ("B", "BH"), ("P", "PH"), ("J", "JH"),
    # the pairs that stand for one sound
    ("V", "W"), ("S", "SH"), ("Y", "I"), ("I", "Y"), ("C", "K"), ("Z", "J"),
)

#: How many alternatives to offer. Few enough to read, enough to show that the number moves.
SPELLING_LIMIT = 4


def _apply_once(letters: str, old: str, new: str) -> list[str]:
    """Every string made by replacing ONE occurrence of `old` with `new`."""
    out, start = [], 0
    while True:
        at = letters.find(old, start)
        if at < 0:
            return out
        out.append(letters[:at] + new + letters[at + len(old):])
        start = at + 1


#: Clusters no Indian name is spelt with. A rule can produce one by accident - S -> SH inside ASHA
#: gives ASHHA, and E -> EE inside EE gives EEE - and an "alternative spelling" nobody would write
#: is worse than none: it makes the whole list look automatic, which it is, but it should not look it.
_IMPLAUSIBLE = re.compile(r"HH|([A-Z])\1\1|^H|[QX]H")


def _plausible(word: str) -> bool:
    return not _IMPLAUSIBLE.search(word)


def spelling_variants(name: str, limit: int = SPELLING_LIMIT) -> dict:
    """Natural alternative spellings of `name`, each with its Chaldean total and number.

    Returns {"usable": bool, "current": {...}, "variants": [...]}, where every entry is
    {"spelling", "total", "number"} and `variants` never contains the reader's own spelling.

    The list is deterministic: the same name always produces the same alternatives in the same
    order. Nothing here is a recommendation, and `usable=False` says plainly that no natural
    respelling of this name lands on a different number - which is a real answer, not a failure.
    """
    original = " ".join((name or "").split())
    current = name_number(original)
    if not current["usable"]:
        return {"usable": False, "current": {"spelling": original, "total": 0, "number": 0},
                "variants": []}

    # Work on the letters while remembering where the spaces were, so "ASHA VERNEKAR" stays two words.
    words = [_letters(word) for word in original.split()]
    seen = {"".join(words)}
    found: list[dict] = []
    for index, word in enumerate(words):
        for old, new in _SPELLING_RULES:
            for candidate in _apply_once(word, old, new):
                spelled = words[:index] + [candidate] + words[index + 1:]
                key = "".join(spelled)
                if key in seen:
                    continue
                seen.add(key)
                if not _plausible(candidate):
                    continue
                value = name_number(" ".join(spelled))
                # Only a spelling that lands on a DIFFERENT number is worth printing: an alternative
                # with the same number tells the reader nothing they did not already have.
                if value["number"] == current["number"]:
                    continue
                found.append({"spelling": " ".join(spelled), "total": value["total"],
                              "number": value["number"]})

    # One per number, cheapest edit first (the rules are in order of how ordinary the variation is),
    # so the reader sees a spread of numbers rather than four ways to reach the same one.
    by_number: dict[int, dict] = {}
    for entry in found:
        by_number.setdefault(entry["number"], entry)
    variants = [by_number[n] for n in sorted(by_number)][:max(0, limit - 1)]
    return {"usable": bool(variants),
            "current": {"spelling": original.upper(), "total": current["total"],
                        "number": current["number"]},
            "variants": variants}
