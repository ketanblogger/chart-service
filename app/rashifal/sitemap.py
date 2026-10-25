"""Sitemap data for Phase 8: the 180 permanent rashifal URLs (12 rashis x 5 periods x 3 language trees) + 6 hubs.

    from app.rashifal.sitemap import rashifal_sitemap_entries, rashifal_hub_entries

Each entry: {"loc", "lastmod", "changefreq", "language", "rashi", "period",
             "alternates": {"en": url, "hi": url, "mr": url, "x-default": url}}.
Every language version is its own `loc`; `alternates` are its hreflang siblings (`<xhtml:link rel="alternate"
hreflang=...>` in sitemap.xml; x-default = the English URL). `lastmod` is when the stored reading was generated,
or - while a page still shows engine facts only, or lacks that language - the start of its current window, which
is when those facts last changed. Paths come from app.rashifal.periods.url_path, the single source of URL slugs.
"""

import datetime as dt
import os

from . import config, store
from .periods import DATED_MONTHS, PERIOD_SLUGS, RASHI_SLUGS, base_period, to_ist, url_path, window_for

_CHANGEFREQ = {"today": "daily", "weekly": "weekly", "monthly": "monthly", "6-months": "monthly", "yearly": "monthly"}


def _base(base_url: str | None) -> str:
    # same rule as app.web.site.base_url(); not imported so the batch side never depends on the web package
    return (base_url or os.environ.get("BASE_URL", "http://localhost:8000")).rstrip("/")


def _utc(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _alternates(base: str, languages, rashi=None, period=None) -> dict:
    alternates = {code: base + url_path(code, rashi, period) for code in languages}
    alternates["x-default"] = alternates["en"]
    return alternates


def rashifal_sitemap_entries(base_url: str | None = None, moment: dt.datetime | None = None) -> list[dict]:
    """len(languages) x 60 entries, in (language, rashi, period) order. Reads the store; never calls the AI."""
    base, now, stored, languages = _base(base_url), to_ist(moment), store.list_pages(), config.languages()
    entries = []
    # THE ROLLING PERIODS ALWAYS, THE DATED MONTHS ONLY ONCE WRITTEN. A rolling URL answers every
    # day whether or not anybody has written to it - the engine's tables are there - so it belongs
    # in the sitemap from the start. january-2027 with no reading on it is a thin page, and asking
    # Google to crawl twelve of those per rashi is asking to be judged on them.
    dated = [period for period in DATED_MONTHS if any((r, period) in stored for r in RASHI_SLUGS)]
    for code in languages:
        for rashi in RASHI_SLUGS:
            for period in (*PERIOD_SLUGS, *dated):
                if period in DATED_MONTHS and (rashi, period) not in stored:
                    continue
                row = stored.get((rashi, period))
                written = row is not None and code in row["languages"]
                entries.append({
                    "loc": base + url_path(code, rashi, period),
                    "lastmod": row["generated_at"] if written else _utc(window_for(period, now).start),
                    "changefreq": _CHANGEFREQ[base_period(period)], "language": code, "rashi": rashi, "period": period,
                    "alternates": _alternates(base, languages, rashi, period),
                })
    return entries


def rashifal_hub_entries(base_url: str | None = None, moment: dt.datetime | None = None) -> list[dict]:
    """The daily and weekly hub of each language tree (all 12 rashis on one page)."""
    base, now, languages = _base(base_url), to_ist(moment), config.languages()
    entries = []
    for code in languages:
        for period in ("today", "weekly"):
            rows = store.hub_rows(period).values()
            newest = max((row["generated_at"] for row in rows if code in row["languages"]), default=None)
            entries.append({
                "loc": base + url_path(code, period=period), "lastmod": newest or _utc(window_for(period, now).start),
                "changefreq": "daily" if period == "today" else "weekly", "language": code, "rashi": None, "period": period,
                "alternates": _alternates(base, languages, None, period),
            })
    return entries
