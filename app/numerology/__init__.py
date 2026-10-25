"""Numerology: the calculators, the number meanings, and the pages they sit on.

SEPARATE FROM app/engine ON PURPOSE. Everything in app/engine is astronomy - positions computed from
the Swiss Ephemeris, true whoever is asking. Numerology is arithmetic over a name and a date in a
tradition that has several schools which disagree. Keeping it in its own package means nobody can
mistake one for the other, and the page can say which school it is using.

CHALDEAN ONLY, which is the proprietor's decision. Pythagorean assigns 1-9 across the alphabet in
order and gives different answers; mixing the two silently is how a numerology site becomes one
nobody can check.
"""
