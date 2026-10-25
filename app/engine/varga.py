"""Navamsa (D9) - the divisional chart the flagship report prints next to the D1.

Rule (standard Parashari, Brihat Parashara Hora Shastra ch. 6 "Shodasavarga"): each 30° sign is cut
into nine navamsas of 3°20'. Where the count starts depends on the sign's nature:

    movable (chara)      Mesha, Karka, Tula, Makara      -> counting starts from the sign itself
    fixed (sthira)       Vrishabha, Simha, Vrishchika, Kumbha -> from the 9th sign from it
    dual (dwisvabhava)   Mithuna, Kanya, Dhanu, Meena    -> from the 5th sign from it

Those three starting points are exactly what makes the division continuous around the zodiac, so the
rule collapses to `(sign_index * 9 + part) mod 12`, counting from Mesha - because 9 * sign_index and
sign_index + offset(nature) are congruent mod 12 for every sign. `navamsa_sign()` implements the
collapsed form; `_navamsa_sign_by_rule()` implements the literal movable/fixed/dual rule and a test
asserts the two agree at 10,800 longitudes (every 2 arc-minutes of the zodiac), so the shortcut is not
taken on trust. Both decompose the longitude into sign and part rather than dividing the whole circle
by 3°20': `30 / 9` is not exact in binary, and dividing straight through put every exact sign boundary
one navamsa too low.

VERIFICATION (independent published charts, checked 2026-09-21):

1. Mahatma Gandhi, 2 Oct 1869, 07:11:53 LMT, Porbandar (21N38, 69E36). Published D9 at
   https://sitharsastrology.com/blog/mahatma-gandhi-birth-chart-analysis gives
   Sun Mithuna, Chandra Meena, Mangal Vrishabha, Budha Makara, Guru Dhanu, Shukra Vrishabha,
   Shani Makara, Rahu Tula, Ketu Mesha. This module reproduces all nine exactly.
   (That source's D9 lagna is Makara against our Vrishchika; Gandhi's minute of birth is disputed and
   the lagna is the only quantity sensitive to it - the grahas, which are not, all agree.)

2. Jawaharlal Nehru, 14 Nov 1889, 23:30 IST, Allahabad. D1 longitudes published by
   AstroSage (https://celebrity.astrosage.com/jawaharlal-nehru-birth-chart.asp, rated "Accurate (A)",
   source Kundli Sangraha) agree with this engine to within arc-seconds; applying the literal
   movable/fixed/dual rule to those published degrees by hand gives Sun Karka, Chandra Dhanu,
   Mangal Meena, Budha Meena, Guru Simha, Shukra Dhanu, Shani Karka - which is what this module
   returns. (Nehru's lagna sits on the Karka/Simha cusp and differs between sources; same caveat.)

3. A. P. J. Abdul Kalam, 15 Oct 1931, 01:15 IST, Rameswaram - every position worked longhand in
   tests/test_varga.py, so the whole division can be checked by eye. The published analysis of that
   chart independently confirms the placements the D9 is derived from.

Vargottama: a graha (or the lagna) occupying the same sign in D1 and in D9. It can only happen in the
1st navamsa of a movable sign, the 5th of a fixed sign and the 9th of a dual sign; that identity is
also asserted in the tests.
"""

from .constants import GRAHA_KEYS, graha_name, sign_info
from .core import house_from

NAVAMSA_SPAN = 30 / 9  # 3°20'

# 0 = movable (chara), 1 = fixed (sthira), 2 = dual (dwisvabhava), by 0-based sign index.
_NATURE = ("movable", "fixed", "dual")
# Where the nine navamsas of a sign start counting from, as an offset in signs from the sign itself.
_START_OFFSET = {"movable": 0, "fixed": 8, "dual": 4}

DIVISION = "D9 (Navamsa), Parashari: 3°20' parts, movable from the sign, fixed from the 9th, dual from the 5th"


def sign_nature(sign_index0: int) -> str:
    """"movable" | "fixed" | "dual" for a 0-based sign index."""
    return _NATURE[sign_index0 % 3]


def navamsa_part(longitude: float) -> int:
    """Which of the nine 3°20' parts of its sign a longitude falls in, 0-8."""
    longitude %= 360
    return min(int((longitude - int(longitude // 30) * 30) // NAVAMSA_SPAN), 8)


def navamsa_sign(longitude: float) -> int:
    """0-based navamsa sign index for a sidereal longitude."""
    longitude %= 360
    return (int(longitude // 30) * 9 + navamsa_part(longitude)) % 12


def _navamsa_sign_by_rule(longitude: float) -> int:
    """The literal movable/fixed/dual rule. Kept as the reference implementation for the tests."""
    longitude %= 360
    sign0 = int(longitude // 30)
    part = navamsa_part(longitude)  # 0-8, which of the nine 3°20' parts
    return (sign0 + _START_OFFSET[sign_nature(sign0)] + part) % 12


def navamsa_position(longitude: float, navamsa_lagna_sign: int | None = None) -> dict:
    """Navamsa placement of one longitude. `navamsa_lagna_sign` (1-12) adds the house from the D9 lagna."""
    d1_sign0 = int(longitude % 360 // 30)
    d9_sign0 = navamsa_sign(longitude)
    entry = {
        "sign": sign_info(d9_sign0),
        "navamsa": navamsa_part(longitude) + 1,  # 1-9 within the D1 sign
        "d1_sign_nature": sign_nature(d1_sign0),
        "vargottama": d9_sign0 == d1_sign0,
    }
    if navamsa_lagna_sign is not None:
        entry["house"] = house_from(navamsa_lagna_sign, d9_sign0 + 1)
    return entry


def navamsa_chart(chart: dict) -> dict:
    """The whole D9 for a computed chart: D9 lagna, every graha's D9 sign and house from the D9 lagna,
    a 12-house table (for the renderer) and the vargottama list.

    SHAPE: deliberately the same as the D1 chart - `lagna`, `grahas` keyed by graha with
    `sign` / `house` / `retrograde`, and `houses` as a 12-entry list of {house, sign, grahas} - so the
    chart renderer that draws the rashi chart draws this one unchanged. There is no `degree`: a
    "degree within the navamsa sign" is not a quantity the classical texts use, and inventing one
    would only invite it onto the page.

    Houses in this block are ALWAYS counted from the navamsa lagna - never from the D1 lagna. The key
    is `house` inside `navamsa`, and `house_from_navamsa_lagna` is given as an explicit alias so a
    reader cannot mistake it for a rashi-chart house.
    """
    lagna = navamsa_position(chart["lagna"]["longitude"])
    lagna_sign = lagna["sign"]["index"]
    lagna["house"] = 1
    lagna["house_from_navamsa_lagna"] = 1

    grahas = {}
    for key in GRAHA_KEYS:
        position = chart["grahas"][key]
        entry = navamsa_position(position["longitude"], lagna_sign)
        entry["graha"] = graha_name(key)
        entry["house_from_navamsa_lagna"] = entry["house"]
        entry["d1_sign"] = position["sign"]
        # Retrogression is a physical fact about the graha, not a property of the division, so it is
        # copied straight from D1. With `graha`, `sign`, `house` and `retrograde` present, a D9 row
        # has the same field names as a D1 row and ONE renderer can draw both charts.
        entry["retrograde"] = position["retrograde"]
        grahas[key] = entry

    return {
        "division": DIVISION,
        "lagna": lagna,
        "grahas": grahas,
        "houses": [
            {
                "house": house,
                "sign": sign_info((lagna_sign - 1 + house - 1) % 12),
                "grahas": [key for key, g in grahas.items() if g["house"] == house],
            }
            for house in range(1, 13)
        ],
        "vargottama": [key for key, g in grahas.items() if g["vargottama"]],
        "lagna_vargottama": lagna["vargottama"],
    }


# `engine.navamsa(chart)` reads better at a call site than `navamsa_chart`; both are the same function.
navamsa = navamsa_chart
