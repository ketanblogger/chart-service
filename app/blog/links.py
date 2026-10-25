"""Internal links added to a post at RENDER time: a term in the prose becomes a link to the tool.

WHY RENDER TIME AND NOT ON THE WAY IN. A post is stored as the Markdown its writer sent. If links
were baked in at save time they would be frozen: a term added to the map next month would never reach
the eighty posts already written, a URL that moved would leave dead links in stored text nobody
re-reads, and the stored body would stop being what the writer actually wrote. Adding them as the
page is built means the whole archive follows the map, every time, and the map is the only thing
anybody has to maintain.

THE MAP IS THE ONLY THING TO EDIT. Everything below `TERMS` is mechanism. A new term is one line in
one language's dict; the registry key it points at is resolved per tree, so a Hindi post links to the
Hindi page without anybody writing a path.

WHAT IT DELIBERATELY WILL NOT DO:
  - more than MAX_LINKS_PER_POST in one post. A page where every other phrase is blue reads like a
    directory and a reader stops seeing any of them.
  - the same term twice. The first mention is where somebody wonders what it means.
  - a link inside a heading, an existing link, code, or a figure caption. A heading that is half
    hyperlink looks broken, and a link inside a link is not a thing.
  - a link to the page the reader is already on.
  - a second link to a target the post already points at in its own prose. The writer's own link is
    better placed than ours, because they chose where it went.

"nakshatra" IS IN THE MAP NOW. It was the one term in the original brief with nowhere to point -
27 pages and no front door - which is what prompted the hub at /nakshatra.
"""
from __future__ import annotations

import re

from app.web import i18n

#: The most links this adds to one post, however many terms match.
MAX_LINKS_PER_POST = 5

#: TERM -> (registry key, params). Lower-case; matching is case-insensitive and whole-word.
#: Longest term wins where two overlap ("kundli matching" before "kundli"), so a shorter term that is
#: a prefix of a longer one costs nothing.
#:
#: ADD TERMS HERE. One line per term per language. A key that does not exist in the registry, or has
#: no page in that language, is skipped at render time rather than raising - so a term can be added
#: for a page that only exists in one tree.
TERMS: dict[str, dict[str, tuple[str, dict]]] = {
    "en": {
        # "nadi dosha" and "bhakoot dosha" are further down, where they already were. These two are
        # the SHORT spellings, which is how the term is actually typed: "nadi dosh" is a
        # 50,000-a-month search and "nadi dosha" is not the same string.
        "nadi dosh": ("match-dosha", {"dosha": "nadi"}),
        "bhakoot dosh": ("match-dosha", {"dosha": "bhakoot"}),
        "marriage biodata": ("biodata", {}),
        "biodata": ("biodata", {}),
        "biodata maker": ("biodata", {}),
        "vivah muhurat": ("muhurat-year", {"purpose": "vivah", "year": 2027}),
        "marriage muhurat": ("muhurat-year", {"purpose": "vivah", "year": 2027}),
        "griha pravesh muhurat": ("muhurat-year", {"purpose": "griha-pravesh", "year": 2027}),
        "hindu calendar": ("hindu-calendar", {"year": 2027}),
        "ekadashi": ("ekadashi-year", {"year": 2027}),
        "diwali": ("diwali-year", {"year": 2027}),
        "kundli matching": ("matching", {}),
        "kundali matching": ("matching", {}),
        "horoscope matching": ("matching", {}),
        "guna milan": ("matching", {}),
        "gun milan": ("matching", {}),
        "match by name": ("gun-milan-name", {}),
        "sade sati": ("sade-sati", {}),
        "nakshatra": ("nakshatra-hub", {}),
        "nakshatras": ("nakshatra-hub", {}),
        "numerology": ("numerology", {}),
        "numerology report": ("numerology-report", {}),
        "mulank": ("numerology", {}),
        "bhagyank": ("numerology", {}),
        "lo shu grid": ("numerology", {}),
        "name number": ("numerology", {}),
        "janma nakshatra": ("nakshatra-hub", {}),
        "sadesati": ("sade-sati", {}),
        "manglik": ("mangal-dosha", {}),
        "mangal dosha": ("mangal-dosha", {}),
        "panchang": ("panchang", {}),
        "birth chart": ("kundali", {}),
        "janam kundali": ("kundali", {}),
        "nadi dosha": ("match-dosha", {"dosha": "nadi"}),
        "bhakoot dosha": ("match-dosha", {"dosha": "bhakoot"}),
        "rashifal": ("rashifal-hub", {}),
        # The two the existing posts are actually about. `sidereal` is English-only, which the
        # per-tree resolution handles by simply not offering it in the other two.
        "ayanamsa": ("sidereal", {}),
        "sidereal zodiac": ("sidereal", {}),
        "vedic astrology": ("astrology", {}),
        "when will i get married": ("marriage-timing", {}),
        "kundli pdf": ("kundli-pdf", {}),
    },
    "hi": {
        # नाड़ी दोष and भकूट दोष are further down, where they already were.
        "काल सर्प दोष": ("dosha-guide", {"dosha": "kaal-sarp"}),
        "पितृ दोष": ("dosha-guide", {"dosha": "pitra"}),
        "विवाह बायोडाटा": ("biodata", {}),
        "बायोडाटा": ("biodata", {}),
        "विवाह मुहूर्त": ("muhurat-year", {"purpose": "vivah", "year": 2027}),
        "गृह प्रवेश मुहूर्त": ("muhurat-year", {"purpose": "griha-pravesh", "year": 2027}),
        "हिंदू कैलेंडर": ("hindu-calendar", {"year": 2027}),
        "एकादशी": ("ekadashi-year", {"year": 2027}),
        "दिवाली": ("diwali-year", {"year": 2027}),
        "कुंडली मिलान": ("matching", {}),
        "गुण मिलान": ("matching", {}),
        "नाम से गुण मिलान": ("gun-milan-name", {}),
        "साढ़े साती": ("sade-sati", {}),
        "नक्षत्र": ("nakshatra-hub", {}),
        "जन्म नक्षत्र": ("nakshatra-hub", {}),
        "अंक ज्योतिष": ("numerology", {}),
        "अंक ज्योतिष रिपोर्ट": ("numerology-report", {}),
        "मूलांक": ("numerology", {}),
        "भाग्यांक": ("numerology", {}),
        "साढ़ेसाती": ("sade-sati", {}),
        "मांगलिक": ("mangal-dosha", {}),
        "मंगल दोष": ("mangal-dosha", {}),
        "पंचांग": ("panchang", {}),
        "जन्म कुंडली": ("kundali", {}),
        "नाड़ी दोष": ("match-dosha", {"dosha": "nadi"}),
        "भकूट दोष": ("match-dosha", {"dosha": "bhakoot"}),
        "राशिफल": ("rashifal-hub", {}),
        "ज्योतिष": ("astrology", {}),
        "शादी कब होगी": ("marriage-timing", {}),
        "कुंडली पीडीएफ": ("kundli-pdf", {}),
    },
    "mr": {
        "लग्न बायोडाटा": ("biodata", {}),
        "बायोडाटा": ("biodata", {}),
        "विवाह मुहूर्त": ("muhurat-year", {"purpose": "vivah", "year": 2027}),
        "गृहप्रवेश मुहूर्त": ("muhurat-year", {"purpose": "griha-pravesh", "year": 2027}),
        "हिंदू दिनदर्शिका": ("hindu-calendar", {"year": 2027}),
        "एकादशी": ("ekadashi-year", {"year": 2027}),
        "दिवाळी": ("diwali-year", {"year": 2027}),
        "पत्रिका जुळवणी": ("matching", {}),
        "गुण मेलन": ("matching", {}),
        "साडेसाती": ("sade-sati", {}),
        "नक्षत्र": ("nakshatra-hub", {}),
        "जन्मनक्षत्र": ("nakshatra-hub", {}),
        "अंकज्योतिष": ("numerology", {}),
        "अंकज्योतिष अहवाल": ("numerology-report", {}),
        "मूलांक": ("numerology", {}),
        "भाग्यांक": ("numerology", {}),
        "मंगळ दोष": ("mangal-dosha", {}),
        "पंचांग": ("panchang", {}),
        "जन्म पत्रिका": ("kundali", {}),
        "नाडी दोष": ("match-dosha", {"dosha": "nadi"}),
        "भकूट दोष": ("match-dosha", {"dosha": "bhakoot"}),
        "राशीभविष्य": ("rashifal-hub", {}),
        "ज्योतिष": ("astrology", {}),
        "लग्न कधी होईल": ("marriage-timing", {}),
        "पत्रिका पीडीएफ": ("kundli-pdf", {}),
    },
}

#: Inside any of these, nothing is linked. `a` because a link in a link is not a thing; the headings
#: because one that is half hyperlink looks broken; `code`/`pre` because a term in code is not prose;
#: `figcaption` because a caption is a label, not a sentence.
_NO_LINK_INSIDE = frozenset({"a", "h1", "h2", "h3", "h4", "h5", "h6", "code", "pre", "figcaption"})

_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)[^>]*>")
#: Devanagari has no cased letters and `\b` behaves differently around it, so the boundary is written
#: as "not a letter of any script" on each side rather than as `\b`.
_BOUNDARY = r"(?<![\wऀ-ॿ])%s(?![\wऀ-ॿ])"


def _targets(lang: str, skip_paths: frozenset[str]) -> list[tuple[str, str]]:
    """(term, path) for this tree, longest term first, minus anything already linked or self."""
    out: list[tuple[str, str]] = []
    for term, (key, params) in TERMS.get(lang, {}).items():
        try:
            path = i18n.url_for(key, lang, **params)
        except Exception:        # a key with no page in this tree is simply not offered here
            continue
        if not path or path in skip_paths:
            continue
        out.append((term, path))
    # A term that resolves to nothing is silently absent from the page, which is the one failure a
    # person adding terms cannot see. tests/test_blog_links.py resolves EVERY term in the map and
    # fails on one that does not, so the silence is caught here rather than in a month's traffic.
    out.sort(key=lambda pair: -len(pair[0]))
    return out


def _linkable_spans(html: str) -> list[tuple[int, int]]:
    """The (start, end) ranges of `html` that are prose we may link inside."""
    spans: list[tuple[int, int]] = []
    depth = 0
    cursor = 0
    for tag in _TAG.finditer(html):
        name = tag.group(2).lower()
        if depth == 0 and tag.start() > cursor:
            spans.append((cursor, tag.start()))
        if name in _NO_LINK_INSIDE:
            if tag.group(1):          # closing
                depth = max(0, depth - 1)
            elif not tag.group(0).endswith("/>"):
                depth += 1
        cursor = tag.end()
    if depth == 0 and cursor < len(html):
        spans.append((cursor, len(html)))
    return spans


def add_links(html: str, *, lang: str, self_path: str = "",
              also_linked: tuple[str, ...] = ()) -> tuple[str, int]:
    """Link the first mention of up to MAX_LINKS_PER_POST terms. Returns (html, how many).

    `also_linked` is for targets the PAGE links to from outside this html - the tool CTA lives in the
    template, so the body cannot see it, and without this the same page gets linked twice.
    """
    already = (frozenset(re.findall(r'href="([^"]+)"', html))
               | ({self_path} if self_path else frozenset())
               | frozenset(path for path in also_linked if path))
    targets = _targets(lang, already)
    if not targets:
        return html, 0

    spans = _linkable_spans(html)
    # EVERY EDIT IS PLANNED FIRST, THEN APPLIED FROM THE END. Substituting as we go would shift every
    # later offset by the length of the tag just inserted, and the second link would land mid-word.
    edits: list[tuple[int, int, str]] = []
    used_paths: set[str] = set()
    for term, path in targets:
        if len(edits) >= MAX_LINKS_PER_POST:
            break
        if path in used_paths:
            continue
        pattern = re.compile(_BOUNDARY % re.escape(term), re.I)
        for start, end in spans:
            found = pattern.search(html, start, end)
            if not found:
                continue
            if any(not (found.end() <= s or found.start() >= e) for s, e, _ in edits):
                continue              # overlaps a link already planned: the longer term won
            edits.append((found.start(), found.end(),
                          f'<a href="{path}">{html[found.start():found.end()]}</a>'))
            used_paths.add(path)
            break
    for start, end, replacement in sorted(edits, reverse=True):
        html = html[:start] + replacement + html[end:]
    return html, len(edits)
