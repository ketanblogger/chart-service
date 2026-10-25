"""The permanent URL vocabulary and the time window behind each period slug.

All windows are in IST (Asia/Kolkata, the platform's home timezone) and half-open: [start, end).

| slug       | window                                                             | refreshed            |
|------------|--------------------------------------------------------------------|----------------------|
| today      | the IST calendar day containing the run moment                     | daily, 00:05 IST     |
| weekly     | Monday 00:00 - next Monday 00:00 (the Mon-Sun week of the run date) | Mondays, 00:10 IST   |
| monthly    | the IST calendar month containing the run moment                   | 1st of each month    |
| 6-months   | 1st of the current month 00:00 + 6 calendar months                 | 1st of each month    |
| yearly     | the CALENDAR year, switching to the next one on 20 November        | once a year, 20 Nov  |

(`monthly` replaced the MVP's `3-months`: it is what people search for.)

Why 6-months rolls monthly from the 1st: a calendar-half page is mostly about the past by the time it
ends, while a window that rolls forward each month always looks ahead and gives a fresh reason to re-crawl
the same permanent URL. Anchoring to the 1st (not to the run date) keeps the window identical for every run
in a month, so refreshes are idempotent. Nobody searches for a calendar half-year, so it stays rolling.

Why yearly is NOT rolling: people search "rashifal 2027", and that demand spikes in November and December
of 2026. A rolling twelve months can never answer it - in November 2026 the window would be Nov 2026 to
Nov 2027, which is not any year anyone types. So yearly is the calendar year, and it turns over on
20 NOVEMBER rather than on 1 January: from that date the page is next year's, titled with next year, which
is exactly when the searches start. The cost of the old rationale is bounded to the ~6 weeks before the
year begins, and in those weeks a reader looking at next year is the reader we have. It changes once a
year, so it is generated once a year.

"""

import datetime as dt
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from app.engine.constants import sign_info

IST = ZoneInfo("Asia/Kolkata")

# The permanent slugs, in zodiac order - these are public URLs and must never change. They equal the
# engine's sign slugs (sign_info(i)["slug"]).
RASHI_SLUGS = ["mesha", "vrishabha", "mithuna", "karka", "simha", "kanya",
               "tula", "vrishchika", "dhanu", "makara", "kumbha", "meena"]
assert RASHI_SLUGS == [sign_info(i)["slug"] for i in range(12)]

PERIOD_SLUGS = ["today", "weekly", "monthly", "6-months", "yearly"]  # internal keys (also the English URL slugs)

#: The months that have a dated page, and the trees each one exists in. A dated month is written by
#: hand ahead of time and keeps its URL forever, which the rolling /masik cannot: that page is
#: whatever month it happens to be.
#:
#: THIS IS A DECLARATION, NOT A QUERY. The first version asked the store which languages a month had
#: been written in, and that made the published URL set depend on mutable state: two count tests
#: became order-dependent, and the hreflang reciprocity check compared a cached crawl against a live
#: lookup and found them disagreeing. A page's language family has to be the same answer every time
#: it is asked, in any process, before the database exists. So publishing a month is an edit here.
#:
#: Adding a month to this table is the act of releasing it, which is also what keeps thin pages
#: impossible: there is no registered URL for a month nobody has written.
#: EMPTY UNTIL A MONTH'S WHOLE BATCH EXISTS. Declaring 2027-01 with three of its twenty-four
#: readings written published twenty-one URLs with nothing on them and nothing linking them - the
#: orphan guard counted them all. A month is twelve rashis in each tree it is released in, and the
#: declaration is the last step of writing it, not the first.
#:
#: tests/test_rashifal_dated_months.py enforces that: every declared (month, tree) must have a
#: reading for all twelve rashis, so this table cannot run ahead of the content again.
DATED_MONTH_LANGS: dict[str, tuple[str, ...]] = {"2027-01": ("hi", "mr")}

#: Every dated month, as "YYYY-MM". A dated month is a FLAVOUR OF MONTHLY, not a sixth period - it
#: carries the same sixteen sections and goes through the same checks. What differs is only that its
#: window is one named calendar month instead of the one we are standing in.
DATED_MONTHS = tuple(DATED_MONTH_LANGS)

#: Every month a dated URL could name, written or not. `window_for` and the slug table accept these
#: so a page can be prepared and checked before it is declared above.
ALL_DATED_MONTHS = tuple(f"2027-{month:02d}" for month in range(1, 13))

#: Every period the STORE may hold. PERIOD_SLUGS alone is what `refresh()` generates, and a dated
#: month must stay out of it: adding twelve more would make the nightly job try to write 144 pages
#: it has no brief for and nobody asked for.
ALL_PERIODS = (*PERIOD_SLUGS, *ALL_DATED_MONTHS)

_RE_DATED_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def dated_month(period: str) -> tuple[int, int] | None:
    """(year, month) for a dated period, None for a rolling one."""
    found = _RE_DATED_MONTH.match(period or "")
    return (int(found.group(1)), int(found.group(2))) if found else None


def is_dated_month(period: str) -> bool:
    return dated_month(period) is not None


def base_period(period: str) -> str:
    """The KIND of page this period is. "2027-01" is a monthly page; everything else is itself.

    Every place that asks "how long is this reading, how many sections, what shape" wants this, and
    every place that asks "which window exactly" wants the period itself.
    """
    return "monthly" if is_dated_month(period) else period


_MONTHS_AHEAD = {"monthly": 1, "6-months": 6}   # yearly is a calendar year, see `window_for`
# Month and day the yearly page turns over to the next year. November, because "<sign> rashifal <next
# year>" searches start then; see the module docstring.
#
# MOVED FROM 20 TO 5 NOVEMBER, so the rolling page turns over on the day the dated 2027 pages go
# live. With the old date the two would have disagreed for a fortnight: /horoscope/mesha/2027 saying
# 2027 while /horoscope/mesha/yearly still said 2026, which is the site contradicting itself on the
# one question the reader came with. The searches start in early November anyway, which is the same
# reasoning that put this in November at all.
#
# THE SWITCH IS A DATE, NOT A PROMISE THAT THE CONTENT EXISTS. `window_for` only says which year the
# page is ABOUT; whether a reading for that year has been written for this rashi in this language is
# a separate question, and app/web/rashifal.py falls back per page rather than showing a 2027 title
# over a 2026 reading.
YEARLY_SWITCH = (11, 5)

# URL vocabulary per language tree, each taken from that language's own search terms rather than
# translated from English. The web layer owns the routes; these maps are
# the single source for slugs so the pages, the sitemap helper and the tests cannot drift apart.
URL_PREFIX = {"en": "/horoscope", "hi": "/hi/rashifal", "mr": "/mr/rashi-bhavishya"}
URL_PERIOD_SLUGS = {
    "en": {"today": "today", "weekly": "weekly", "monthly": "monthly", "6-months": "6-months", "yearly": "yearly"},
    "hi": {"today": "aaj", "weekly": "saptahik", "monthly": "masik", "6-months": "6-mahine", "yearly": "varshik"},
    "mr": {"today": "aaj", "weekly": "saptahik", "monthly": "masik", "6-months": "6-mahine", "yearly": "varshik"},
}

#: The dated monthly slugs, defined HERE because this module is the one the batch side may import -
#: app/web/i18n.py has its own copy of the rolling table so the two packages stay independent, and
#: it reuses this dict rather than building a second month-name list that could drift from it.
#:
#: The month name is English in all three trees: "dhanu rashifal january 2027" is how the query is
#: typed, and one spelling per month keeps the three trees' URLs parallel - which is what lets the
#: hreflang set be reciprocal without a per-language month table to keep in step.
_MONTH_SLUGS = ("january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december")
DATED_MONTH_SLUGS = {period: f"{_MONTH_SLUGS[int(period[5:7]) - 1]}-{period[:4]}"
                     for period in ALL_DATED_MONTHS}

#: A SEPARATE TABLE, deliberately. The first version updated URL_PERIOD_SLUGS in place and turned a
#: closed set of five rolling slugs per tree into seventeen - which broke every caller that iterates
#: it meaning "the periods this site has": the sitemap's URL count, the registry round-trip, and the
#: vocabulary test that asserts a Hindi tree reads aaj / saptahik / masik / 6-mahine / varshik and
#: is never date-stamped. That test is right: the rolling family and the dated family are different
#: things, and a dated URL is date-stamped on purpose.
#:
#: So anything that wants both asks for both. `period_slug` below is the one lookup that does.


def period_slug(language: str, period: str) -> str:
    """URL slug of a period in a tree, rolling or dated. KeyError for anything else."""
    if period in DATED_MONTH_SLUGS:
        return DATED_MONTH_SLUGS[period]
    return URL_PERIOD_SLUGS[language][period]

_EN_SIGNS = ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn",
             "aquarius", "pisces"]
_HI_RASHIS = ["mesh", "vrishabh", "mithun", "kark", "singh", "kanya", "tula", "vrishchik", "dhanu", "makar", "kumbh", "meen"]
URL_RASHI_SLUGS = {
    "en": dict(zip(RASHI_SLUGS, _EN_SIGNS)),
    "hi": dict(zip(RASHI_SLUGS, _HI_RASHIS)),  # the transliterations people type (keyword map §4)
    "mr": dict(zip(RASHI_SLUGS, _HI_RASHIS)),
}


def url_path(language: str, rashi: str | None = None, period: str | None = None) -> str:
    """Permanent path of a rashifal page in one language tree.

    url_path("hi", "tula", "today") -> /hi/rashifal/tula/aaj        url_path("en", "tula", "weekly") -> /horoscope/libra/weekly
    url_path("mr") -> /mr/rashi-bhavishya (daily hub)               url_path("hi", period="weekly") -> /hi/rashifal/saptahik (weekly hub)
    """
    path = URL_PREFIX[language]
    if rashi is not None:
        path += "/" + URL_RASHI_SLUGS[language][rashi]
    if period is not None and not (rashi is None and period == "today"):
        path += "/" + period_slug(language, period)
    return path


@dataclass(frozen=True)
class Window:
    period: str
    start: dt.datetime  # inclusive, IST
    end: dt.datetime  # exclusive, IST

    @property
    def start_date(self) -> dt.date:
        return self.start.date()

    @property
    def end_date(self) -> dt.date:
        """Last calendar day inside the window (what a reader calls the end)."""
        return (self.end - dt.timedelta(days=1)).date()

    @property
    def key(self) -> str:
        """Identifies the window in the store: same key = same period instance."""
        return self.start_date.isoformat()

    @property
    def year(self) -> int:
        """The calendar year this window is about - what the title prints for a yearly page."""
        return self.start_date.year

    @property
    def days(self) -> int:
        return (self.end.date() - self.start.date()).days


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def to_ist(moment: dt.datetime | None) -> dt.datetime:
    """None -> now. Naive datetimes are read as IST (same rule as the engine)."""
    if moment is None:
        return now_ist()
    if moment.tzinfo is None:
        return moment.replace(tzinfo=IST)
    return moment.astimezone(IST)


def _midnight(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(0, 0), tzinfo=IST)


def _add_months(day: dt.date, months: int) -> dt.date:
    index = day.year * 12 + (day.month - 1) + months
    return dt.date(index // 12, index % 12 + 1, 1)


def window_for(period: str, moment: dt.datetime | None = None) -> Window:
    # A DATED MONTH IGNORES `moment` ENTIRELY. That is the whole point of it: /masik is whatever
    # month it is now, and january-2027 is January 2027 in June and in the following December.
    if (named := dated_month(period)):
        year, month = named
        first = dt.date(year, month, 1)
        return Window(period, _midnight(first), _midnight(_add_months(first, 1)))
    if period not in PERIOD_SLUGS:
        raise ValueError(f"unknown period {period!r}; use one of {PERIOD_SLUGS}")
    today = to_ist(moment).date()
    if period == "today":
        return Window(period, _midnight(today), _midnight(today + dt.timedelta(days=1)))
    if period == "weekly":
        monday = today - dt.timedelta(days=today.weekday())
        return Window(period, _midnight(monday), _midnight(monday + dt.timedelta(days=7)))
    if period == "yearly":
        year = today.year + 1 if (today.month, today.day) >= YEARLY_SWITCH else today.year
        return Window(period, _midnight(dt.date(year, 1, 1)), _midnight(dt.date(year + 1, 1, 1)))
    first = today.replace(day=1)
    return Window(period, _midnight(first), _midnight(_add_months(first, _MONTHS_AHEAD[period])))


def rashi_index(slug: str) -> int:
    """1-12 for a rashi slug; ValueError for anything else (only the 12 exact slugs are URLs)."""
    try:
        return RASHI_SLUGS.index(slug) + 1
    except ValueError:
        raise ValueError(f"unknown rashi {slug!r}") from None
