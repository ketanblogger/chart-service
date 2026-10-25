"""Every Indian place with a thousand people or more, for the birth-place field.

WHY THIS EXISTS BESIDE cities.py. The hand-kept list in that module has 137 entries. It is the right
size for the panchang and festival dropdowns, which ask "which city do you want this FOR" and are
better for being short. It is the wrong list for a required birth-place field: Bhiwandi has 874,000
people and Dewas 290,000, and neither was in it, so for anybody born there the form simply ended.

7,206 places, from GeoNames cities1000 (CC BY 4.0 - see docs/CREDITS.md). Built by
scripts/build_places.py and shipped with the site: NO EXTERNAL CALL IS MADE FOR A PLACE, at request
time or ever. A birth chart has to be computable on a phone with a bad connection, and a reader's
birth place is not something to hand to somebody else's geocoder.

VILLAGES ARE NOT IN IT, and the form says so plainly rather than pretending. A place a few tens of
kilometres away changes a chart by a minute or two of arc - well below anything a reading reports -
so the honest instruction is "pick the nearest town", said in those words with the reason attached.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name("places_in.json")
TIMEZONE = "Asia/Kolkata"


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def places() -> list[dict]:
    """[{"name", "state", "lat", "lon", "tz", "deva"}], biggest place first."""
    data = _raw()
    states = data["states"]
    return [{"name": row[0], "state": states[row[1]], "lat": row[2], "lon": row[3],
             "tz": TIMEZONE, "deva": row[4] if len(row) > 4 else ""}
            for row in data["places"]]


def payload() -> dict:
    """Exactly what ships to the browser: the compact form, unexpanded.

    248 KB as it stands and 104 KB over the wire. Expanded into one object per place it is 656 KB,
    and the key names were three quarters of those bytes.
    """
    return _raw()


# ---- matching ---------------------------------------------------------------------------------------

#: Devanagari to Latin, letter by letter. NOT a transliteration scheme anybody would publish - it is a
#: SEARCH KEY, and it only has to put "पुणे" and "Pune" in the same place.
#:
#: Only 797 of the 7,206 places carry a Hindi or Marathi name in GeoNames, so a reader typing their own
#: town in their own script matches by this path far more often than by a stored name. That is why it
#: exists at all.
_DEVA = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "ai",
    "ओ": "o", "औ": "au", "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e",
    "ै": "ai", "ो": "o", "ौ": "au",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
    "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
    "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
    "ल": "l", "ळ": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "ः": "h", "ँ": "n", "्": "", "़": "",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4", "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

#: The anusvara takes the sound of what follows it: मुंबई is Mumbai, not Munbai. Before a labial it is
#: an m, otherwise an n - which is the whole of the rule for place names.
_LABIALS = "पफबभम"


#: The vowel LETTERS, as opposed to the matras that hang off a consonant.
_VOWELS = "अआइईउऊऋएऐओऔ"
_CONSONANTS = "कखगघङचछजझञटठडढणतथदधनपफबभमयरलळवशषसह"


def transliterate(text: str) -> str:
    """Devanagari to a Latin search key. Latin text passes through unchanged.

    THE INHERENT VOWEL IS THE WHOLE DIFFICULTY. Every Devanagari consonant carries an unwritten "a",
    and Hindi then deletes most of them: नागपूर is Nagpur, not Nagapura. Writing them all in gives
    nonsense, and leaving them all out turns मुंबई into "mumbi" - which is how this first shipped and
    why Mumbai came second to Navi Mumbai in its own search.

    The rule that covers place names: sound the inherent "a" ONLY before a standalone vowel letter,
    where it is always pronounced, and leave it out everywhere else, where it usually is not. That is
    not Hindi phonology; it is the approximation that puts the most place names in the right bucket,
    and `key` below is tolerant enough to absorb the rest.
    """
    out = []
    for position, char in enumerate(text):
        following = text[position + 1] if position + 1 < len(text) else ""
        if char == "ं":
            out.append("m" if following in _LABIALS else "n")
            continue
        out.append(_DEVA.get(char, char))
        if char in _CONSONANTS and following in _VOWELS:
            out.append("a")
    return "".join(out)


def key(text: str) -> str:
    """The form two spellings of one place have in common.

    WHAT IT FLATTENS, and why each one earns its place:
      - case, accents, spaces, hyphens and apostrophes       (Pimpri-Chinchwad / pimpri chinchwad)
      - Devanagari, through `transliterate`                   (पुणे -> pune)
      - m and n, which the anusvara rule cannot always settle (Mumbai / Munbai)
      - a trailing 'a', which Hindi drops and English keeps   (Satara / Satar)

    IT DOES NOT COLLAPSE DOUBLED LETTERS, though an earlier version did, on the theory that it would
    absorb Alleppey/Alepey. Measured, it did the opposite: matching got WORSE (99.2% to 99.6% of the
    Devanagari names finding their own place) and "zzzz" collapsed to "z", which then matched every
    city with a z in it. A tolerance nobody measured, costing accuracy and precision at once.
    It is deliberately lossy. Two different places can share a key, and that is fine: this decides
    what to OFFER somebody, never what to compute a chart from.
    """
    text = transliterate(text).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = "".join(char for char in text if char.isalnum())
    # m/n: the anusvara rule cannot always settle which one a speller chose.
    # v/w: Devanagari has one letter for both, English spellings of Indian places use either, and
    #      देवास is written Dewas.
    settled = text.replace("m", "n").replace("w", "v")
    return settled[:-1] if len(settled) > 3 and settled.endswith("a") else settled


@lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for place in places():
        for spelling in (place["name"], place["deva"]):
            if spelling:
                found.setdefault(key(spelling), place)
        # "Belagavi (Belgaum)" is findable by either half, the way the curated list already allowed.
        for part in place["name"].replace(")", "").split("("):
            if part.strip():
                found.setdefault(key(part), place)
    return found


def find(name: str) -> dict | None:
    """The place a submitted name means, or None. Exact-ish: this resolves, it does not suggest."""
    return _index().get(key(name or ""))


def search(query: str, limit: int = 50) -> list[dict]:
    """Places to offer for what somebody has typed so far, best first.

    Mirrors filterCities() in render.js, which is what actually runs for a reader - this exists so the
    behaviour can be tested in Python and so a server-side caller has the same answer. The order is
    the one the data ships in (largest place first), so between two Nashiks the bigger one leads.
    """
    wanted = key(query)
    if not wanted:
        return places()[:limit]
    starts, contains = [], []
    for place, keys in _keyed():
        for candidate in keys:
            if candidate.startswith(wanted):
                starts.append(place)
                break
            if wanted in candidate:
                contains.append(place)
                break
    return (starts + contains)[:limit]


@lru_cache(maxsize=1)
def _keyed() -> tuple[tuple[dict, tuple[str, ...]], ...]:
    """Every place with its search keys, computed ONCE.

    `key` is cheap and 7,206 places times two spellings is not: recomputing them per keystroke made
    the suite's own measurement of this function take longer than the rest of the suite put together.
    render.js caches the same thing on each city object for the same reason - there it is a phone
    doing the work on every keypress.
    """
    out = []
    for place in places():
        keys = tuple(key(spelling) for spelling in (place["name"], place["deva"]) if spelling)
        out.append((place, keys))
    return tuple(out)
