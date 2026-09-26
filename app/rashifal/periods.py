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
_MONTHS_AHEAD = {"monthly": 1, "6-months": 6}   # yearly is a calendar year, see `window_for`
# Month and day the yearly page turns over to the next year. November, because "<sign> rashifal <next
# year>" searches start then; see the module docstring.
YEARLY_SWITCH = (11, 20)

# URL vocabulary per language tree, each taken from that language's own search terms rather than
# translated from English. The web layer owns the routes; these maps are
# the single source for slugs so the pages, the sitemap helper and the tests cannot drift apart.
URL_PREFIX = {"en": "/horoscope", "hi": "/hi/rashifal", "mr": "/mr/rashi-bhavishya"}
URL_PERIOD_SLUGS = {
    "en": {"today": "today", "weekly": "weekly", "monthly": "monthly", "6-months": "6-months", "yearly": "yearly"},
    "hi": {"today": "aaj", "weekly": "saptahik", "monthly": "masik", "6-months": "6-mahine", "yearly": "varshik"},
    "mr": {"today": "aaj", "weekly": "saptahik", "monthly": "masik", "6-months": "6-mahine", "yearly": "varshik"},
}
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
        path += "/" + URL_PERIOD_SLUGS[language][period]
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
