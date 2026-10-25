"""Engine-derived truth about the twelve rashis, for checking what the sign-hub essays claim.

Nothing here is typed from an astrology book. Every fact is computed from the tables the CHART is drawn from -
app/engine/constants.py and app/engine/dignity.py - so a claim in the prose is checked against the same source
the site's own calculations use, and the two cannot drift apart while agreeing with each other.

Houses are counted from the rashi, whole-sign, the way an Indian horoscope column is read: the rashi itself is
the 1st, the next sign the 2nd, and so on round to the 12th.
"""

from app.engine import constants
from app.engine.dignity import EXALTATION, OWN_SIGNS

SIGNS = constants._SIGNS            # (english, sanskrit, devanagari, lord), index 0 = Aries
NAKSHATRAS = constants._NAKSHATRAS  # (name, devanagari), index 0 = Ashwini
GRAHAS = tuple(EXALTATION)          # the seven that own signs and have a dignity


def sign_index(name: str) -> int:
    """1-12 from an English, Sanskrit or Devanagari sign name."""
    for i, row in enumerate(SIGNS, start=1):
        if name in row[:3]:
            return i
    raise KeyError(name)


def lord_of(sign: int) -> str:
    return SIGNS[sign - 1][3]


def house_from(rashi: int, other: int) -> int:
    """Which house `other` is, counted from `rashi` as the 1st."""
    return ((other - rashi) % 12) + 1


def sign_at_house(rashi: int, house: int) -> int:
    return ((rashi - 1 + house - 1) % 12) + 1


def lord_of_house(rashi: int, house: int) -> str:
    return lord_of(sign_at_house(rashi, house))


def houses_owned_from(rashi: int, graha: str) -> list[int]:
    """Every house, counted from `rashi`, whose sign `graha` owns. Two for all but the Sun and the Moon."""
    return sorted(house_from(rashi, sign) for sign in OWN_SIGNS[graha])


def exaltation(graha: str) -> tuple[int, float]:
    return EXALTATION[graha]


def debilitation(graha: str) -> tuple[int, float]:
    """The 7th sign from the exaltation, at the same degree - the rule dignity.py itself states."""
    sign, degree = EXALTATION[graha]
    return sign_at_house(sign, 7), degree


def nakshatra_lord(index0: int) -> str:
    """Vimshottari lord of a nakshatra, by its 0-based index - the rule constants.py states."""
    entry = constants.DASHA_SEQUENCE[index0 % 9]
    return entry[0] if isinstance(entry, (tuple, list)) else entry


def nakshatra_index(name: str) -> int:
    for i, row in enumerate(NAKSHATRAS):
        if name in row:
            return i
    raise KeyError(name)


def nakshatra_spans(rashi: int) -> list[tuple[int, list[int]]]:
    """The nakshatras a sign spans, as (0-based nakshatra index, [pada numbers]).

    A sign is 30 degrees and a nakshatra 13 degrees 20 minutes, so a sign covers exactly nine padas and the
    boundaries fall inside nakshatras - which is why these essays talk about "the last two padas of Chitra".
    Computed from the spans rather than listed, so it is right for all twelve without a table to mistype.
    """
    start, end = (rashi - 1) * 30.0, rashi * 30.0
    out: dict[int, list[int]] = {}
    pada = constants.PADA_SPAN
    for p in range(108):                      # 27 nakshatras x 4 padas
        low, high = p * pada, (p + 1) * pada
        if low < end - 1e-9 and high > start + 1e-9:
            out.setdefault(p // 4, []).append(p % 4 + 1)
    return [(index, padas) for index, padas in sorted(out.items())]


def sade_sati_signs(rashi: int) -> list[int]:
    """Saturn in the 12th, the 1st or the 2nd from the Moon sign."""
    return [sign_at_house(rashi, h) for h in (12, 1, 2)]


def dhaiya_signs(rashi: int) -> list[int]:
    """The small panoti: Saturn in the 4th or the 8th from the Moon sign."""
    return [sign_at_house(rashi, h) for h in (4, 8)]
