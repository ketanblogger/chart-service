"""The labelled example kundli chart shown on the chart tools' own pages.

DRAWN BY chart_svg(), the same function that draws a reader's own chart and the one in their PDF. A
second drawing of the same diagram would be a second thing to keep correct, and the first time the real
chart changed, the example teaching people to read it would quietly start teaching the wrong thing.

INLINE, NOT AN IMAGE FILE. An SVG loaded through `<img>` is sandboxed and cannot reach the site's
webfont, so its text is drawn with whatever face the device happens to have - which on a machine with
no system Devanagari font is a grid of boxes. That is how the first version of this rendered. Inline,
the page's own fonts apply, the labels are ordinary selectable HTML in app/web/content/<lang>.py like
every other string here, there is no extra request, and the diagram stays crisp at any zoom.

The birth is invented, like every fixture on this site, and the panel says so in its own heading.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache

from markupsafe import Markup

#: An invented birth: 14 March 1991, 07:20, Pune. Never a real person's, here or anywhere else.
EXAMPLE_BIRTH = dict(birth_date=dt.date(1991, 3, 14), birth_time=dt.time(7, 20),
                     lat=18.5204, lon=73.8567, tz="Asia/Kolkata")


@lru_cache(maxsize=4)
def example_chart(lang: str) -> Markup:
    """The example chart as inline SVG markup for this language's script.

    Cached: it is the same diagram for every visitor, and computing a chart per page view to draw a
    picture that never changes would be a strange way to spend an ephemeris call.
    """
    # IMPORTED HERE, NOT AT MODULE LEVEL. app.web.routes imports this module while app.pdf is still
    # being set up, and a top-level import of either one turns that into a circular import at startup.
    from app.engine.chart import compute_chart
    from app.pdf.chart_svg import chart_svg

    chart = compute_chart(**EXAMPLE_BIRTH)
    return Markup(chart_svg(chart, script="en" if lang == "en" else "deva",
                            label=_aria(lang)))


def _aria(lang: str) -> str:
    """What a screen reader is told the diagram is.

    The LABELS below it are the real explanation and they are read as ordinary text, so this says what
    the picture is and gets out of the way rather than reciting twelve house positions.
    """
    from app.web import pages

    return pages.ui(lang)["example_chart_aria"]
