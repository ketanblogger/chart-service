"""The URL registry: every public page, in every language, in ONE place.

Three language trees on one domain: English at `/`, Hindi under `/hi/`, Marathi under `/mr/`. Slugs are transliterated
Latin (that is how people search); each language version has its own slug written to its own keyword:

    url_for("matching", "mr")                                   -> "/mr/patrika-matching"
    url_for("rashifal-reading", "hi", rashi="tula", period="today")  -> "/hi/rashifal/tula/aaj"
    alternates("kundali")     -> {"en": ".../birth-chart", "hi": ".../hi/kundli", "mr": ".../mr/kundali", "x-default": en}
    resolve("/horoscope/libra/weekly")  -> ("rashifal-reading", "en", {"rashi": "tula", "period": "weekly"})
    legacy_redirect("/rashifal/mesha/3-months", "lang=hi")      -> "/hi/rashifal/mesh/masik"

Nothing else in the web layer spells a path: templates use `url_for` (a Jinja global), the sitemap iterates
`all_pages()`, and tests/test_no_hardcoded_paths.py greps templates / JS for stray internal links.

Parameters are INTERNAL keys, never slugs:
  * `rashi`  - the engine's sign slug (RASHI_KEYS: "mesha" ... "meena"; == app.engine sign_info(i)["slug"], the key of
               the rashifal content store). `rashi_key(anything)` normalises an index, an English sign or any slug.
  * `period` - PERIOD_KEYS: "today", "weekly", "monthly", "6-months", "yearly" (the store's period keys).

This module imports nothing from the engine, the store or the AI layer, so everybody can import it.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import parse_qs

from app.web import site

LANGS = ("en", "hi", "mr")
DEFAULT_LANG = "en"  # also hreflang x-default
HTML_LANG = {"en": "en", "hi": "hi", "mr": "mr"}  # <html lang>, Content-Language, JSON-LD inLanguage, hreflang
OG_LOCALE = {"en": "en_IN", "hi": "hi_IN", "mr": "mr_IN"}
LANGUAGE_NAMES = {"en": "English", "hi": "हिन्दी", "mr": "मराठी"}  # each in its own script, for the switcher
LANG_PREFIX = {"en": "", "hi": "/hi", "mr": "/mr"}

# ---- rashis ------------------------------------------------------------------------------------------

RASHI_KEYS = ("mesha", "vrishabha", "mithuna", "karka", "simha", "kanya",
              "tula", "vrishchika", "dhanu", "makara", "kumbha", "meena")  # zodiac order; also the legacy URL slugs
_SIGN_SLUGS = ("aries", "taurus", "gemini", "cancer", "leo", "virgo",
               "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces")  # English tree
_RASHI_SLUGS = ("mesh", "vrishabh", "mithun", "kark", "singh", "kanya",
                "tula", "vrishchik", "dhanu", "makar", "kumbh", "meen")  # Hindi + Marathi trees (SEO map spellings)
RASHI_SLUGS = {"en": _SIGN_SLUGS, "hi": _RASHI_SLUGS, "mr": _RASHI_SLUGS}

# Internal-link priority: rashis by monthly search demand per language, highest first (SEO map §4 table; ties keep
# zodiac order). Use `rashis_by_demand(lang)` wherever a page lists "other rashis".
_DEMAND = {
    "hi": ("tula", "kumbha", "kanya", "mesha", "makara", "simha", "mithuna", "meena", "vrishchika", "dhanu", "karka",
           "vrishabha"),
    "en": ("karka", "vrishchika", "simha", "mesha", "kanya", "kumbha", "vrishabha", "tula", "mithuna", "meena",
           "makara", "dhanu"),
    "mr": ("simha", "tula", "mesha", "kumbha", "kanya", "mithuna", "dhanu", "makara", "meena", "karka", "vrishabha",
           "vrishchika"),
}

# Display names (static reference data, same spellings as app/engine/constants.py + the Marathi forms).
_SIGN_NAMES = ("Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn",
               "Aquarius", "Pisces")
_LATIN_NAMES = ("Mesh", "Vrishabh", "Mithun", "Kark", "Singh", "Kanya", "Tula", "Vrishchik", "Dhanu", "Makar", "Kumbh",
                "Meen")  # how Hindi / Marathi searchers type the rashi
_DEVA_NAMES = {
    "hi": ("मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या", "तुला", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन"),
    "mr": ("मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या", "तूळ", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन"),
}
_SIGN_LORDS = ("Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Saturn",
               "Jupiter")
GRAHA_NAMES = {
    "en": {"Sun": "Sun (Surya)", "Moon": "Moon (Chandra)", "Mars": "Mars (Mangal)", "Mercury": "Mercury (Budha)",
           "Jupiter": "Jupiter (Guru)", "Venus": "Venus (Shukra)", "Saturn": "Saturn (Shani)", "Rahu": "Rahu",
           "Ketu": "Ketu"},
    "hi": {"Sun": "सूर्य", "Moon": "चंद्र", "Mars": "मंगल", "Mercury": "बुध", "Jupiter": "गुरु", "Venus": "शुक्र",
           "Saturn": "शनि", "Rahu": "राहु", "Ketu": "केतु"},
    "mr": {"Sun": "सूर्य", "Moon": "चंद्र", "Mars": "मंगळ", "Mercury": "बुध", "Jupiter": "गुरू", "Venus": "शुक्र",
           "Saturn": "शनी", "Rahu": "राहू", "Ketu": "केतू"},
}


def rashi_names(rashi: str | int, lang: str) -> dict[str, str]:
    """How a rashi is written in a language tree - the values of the {rashi} {latin} {sign} {deva} {lord} copy
    placeholders. `rashi` is the primary name readers of that language use: "Libra" (en), "तुला" (hi), "तूळ" (mr)."""
    index = rashi_index(rashi) - 1
    deva = _DEVA_NAMES["mr" if lang == "mr" else "hi"][index]
    return {"key": RASHI_KEYS[index], "index": index + 1, "slug": RASHI_SLUGS[lang][index],
            "rashi": _SIGN_NAMES[index] if lang == "en" else deva, "latin": _LATIN_NAMES[index],
            "sign": _SIGN_NAMES[index], "deva": deva, "lord": GRAHA_NAMES[lang][_SIGN_LORDS[index]]}


# ---- periods -----------------------------------------------------------------------------------------

PERIOD_KEYS = ("today", "weekly", "monthly", "6-months", "yearly")
PERIOD_SLUGS = {
    "en": {"today": "today", "weekly": "weekly", "monthly": "monthly", "6-months": "6-months", "yearly": "yearly"},
    "hi": {"today": "aaj", "weekly": "saptahik", "monthly": "masik", "6-months": "6-mahine", "yearly": "varshik"},
    "mr": {"today": "aaj", "weekly": "saptahik", "monthly": "masik", "6-months": "6-mahine", "yearly": "varshik"},
}
_LEGACY_PERIODS = {"today": "today", "weekly": "weekly", "3-months": "monthly", "6-months": "6-months", "yearly": "yearly"}

# ---- the registry ------------------------------------------------------------------------------------
# page key -> per-language path template. "{rashi}" / "{period}" are filled with that language's slug.

RASHIFAL_ROOT = {"en": "/horoscope", "hi": "/hi/rashifal", "mr": "/mr/rashi-bhavishya"}

PAGES: dict[str, dict[str, str]] = {
    "home": {"en": "/", "hi": "/hi/", "mr": "/mr/"},
    "kundali": {"en": "/birth-chart", "hi": "/hi/kundli", "mr": "/mr/kundali"},
    "matching": {"en": "/horoscope-matching", "hi": "/hi/kundali-matching", "mr": "/mr/patrika-matching"},
    "mangal-dosha": {"en": "/mangal-dosha", "hi": "/hi/mangal-dosha", "mr": "/mr/mangal-dosha"},
    "sade-sati": {"en": "/sade-sati", "hi": "/hi/sade-sati", "mr": "/mr/sade-sati"},
    # English only, and it is a CALCULATOR rather than a policy page - the one page in the registry that is
    # both. It runs the same engine and the same form as "kundali"; what differs is that the reader arrived
    # searching for the word "sidereal", so the page answers that question first and calculates second.
    "sidereal": {"en": "/sidereal-birth-chart"},
    "consultation": {"en": "/ai-astrologer", "hi": "/hi/ai-jyotish", "mr": "/mr/ai-jyotish"},
    # rashifal: daily hub (all 12 rashis, today), weekly hub, one hub per rashi, 180 reading pages
    "rashifal-hub": dict(RASHIFAL_ROOT),
    "rashifal-weekly": {lang: f"{root}/{PERIOD_SLUGS[lang]['weekly']}" for lang, root in RASHIFAL_ROOT.items()},
    "rashifal-rashi": {lang: root + "/{rashi}" for lang, root in RASHIFAL_ROOT.items()},
    "rashifal-reading": {lang: root + "/{rashi}/{period}" for lang, root in RASHIFAL_ROOT.items()},
    # policy / trust pages: English only (no hreflang alternates), linked from all three footers
    "about": {"en": "/about"},
    "contact": {"en": "/contact"},
    "privacy": {"en": "/privacy"},
    "terms": {"en": "/terms"},
    "refund-policy": {"en": "/refund-policy"},
    "disclaimer": {"en": "/disclaimer"},
}

TOOL_KEYS = ("kundali", "matching", "mangal-dosha", "sade-sati")  # the four free calculators, in nav order
# Calculator pages that exist in some languages only, so they cannot join TOOL_KEYS: that tuple drives the
# navigation of all three trees, and a nav entry pointing at a page a tree does not have is a broken link.
# They get routes, a sitemap entry and hreflang from `page_langs` like any other page; they are simply not
# in the chrome. Keep them out of NAV_KEYS deliberately rather than by oversight.
EN_ONLY_TOOL_KEYS = ("sidereal",)
POLICY_KEYS = ("about", "contact", "privacy", "terms", "refund-policy", "disclaimer")
_PARAMS = {"rashifal-rashi": ("rashi",), "rashifal-reading": ("rashi", "period")}


def page_langs(page_key: str) -> tuple[str, ...]:
    """Languages a page exists in, in LANGS order."""
    return tuple(lang for lang in LANGS if lang in PAGES[page_key])


def rashi_key(value: str | int) -> str:
    """Normalise a 1-12 index, an internal key or ANY tree's slug ("libra", "tula", "mesh", "mesha") to the key."""
    if isinstance(value, int):
        if 1 <= value <= 12:
            return RASHI_KEYS[value - 1]
        raise KeyError(f"rashi index {value!r} is not 1-12")
    for names in (RASHI_KEYS, _SIGN_SLUGS, _RASHI_SLUGS):
        if value in names:
            return RASHI_KEYS[names.index(value)]
    raise KeyError(f"unknown rashi {value!r}")


def rashi_slug(rashi: str | int, lang: str) -> str:
    return RASHI_SLUGS[lang][RASHI_KEYS.index(rashi_key(rashi))]


def rashi_index(rashi: str | int) -> int:
    """1-12."""
    return RASHI_KEYS.index(rashi_key(rashi)) + 1


def period_slug(period: str, lang: str) -> str:
    return PERIOD_SLUGS[lang][period]


def rashis_by_demand(lang: str) -> tuple[str, ...]:
    """The 12 rashi keys, highest search demand first for that language (internal-link order)."""
    return _DEMAND[lang]


def url_for(page_key: str, lang: str = DEFAULT_LANG, **params) -> str:
    """Site-relative path of a page in a language. KeyError for an unknown page, language, rashi or period."""
    template = PAGES[page_key][lang]
    expected = _PARAMS.get(page_key, ())
    if set(params) != set(expected):
        raise KeyError(f"{page_key} takes parameters {expected}, got {tuple(params)}")
    values = {}
    if "rashi" in params:
        values["rashi"] = rashi_slug(params["rashi"], lang)
    if "period" in params:
        values["period"] = PERIOD_SLUGS[lang][params["period"]]
    return template.format(**values)


def absolute(path: str) -> str:
    return site.base_url() + path


def alternates(page_key: str, **params) -> dict[str, str]:
    """hreflang set of a page: {"en": url, "hi": url, "mr": url, "x-default": url} - absolute URLs from BASE_URL,
    identical on every language version (that is what makes the set reciprocal). {} for a single-language page."""
    langs = page_langs(page_key)
    if len(langs) < 2:
        return {}
    links = {HTML_LANG[lang]: absolute(url_for(page_key, lang, **params)) for lang in langs}
    links["x-default"] = links[HTML_LANG[DEFAULT_LANG]]
    return links


@dataclass(frozen=True)
class PageRef:
    """One logical page (all its language versions). `params` is a tuple of (name, value) pairs."""

    key: str
    params: tuple[tuple[str, str], ...] = ()

    @property
    def kwargs(self) -> dict[str, str]:
        return dict(self.params)

    @property
    def langs(self) -> tuple[str, ...]:
        return page_langs(self.key)

    def path(self, lang: str = DEFAULT_LANG) -> str:
        return url_for(self.key, lang, **self.kwargs)

    def url(self, lang: str = DEFAULT_LANG) -> str:
        return absolute(self.path(lang))

    def alternates(self) -> dict[str, str]:
        return alternates(self.key, **self.kwargs)


def all_pages() -> Iterator[PageRef]:
    """Every indexable logical page, once: fixed pages, 12 rashi hubs, 60 readings. One sitemap <url> per
    (ref, lang) for lang in ref.langs - 6x3 + 2x3 + 12x3 + 60x3 + 6 = 246 URLs."""
    for key in PAGES:
        if key == "rashifal-rashi":
            for rashi in RASHI_KEYS:
                yield PageRef(key, (("rashi", rashi),))
        elif key == "rashifal-reading":
            for rashi in RASHI_KEYS:
                for period in PERIOD_KEYS:
                    yield PageRef(key, (("rashi", rashi), ("period", period)))
        else:
            yield PageRef(key)


def all_paths() -> Iterator[tuple[str, str, str, dict[str, str]]]:
    """(path, page_key, lang, params) for every public URL."""
    for ref in all_pages():
        for lang in ref.langs:
            yield ref.path(lang), ref.key, lang, ref.kwargs


def _build_reverse() -> dict[str, tuple[str, str, dict[str, str]]]:
    table: dict[str, tuple[str, str, dict[str, str]]] = {}
    for path, key, lang, params in all_paths():
        # A collision (e.g. a rashi slug equal to "weekly" / "saptahik") must fail loudly at import.
        assert path not in table, f"URL collision: {path} is both {table[path][:2]} and {(key, lang)}"
        table[path] = (key, lang, params)
    return table


_REVERSE = _build_reverse()


def resolve(path: str) -> tuple[str, str, dict[str, str]] | None:
    """Reverse lookup: "/hi/rashifal/tula/aaj" -> ("rashifal-reading", "hi", {"rashi": "tula", "period": "today"}).
    Exact paths only ("/hi" and "/mr" also resolve to the language home). None for anything else."""
    if path in ("/hi", "/mr"):
        path += "/"
    found = _REVERSE.get(path)
    return (found[0], found[1], dict(found[2])) if found else None


def lang_of_path(path: str) -> str:
    """Language tree a path belongs to, registered or not (error pages, /order/... -> "en")."""
    for lang in ("hi", "mr"):
        if path == LANG_PREFIX[lang] or path.startswith(LANG_PREFIX[lang] + "/"):
            return lang
    return DEFAULT_LANG


# ---- legacy URLs (the pre-SEO-map site) -> 301 ------------------------------------------------------------

LEGACY_REDIRECTS = {  # fixed old path -> (page_key, lang)
    "/janam-kundali": ("kundali", "en"),
    "/kundali-matching": ("matching", "en"),
    "/consultation": ("consultation", "en"),
    "/marathi-kundali": ("kundali", "mr"),
    "/rashifal": ("rashifal-hub", "en"),
    # The Hindi chart page was /hi/kundali until the slug was renamed to /hi/kundli: "kundli" is the spelling
    # with the search demand behind it (the keyword map), and the page had been submitted to Search Console
    # that same week, so it had nothing ranked to lose. The old path keeps 301ing for anything linking to it.
    "/hi/kundali": ("kundali", "hi"),
}
LEGACY_ROUTE_PATTERNS = ("/janam-kundali", "/kundali-matching", "/consultation", "/marathi-kundali", "/rashifal",
                         "/hi/kundali", "/rashifal/{rashi}", "/rashifal/{rashi}/{period}")  # what routes.py registers


def legacy_redirect(path: str, query: str = "") -> str | None:
    """New path for an old URL, in ONE hop, or None if `path` is not a legacy URL.

    Old rashifal URLs were /rashifal[/{rashi}[/{period}]] with `?lang=mr|hi` for the translations; old rashi slugs
    are RASHI_KEYS and the old "3-months" period is now "monthly". An unknown `lang` value falls back to English.
    The fixed table also holds /hi/kundali, the Hindi chart page's slug before it was renamed to /hi/kundli."""
    path = path.rstrip("/") or "/"
    wanted = (parse_qs(query.lstrip("?")).get("lang") or [""])[0]
    if path in LEGACY_REDIRECTS:
        key, lang = LEGACY_REDIRECTS[path]
        if key == "rashifal-hub" and wanted in LANGS:
            lang = wanted
        return url_for(key, lang)
    parts = path.strip("/").split("/")
    if parts[0] != "rashifal" or not 2 <= len(parts) <= 3 or parts[1] not in RASHI_KEYS:
        return None
    lang = wanted if wanted in LANGS else DEFAULT_LANG
    if len(parts) == 2:
        return url_for("rashifal-rashi", lang, rashi=parts[1])
    if parts[2] not in _LEGACY_PERIODS:
        return None
    return url_for("rashifal-reading", lang, rashi=parts[1], period=_LEGACY_PERIODS[parts[2]])


def switcher(page_key: str | None, lang: str, **params) -> list[dict]:
    """Language switcher entries for a page: [{"lang", "label", "path", "current"}] - the SAME page in every
    language; a page that does not exist in a language (policy pages, errors) links to that language's home."""
    links = []
    for code in LANGS:
        if page_key in PAGES and code in PAGES[page_key]:
            path = url_for(page_key, code, **params)
        else:
            path = url_for("home", code)
        links.append({"lang": code, "hreflang": HTML_LANG[code], "label": LANGUAGE_NAMES[code], "path": path,
                      "current": code == lang})
    return links
