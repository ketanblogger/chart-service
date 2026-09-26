"""Adapter between `engine.report_facts` and the flagship Kundali book.

The engine (calc-engine-2) computes every fact the book needs: navamsa, dignity, aspects, yogas, the
deterministic top-3/top-3 highlights, the gemstone table, dhaiya, and the complete dated timeline. The
two-layer rule means **nothing here does astronomy, and nothing here formats a date**.

Date formatting in particular is the engine's job and only the engine's (team-lead decision): the PDF
needs localised ranges in places where no AI prose exists at all - the Part G year table, running
headers, chapter headings - so one formatter is the only version of this that cannot drift across a
45-page book. Every range arrives as `{"start", "end", "label", "labels": {"en","hi","mr"}, ...}` and
this module passes `labels[language]` straight through, or an empty string if it is ever missing.

What this module actually does: group the engine's flat `windows` list back into the chapters of Part D
(past, current year, each near year, each far block), pick the window ids a given call may use, and say
which fact types the engine supplied for this chart.
"""

import datetime as dt

from app import engine

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# The life areas a window's prose may be tagged with. These are the keys platform's renderer knows.
# The engine's own vocabulary is finer (it also emits `travel`, `study` and `spiritual`); those stay in
# `data` for anyone who wants them, but the writer tags with these seven. `study` is deliberately not
# among them - for a reader it is not usefully distinct from `education`.
AREAS = ("career", "money", "marriage", "health", "education", "family", "property")


def label_of(engine_range: dict, language: str) -> str:
    """The engine's printed range in one language. Never formatted here - see the module docstring."""
    return (engine_range.get("labels") or {}).get(language) or ""


def report_facts(chart: dict, as_of: dt.date) -> dict:
    """`engine.report_facts` for this chart. Nothing is added; ids and labels come from the engine."""
    return engine.report_facts(chart, dt.datetime.combine(as_of, dt.time(12, 0), tzinfo=IST))


# ---- grouping --------------------------------------------------------------------------------------


def windows_of(timeline: dict, indexes) -> list:
    return [timeline["windows"][i] for i in indexes]


def current_year_windows(timeline: dict) -> list:
    return windows_of(timeline, timeline["current_year"]["window_indexes"])


def near_year_windows(timeline: dict) -> list:
    """[(year section, its windows)] - one chapter of Part D3 each."""
    return [(year, windows_of(timeline, year["window_indexes"])) for year in timeline.get("near_years", [])]


def far_block_windows(timeline: dict) -> list:
    """[(block section, its windows)] - one chapter of Part D4 each."""
    return [(block, windows_of(timeline, block["window_indexes"])) for block in timeline.get("far_blocks", [])]


def past_entries(timeline: dict) -> list:
    return timeline["past"]["entries"]


def every_window(timeline: dict) -> list:
    """Every window and past entry, in book order."""
    return list(past_entries(timeline)) + list(timeline.get("windows") or [])


def all_windows(timeline: dict) -> dict:
    """{id: window or past entry} - what book_report resolves the writer's `window_id` against."""
    return {window["id"]: window for window in every_window(timeline)}


# A Part E chapter is reference material, not a second timeline. Almost every window touches career or
# money somewhere down its ranking, so "mentions this area at all" selects the whole book and doubles
# the input tokens of two calls for nothing. Only windows where the area is among the strongest few
# count, and only the nearest handful of those - Part E is about what this area looks like, and Part D
# already carries the full chronology.
AREA_RANK = 3      # the area must be in a window's top three
AREA_WINDOWS = 8   # and only the nearest this many are sent


def windows_for_areas(timeline: dict, areas: set, rank: int = AREA_RANK,
                      limit: int = AREA_WINDOWS) -> list:
    """The windows where these life areas are genuinely prominent - what a Part E chapter draws on.

    Selection only: the engine already tagged each window with its areas and their weights.
    """
    chosen = []
    for window in timeline.get("windows") or []:
        ranked = sorted(window.get("areas") or [],
                        key=lambda row: (-row.get("weight", 0), row.get("area", "")))
        if {row.get("area") for row in ranked[:rank]} & areas:
            chosen.append(window)
    return chosen[:limit]


def window_areas(window: dict, limit: int = 4) -> list:
    """The strongest life areas this window lights up, restricted to the keys the writer may use.

    Reads `areas` only. The engine keeps a deprecated `pillars` alias purely because this module used
    to read it; depending on it again would keep it alive forever.
    """
    ranked = sorted((row for row in window.get("areas") or [] if row.get("area") in AREAS),
                    key=lambda row: (-row.get("weight", 0), row["area"]))
    return [row["area"] for row in ranked[:limit]]


# ---- what the book may assert ------------------------------------------------------------------------


def supplied(facts: dict) -> dict:
    """Which fact types the engine actually gave us for this chart. Drives both the book's chapter list
    (a chapter with no facts is not written) and the validator's `untraceable` check (a fact type the
    engine did not supply may not be asserted at all)."""
    return {
        "has_navamsa": bool(facts.get("navamsa")),
        "has_dignity": bool(facts.get("dignity")),
        "has_aspects": bool(facts.get("aspects")),
        "has_yogas": bool(facts.get("yogas")),
        "has_gemstone": bool((facts.get("gemstone") or {}).get("recommended")),
    }


def window_public(window: dict, language: str) -> dict:
    """The engine's own facts about one window, in the shape the report JSON publishes (docs/API.md).

    Works for a timeline window and for a past-strip entry alike. This is the half of a written window
    the AI never touches: `start` and `end` are the engine's ISO dates passed straight through, and
    `label` is the engine's own printed range. The model supplied only an id, a headline, prose and
    per-area lines.
    """
    engine_range = window["range"]
    dasha = window.get("dasha") or {}

    def lord(level):
        entry = dasha.get(level)
        return (entry or {}).get("lord") if isinstance(entry, dict) else None

    if dasha:
        lords = {level: lord(level) for level in ("mahadasha", "antardasha", "pratyantardasha")}
    else:  # a past-strip entry carries only the mahadasha it covers
        lords = {"mahadasha": window.get("mahadasha_lord"), "antardasha": None, "pratyantardasha": None}
    return {
        "window_id": window["id"],
        "start": engine_range["start"],
        "end": engine_range["end"],
        "label": label_of(engine_range, language),
        "dasha": lords,
        "transits": window.get("transits") or [],
        "saturn_phases": window.get("saturn_phases") or [],
        "houses_lit": window.get("houses_lit") or [],
    }
