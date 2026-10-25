"""The life timeline the paid report is written against: the dated windows its life-timeline
chapters are built from, and the feed for its year-by-year table.

The AI never works out a date, an age or a house. This module hands it a list of windows; each window
is a REAL calendar date-range carrying everything that is active inside it.

THE STRIP IS EXACTLY CONTIGUOUS. One boundary, `today_boundary` = the 1st of the month containing
`as_of`, separates past from future:

    D1 past        birth -> today_boundary      one entry per MAHADASHA change only (compact)
    D2 current     today_boundary -> a 1 Jan    split by antardasha AND pratyantardasha boundaries
                                                merged with month-level transit events
    D3 near        4 calendar years             each year split into 2-4 ranges at antardasha shifts
    D4 far         5-year blocks                each block still carries dated sub-ranges

D2 runs to the next 1 January, unless that is less than `current_year_min_months` away, in which case
it runs to the one after (a report bought on 20 December must not get an 11-day "current year").
Everything after D2 is whole calendar years, which is what makes the year-by-year table line up.

WINDOW COUNT IS CHART-DRIVEN: the book runs as long as the chart demands and no longer, so it is
never padded to a page count nor cut to save one. A chart in a Rahu mahadasha with
many short pratyantardashas and several ingresses produces more windows than a quiet one. The knobs
in `KNOBS` bound the work (and therefore the AI cost) but are deliberately loose; pass `knobs=` to
tighten them without touching this file.

DATE RANGES are emitted in ONE canonical form everywhere in this module, `date_range()`:
    {"start": "2026-09-01", "end": "2026-12-20", "label": "Sep 2026 - Dec 2026",
     "start_ym": "2026-09", "end_ym": "2026-12", "days": 110}
`start` is inclusive, `end` is EXCLUSIVE, and `label`/`end_ym` name the last month actually covered.
Never an age band, never a decade.

EVERY GRAHA MENTIONED CARRIES BOTH HOUSE COUNTS. `house_from_lagna` and `house_from_moon` are always
both present and always named - there is no bare `house` key anywhere in this module's output, so a
from-the-Moon house can never be written up as "your Nth house".
"""

from datetime import date, datetime, time, timedelta, timezone, tzinfo

from .aspects import chart_graha_signs
from .constants import GRAHA_KEYS, LANGUAGES, MONTHS, graha_name
from .core import DEFAULT_TZ, as_utc, house_from, parse_tz
from .dasha import (
    YEAR_DAYS,
    antardashas_between,
    boundaries_between,
    cycle_start,
    cycles_needed,
    dasha_tree,
    running_dasha,
)
from .sadesati import saturn_stays
from .transits import transit_events

KNOBS = {
    # D2 - the current year
    "current_year_min_months": 6,       # extend into the next calendar year if less remains than this
    "current_year_max_windows": 24,     # ~monthly at most; raise for a denser book, lower to cut AI cost
    "current_year_min_window_days": 20,
    # D3 - the near years
    "near_years": 4,
    "near_min_ranges_per_year": 2,      # the book's rule: 2-4 date-ranges within a year
    "near_max_ranges_per_year": 4,
    "near_max_window_days": 200,        # a year with no antardasha shift is still split, never left whole
    # D4 - beyond
    "far_blocks": 4,
    "far_block_years": 5,
    "far_max_ranges_per_block": 6,
    "far_min_window_days": 150,
    "far_max_window_days": 730,         # "beyond" stays dated: no sub-range longer than two years
    # which transits are attached at which depth
    "current_year_ingress_grahas": ("Sun", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu"),
    "current_year_station_grahas": ("Mercury", "Venus", "Mars", "Jupiter", "Saturn"),
    "far_grahas": ("Jupiter", "Saturn", "Rahu", "Ketu"),
}

DATE_RANGE_FORMAT = ('{"start": ISO date (inclusive), "end": ISO date (EXCLUSIVE), '
                     '"label": "Mon YYYY \u2013 Mon YYYY" naming the first and last month covered, '
                     '"start_ym"/"end_ym": "YYYY-MM", "days": int}')

_DASH = " \u2013 "  # en dash WITH spaces: the one canonical separator every printed range uses
DAY_PRECISION_DAYS = 45  # shorter than this and the label names days, not months - see date_range()

# Priorities for boundary merging: lower survives longer.
P_MAHADASHA, P_ANTARDASHA, P_PRATYANTARDASHA, P_SATURN, P_TRANSIT = 0, 1, 2, 3, 4

HOUSE_AREAS = {
    1: ("self", "vitality", "personality"),
    2: ("money", "family", "speech", "savings"),
    3: ("courage", "siblings", "communication", "short travel"),
    4: ("home", "mother", "property", "vehicle", "peace of mind"),
    5: ("education", "children", "creativity", "romance"),
    6: ("daily work", "competition", "debts", "routine health"),
    7: ("marriage", "partnership", "business partner"),
    8: ("change", "inheritance", "research", "the unexpected"),
    9: ("fortune", "father", "dharma", "long travel", "higher study"),
    10: ("career", "status", "public standing"),
    11: ("gains", "income", "network", "elder siblings"),
    12: ("expenses", "foreign matters", "spirituality", "rest"),
}
# THE life-area vocabulary for the whole book: the key set the AI writes per area and the PDF lays
# out, and the same keys the life-area deep dives use. A window claims an area only when one of that
# area's houses is actually lit by the window's dasha lords or transits - an area with nothing behind
# it is omitted rather than emitted empty.
#
# The house behind each area, so a reader can check the claim:
#   career     10 karma / profession, 6 daily work and service
#   money       2 accumulated wealth, 11 gains and income
#   marriage    7 spouse and partnership
#   family      2 kutumba (the household), 4 home and mother
#   health      1 body and vitality, 6 ailments and routine, 8 chronic matters
#   education   4 formal schooling, 5 intellect and exams
#   property    4 land, house and vehicle
#   travel      3 short journeys, 9 long journeys, 12 foreign lands
#   study       5 learning, 9 higher study and research
#   spiritual   9 dharma, 12 moksha and retreat
# education vs study: education is schooling and exams, study is higher and self-directed learning.
# They share the 5th, which is why a chart can light both.
AREAS = {
    "career": (10, 6),
    "money": (2, 11),
    "marriage": (7,),
    "family": (2, 4),
    "health": (1, 6, 8),
    "education": (4, 5),
    "property": (4,),
    "travel": (3, 9, 12),
    "study": (5, 9),
    "spiritual": (9, 12),
}
# DEPRECATED alias for the old six-key "pillars" vocabulary. `app/ai/engine_facts.py` imports this
# name and `app/ai/compact.py` reads a `pillars` key off windows, highlight factors and year rows, so
# both are still emitted alongside `areas` - with the old inner key `pillar` - until ai-layer moves
# over. Note the vocabulary itself changed: the old `family_property` is now `family` and `property`
# separately, and `travel`, `study` and `spiritual` are new.
PILLARS = AREAS


# --- the canonical date range --------------------------------------------------------------------

def format_range(start: date, last: date, language: str, precision: str) -> str:
    """The printed range for one language. `last` is the last day COVERED, not the exclusive end.

    Month precision: "Jan 2026" for a range inside one month, "Jan 2026 - Mar 2026" otherwise.
    Day precision:   "3 Oct 2026", "3 - 26 Oct 2026", "3 Oct - 14 Nov 2026",
                     "20 Dec 2026 - 14 Jan 2027" - the shortest form that is still unambiguous.
    Years and days are Latin digits in all three languages; the separator is an en dash with spaces.
    """
    months = MONTHS[language]
    if precision == "month":
        first = f"{months[start.month - 1]} {start.year}"
        final = f"{months[last.month - 1]} {last.year}"
        return first if first == final else f"{first}{_DASH}{final}"
    if start == last:
        return f"{start.day} {months[start.month - 1]} {start.year}"
    if (start.year, start.month) == (last.year, last.month):
        return f"{start.day}{_DASH}{last.day} {months[last.month - 1]} {last.year}"
    if start.year == last.year:
        return (f"{start.day} {months[start.month - 1]}{_DASH}"
                f"{last.day} {months[last.month - 1]} {last.year}")
    return (f"{start.day} {months[start.month - 1]} {start.year}{_DASH}"
            f"{last.day} {months[last.month - 1]} {last.year}")


def date_range(start: date, end: date) -> dict:
    """THE date-range shape used across the whole report, in every language.

    INTERVAL CONVENTION, stated once and true everywhere in this engine: the range is HALF-OPEN.
    `start` is included, `end` is EXCLUSIVE and is the same day the next window begins. The printed
    labels name the last day actually covered (`end` minus one day), and `end_ym` likewise names the
    last month actually covered - so a window ending 2026-10-01 is labelled "... Sep 2026", never
    "... Oct 2026". Consecutive windows therefore satisfy `a["end"] == b["start"]` exactly.

    `label` is the English string (unchanged since the first contract). `labels` carries all three
    languages; the engine owns this formatting so the same range is byte-identical in the book, the
    tables and anywhere else it appears. The AI never writes a date - it names a window id and the
    renderer prints `labels[language]`.

    `precision` is "day" for ranges shorter than DAY_PRECISION_DAYS (45), and "month" otherwise or
    whenever the range covers whole calendar months exactly. A three-week pratyantardasha window
    printed as "Oct 2026" would be both wrong and, next to its neighbour, ambiguous; at 45 days and
    up the month form the book prints is exact enough. One consequence worth relying on: no two windows
    of one timeline ever carry the same label, because two consecutive windows can only collide when
    one of them sits inside a single month, and that one takes day precision.
    """
    if end <= start:
        raise ValueError(f"end {end} must be after start {start}")
    last = end - timedelta(days=1)
    # Month precision for anything at least DAY_PRECISION_DAYS long, and for a range that covers
    # whole calendar months exactly (starts on a 1st, ends on a 1st) however short it is - a window
    # that is precisely January should read "Jan 2026", not "1 - 31 Jan 2026".
    whole_months = start.day == 1 and end.day == 1
    precision = "month" if whole_months or (end - start).days >= DAY_PRECISION_DAYS else "day"
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": format_range(start, last, "en", precision),
        "labels": {language: format_range(start, last, language, precision) for language in LANGUAGES},
        "precision": precision,
        "start_ym": f"{start.year:04d}-{start.month:02d}",
        "end_ym": f"{last.year:04d}-{last.month:02d}",
        "days": (end - start).days,
    }


def _utc(day: date, zone: tzinfo) -> datetime:
    return datetime.combine(day, time(0, 0), tzinfo=zone).astimezone(timezone.utc)


def window_id(start: date) -> str:
    """The handle the AI uses to name a window: "w-2026-10-03", the window's own start date.

    Unique because the windows are contiguous (no two start on the same day), stable for a given
    chart and `as_of`, and SELF-CHECKING: `id == "w-" + range["start"]` always, so a made-up id is
    almost never a real one and a mismatched id is caught by comparing it against the window it was
    attached to. That is what a bare index cannot do - an off-by-one there silently attaches text to
    the wrong period, which in a paid report means a wrong prediction against a wrong date.
    """
    return f"w-{start.isoformat()}"


def past_id(start: date) -> str:
    """Same idea for the D1 past strip, which the AI also writes one line per entry for."""
    return f"p-{start.isoformat()}"


# --- boundary merging ----------------------------------------------------------------------------

def _collect(items, start: date, end: date) -> dict[date, tuple[int, list[str]]]:
    """(date, priority, reason) -> {date: (best priority, all reasons)}, inside (start, end) only."""
    out: dict[date, tuple[int, list[str]]] = {}
    for when, priority, reason in items:
        if not start < when < end:
            continue
        if when in out:
            best, reasons = out[when]
            if reason not in reasons:
                reasons.append(reason)
            out[when] = (min(best, priority), reasons)
        else:
            out[when] = (priority, [reason])
    return out


def _edges(start: date, end: date, chosen: dict) -> list[date]:
    return [start, *sorted(chosen), end]


def _merged_days(edges: list[date], when: date) -> int:
    i = edges.index(when)
    return (edges[i + 1] - edges[i - 1]).days


def _drop_one(start: date, end: date, chosen: dict) -> bool:
    """Remove the least important boundary. Never removes a mahadasha boundary. False when none left."""
    droppable = [w for w, (p, _) in chosen.items() if p > P_MAHADASHA]
    if not droppable:
        return False
    edges = _edges(start, end, chosen)
    worst = max(chosen[w][0] for w in droppable)
    victim = min((w for w in droppable if chosen[w][0] == worst),
                 key=lambda w: (_merged_days(edges, w), w))
    del chosen[victim]
    return True


def _enforce_min_days(start: date, end: date, chosen: dict, min_days: int) -> None:
    """Merge away windows shorter than `min_days`, by dropping ONE of the two boundaries that bound
    the short window - never some unrelated boundary elsewhere in the section. A short window whose
    both edges are mahadasha boundaries (or the section's own edges) is left alone: that is a real
    period of the chart, not padding, and dropping other boundaries would not fix it.
    """
    while True:
        edges = _edges(start, end, chosen)
        lengths = [(edges[i + 1] - edges[i]).days for i in range(len(edges) - 1)]
        acted = False
        for i in sorted(range(len(lengths)), key=lambda k: (lengths[k], k)):
            if lengths[i] >= min_days:
                break
            candidates = [w for w in (edges[i], edges[i + 1])
                          if w in chosen and chosen[w][0] > P_MAHADASHA]
            if not candidates:
                continue
            victim = max(candidates, key=lambda w: (chosen[w][0], -_merged_days(edges, w), w))
            del chosen[victim]
            acted = True
            break
        if not acted:
            return


def _add_one(start: date, end: date, chosen: dict, pool: dict, min_days: int = 0) -> bool:
    """Take from `pool` the boundary that splits the longest current segment most evenly.
    With `min_days`, a boundary that would create a window shorter than that is not taken."""
    if not pool:
        return False
    edges = _edges(start, end, chosen)
    best, best_key = None, None
    for when in pool:
        i = next(k for k in range(len(edges) - 1) if edges[k] <= when < edges[k + 1])
        left, right = (when - edges[i]).days, (edges[i + 1] - when).days
        if min_days and min(left, right) < min_days:
            continue
        key = (-(left + right), -min(left, right), when)
        if best_key is None or key < best_key:
            best, best_key = when, key
    if best is None:
        return False
    chosen[best] = pool.pop(best)
    return True


def _segments(start: date, end: date, chosen: dict) -> list[int]:
    edges = _edges(start, end, chosen)
    return [(b - a).days for a, b in zip(edges, edges[1:])]


def _split(start: date, end: date, pool, extra=(), *, min_count: int = 1,
           max_count: int | None = None, min_days: int = 0,
           max_days: int | None = None) -> list[tuple[date, date, list[str]]]:
    """Contiguous, non-overlapping, sorted (window_start, window_end, reasons-for-this-start).

    `pool` is the preferred boundary set, `extra` a fallback drawn on to reach `min_count` and to
    break up any window longer than `max_days` (each addition splits the longest window most evenly).
    Boundaries are dropped least-important-first to satisfy `max_count` and `min_days`; a mahadasha
    boundary is never dropped, so a window can exceed `max_count` or undercut `min_days` only when
    mahadasha changes alone force it - which is a real fact about the chart, not padding.

    Order of operations, fixed so the result is deterministic: grow to `min_count`, shrink to
    `max_count`, merge away windows under `min_days`, then grow again to break windows over
    `max_days` (respecting both `max_count` and `min_days`).
    """
    chosen = _collect(pool, start, end)
    spare = {w: v for w, v in _collect(extra, start, end).items() if w not in chosen}

    while len(chosen) + 1 < min_count and _add_one(start, end, chosen, spare):
        pass
    while max_count is not None and len(chosen) + 1 > max_count and _drop_one(start, end, chosen):
        pass
    if min_days:
        _enforce_min_days(start, end, chosen, min_days)
    while (max_days and max(_segments(start, end, chosen)) > max_days
           and (max_count is None or len(chosen) + 1 < max_count)
           and _add_one(start, end, chosen, spare, min_days)):
        pass

    edges = _edges(start, end, chosen)
    return [(a, b, chosen.get(a, (None, ["section start"]))[1]) for a, b in zip(edges, edges[1:])]


# --- static per-chart facts -----------------------------------------------------------------------

def graha_facts(chart: dict, dignities: dict, navamsa: dict) -> dict:
    """Per graha, the natal facts a window repeats. Both house counts, always named."""
    moon_sign = chart["grahas"]["Moon"]["sign"]["index"]
    signs = chart_graha_signs(chart)
    facts = {}
    for key in GRAHA_KEYS:
        position = chart["grahas"][key]
        facts[key] = {
            **graha_name(key),
            "natal_sign": position["sign"],
            "house_from_lagna": position["house"],
            "house_from_moon": house_from(moon_sign, signs[key]),
            "rules_houses_from_lagna": dignities[key]["rules_houses"],
            "dignity": dignities[key]["dignity"]["label"],
            "combust": dignities[key]["combustion"]["combust"],
            "retrograde": position["retrograde"],
            "nakshatra": position["nakshatra"]["name"],
            "navamsa_sign": navamsa["grahas"][key]["sign"],
            "house_from_navamsa_lagna": navamsa["grahas"][key]["house"],
        }
    return facts


def _areas(houses) -> list[str]:
    seen = []
    for house in sorted(set(houses)):
        for area in HOUSE_AREAS[house]:
            if area not in seen:
                seen.append(area)
    return seen


def areas_for(houses) -> list[dict]:
    """The life areas these houses light up. An area with no house behind it is omitted, never
    emitted empty. Sorted by how many of its houses are lit, then by name, so the order is total."""
    houses = set(houses)
    out = [{"area": area, "houses": sorted(houses & set(area_houses)), "weight": len(houses & set(area_houses))}
           for area, area_houses in AREAS.items() if houses & set(area_houses)]
    out.sort(key=lambda a: (-a["weight"], a["area"]))
    return out


def _deprecated_pillars(areas: list[dict]) -> list[dict]:
    """`areas` under its old key name. Remove once app/ai has migrated."""
    return [{"pillar": a["area"], "houses": a["houses"], "weight": a["weight"]} for a in areas]


# --- transits -------------------------------------------------------------------------------------

def _transit_rows(events, lagna_sign: int, moon_sign: int, facts: dict) -> list[dict]:
    rows = []
    for event in events:
        key = event["graha"]["key"]
        sign = event["to_sign"] if event["type"] == "ingress" else event["sign"]
        rows.append({
            "date": event["datetime"][:10],
            "graha": event["graha"],
            "event": ("enters" if event["type"] == "ingress" else f"turns {event['direction']} in"),
            "retrograde_entry": bool(event.get("retrograde")) if event["type"] == "ingress" else None,
            "sign": sign,
            "house_from_lagna": house_from(lagna_sign, sign["index"]),
            "house_from_moon": house_from(moon_sign, sign["index"]),
            "natal_house_from_lagna": facts[key]["house_from_lagna"],
            "natal_house_from_moon": facts[key]["house_from_moon"],
            "rules_houses_from_lagna": facts[key]["rules_houses_from_lagna"],
        })
    return rows


def _events_in(rows, start: date, end: date) -> list[dict]:
    return [row for row in rows if start.isoformat() <= row["date"] < end.isoformat()]


def _stays_in(stays, start: date, end: date) -> list[dict]:
    return [{**stay, "range": date_range(date.fromisoformat(stay["start"]), date.fromisoformat(stay["end"]))}
            for stay in stays
            if stay["start"] < end.isoformat() and stay["end"] > start.isoformat()]


# --- windows ---------------------------------------------------------------------------------------

class _Builder:
    def __init__(self, chart: dict, dignities: dict, navamsa: dict, as_of_utc: datetime, knobs: dict):
        self.chart = chart
        self.knobs = knobs
        self.zone = parse_tz(chart["input"]["timezone"] or DEFAULT_TZ)
        self.birth_utc = datetime.fromisoformat(chart["input"]["datetime_utc"])
        self.birth_date = self.birth_utc.astimezone(self.zone).date()
        self.moon_longitude = chart["grahas"]["Moon"]["longitude"]
        self.moon_sign = chart["grahas"]["Moon"]["sign"]["index"]
        self.lagna_sign = chart["lagna"]["sign"]["index"]
        self.facts = graha_facts(chart, dignities, navamsa)
        self.as_of = as_of_utc.astimezone(self.zone).date()
        self.today_boundary = self.as_of.replace(day=1)
        self.cycle_end = (cycle_start(self.moon_longitude, self.birth_utc)
                          + timedelta(days=120 * YEAR_DAYS)).astimezone(self.zone).date()
        self.transit_rows: list[dict] = []
        self.stays: list[dict] = []

    # -- helpers
    def utc(self, day: date) -> datetime:
        return _utc(day, self.zone)

    def dasha_boundaries(self, start: date, end: date, levels: int = 3):
        priority = {0: P_MAHADASHA, 1: P_ANTARDASHA, 2: P_PRATYANTARDASHA}
        return [(when, priority[level], f"{('mahadasha', 'antardasha', 'pratyantardasha')[level]} of {lord} begins")
                for when, level, lord in boundaries_between(self.moon_longitude, self.birth_utc, self.zone,
                                                            self.utc(start), self.utc(end), levels)]

    def transit_boundaries(self, start: date, end: date):
        return [(date.fromisoformat(row["date"]), P_TRANSIT,
                 f"{row['graha']['name']} {row['event']} {row['sign']['name']}")
                for row in _events_in(self.transit_rows, start, end)]

    def saturn_boundaries(self, start: date, end: date):
        out = []
        for stay in self.stays:
            when = date.fromisoformat(stay["start"])
            if start < when < end:
                label = stay["phase_label"] or f"Shani enters {stay['sign']['name']}"
                out.append((when, P_SATURN, label))
        return out

    # -- payload
    def window(self, start: date, end: date, reasons, *, with_pratyantardasha: bool, transits: bool) -> dict:
        # by_local_date: the window starts on a printed date, so its dasha must be the one the
        # reader will see against that date - see dasha.running_dasha.
        running = running_dasha(self.moon_longitude, self.birth_utc, self.zone, self.utc(start),
                                by_local_date=True)
        periods = antardashas_between(self.moon_longitude, self.birth_utc, self.zone,
                                      self.utc(start), self.utc(end))
        lords = []
        for lord in ([running["mahadasha"]["lord"]["key"], running["antardasha"]["lord"]["key"]]
                     + ([running["pratyantardasha"]["lord"]["key"]] if with_pratyantardasha else [])):
            if lord not in lords:
                lords.append(lord)

        houses = set()
        for lord in lords:
            houses.add(self.facts[lord]["house_from_lagna"])
            houses.update(self.facts[lord]["rules_houses_from_lagna"])

        events = _events_in(self.transit_rows, start, end) if transits else []
        for row in events:
            houses.add(row["house_from_lagna"])

        dasha = {
            "mahadasha": running["mahadasha"],
            "antardasha": running["antardasha"],
            "pratyantardasha": running["pratyantardasha"] if with_pratyantardasha else None,
            "antardashas_in_window": [
                {"mahadasha_lord": p["mahadasha"]["lord"], "antardasha_lord": p["antardasha"]["lord"],
                 "range": date_range(max(start, date.fromisoformat(p["antardasha"]["start"])),
                                     min(end, date.fromisoformat(p["antardasha"]["end"])))}
                for p in periods
                if max(start, date.fromisoformat(p["antardasha"]["start"]))
                < min(end, date.fromisoformat(p["antardasha"]["end"]))
            ],
        }
        return {
            "id": window_id(start),
            "range": date_range(start, end),
            "why_it_starts_here": reasons,
            "dasha": dasha,
            "active_lords": [self.facts[lord] for lord in lords],
            "transits": events,
            "saturn_phases": _stays_in(self.stays, start, end),
            "houses_lit": sorted(houses),
            "life_areas": _areas(houses),
            "areas": areas_for(houses),
            "pillars": _deprecated_pillars(areas_for(houses)),
        }


def build_timeline(chart: dict, dignities: dict, navamsa: dict,
                   as_of: datetime | None = None, knobs: dict | None = None) -> dict:
    """The complete window list for the report. See the module docstring for the section layout."""
    settings = {**KNOBS, **(knobs or {})}
    builder = _Builder(chart, dignities, navamsa, as_utc(as_of), settings)

    # section boundaries
    d2_start = builder.today_boundary
    d2_end = date(d2_start.year + 1, 1, 1)
    if (d2_end - d2_start).days < settings["current_year_min_months"] * 30:
        d2_end = date(d2_start.year + 2, 1, 1)
    d3_end = date(d2_end.year + settings["near_years"], 1, 1)
    # Not clamped to the 120-year cycle: the Vimshottari sequence repeats rather than stopping, and
    # truncating the strip there would leave a chart that outlived one round with no timeline at all.
    # `coverage.dasha_cycle_ends` still reports where the first round ended.
    d4_end = date(d3_end.year + settings["far_blocks"] * settings["far_block_years"], 1, 1)

    # transits, scanned once for the whole strip
    builder.transit_rows = _scan_transits(builder, d2_start, d2_end, d3_end, d4_end, settings)
    builder.stays = saturn_stays(builder.moon_sign, builder.utc(d2_start), builder.utc(max(d4_end, d3_end)),
                                 chart["input"]["timezone"] or DEFAULT_TZ)

    past = _past(builder)
    current_year = _section(builder, d2_start, d2_end, kind="current_year")
    near = [_section(builder, date(year, 1, 1), date(year + 1, 1, 1), kind="near")
            for year in range(d2_end.year, d3_end.year)]
    far = []
    block_start = d3_end
    while block_start < d4_end:
        block_end = min(date(block_start.year + settings["far_block_years"], 1, 1), d4_end)
        if block_end <= block_start:
            break
        far.append(_section(builder, block_start, block_end, kind="far"))
        block_start = block_end

    flat = []
    for section in [current_year, *near, *far]:
        first = len(flat)
        for window in section.pop("windows"):
            flat.append({"section": section["section"], **window})
        section["window_indexes"] = list(range(first, len(flat)))
        section["window_ids"] = [w["id"] for w in flat[first:]]

    return {
        "as_of": builder.as_of.isoformat(),
        "today_boundary": builder.today_boundary.isoformat(),
        "date_range_format": DATE_RANGE_FORMAT,
        "interval": ("Half-open: `start` is included, `end` is EXCLUSIVE and is the same day the next "
                     "window begins, so windows[i].end == windows[i+1].start. Labels name the last day "
                     "actually covered (end minus one day)."),
        "languages": list(LANGUAGES),
        "house_convention": ("house_from_lagna is counted from the lagna sign; house_from_moon from the "
                             "Moon sign; house_from_navamsa_lagna from the navamsa lagna. Never mix them."),
        "knobs": {k: list(v) if isinstance(v, tuple) else v for k, v in settings.items()},
        "coverage": {
            "past": date_range(builder.birth_date, d2_start),
            "current_year": date_range(d2_start, d2_end),
            "near_years": date_range(d2_end, d3_end),
            "far_years": date_range(d3_end, d4_end) if d4_end > d3_end else None,
            "dasha_cycle_ends": builder.cycle_end.isoformat(),
            "dasha_cycles_used": cycles_needed(builder.moon_longitude, builder.birth_utc,
                                               builder.utc(d4_end)),
        },
        "past": past,
        "current_year": current_year,
        "near_years": near,
        "far_blocks": far,
        # THE list the report is written against: flat, sorted, contiguous from `current_year.start`
        # to the end of the last far block. The sections above index into it via `window_indexes`
        # rather than repeating the objects.
        "windows": flat,
        "window_count": len(flat),
        "year_table": _year_table(builder, d2_start, d3_end),
    }


def _scan_transits(builder: _Builder, d2_start: date, d2_end: date, d3_end: date, d4_end: date,
                   settings: dict) -> list[dict]:
    """Current year: the grahas a month-level read needs. Beyond it: the slow grahas only."""
    wanted = set(settings["current_year_ingress_grahas"]) | set(settings["current_year_station_grahas"])
    events = transit_events(builder.utc(d2_start), builder.utc(d2_end), include_moon=False,
                            tz=builder.chart["input"]["timezone"] or DEFAULT_TZ, grahas=sorted(wanted))
    far_end = max(d3_end, d4_end)
    if far_end > d2_end:
        events += transit_events(builder.utc(d2_end), builder.utc(far_end), include_moon=False,
                                 tz=builder.chart["input"]["timezone"] or DEFAULT_TZ,
                                 grahas=list(settings["far_grahas"]))
    keep = []
    for event in events:
        key = event["graha"]["key"]
        if event["type"] == "ingress" and key not in settings["current_year_ingress_grahas"] \
                and key not in settings["far_grahas"]:
            continue
        if event["type"] == "station" and key not in settings["current_year_station_grahas"]:
            continue
        keep.append(event)
    keep.sort(key=lambda e: e["datetime_utc"])
    return _transit_rows(keep, builder.lagna_sign, builder.moon_sign, builder.facts)


def _past(builder: _Builder) -> dict:
    """D1: one compact entry per mahadasha between birth and today. No transits, no sub-periods."""
    entries = []
    cycles = cycles_needed(builder.moon_longitude, builder.birth_utc,
                           builder.utc(builder.today_boundary))
    for node in dasha_tree(builder.moon_longitude, builder.birth_utc, levels=1, cycles=cycles):
        start = max(node["start"].astimezone(builder.zone).date(), builder.birth_date)
        end = min(node["end"].astimezone(builder.zone).date(), builder.today_boundary)
        if end <= start:
            continue
        lord = node["lord"]
        entries.append({
            "id": past_id(start),
            "range": date_range(start, end),
            "mahadasha_lord": graha_name(lord),
            "dasha_cycle": node["cycle"],
            "full_mahadasha": date_range(node["start"].astimezone(builder.zone).date(),
                                         node["end"].astimezone(builder.zone).date()),
            "partial": (node["start"].astimezone(builder.zone).date() < builder.birth_date
                        or node["end"].astimezone(builder.zone).date() > builder.today_boundary),
            "age_years": [_age(builder.birth_date, start), _age(builder.birth_date, end)],
            "lord_facts": builder.facts[lord],
            "houses_lit": sorted({builder.facts[lord]["house_from_lagna"],
                                  *builder.facts[lord]["rules_houses_from_lagna"]}),
        })
    return {
        "section": "past",
        "detail": "mahadasha changes only - context and credibility, not a reading",
        "range": date_range(builder.birth_date, builder.today_boundary),
        "entries": entries,
    }


def _age(birth: date, when: date) -> int:
    return when.year - birth.year - ((when.month, when.day) < (birth.month, birth.day))


def _section(builder: _Builder, start: date, end: date, kind: str) -> dict:
    settings = builder.knobs
    if kind == "current_year":
        pool = (builder.dasha_boundaries(start, end, levels=3)
                + builder.saturn_boundaries(start, end)
                + builder.transit_boundaries(start, end))
        pieces = _split(start, end, pool, min_count=1,
                        max_count=settings["current_year_max_windows"],
                        min_days=settings["current_year_min_window_days"])
        with_praty, transits = True, True
    elif kind == "near":
        pool = (builder.dasha_boundaries(start, end, levels=2)
                + builder.saturn_boundaries(start, end))
        extra = builder.dasha_boundaries(start, end, levels=3)
        pieces = _split(start, end, pool, extra,
                        min_count=settings["near_min_ranges_per_year"],
                        max_count=settings["near_max_ranges_per_year"],
                        max_days=settings["near_max_window_days"])
        with_praty, transits = False, True
    else:
        pool = (builder.dasha_boundaries(start, end, levels=2)
                + builder.saturn_boundaries(start, end))
        extra = builder.dasha_boundaries(start, end, levels=3)
        pieces = _split(start, end, pool, extra,
                        max_count=settings["far_max_ranges_per_block"],
                        min_days=settings["far_min_window_days"],
                        max_days=settings["far_max_window_days"])
        with_praty, transits = False, True

    windows = [builder.window(a, b, reasons, with_pratyantardasha=with_praty, transits=transits)
               for a, b, reasons in pieces]
    return {
        # Unique per section, so a flat window can always be traced back to its block.
        "section": kind if kind == "current_year" else f"{kind}_{start.year}",
        "kind": kind,
        "range": date_range(start, end),
        "year": start.year if kind in ("near", "current_year") else None,
        "windows": windows,
    }


def _year_table(builder: _Builder, start: date, end: date) -> list[dict]:
    """The year-by-year table feed: one row per calendar year covered by D2 + D3, with its dashas
    and transits."""
    rows = []
    for year in range(start.year, end.year):
        year_start = max(start, date(year, 1, 1))
        year_end = min(end, date(year + 1, 1, 1))
        if year_end <= year_start:
            continue
        periods = antardashas_between(builder.moon_longitude, builder.birth_utc, builder.zone,
                                      builder.utc(year_start), builder.utc(year_end))
        houses = set()
        dashas = []
        for period in periods:
            clip_start = max(year_start, date.fromisoformat(period["antardasha"]["start"]))
            clip_end = min(year_end, date.fromisoformat(period["antardasha"]["end"]))
            if clip_end <= clip_start:
                continue
            maha, antar = period["mahadasha"]["lord"]["key"], period["antardasha"]["lord"]["key"]
            for lord in (maha, antar):
                houses.add(builder.facts[lord]["house_from_lagna"])
                houses.update(builder.facts[lord]["rules_houses_from_lagna"])
            dashas.append({
                "range": date_range(clip_start, clip_end),
                "mahadasha": builder.facts[maha],
                "antardasha": builder.facts[antar],
            })
        transits = _events_in(builder.transit_rows, year_start, year_end)
        for row in transits:
            houses.add(row["house_from_lagna"])
        rows.append({
            "year": year,
            "range": date_range(year_start, year_end),
            "age_at_year_start": _age(builder.birth_date, year_start),
            "dashas": dashas,
            "transits": transits,
            "saturn_phases": _stays_in(builder.stays, year_start, year_end),
            "houses_lit": sorted(houses),
            "life_areas": _areas(houses),
            "areas": areas_for(houses),
            "pillars": _deprecated_pillars(areas_for(houses)),
        })
    return rows


# --- the lean, grouped view the writer actually reads ----------------------------------------------

_LEAN_LORD_FIELDS = ("key", "name", "devanagari", "house_from_lagna", "house_from_moon",
                     "rules_houses_from_lagna", "dignity", "combust", "retrograde")


def _lean_period(period: dict | None) -> dict | None:
    if period is None:
        return None
    return {"lord": period["lord"]["name"], "key": period["lord"]["key"],
            "devanagari": period["lord"]["devanagari"], "start": period["start"], "end": period["end"]}


def _lean_window(window: dict) -> dict:
    span = window["range"]
    return {
        "id": window["id"],
        "section": window["section"],
        "start": span["start"],
        "end": span["end"],
        "label": span["label"],
        "labels": span["labels"],
        "mahadasha": _lean_period(window["dasha"]["mahadasha"]),
        "antardasha": _lean_period(window["dasha"]["antardasha"]),
        "pratyantardasha": _lean_period(window["dasha"]["pratyantardasha"]),
        "lords": [{field: lord[field] for field in _LEAN_LORD_FIELDS} for lord in window["active_lords"]],
        "transits": [
            {"date": row["date"], "graha": row["graha"]["name"], "event": row["event"],
             "to_sign": row["sign"]["name"], "house_from_lagna": row["house_from_lagna"],
             "house_from_moon": row["house_from_moon"],
             "note": f"natally in house {row['natal_house_from_lagna']} from the lagna, "
                     f"{row['natal_house_from_moon']} from the Moon"}
            for row in window["transits"]
        ],
        "saturn_phase": next((phase["phase"] for phase in window["saturn_phases"] if phase["phase"]), None),
        "areas": [area["area"] for area in window["areas"]],
        "houses_lit": window["houses_lit"],
    }


def _lean_past(entry: dict) -> dict:
    span = entry["range"]
    lord = entry["lord_facts"]
    return {
        "id": entry["id"],
        "section": "past",
        "start": span["start"],
        "end": span["end"],
        "label": span["label"],
        "labels": span["labels"],
        "mahadasha": {"lord": entry["mahadasha_lord"]["name"], "key": entry["mahadasha_lord"]["key"],
                      "devanagari": entry["mahadasha_lord"]["devanagari"],
                      "start": entry["full_mahadasha"]["start"], "end": entry["full_mahadasha"]["end"]},
        "antardasha": None,
        "pratyantardasha": None,
        "lords": [{field: lord[field] for field in _LEAN_LORD_FIELDS}],
        "transits": [],
        "age_years": entry["age_years"],
        "areas": [area["area"] for area in areas_for(entry["houses_lit"])],
        "houses_lit": entry["houses_lit"],
    }


def timeline_windows(chart: dict, as_of: datetime | None = None, knobs: dict | None = None,
                     dignities: dict | None = None, navamsa: dict | None = None,
                     timeline: dict | None = None) -> dict:
    """The timeline as the writer reads it: grouped into the book's life-timeline chapters, with each
    window flattened to the fields a writer needs and nothing else.

    Same facts as `build_timeline`, about a fifth of the bytes. What is dropped from each window is
    everything already known chart-wide (a lord's natal sign, nakshatra and navamsa placement) and
    everything only a checker needs (`why_it_starts_here`, `antardashas_in_window`, per-transit natal
    house numbers - folded into one `note` string). What is NEVER dropped is `house_from_lagna` and
    `house_from_moon` on every graha, and the ISO `start`/`end` with the pre-formatted `labels`.

    Pass `timeline=` to reuse one already built; otherwise it is built here.
    """
    if timeline is None:
        if dignities is None:
            from .dignity import graha_dignities
            dignities = graha_dignities(chart)
        if navamsa is None:
            from .varga import navamsa_chart
            navamsa = navamsa_chart(chart)
        timeline = build_timeline(chart, dignities, navamsa, as_of=as_of, knobs=knobs)

    windows = {window["id"]: _lean_window(window) for window in timeline["windows"]}

    def group(section: dict) -> list[dict]:
        return [windows[window_id] for window_id in section["window_ids"]]

    return {
        "as_of": timeline["as_of"],
        "interval": timeline["interval"],
        "languages": timeline["languages"],
        "past": [_lean_past(entry) for entry in timeline["past"]["entries"]],
        "current_year": group(timeline["current_year"]),
        "years": [{"year": section["year"], "label": section["range"]["label"],
                   "labels": section["range"]["labels"], "start": section["range"]["start"],
                   "end": section["range"]["end"], "windows": group(section)}
                  for section in timeline["near_years"]],
        "blocks": [{"label": section["range"]["label"], "labels": section["range"]["labels"],
                    "start": section["range"]["start"], "end": section["range"]["end"],
                    "windows": group(section)}
                   for section in timeline["far_blocks"]],
        "window_ids": [window["id"] for window in timeline["windows"]],
        "past_ids": [entry["id"] for entry in timeline["past"]["entries"]],
    }
