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

from app.rashifal.i18n import rashi_name as _rashi_name  # the one Marathi spelling table; see _DEVA_NAMES
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
# DERIVED, not a third copy. These were written out by hand and drifted: on 2026-09-30 the Marathi tuple
# still said धनु at position nine while the rashifal table, the PDF labels and the hand-written Marathi copy
# on the rashi pages all said धनू - so a Marathi reader got "धनु राशिभविष्य" in the page TITLE above a page
# that said धनू forty-two times. The spelling authority is `app/rashifal/i18n.rashi_name`, which the rashifal
# pages and the AI briefs already read; this file now reads it too rather than agreeing with it by hand.
# (Hindi is unchanged by the derivation: the two tuples were identical, which is asserted in tests/test_i18n_registry.py.)
_DEVA_NAMES = {lang: tuple(_rashi_name(index, lang) for index in range(1, 13)) for lang in ("hi", "mr")}
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
    "gun-milan-name": {"en": "/gun-milan-by-name", "hi": "/hi/naam-se-gun-milan",
                       "mr": "/mr/navavarun-gun-melan"},
    "mangal-dosha": {"en": "/mangal-dosha", "hi": "/hi/mangal-dosha", "mr": "/mr/mangal-dosha"},
    "sade-sati": {"en": "/sade-sati", "hi": "/hi/sade-sati", "mr": "/mr/sade-sati"},
    # English only, and it is a CALCULATOR rather than a policy page - the one page in the registry that is
    # both. It runs the same engine and the same form as "kundali"; what differs is that the reader arrived
    # searching for the word "sidereal", so the page answers that question first and calculates second.
    "sidereal": {"en": "/sidereal-birth-chart"},
    "consultation": {"en": "/ai-astrologer", "hi": "/hi/ai-jyotish", "mr": "/mr/ai-jyotish"},
    # "aaj ka panchang" is 100K-1M a month and "पंचांग" another 50K. Everything on the page comes out of
    # the ephemeris, so it costs nothing per view and nothing per day - unlike the rashifal, which is the
    # reason this is worth having at all.
    #
    # ONE INDEXED URL PER LANGUAGE, which is TODAY. Other dates are reachable by the picker and are
    # noindex: a panchang has a page for every date since the calendar began, and inviting a crawler to
    # all of them is how a site spends its crawl budget on pages nobody searched for. The query people
    # type is "aaj ka panchang" - today's - and that is the page that is in the sitemap.
    "panchang": {"en": "/panchang", "hi": "/hi/aaj-ka-panchang", "mr": "/mr/aajche-panchang"},
    # "meri shadi kab hogi" is 50K a month and rising hard. The page answers it the only way a chart can:
    # with the standing indications and the periods tradition reads as supportive, never with a date.
    # The engine behind it (app/engine/timing.py) takes the question as DATA, so "naukri kab lagegi" is
    # a TOPICS entry and its copy rather than a second engine.
    # "kundli" and "kundali" are 100K-1M a month each, and the English tree answered them at
    # /birth-chart - a page named after a phrase with a fraction of the demand. This is the SAME tool and
    # the same engine at the name people type; what differs is that it answers "what is a kundli and how
    # do I read one" underneath, which /birth-chart does not. The Hindi and Marathi trees already live at
    # /hi/kundli and /mr/kundali, so this is the English tree catching up rather than a new family.
    # The pillar. "ज्योतिष" is 50K a month on its own, and the query behind it is not transactional -
    # somebody wants to understand the thing, not calculate anything. Every tool on this site is a leaf;
    # this is the trunk they hang from, and the one page that can answer "what IS this" at length.
    "astrology": {"en": "/astrology", "hi": "/hi/jyotish", "mr": "/mr/jyotish"},
    "kundli": {"en": "/kundli"},
    "marriage-timing": {"en": "/when-will-i-get-married",
                        "hi": "/hi/shadi-kab-hogi",
                        "mr": "/mr/lagna-kadhi-hoil"},
    # "makar rashi in english" - a real query, in all three trees, with the same spelling in each because
    # that is how it is typed. Answers the question in the first sentence and then explains the thing
    # behind it: that a rashi is a MOON sign and the English name people are matching it to is usually
    # being used for a sun sign.
    # Festival muhurta, per festival and year. The windows are computed per city and the date itself is
    # decided by which tithi is running at the moment the observance needs - see app/engine/festivals.py.
    # "/muhurat/", NOT "/muhurta/". The muhurta finder owns that prefix and sits OUTSIDE this registry on
    # purpose - it ships with site.MUHURTA off, and a sitemap entry for a switched-off page is a 404 we
    # invited a crawler to. Putting indexed festival pages under its prefix made "muhurta" a registry
    # segment and turned that tool's own path_for() into a hardcoded-path violation. "muhurat" is also the
    # spelling people type: every published panchang writes "Lakshmi Puja Muhurat".
    "festival": {"en": "/muhurat/{festival}-{year}",
                 "hi": "/hi/muhurat/{festival}-{year}",
                 "mr": "/mr/muhurat/{festival}-{year}"},
    # A PERMANENT ADDRESS FOR ONE YEAR'S READING. The rolling yearly page at /horoscope/{rashi}/yearly is
    # always "this year", so it has no address a link or a search result can point at for 2027, and every
    # January its content silently becomes a different year's. These do not move. People start searching
    # "rashifal 2027" in the autumn before it, which is now.
    # NUMEROLOGY. "numerology calculator" and "name numerology calculator" are 500,000 searches a
    # month each - the largest single term this site has gone after. The Devanagari trees use
    # "ank-jyotish", which is what numerology is called in both.
    "numerology": {"en": "/numerology-calculator", "hi": "/hi/ank-jyotish",
                   "mr": "/mr/ank-jyotish"},
    # "lo shu grid" and "lo shu grid calculator" are 50,000 a month each. The main calculator already
    # draws the grid; this is the page somebody typing that term lands on, with the grid first.
    "lo-shu": {"en": "/lo-shu-grid-calculator", "hi": "/hi/lo-shu-grid",
               "mr": "/mr/lo-shu-grid"},
    # THE PAID REPORT'S OWN PAGE: what is in it, a sample of each section, the price, and the only
    # button that buys it.
    "numerology-report": {"en": "/numerology-report", "hi": "/hi/numerology-report",
                          "mr": "/mr/numerology-report"},
    # MULANK 1-9. "mulank 1" through "mulank 9" and "{n} number in numerology" are 50,000 searches a
    # month each - nine numbers, three trees, twenty-seven pages.
    "mulank": {"en": "/mulank-{number}", "hi": "/hi/mulank-{number}", "mr": "/mr/mulank-{number}"},
    # Mobile, vehicle, house and business numbers - many 5,000-a-month variants, one page with tabs
    # rather than four thin ones saying the same thing about different digits.
    "number-check": {"en": "/mobile-number-numerology", "hi": "/hi/mobile-number-numerology",
                     "mr": "/mr/mobile-number-numerology"},
    # THE MARRIAGE BIODATA MAKER. Seven separate terms at 50,000 searches a month each - "marriage
    # biodata", "biodata maker", "marriage biodata format", "marriage biodata maker", "create biodata
    # for marriage", "marriage biodata template" and "marathi biodata maker" - which makes this the
    # most-searched thing on the site after the numerology calculator, and the only one of them that
    # is a document rather than a reading.
    #
    # MARATHI IS NOT AN AFTERTHOUGHT HERE. "marathi biodata maker" alone is 50,000 a month and
    # "biodata format for marriage in marathi" and "marathi marriage biodata template" are 5,000
    # each; the Marathi tree gets the same tool with its own labels (रास, नाडी, मंगळ - not the Hindi
    # ones), which is the whole reason somebody searching in Marathi would use this rather than a
    # generic template.
    "biodata": {"en": "/marriage-biodata-maker", "hi": "/hi/vivah-biodata-maker",
                "mr": "/mr/lagna-biodata-maker"},
    # "marriage biodata format in word" and its many variants are 50,000 a month between them, and
    # the thing being asked for is a FILE - so this page's job is to hand over the .docx, not to
    # explain what a biodata is. It is a separate page because the intent is different: the maker is
    # for somebody filling one in, this is for somebody who wants the format to type into.
    # DIWALI. "diwali 2027" is 50,000 searches a month - the biggest single dated term this site
    # has gone after - and the one thing a reader actually wants from it is the Lakshmi puja
    # muhurat in their own city, which the engine computes.
    "diwali-year": {"en": "/diwali-{year}", "hi": "/hi/diwali-{year}", "mr": "/mr/diwali-{year}"},
    # HINDI AND ENGLISH ONLY. The Marathi demand for these texts is a fraction of the Hindi, and a
    # Marathi tree would mean a third set of verses to source, compare and have read - the cost is
    # in the sourcing, not the template.
    "mantra-hub": {"en": "/mantra", "hi": "/hi/mantra"},
    "mantra": {"en": "/mantra/{slug}", "hi": "/hi/mantra/{slug}"},
    # THE WHOLE YEAR ON ONE PAGE. "hindu calendar {year}" and "festival calendar {year}" together
    # are the second-biggest, and this is also where the amavasya and purnima dates live - two
    # thin pages of their own would say less than one page that puts them beside the festivals.
    "hindu-calendar": {"en": "/hindu-calendar-{year}", "hi": "/hi/hindu-calendar-{year}",
                       "mr": "/mr/hindu-calendar-{year}"},
    # Ekadashi has its own page because people fast on them and look up the next one, which is a
    # different question from "what falls this year".
    "ekadashi-year": {"en": "/ekadashi-{year}", "hi": "/hi/ekadashi-{year}",
                      "mr": "/mr/ekadashi-{year}"},
    # MUHURAT DATES FOR A YEAR, one page per purpose. "vivah muhurat 2027" is 5,000 searches a
    # month and rising fast, and the others are 500 each - small numbers that are worth having
    # because the engine already computes every one of these and the pages cost no AI at all.
    #
    # NOT under /muhurat/, which the festival pages use, and not under /muhurta/, which the finder
    # tool owns. The bare form is also what people type.
    "muhurat-year": {"en": "/{purpose}-muhurat-{year}", "hi": "/hi/{purpose}-muhurat-{year}",
                     "mr": "/mr/{purpose}-muhurat-{year}"},
    "biodata-word": {"en": "/marriage-biodata-format-in-word",
                     "hi": "/hi/marriage-biodata-format-word",
                     "mr": "/mr/marriage-biodata-format-word"},
    # ONE PAGE PER SLOW GRAHA PER YEAR. "jupiter transit 2026" is 50,000 searches a month and the
    # gochar terms 5,000 each; this site had the dates and no page to put them on. Marathi uses शनी
    # with the long ी, which is that tree's spelling.
    "gochar": {"en": "/{graha}-transit-{year}", "hi": "/hi/{graha}-gochar-{year}",
               "mr": "/mr/{graha}-gochar-{year}"},
    # ONE PAGE FOR THE WHOLE YEAR, all twelve rashis. "rashifal 2027" and "राशिफल 2027" are the big
    # terms; the per-rashi pages below answer "my sign in 2027" and this one answers "2027".
    "rashifal-year-hub": {"en": "/horoscope/{year}", "hi": "/hi/rashifal/{year}",
                          "mr": "/mr/rashi-bhavishya/{year}"},
    "rashifal-year": {"en": "/horoscope/{rashi}/{year}",
                      "hi": "/hi/rashifal/{rashi}/{year}",
                      "mr": "/mr/rashi-bhavishya/{rashi}/{year}"},
    # Sade Sati per Moon sign, BELOW the calculator at /sade-sati the way the readings sit below /sade-sati.
    # The key is "sade-sati-rashi" and not "sade-sati": that name is already the calculator's, and a
    # dict literal accepts a repeated key in silence and keeps the last one, so the first attempt replaced
    # the calculator's own URL with this one and nothing said a word.
    # Per-tree slugs here, unlike rashi-in-english: "sade sati" is itself the Indian term, so an English
    # searcher types "sade sati capricorn". That exception was for a query that CARRIES the Indian name.
    "sade-sati-rashi": {"en": "/sade-sati/{rashi}",
                        "hi": "/hi/shani-sade-sati/{rashi}",
                        "mr": "/mr/shani-sade-sati/{rashi}"},
    # One page per nakshatra, in all three trees. "nakshatra in hindi" and "mool nakshatra in hindi" are
    # 5K each and the other twenty-five are around 500 - small individually, 81 pages together, and
    # written once with no daily AI cost. The slug is the nakshatra's own key, lowercased.
    # The dosha guides. HINDI FIRST because that is where the demand is: "pitradosh ke upay" and
    # "kaal sarp dosh" are 5K each and "manglik dosh kaise check kare" 500 - and because these are the
    # three subjects most used to frighten people into paying for a puja. The pages explain what the
    # configuration IS, how it is and is not identified, and sell nothing against it.
    # HINDI ONLY, AND DELIBERATELY SO. All three target queries are Hindi - "pitradosh ke upay",
    # "kaal sarp dosh", "manglik dosh kaise check kare" - and the English tree already answers mangal
    # dosha with a calculator. Adding thin English and Marathi versions to fill a registry would be
    # three more pages with nothing to say, which is how a site accumulates the kind of page Search
    # Console files under "Discovered - currently not indexed". They follow when there is demand.
    # "rashifal by name" is 50K a month. The engine already does this - namakshar.from_name() takes a
    # name, finds its first syllable, and maps it to the nakshatra pada and Moon sign the traditional
    # namakshar chakra assigns. The page's job is to be honest that this is the NAME-BASED method and
    # not a birth chart.
    # "kundali pdf" and "detailed kundli" are transactional queries - somebody wants the document, not
    # an explanation. This page is the one place that says plainly what the FREE PDF contains and what
    # the paid report adds, with a sample of each, and then goes to checkout.
    "kundli-pdf": {"en": "/kundli-pdf", "hi": "/hi/kundli-pdf", "mr": "/mr/kundali-pdf"},
    # "astrosage alternative" / "best free kundli website". An honest, dated comparison - including
    # where the others are better, which is the only thing that makes such a page worth reading.
    # The blog, English only - stated as a decision in app/blog/paths.py rather than left as an
    # omission. A post's path carries its slug; the family expands from the published posts, so a draft
    # has no URL in the sitemap any more than it has one on the site.
    "blog": {"en": "/blog", "hi": "/hi/blog", "mr": "/mr/blog"},
    "blog-post": {"en": "/blog/{slug}", "hi": "/hi/blog/{slug}", "mr": "/mr/blog/{slug}"},
    "compare": {"en": "/compare-free-kundli-websites",
                "hi": "/hi/best-free-kundli-website",
                "mr": "/mr/best-free-kundli-website"},
    "rashi-by-name": {"en": "/rashi-by-name", "hi": "/hi/naam-se-rashi",
                      "mr": "/mr/navavarun-rashi"},
    # "love rashifal" and "aaj ka love rashifal" are 50K each. These reuse the relationships section the
    # reading ALREADY has - no new AI call, no new daily cost.
    "love-rashifal": {"en": "/horoscope/{rashi}/love",
                      "hi": "/hi/rashifal/{rashi}/prem",
                      "mr": "/mr/rashi-bhavishya/{rashi}/prem"},
    "dosha-guide": {"hi": "/hi/dosh/{dosha}"},
    # The two doshas a MATCHING result reports, in every tree - because a matching result exists in
    # every tree. "nadi dosh" alone is 50,000 searches a month.
    "match-dosha": {"en": "/{dosha}-dosha", "hi": "/hi/{dosha}-dosh", "mr": "/mr/{dosha}-dosh"},
    # THE HUB FOR ALL 27. "nakshatras" is 50,000 searches a month and the word had nowhere to point:
    # twenty-seven pages and no front door, which is also why the blog's link map could not use the
    # term at all.
    "nakshatra-hub": {"en": "/nakshatra", "hi": "/hi/nakshatra", "mr": "/mr/nakshatra"},
    "nakshatra": {"en": "/nakshatra/{nakshatra}",
                  "hi": "/hi/nakshatra/{nakshatra}",
                  "mr": "/mr/nakshatra/{nakshatra}"},
    "rashi-in-english": {"en": "/rashi/{rashi}-in-english",
                         "hi": "/hi/rashi/{rashi}-in-english",
                         "mr": "/mr/rashi/{rashi}-in-english"},
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
    "pricing": {"en": "/pricing"},
    "delivery-policy": {"en": "/delivery-policy"},
    "refund-policy": {"en": "/refund-policy"},
    "disclaimer": {"en": "/disclaimer"},
}

TOOL_KEYS = ("kundali", "matching", "mangal-dosha", "sade-sati")  # the four free calculators, in nav order
# IN ALL THREE TREES, AND DELIBERATELY NOT IN THE NAV. TOOL_KEYS is the navigation set - a test says
# so in those words - and EN_ONLY_TOOL_KEYS is for pages a tree does not have. A tool that every tree
# has but the chrome should not carry had nowhere to live, so it has one: a fifth nav entry for a
# second door into a tool already in the nav would spend the chrome on a distinction most readers do
# not have. Reached from the matching page, from search, and from the love pages.
EXTRA_TOOL_KEYS = ("gun-milan-name",)
# Calculator pages that exist in some languages only, so they cannot join TOOL_KEYS: that tuple drives the
# navigation of all three trees, and a nav entry pointing at a page a tree does not have is a broken link.
# They get routes, a sitemap entry and hreflang from `page_langs` like any other page; they are simply not
# in the chrome. Keep them out of NAV_KEYS deliberately rather than by oversight.
EN_ONLY_TOOL_KEYS = ("sidereal", "kundli")
# Razorpay checks for these by name before activating international payments, and refused on
# 2026-09-29 because "Pricing of services" and a shipping/delivery policy did not exist.
POLICY_KEYS = ("about", "contact", "pricing", "delivery-policy", "privacy", "terms",
               "refund-policy", "disclaimer")
_PARAMS = {"rashifal-rashi": ("rashi",), "rashifal-reading": ("rashi", "period"),
           "rashi-in-english": ("rashi",), "sade-sati-rashi": ("rashi",), "nakshatra": ("nakshatra",), "dosha-guide": ("dosha",), "match-dosha": ("dosha",), "blog-post": ("slug",), "love-rashifal": ("rashi",),
           "rashifal-year": ("rashi", "year"), "rashifal-year-hub": ("year",),
           "gochar": ("graha", "year"), "mulank": ("number",),
           "muhurat-year": ("purpose", "year"), "diwali-year": ("year",),
           "hindu-calendar": ("year",), "ekadashi-year": ("year",),
           "festival": ("festival", "year"), "mantra": ("slug",)}


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
        # THE INDIAN NAME IN EVERY TREE for this family, because the query is "makar rashi in english" -
        # the reader knows their rashi by that name and is asking what it is called in English.
        # "/rashi/capricorn-in-english" would answer a question nobody has.
        values["rashi"] = rashi_slug(params["rashi"], "hi" if page_key == "rashi-in-english" else lang)
    if "period" in params:
        values["period"] = PERIOD_SLUGS[lang][params["period"]]
    if "year" in params:
        values["year"] = str(params["year"])
    if "festival" in params:
        values["festival"] = str(params["festival"])
    if "slug" in params:
        values["slug"] = str(params["slug"])
    if "dosha" in params:
        values["dosha"] = str(params["dosha"])
    if "number" in params:
        values["number"] = str(params["number"])
    if "graha" in params:
        # The same slug in every tree: "shani" is what a Hindi and a Marathi reader both type, and
        # an English one searching "shani transit 2027" types it too.
        values["graha"] = str(params["graha"]).lower()
    if "purpose" in params:
        # The muhurta engine's own purpose key, and the same slug in all three trees for the same
        # reason as the grahas: "vivah muhurat 2027" is what the search looks like in every one.
        values["purpose"] = str(params["purpose"]).lower()
    if "nakshatra" in params:
        # The nakshatra's own key, lowercased - "ashwini", "purvashadha". The same slug in every tree:
        # a nakshatra has one name, and a Hindi reader searching for it types that name.
        values["nakshatra"] = str(params["nakshatra"]).lower().replace(" ", "-")
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
    #: The trees THIS page exists in, when that is narrower than the family's. A blog post exists in the
    #: language it was written in and nowhere else - it is not an English page awaiting translation, and
    #: listing it under every tree would put a Hindi URL in the English sitemap. None means "the whole
    #: family", which is what every other page is.
    langs_override: tuple[str, ...] | None = None

    @property
    def kwargs(self) -> dict[str, str]:
        return dict(self.params)

    @property
    def langs(self) -> tuple[str, ...]:
        if self.langs_override is not None:
            # Still intersected with the family's own trees: a page cannot claim a tree the registry
            # does not give it a path in.
            return tuple(lang for lang in page_langs(self.key) if lang in self.langs_override)
        return page_langs(self.key)

    def path(self, lang: str = DEFAULT_LANG) -> str:
        return url_for(self.key, lang, **self.kwargs)

    def url(self, lang: str = DEFAULT_LANG) -> str:
        return absolute(self.path(lang))

    def alternates(self) -> dict[str, str]:
        """The hreflang set for THIS page, which is not always the one its key implies.

        A blog post exists in the tree it was written in and gains a sibling only when somebody writes
        one, so the registry's answer - every language the KEY is published in - was declaring
        /hi/blog/<slug> and /mr/blog/<slug> as alternates of posts nobody had translated. The page
        itself has always got this right; the SITEMAP did not, and the two disagreeing is what the
        smoke check caught. Google reads the sitemap.
        """
        if self.key == "blog-post":
            from app.blog import pages as blog_pages

            return blog_pages.sitemap_alternates(dict(self.params))
        # A ref pinned to one language (`langs_override`) has nothing to point at either.
        if len(self.langs) < 2:
            return {}
        return alternates(self.key, **self.kwargs)


#: The festivals with a page, and the years they are published for. Bhai Dooj is deliberately ABSENT:
#: our Dwitiya times agree with the published ones to the minute, but panchangs disagree about which day
#: that makes the festival, because on 10 November 2026 Dwitiya covers only part of aparahna. A family acts
#: on this date, so the disagreement is reported rather than resolved by us.
FESTIVAL_PAGES = (("dhanteras", 2026), ("lakshmi-puja", 2026))

#: The years with a permanent page. Adding 2028 is this line and nothing else; the pages, the sitemap
#: entries, the hreflang and the links from the rolling yearly page all follow from it.
YEAR_PAGES = (2027,)

# The five a family actually looks up a date for. "business" and "travel" stay finder-only: nobody
# searches "business muhurat 2027", and a page per purpose that nobody wants is a page to maintain.
MUHURAT_PURPOSES = ("vivah", "griha-pravesh", "vehicle", "property", "naming")

#: THE SLOW GRAHAS WITH A PAGE OF THEIR OWN. Rahu and Ketu share one: they are always opposite each
#: other, so two pages would be the same dates twice with the houses swapped - which is a duplicate
#: in every sense a search engine cares about and in the only sense a reader does.
GOCHAR_GRAHAS = ("shani", "guru", "rahu-ketu")


def all_pages() -> Iterator[PageRef]:
    """Every indexable logical page, once: fixed pages, 12 rashi hubs, 60 readings. One sitemap <url> per
    (ref, lang) for lang in ref.langs - 363 URLs.

    The arithmetic is deliberately NOT spelled out as a sum any more. It used to read
    "6x3 + 2x3 + 12x3 + 60x3 + 6 = 246", and when the English-only /sidereal-birth-chart page landed on
    2026-09-25 the sum went stale in four places at once - here, the smoke check, and twice in docs/API.md -
    because each of them had copied a different slice of it. A count that is derived in one place and
    asserted against the registry cannot drift; a sum written out in prose drifts silently.
    `tests/test_seo.py` pins the number against this function, so a new page fails a test rather than
    leaving a comment quietly wrong."""
    for key in PAGES:
        if key == "festival":
            for festival, year in FESTIVAL_PAGES:
                yield PageRef(key, (("festival", festival), ("year", str(year))))
        elif key == "mulank":
            for number in range(1, 10):
                yield PageRef(key, (("number", str(number)),))
        elif key == "gochar":
            for graha in GOCHAR_GRAHAS:
                for year in YEAR_PAGES:
                    yield PageRef(key, (("graha", graha), ("year", str(year))))
        elif key == "mantra":
            # ONLY THE RELEASED TEXTS. The sitemap is a promise that a URL answers, and an
            # unreleased page answers 404 by design - listing it would be asking Google to
            # crawl a 404 every day until the release date.
            from app.mantra import texts as _mantra

            for text in _mantra.live():
                yield PageRef(key, (("slug", text.slug),))
        elif key in ("diwali-year", "hindu-calendar", "ekadashi-year"):
            for year in YEAR_PAGES:
                yield PageRef(key, (("year", str(year)),))
        elif key == "muhurat-year":
            for purpose in MUHURAT_PURPOSES:
                for year in YEAR_PAGES:
                    yield PageRef(key, (("purpose", purpose), ("year", str(year))))
        elif key == "rashifal-year-hub":
            for year in YEAR_PAGES:
                yield PageRef(key, (("year", str(year)),))
        elif key == "rashifal-year":
            for rashi in RASHI_KEYS:
                for year in YEAR_PAGES:
                    yield PageRef(key, (("rashi", rashi), ("year", str(year))))
        elif key in ("rashifal-rashi", "rashi-in-english", "sade-sati-rashi", "love-rashifal"):
            for rashi in RASHI_KEYS:
                yield PageRef(key, (("rashi", rashi),))
        elif key == "blog-post":
            # Published posts only. `published_slugs()` is written for this moment: its own read-only
            # connection, and () when the database does not exist - because THIS RUNS AT IMPORT TIME,
            # from _build_reverse(), before any test has pointed APP_DB anywhere, and building the URL
            # registry must never create a database.
            #
            # It is also why app/blog/admin.py imports `_page` lazily: this import reaches the blog
            # package while app.admin.routes is half-initialised, and a module-level import back into it
            # closed the cycle and stopped the application starting.
            from app.blog import store as blog_store

            # A post exists in the tree it was WRITTEN in, not in all three. A Hindi post is not an
            # English page waiting to be translated, and listing it under /blog would put a Hindi URL
            # in the English sitemap.
            for slug, language in blog_store.published_slugs():
                yield PageRef(key, (("slug", slug),), langs_override=(language,))
        elif key == "dosha-guide":
            from app.web.dosha_guides import DOSHAS

            for dosha in DOSHAS:
                yield PageRef(key, (("dosha", dosha),))
        elif key == "match-dosha":
            from app.web.dosha_guides import MATCH_DOSHAS

            for dosha in MATCH_DOSHAS:
                yield PageRef(key, (("dosha", dosha),))
        elif key == "nakshatra":
            from app.web.nakshatra_data import NAKSHATRAS

            for nakshatra in NAKSHATRAS:
                yield PageRef(key, (("nakshatra", nakshatra.key),))
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
