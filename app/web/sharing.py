"""WhatsApp share links, and the rule that the shared text never carries a birth.

WHY WHATSAPP AND NOTHING ELSE. This site's readers forward things to family, and they do it there.
A row of five networks is five icons nobody taps; one is a decision.

WHAT IS SHARED IS A LINK AND A SENTENCE, and the sentence is about the PAGE, never about the person.
A rashifal page is the same page for everybody born under that sign, so its link is safe to send. A
kundli result is NOT a page - it is one person's chart, computed from their birth date, time and
place - so what gets shared from there is the TOOL, not the result. Nothing in a share URL may carry a
date, a time, a place, a name or any part of a chart: a WhatsApp message is forwarded onward by people
who never saw the original, and a birth detail in a query string ends up in strangers' chat history.

THE TAG IS HOW THE FUNNEL SEES IT. The link carries `utm_source=whatsapp` and a `utm_content` naming
which page it was shared FROM, so arrivals can be counted against the pages that actually get
forwarded. Both are fixed words from this module, never anything a caller supplies.
"""
from __future__ import annotations

from urllib.parse import quote

from app.web import i18n

#: The one network. Adding a second is a decision about the page, not a parameter.
ENDPOINT = "https://wa.me/?text="

#: Where a share may come from. A fixed set, because it becomes a `utm_content` value that the funnel
#: groups by - and a free-text label would make that grouping unreadable within a week.
SOURCES = ("rashifal", "kundli", "blog")

COPY = {
    "en": {
        "blog": "{title} - RashiKundli",
        "rashifal": "{title} - today's reading, free on RashiKundli",
        "kundli": "Free janam kundli, calculated with the Swiss Ephemeris - no sign-up",
        "button": "Share on WhatsApp",
    },
    "hi": {
        "blog": "{title} - RashiKundli",
        "rashifal": "{title} - आज का राशिफल, RashiKundli पर मुफ़्त",
        "kundli": "मुफ़्त जन्मकुंडली, स्विस एफेमेरिस से गणना - कोई साइन-अप नहीं",
        "button": "WhatsApp पर भेजें",
    },
    "mr": {
        "blog": "{title} - RashiKundli",
        "rashifal": "{title} - आजचे राशीभविष्य, RashiKundli वर मोफत",
        "kundli": "मोफत जन्मकुंडली, स्विस एफेमेरिसने गणना - साइन-अप नाही",
        "button": "WhatsApp वर पाठवा",
    },
}


def tagged_url(path: str, source: str) -> str:
    """The absolute URL to share, tagged so arrivals through it can be counted."""
    joiner = "&" if "?" in path else "?"
    return i18n.absolute(f"{path}{joiner}utm_source=whatsapp&utm_medium=social&utm_content={source}")


def share(path: str, source: str, lang: str = "en", title: str = "") -> dict | None:
    """What the template needs to offer a share, or None if the source is unknown.

    NO wa.me URL IS RETURNED, and that is deliberate. Four separate guards in this repository forbid a
    third-party URL anywhere in a page's markup - and they are right: a page should fetch, render and
    reference nothing it does not own. Needing to except the same link from all four was the design
    telling me it was wrong.

    So the page carries the TEXT and the tagged URL as data, and static/js/analytics.js assembles
    `wa.me/?text=...` when the button is actually pressed. Nothing third-party appears in the HTML, the
    guards stay exactly as they were, and the share opens on the tap as it would have anyway.

    `title` is the PAGE's own title - "Tula rashifal", "Libra horoscope" - never a person's name, and
    it is absent entirely from the kundli source, where no title exists that is not somebody's chart.
    """
    if source not in SOURCES:
        return None
    words = COPY.get(lang) or COPY["en"]
    text = words[source].format(title=title) if "{title}" in words[source] else words[source]
    return {"text": text, "url": tagged_url(path, source), "label": words["button"]}


def whatsapp_url(text: str, url: str) -> str:
    """The wa.me link itself. Used by the tests and by nothing that renders a page."""
    return ENDPOINT + quote(f"{text}\n{url}")
