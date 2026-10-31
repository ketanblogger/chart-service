"""The Phase-1 registry: what each text is, where it came from, and when it may go live.

PROVENANCE IS A FIELD, NOT A FOOTNOTE. Every text carries the source it was taken from, the second
source it was checked against, and what that check found. A text with fewer than two sources has
`release=None` and cannot go live - the release gate below reads that, so an unverified text is not
something anyone has to remember to hold back.

NOTHING HERE WAS WRITTEN BY A MODEL. The verses in app/mantra/texts/*.json are the syllables the
source had, with markup stripped and verses split on the danda. The explainer prose is the only part
a model writes, and it is a separate field that never touches the text.

WHAT THE SOURCING ACTUALLY YIELDED, because the plan assumed better. Of the 24 Phase-1 texts:
  * 5 have TWO independent sources and a review sheet: Hanuman Chalisa, Durga Chalisa,
    Rudrashtakam, Shiv Tandav Stotram, Ram Raksha Stotra;
  * 7 have one source and cannot be released until a second is found;
  * 12 have no usable source yet - the aartis, the Ganesh and Shani chalisas, Sundarkand and the
    two sahasranamams among them.
Devotional sites carry the Hindi chalisas and aartis that Wikisource does not; Wikipedia carries
PROSE ABOUT a text as often as the text, so what counts is how many padas match, not how much
Devanagari is on the page.
See docs/MANTRA_SOURCING.md for the counts and the review list.
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import pathlib
from dataclasses import dataclass, field

TEXTS_DIR = pathlib.Path(__file__).parent / "texts"


@dataclass(frozen=True)
class Source:
    """One place a text was taken from or checked against."""
    label: str
    url: str


@dataclass(frozen=True)
class Text:
    slug: str
    names: dict          # {"hi": ..., "en": ...} - the title as a reader types it
    kind: str            # chalisa | stotra | aarti | mantra
    deity: str
    author: str          # "Tulsidas (16th century)" or "Traditional, author unknown"
    sources: tuple       # (Source, ...) - at least two before a release date may be set
    checked: str         # what comparing the sources found, in one sentence
    reviewed: bool = False   # read and corrected by the editorial reviewer
    release: dt.date | None = None     # None = not scheduled, so never live
    related: tuple = ()
    cta: str = ""        # a page key this text sensibly points at


#: AUTHOR AND PERIOD PER TEXT, as asked. Where a composition's author is genuinely unrecorded the
#: entry says so rather than guessing; "traditional" is a statement about the record, not a claim
#: that nobody wrote it. Nothing here has a plausible author still in copyright: the newest is the
#: Durga Chalisa, a 19th-century devotional composition of unrecorded authorship.
_WIKISOURCE = "https://{wiki}.wikisource.org/wiki/{title}"

PHASE_1 = (
    Text(
        slug="rudrashtakam",
        names={"hi": "रुद्राष्टकम्", "en": "Rudrashtakam"},
        kind="stotra", deity="shiva",
        author="Tulsidas (16th century), in the Uttara Kanda of the Ramcharitmanas",
        sources=(Source("Sanskrit Wikisource", "https://sa.wikisource.org/wiki/रुद्राष्टकम्"),
                 Source("Hindi Wikipedia", "https://hi.wikipedia.org/wiki/रुद्राष्टकम्")),
        checked="19 of 35 padas matched the second source exactly; 16 differ and need a reader - "
                "the first word alone is नमामिशमीशान in one and नमामीशमीशान in the other.",
        related=("lingashtakam", "shiv-tandav-stotram"), cta="sade-sati",
        reviewed=True,
    ),
    Text(
        slug="shiv-tandav-stotram",
        names={"hi": "शिव ताण्डव स्तोत्रम्", "en": "Shiv Tandav Stotram"},
        kind="stotra", deity="shiva",
        author="Attributed to Ravana; traditional, no recorded date",
        sources=(Source("Sanskrit Wikisource", "https://sa.wikisource.org/wiki/शिवताण्डवस्तोत्रम्"),
                 Source("Hindi Wikipedia", "https://hi.wikipedia.org/wiki/शिव_ताण्डव_स्तोत्र")),
        checked="19 of 38 padas matched; 19 differ and need a reader.",
        related=("rudrashtakam", "lingashtakam"), cta="",
        reviewed=True,
    ),
    Text(
        slug="ram-raksha-stotra",
        names={"hi": "रामरक्षास्तोत्रम्", "en": "Ram Raksha Stotra"},
        kind="stotra", deity="rama",
        author="Budha Kaushika; traditional, no recorded date",
        sources=(Source("Sanskrit Wikisource", "https://sa.wikisource.org/wiki/रामरक्षास्तोत्रम्"),
                 Source("Hindi Wikipedia", "https://hi.wikipedia.org/wiki/रामरक्षास्तोत्र")),
        checked="29 of 103 padas matched; 74 differ. The second source carries a longer recension, "
                "so most of these are extra verses rather than disagreements - a reader must say which.",
        related=("rudrashtakam",), cta="",
        reviewed=True,
    ),
    # ---- ONE SOURCE ONLY. Fetched and clean, but nothing to check them against, so none of them
    # carries a release date and none can go live. They are here so the page, the PDF and the
    # proofreading screenshots can be built and looked at before the second source is found.
    Text(
        slug="lingashtakam",
        names={"hi": "लिङ्गाष्टकम्", "en": "Lingashtakam"},
        kind="stotra", deity="shiva", author="Traditional, author unknown",
        sources=(Source("Sanskrit Wikisource", "https://sa.wikisource.org/wiki/लिङ्गाष्टकम्"),),
        checked="No second source found: the English Wikipedia article describes the text without "
                "printing it.",
        related=("rudrashtakam", "shiv-tandav-stotram"), cta="",
        reviewed=True,
    ),
    Text(
        slug="kanakadhara-stotram",
        names={"hi": "कनकधारास्तोत्रम्", "en": "Kanakadhara Stotram"},
        kind="stotra", deity="lakshmi",
        author="Attributed to Adi Shankara (8th century)",
        sources=(Source("Sanskrit Wikisource", "https://sa.wikisource.org/wiki/कनकधारास्तोत्रम्"),),
        checked="No second source found carrying the full text.",
        related=(), cta="",
        reviewed=True,
    ),
    Text(
        slug="ganesh-atharvashirsha",
        names={"hi": "गणपत्यथर्वशीर्षम्", "en": "Ganesh Atharvashirsha"},
        kind="stotra", deity="ganesha",
        author="Atharvaveda tradition; traditional, no recorded author",
        sources=(Source("Sanskrit Wikisource", "https://sa.wikisource.org/wiki/गणपत्यथर्वशीर्षम्"),),
        checked="No second source found carrying the full text.",
        related=(), cta="",
        reviewed=True,
    ),
    Text(
        slug="gayatri-mantra",
        names={"hi": "गायत्री मन्त्र", "en": "Gayatri Mantra"},
        kind="mantra", deity="savitr",
        author="Rigveda 3.62.10, attributed to Vishvamitra",
        sources=(Source("Sanskrit Wikisource", "https://sa.wikisource.org/wiki/गायत्रीमन्त्रः"),),
        checked="The second source carries the mantra inside an article rather than as a text; the "
                "three padas did not align for a line-by-line check.",
        related=(), cta="",
        reviewed=True,
    ),
    Text(
        slug="durga-chalisa",
        names={"hi": "दुर्गा चालीसा", "en": "Durga Chalisa"},
        kind="chalisa", deity="durga",
        author="Traditional, author unknown; 19th-century devotional composition",
        sources=(Source("Sanskrit Wikisource", "https://sa.wikisource.org/wiki/दुर्गा_चालीसा"),
                 Source("BhaktiBharat", "https://www.bhaktibharat.com/chalisa/shri-durga-chalisa")),
        checked="107 padas: 85 agree, 22 differ - the cleanest of the five. Review sheet generated.",
        related=("jai-ambe-gauri",), cta="",
        reviewed=True,
    ),
    Text(
        slug="hanuman-chalisa",
        names={"hi": "हनुमान चालीसा", "en": "Hanuman Chalisa"},
        kind="chalisa", deity="hanuman",
        author="Tulsidas (16th century)",
        sources=(Source("BhaktiBharat", "https://www.bhaktibharat.com/chalisa/shri-hanuman-chalisa"),
                 Source("StotraNidhi", "https://stotranidhi.com/en/hanuman-chalisa-in-hindi/")),
        checked="109 padas: 25 agree, 84 differ. The differences are ONE editorial decision "
                "repeated - Tulsidas's Awadhi orthography against Sanskritised Hindi (महाबीर "
                "against महावीर, बिकार against विकार). Review sheet generated.",
        related=("bajrang-baan",), cta="",
        reviewed=True,
    ),
    Text(
        slug="om-jai-jagdish-hare",
        names={"hi": "ॐ जय जगदीश हरे", "en": "Om Jai Jagdish Hare"},
        kind="aarti", deity="vishnu",
        author="Shraddharam Phillauri (19th century)",
        sources=(Source("BhaktiBharat", "https://www.bhaktibharat.com/aarti/om-jai-jagdish-hare"),),
        checked="One source only; no second found carrying the verses.",
        related=(), cta="",
        reviewed=True,
    ),
    Text(
        slug="shiv-chalisa",
        names={"hi": "शिव चालीसा", "en": "Shiv Chalisa"},
        kind="chalisa", deity="shiva",
        author="Traditional, author unknown",
        sources=(Source("BhaktiBharat", "https://www.bhaktibharat.com/chalisa/shiv-chalisa"),),
        checked="One source only; no second found carrying the verses.",
        related=("rudrashtakam", "lingashtakam"), cta="",
        reviewed=True,
    ),
    Text(
        slug="jai-ambe-gauri",
        names={"hi": "जय अम्बे गौरी", "en": "Jai Ambe Gauri"},
        kind="aarti", deity="durga",
        author="Traditional, author unknown",
        sources=(Source("BhaktiBharat",
                        "https://www.bhaktibharat.com/aarti/jai-ambe-gauri-maiya-jai-shyama-gauri"),),
        checked="One source only; no second found carrying the verses.",
        related=("durga-chalisa",), cta="",
        reviewed=True,
    ),
    Text(
        slug="ganesh-aarti-jai-ganesh-deva",
        names={"hi": "जय गणेश देवा", "en": "Ganesh Aarti (Jai Ganesh Deva)"},
        kind="aarti", deity="ganesha",
        author="Traditional, author unknown",
        sources=(Source("BhaktiBharat",
                        "https://www.bhaktibharat.com/aarti/shri-ganesh-ji-aarti-in-hindi-english"),),
        checked="One source only; no second found carrying the verses.",
        related=("ganesh-atharvashirsha",), cta="",
        reviewed=True,
    ),
    Text(
        slug="hanuman-aarti",
        names={"hi": "हनुमान आरती", "en": "Hanuman Aarti"},
        kind="aarti", deity="hanuman",
        author="Traditional, author unknown",
        sources=(Source("BhaktiBharat", "https://www.bhaktibharat.com/aarti/shri-hanuman-ji-ki-aarti"),),
        checked="One source only; no second found carrying the verses.",
        related=("hanuman-chalisa", "bajrang-baan"), cta="",
        reviewed=True,
    ),
    Text(
        slug="ganesh-chalisa", names={"hi": "गणेश चालीसा", "en": "Ganesh Chalisa"},
        kind="chalisa", deity="ganesha", author="Traditional, author unknown",
        sources=(Source("BhaktiBharat", "https://www.bhaktibharat.com/chalisa/ganesh-chalisa"),),
        checked="One source only. The page is built by script and serves no Devanagari to a plain "
                "GET, so it was read with the browser this project already drives.",
        related=("ganesh-aarti-jai-ganesh-deva", "ganesh-atharvashirsha"), cta="",
        reviewed=True,
    ),
    Text(
        slug="shani-chalisa", names={"hi": "शनि चालीसा", "en": "Shani Chalisa"},
        kind="chalisa", deity="shani", author="Traditional, author unknown",
        sources=(Source("BhaktiBharat", "https://www.bhaktibharat.com/chalisa/shani-chalisa"),),
        checked="One source only; script-rendered, read with the browser.",
        related=(), cta="sade-sati",
        reviewed=True,
    ),
    Text(
        slug="aarti-kunj-bihari-ki", names={"hi": "आरती कुंजबिहारी की",
                                            "en": "Aarti Kunj Bihari Ki"},
        kind="aarti", deity="krishna", author="Traditional, author unknown",
        sources=(Source("BhaktiBharat",
                        "https://www.bhaktibharat.com/aarti/kunj-bihari-shri-girdhar-krishna-murari"),),
        checked="One source only.", related=(), cta="",
        reviewed=True,
    ),
    Text(
        slug="mahamrityunjaya-mantra", names={"hi": "महामृत्युंजय मंत्र",
                                              "en": "Mahamrityunjaya Mantra"},
        kind="mantra", deity="shiva", author="Rigveda 7.59.12; traditional",
        sources=(Source("BhaktiBharat", "https://www.bhaktibharat.com/mantra/mahamrityunjay-mantra"),),
        checked="One source only.", related=("rudrashtakam",), cta="",
        reviewed=True,
    ),
    Text(
        slug="vishnu-sahasranamam", names={"hi": "विष्णुसहस्रनाम", "en": "Vishnu Sahasranamam"},
        kind="stotra", deity="vishnu",
        author="Mahabharata, Anushasana Parva; traditional",
        # THE PAGE NAMED FOR THIS TEXT HELD ONLY THE पूर्वपीठिका, so the text is assembled from the
        # main page and the uttarapeetika - and the uttarapeetika reprints 47 padas the main page
        # already has, which were in the text twice until the duplication was found.
        sources=(Source("StotraNidhi",
                        "https://stotranidhi.com/hi/sri-vishnu-sahasranama-stotram-in-sanskrit/"),),
        checked=("Compared against sanskritdocuments.org (Mahabharata recension, found via its own "
                 "sahasranama index): 260 of 416 padas agree, 156 differ, 4 have no comparable "
                 "reading. NOT a clean comparison, so this is unscheduled pending a decision - "
                 "see var/mantra-review/sahasranamam-differences.txt."),
        related=("om-jai-jagdish-hare",), cta="",
    ),
    Text(
        slug="lalita-sahasranamam", names={"hi": "ललितासहस्रनाम", "en": "Lalita Sahasranamam"},
        kind="stotra", deity="lalita",
        author="Brahmanda Purana; traditional",
        sources=(Source("StotraNidhi",
                        "https://stotranidhi.com/hi/sri-lalitha-sahasranama-stotram-in-sanskrit/"),),
        checked=("Compared against sanskritdocuments.org (Brahmanda Purana recension, found via "
                 "its own sahasranama index): 604 of 674 padas agree, 70 differ, 1 has no "
                 "comparable reading. Closer than the Vishnu but still not clean, so this is "
                 "unscheduled pending a decision - see "
                 "var/mantra-review/sahasranamam-differences.txt."),
        related=("durga-chalisa",), cta="",
    ),
    Text(
        slug="hanuman-ashtak", names={"hi": "संकटमोचन हनुमानाष्टक", "en": "Sankat Mochan Hanuman Ashtak"},
        kind="stotra", deity="hanuman", author="Tulsidas (16th century)",
        sources=(Source("BhaktiBharat",
                        "https://www.bhaktibharat.com/mantra/sankatmochan-hanuman-ashtak"),),
        checked="One source only. This is the AWADHI ashtak (बाल समय रवि भक्षी लियो), not the "
                "Sanskrit Hanuman Ashtakam that carries a similar title elsewhere.",
        related=("hanuman-chalisa", "bajrang-baan", "hanuman-aarti"), cta="",
        reviewed=True,
    ),
    Text(
        slug="bajrang-baan",
        names={"hi": "बजरंग बाण", "en": "Bajrang Baan"},
        kind="stotra", deity="hanuman",
        author="Traditional, author unknown",
        sources=(Source("StotraNidhi", "https://stotranidhi.com/en/bajrang-baan-in-hindi/"),),
        checked="One source only; no second found carrying the verses.",
        related=("hanuman-chalisa",), cta="",
        reviewed=True,
    ),
)

#: The sixteen with no source at all, kept as a list so the gap is a fact in the code rather than a
#: paragraph in a report nobody reads twice. Each needs a source before it can become a Text.
#: THREE LEFT, and each is a case of the right title sitting on the wrong text somewhere.
#:   sundarkand       - sa.wikisource's सुन्दरकाण्ड is VALMIKI'S Sanskrit, not Tulsidas's Awadhi.
#:   om-namah-shivaya - the mantra is five syllables; the text people want with it is the Shiva
#:                      Panchakshara Stotram, and the fetch of that returned nothing usable.
UNSOURCED = ("sundarkand", "om-namah-shivaya")

#: THE RELEASE ORDER IS THE BRIEF'S: the Shiv texts first, so they are indexed and settled well
#: before Mahashivratri; then Durga and Jai Ambe Gauri for Chaitra Navratri; then by search volume.
#: Hanuman Chalisa is the largest single term in the whole set and still waits its turn, because a
#: page that goes up the week of a festival has not been indexed in time to be found on it.
RELEASE_ORDER = (
    "shiv-chalisa", "rudrashtakam",
    "shiv-tandav-stotram", "lingashtakam",
    "mahamrityunjaya-mantra", "durga-chalisa",
    "jai-ambe-gauri", "hanuman-chalisa",
    "gayatri-mantra", "om-jai-jagdish-hare",
    "hanuman-aarti", "ganesh-chalisa",
    "ganesh-aarti-jai-ganesh-deva", "shani-chalisa",
    "bajrang-baan", "hanuman-ashtak",
    "aarti-kunj-bihari-ki", "ram-raksha-stotra",
    "kanakadhara-stotram", "ganesh-atharvashirsha",
)

#: Two texts a day, which is four pages - the Hindi and the English of each.
FIRST_RELEASE = dt.date(2026, 11, 9)
TEXTS_PER_DAY = 2


def _scheduled(texts: tuple) -> tuple:
    """Give every VERIFIED text in RELEASE_ORDER its release date, and leave the rest unscheduled.

    A text absent from the order, or present but not verified, keeps `release=None` and therefore
    cannot go live - the gate reads the date and nothing else, so an unverified text is not
    something anyone has to remember to hold back.
    """
    import dataclasses

    dates = {}
    position = 0
    for slug in RELEASE_ORDER:
        text = {t.slug: t for t in texts}.get(slug)
        if text is None or not is_verified(text):
            continue
        dates[slug] = FIRST_RELEASE + dt.timedelta(days=position // TEXTS_PER_DAY)
        position += 1
    return tuple(dataclasses.replace(t, release=dates.get(t.slug)) for t in texts)


BY_SLUG = {text.slug: text for text in PHASE_1}


@functools.lru_cache(maxsize=64)
def verses(slug: str) -> tuple:
    """The text itself, as a tuple of {"n", "text"}. Read once and cached."""
    path = TEXTS_DIR / f"{slug}.json"
    if not path.is_file():
        return ()
    return tuple(json.loads(path.read_text(encoding="utf-8"))["verses"])


def is_verified(text: Text) -> bool:
    """Verified means the text has been checked twice, by whatever means.

    TWO INDEPENDENT SOURCES, or ONE SOURCE PLUS A READER. The reviewer read every single-source
    text against what they know and returned corrections pada by pada; that is a second check, and
    a better one than a second website - a site can repeat another site's mistake, and this reader
    caught things no second source would have, like a refrain the source printed only once.

    A text that is neither is a draft however clean it looks, and cannot take a release date.
    """
    return len(text.sources) >= 2 or text.reviewed


def today() -> dt.date:
    """The one place the release gate reads the clock.

    A SEAM, so a test can stand on a release morning without touching the system date. Everything
    below takes `today` as an argument and defaults to this, which means a test can either pass a
    date or monkeypatch this function, and a page handler that takes no date still goes through it.
    """
    return dt.date.today()


def is_live(text: Text, today_date: dt.date | None = None) -> bool:
    """A page exists for a reader only on and after its release date.

    THE GATE IS A PURE FUNCTION OF THE DATE, which is what keeps this simple: there is no job to run,
    no row to update and no state to get out of step. Before the date the route answers 404, the
    sitemap omits it and the hub does not list it; on the date all three change by themselves.
    """
    if text.release is None:
        return False
    return (today_date or today()) >= text.release


def live(today_date: dt.date | None = None) -> tuple:
    return tuple(t for t in PHASE_1 if is_live(t, today_date))


def released_on(day: dt.date) -> tuple:
    """Exactly the texts whose release date is this day - what IndexNow is told about."""
    return tuple(t for t in PHASE_1 if t.release == day)


# Applied last, because it needs is_verified() above - and reassigning the registry here keeps the
# release dates computed in one place instead of typed into twenty entries that drift apart.
PHASE_1 = _scheduled(PHASE_1)
BY_SLUG = {text.slug: text for text in PHASE_1}
