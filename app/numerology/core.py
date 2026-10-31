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
    return {
        "name": name,
        "born": born.isoformat(),
        "mulank": mulank(born),
        "bhagyank": bhagyank(born),
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
FRIENDS = {
    1: (1, 2, 3, 9),
    2: (1, 2, 4, 7),
    3: (1, 2, 3, 9),
    4: (2, 4, 6, 7, 8),
    5: (5, 6, 8),
    6: (4, 5, 6, 8),
    7: (2, 4, 7),
    8: (4, 5, 6, 8),
    9: (1, 2, 3, 9),
}

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
