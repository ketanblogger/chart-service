"""THE ONE PLACE A BLOG URL IS SPELLED, and the one place that says the blog is English only.

Why this module exists at all, rather than the paths living in app/web/i18n.py like every other page's:
the registry is owned by the lead and the blog's entries are wired in there separately. So every blog
path is derived from the registry WHEN IT HAS THE ENTRY and from the default beside it when it does
not - which means the routes, the links, the canonical, the admin page and the IndexNow submission
cannot disagree with one another at any point in that wiring, and they all move together the moment the
registry entry lands.

The registry entries this expects (page key, path, parameters):

    "blog":      {"en": "/blog"}                 no parameters
    "blog-post": {"en": "/blog/{slug}"}          parameterised by `slug`

`url_for` is NOT what reads them here - `i18n.PAGES` is, directly. That is deliberate: `url_for` has to
learn how to fill a `{slug}` before it can serve this family, and until it does, reading the templates
means a half-wired registry still produces the same paths rather than an exception on every page.
`tests/test_blog.py::test_the_registry_entries_are_wired_completely_if_they_are_wired_at_all` is what
makes a half-wiring a blog failure rather than a sitemap failure three files away.

ENGLISH ONLY. `LANGS` is the whole statement; see app/blog/__init__.py for why, and app/web/
dosha_guides.py for the same decision taken the other way round (Hindi only, for Hindi demand).
"""

from __future__ import annotations

import re

from app.web import i18n

#: The language trees the blog exists in. Three now - see app/blog/__init__.py, which argued for one
#: and said what would change the answer: "the day there is Hindi demand and a Hindi writer the registry
#: entry gains 'hi' and this module follows". Both halves of that happened.
#:
#: A POST EXISTS IN THE TREE IT WAS WRITTEN IN, not in all three. The trees are where posts MAY live,
#: never a promise that any given post lives in all of them.
LANGS = ("en", "hi", "mr")

#: The default when a caller does not say. Every post written before the language column existed is
#: English, and so is anything the API does not label.
LANG = "en"

LIST_KEY = "blog"
POST_KEY = "blog-post"

#: What the paths are until the registry carries them, and what they must be when it does.
_DEFAULT_LIST = "/blog"
_DEFAULT_POST = "/blog/{slug}"

#: Uploaded images sit under the blog root so a post, its pictures and the index share one prefix - and
#: the route is registered BEFORE the post route, so "media" can never be read as a slug. `RESERVED`
#: keeps it from being one from the other direction too, at the moment a post is created.
_MEDIA_SEGMENT = "media"
RESERVED_SLUGS = frozenset({_MEDIA_SEGMENT, "feed", "rss", "index", "page", "tag", "category", "admin"})

#: A slug is lowercase ASCII words joined by single hyphens. Narrow on purpose: it becomes a URL, a file
#: name is never derived from it, and anything outside this set would have to be escaped somewhere.
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_SLUG_CHARS = 80


def _template(key: str, default: str, lang: str = LANG) -> str:
    """The registry's template for a blog page in one tree, or the default while the entry is absent."""
    try:
        return i18n.PAGES[key][lang]
    except KeyError:
        return default if lang == LANG else f"/{lang}{default}"


def list_template(lang: str = LANG) -> str:
    return _template(LIST_KEY, _DEFAULT_LIST, lang)


def post_template(lang: str = LANG) -> str:
    """The FastAPI route path as well as the link template: `{slug}` is both spellings at once."""
    return _template(POST_KEY, _DEFAULT_POST, lang)


def media_template() -> str:
    """ONE media route, in the English tree, whatever language the post is in.

    An image is bytes with an id - it has no language, and giving it three URLs would mean three cache
    entries for one file and three ways to write the same link in a post body."""
    return f"{_template(LIST_KEY, _DEFAULT_LIST, LANG).rstrip('/')}/{_MEDIA_SEGMENT}/{{image_id}}"


def list_path(lang: str = LANG) -> str:
    return _template(LIST_KEY, _DEFAULT_LIST, lang)


def post_path(slug: str, lang: str = LANG) -> str:
    return _template(POST_KEY, _DEFAULT_POST, lang).format(slug=slug)


def media_path(image_id: str) -> str:
    return media_template().format(image_id=image_id)


def registered() -> bool:
    """True when the URL registry carries the blog, i.e. when it is in the sitemap and has a canonical
    the rest of the site agrees with. The pages serve either way; this is what the admin page reports."""
    return LIST_KEY in i18n.PAGES and POST_KEY in i18n.PAGES


def is_slug(value: str) -> bool:
    return bool(value) and len(value) <= MAX_SLUG_CHARS and bool(SLUG.fullmatch(value)) \
        and value not in RESERVED_SLUGS


def slugify(title: str) -> str:
    """A slug from a title, for a caller that did not choose one. Never trusted as a file name."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return cleaned[:MAX_SLUG_CHARS].strip("-")


# ---- the tool a post is about ------------------------------------------------------------------------
#
# EVERY POST LINKS TO THE TOOL IT IS ABOUT, and the link is not decoration: a post about kundli matching
# that does not reach the matching page is a page that answered a question and then let the reader leave.
# So `tool` is required when a post is created, and it is a registry key rather than a URL - the post
# then follows the tool if the tool's slug ever moves, which is the whole reason the registry exists.
#
# The labels are here and not read from app/web/pages.py on purpose: COPY_KEYS covers the twelve pages
# whose copy is shared across the three trees, and half the pages below (the panchang, the pillar guide,
# the comparison) keep their own copy in their own modules, so there is no one function that can name
# them all. These are the words the blog uses for the link, which is a blog decision.
TOOLS: dict[str, str] = {
    "kundali": "Free birth chart (kundli) calculator",
    "kundli": "What a kundli is, and how to read one",
    "matching": "Free kundli matching (guna milan)",
    "mangal-dosha": "Free mangal dosha check",
    "sade-sati": "Free Sade Sati check",
    "sidereal": "Sidereal birth chart calculator",
    "panchang": "Today's panchang",
    "consultation": "Ask the AI astrologer",
    "astrology": "Vedic astrology: the full guide",
    "marriage-timing": "When will I get married?",
    "rashi-by-name": "Find your rashi from your name",
    "kundli-pdf": "Kundli PDF: what is free and what is paid",
    "rashifal-hub": "Today's horoscope",
    "compare": "Free kundli websites, compared",
}


def tool_keys() -> tuple[str, ...]:
    """The tools a post may be about: those of `TOOLS` the registry can currently give an English path.

    FILTERED RATHER THAN ASSERTED, so a registry change cannot take the whole site down at import - and
    `tests/test_blog.py::test_every_tool_a_post_may_link_to_has_an_english_page` is what notices when one
    of these keys stops resolving, which is the right place for it to be noticed.
    """
    return tuple(key for key in TOOLS if _tool_path(key) is not None)


def _tool_label(key: str, lang: str) -> str:
    """The tool's name IN THE TREE THE LINK ACTUALLY GOES TO.

    The English names below used to be printed on every tree, so the Hindi and Marathi blogs listed
    "Free birth chart (kundli) calculator" to readers who had chosen another language. The site
    already holds a name for each of these pages in each language; this reads that and keeps the
    table as the fallback for the handful of keys the web registry has no copy for.

    The LANGUAGE PASSED IS THE ONE THE PATH RESOLVED TO, not the one the reader is in. A Marathi
    reader sent to an English-only comparison page should see its English name, because that is the
    page they are about to open.
    """
    from app.web import pages as web_pages

    try:
        return web_pages.raw(key, lang).nav_label or TOOLS.get(key, key)
    except KeyError:
        return TOOLS.get(key, key)


def _tool_blurb(key: str, lang: str) -> str:
    """One line about the tool, in the language of the page it links to. Empty where none is written."""
    from app.web import pages as web_pages

    try:
        # FILLED, NOT RAW. These blurbs carry placeholders - the AI astrologer's names the number of
        # free messages - and `raw` is raw on purpose. Printing it unfilled put a literal
        # "{free_messages}" on the blog index, which the site-wide language check would have caught
        # on the next full run and a reader would have caught immediately.
        copy = web_pages.raw(key, lang)
        return web_pages.fill((copy.card_blurb or "").strip(), **web_pages.common_values(lang))
    except KeyError:
        return ""


def _tool_path(key: str, lang: str = LANG) -> str | None:
    """The tool's page IN THE READER'S OWN TREE, falling back to English where that tree has no page.

    A Hindi blog post sending its reader to an English calculator is a dead end dressed as a link. Not
    every tool exists in every tree - the dosha guides are Hindi-only, the comparison page is English-
    only - so the fallback is real rather than theoretical, and it is better than dropping the link.
    """
    for candidate in (lang, LANG):
        try:
            return i18n.url_for(key, candidate)
        except KeyError:
            continue
    return None


def tool_link(key: str, lang: str = LANG) -> dict | None:
    """{"key", "path", "label"} for the tool a post is about, or None if that key has no page at all."""
    for candidate in (lang, LANG):
        try:
            path = i18n.url_for(key, candidate)
        except KeyError:
            continue
        return {"key": key, "path": path, "label": _tool_label(key, candidate),
                "blurb": _tool_blurb(key, candidate)}
    return None
