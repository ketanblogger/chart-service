"""One clean post, shared by the three blog test files.

It has to be a REAL post rather than three hundred repetitions of a word: every check in
app/blog/safety.py runs over it, so a body built from filler would pass the word count and then prove
nothing about the screens. This one is written to pass all of them, which is also the only honest way to
show that a guard fails for its own reason - each test below breaks exactly one thing in this post and
asserts the one problem that follows.

No real person, no real birth data. The prose is about the ayanamsa, which belongs to nobody.
"""

TITLE = "What the ayanamsa actually is"
SUMMARY = ("The one number that separates a Vedic chart from a Western one, where it comes from, and why "
           "two published charts for the same birth can disagree by a whole sign.")

BODY = """
Two astrologers can work from the same birth, run the same arithmetic, and hand back charts that put the
Sun in different signs. Neither of them has made a mistake. They have used different starting points for
the zodiac, and the gap between those starting points has a name.

## Where the number comes from

The sidereal zodiac begins at a fixed point among the stars. The tropical zodiac begins at the equinox,
the moment the Sun crosses the celestial equator heading north. The equinox is not fixed: the axis of the
Earth turns slowly, completing one circuit in roughly twenty-six thousand years, so the equinox creeps
backwards through the constellations at about one degree every seventy-two years. The angle between the
two starting points is the ayanamsa, and it grows a little every year.

Everything on this site is computed with the Lahiri value, which is what Indian official calendars use
and what most published panchangs assume. That is a convention rather than a discovery, and it is worth
knowing that other traditions use a slightly different one.

## Why it matters for a reading

A chart is a set of positions measured against a starting point. Move the starting point and every
position moves with it, so a Sun near the edge of a sign can land in the sign before it. Readers who
have followed a Western sun sign for years often find that a Vedic chart gives them the one behind it,
and the arithmetic above is the whole of the reason.

## What it does not change

The houses keep their order. The relationships between the grahas keep their angles, because those are
measured between positions rather than from the start of the zodiac. So the aspects a reading is built
on do not move at all, which is why the two systems can disagree about a sign name and still agree about
a great deal else.

## Reading this on your own chart

The gap is a little over twenty-four degrees at the moment. If a chart from elsewhere disagrees with one
from here by exactly one sign, that number is almost certainly the whole explanation, and the thing to
check first is which value the other chart was computed with.
""".strip()

TOOL = "sidereal"
CATEGORIES = ["basics", "kundli"]
SLUG = "what-the-ayanamsa-actually-is"


def post(**overrides) -> dict:
    """The submission dict `app/blog/safety.check` and `app/blog/store.save` take."""
    body = {"slug": SLUG, "title": TITLE, "summary": SUMMARY, "body_md": BODY, "tool": TOOL,
            "categories": list(CATEGORIES), "hero_image": None, "author": ""}
    body.update(overrides)
    return body


def api_body(**overrides) -> dict:
    """The same post in the shape POST /api/blog/posts takes."""
    body = {"slug": SLUG, "title": TITLE, "summary": SUMMARY, "body_markdown": BODY, "tool": TOOL,
            "categories": list(CATEGORIES)}
    body.update(overrides)
    return body


#: The smallest real PNG: an 8-bit 1x1 opaque pixel. Bytes, not a path, so no test reads a file.
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
    "9c6360000002000154a24f7f0000000049454e44ae426082")
