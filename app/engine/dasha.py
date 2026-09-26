"""Vimshottari dasha timeline from the Moon's longitude at birth, to three levels.

Year length: 365.25 days (the convention most Indian software uses). The first mahadasha
is listed from its theoretical start, which is before birth; `balance_at_birth` says how
much of it was left when the native was born.

Three levels, all by the same proportional rule - a sub-period of a period lasts
`parent_length * sub_lord_years / 120`:

    mahadasha (level 1)      the 9 Vimshottari periods, 120 years in all
    antardasha (level 2)     9 per mahadasha, starting with the mahadasha lord itself
    pratyantardasha (level 3) 9 per antardasha, starting with the antardasha lord itself

Every level is built so the LAST child ends exactly where its parent ends (`end` is copied, not
re-accumulated), so children tile their parent with no gap, no overlap and no float drift. The
tests assert that over the whole 120-year cycle at all three levels.

BEYOND 120 YEARS. The nine mahadashas total 120 years, which the texts take as a full lifespan. The
sequence does not stop there - it is periodic, so it simply begins again from the same nakshatra lord,
which is what practitioners and Indian software do for the rare chart that outlives one round. The
helpers below therefore extend to as many cycles as the moment being asked about needs, and any period
from the second round onwards carries `"cycle": 2` (or higher) so a reader is never misled into
thinking it is the first. `mahadashas` in the block below stays nine entries long - that list IS the
classical 120-year table - while `current` is answered from the extended sequence.

`vimshottari()` returns the two-level block that /api/chart has always returned - the third level is
729 rows and would triple that response, so it is served by the query helpers instead:
`running_dasha()` for "what is active right now" and `pratyantardashas_between()` /
`antardashas_between()` for "what runs inside this date window", which is what the timeline builder
and the paid report use.
"""

import math
from datetime import date, datetime, timedelta, tzinfo

from .constants import DASHA_SEQUENCE, NAKSHATRA_SPAN, graha_name

YEAR_DAYS = 365.25
TOTAL_YEARS = 120
LEVELS = ("mahadasha", "antardasha", "pratyantardasha")


def _years_months_days(years: float) -> dict:
    whole_years = int(years)
    months = (years - whole_years) * 12
    whole_months = int(months)
    return {
        "years": whole_years,
        "months": whole_months,
        "days": int((months - whole_months) * 30),
        "decimal_years": round(years, 4),
    }


def _first_lord_index(moon_longitude: float) -> int:
    return int(moon_longitude // NAKSHATRA_SPAN) % 9


def cycle_start(moon_longitude: float, birth_utc: datetime) -> datetime:
    """Theoretical start of the running mahadasha at birth (before birth by the elapsed balance)."""
    elapsed = moon_longitude % NAKSHATRA_SPAN / NAKSHATRA_SPAN
    _, first_years = DASHA_SEQUENCE[_first_lord_index(moon_longitude)]
    return birth_utc - timedelta(days=elapsed * first_years * YEAR_DAYS)


BOUNDARY_SLACK = timedelta(days=2)


def cycles_needed(moon_longitude: float, birth_utc: datetime, until: datetime) -> int:
    """How many 120-year rounds the sequence needs to cover `until`, with a couple of days to spare.

    The slack matters: periods are half-open, and `running_dasha(by_local_date=True)` compares
    printed DATES, so a tree that ends exactly at `until` - or on the same local date - answers
    "no period covers this" and the caller gets None. `floor(...) + 1` plus two days guarantees the
    sequence always runs strictly past the moment being asked about. The cost of the extra round in
    the exact-boundary case is nine more nodes.
    """
    span = (until + BOUNDARY_SLACK - cycle_start(moon_longitude, birth_utc)).total_seconds() / 86400
    return max(1, math.floor(span / (TOTAL_YEARS * YEAR_DAYS)) + 1)


def _children(parent_index: int, start: datetime, end: datetime) -> list[tuple[str, datetime, datetime]]:
    """The 9 sub-periods of a period whose lord is DASHA_SEQUENCE[parent_index], in order."""
    span = (end - start).total_seconds()
    out = []
    child_start = start
    for step in range(9):
        lord, years = DASHA_SEQUENCE[(parent_index + step) % 9]
        # The last child ends exactly where the parent does - no accumulated float drift.
        child_end = end if step == 8 else child_start + timedelta(seconds=span * years / TOTAL_YEARS)
        out.append((lord, child_start, child_end))
        child_start = child_end
    return out


def dasha_tree(moon_longitude: float, birth_utc: datetime, levels: int = 3,
               cycles: int = 1) -> list[dict]:
    """The 120-year cycle as nested dicts with exact UTC datetimes (not ISO strings).

    Each node: {"lord", "index" (its position in DASHA_SEQUENCE), "cycle", "start", "end", "children"}.
    `levels` 1, 2 or 3. `cycles` repeats the sequence for a chart that outlives one round; `cycle` is
    1 for the first round, 2 for the next, and so on. This is the internal representation; the public
    helpers below format it.
    """
    if levels not in (1, 2, 3):
        raise ValueError("levels must be 1, 2 or 3")
    if cycles < 1:
        raise ValueError("cycles must be at least 1")
    first = _first_lord_index(moon_longitude)
    start = cycle_start(moon_longitude, birth_utc)

    tree = []
    for step in range(9 * cycles):
        i, cycle = step % 9, step // 9 + 1
        index = (first + i) % 9
        lord, years = DASHA_SEQUENCE[index]
        end = start + timedelta(days=years * YEAR_DAYS)
        node = {"lord": lord, "index": index, "cycle": cycle,
                "start": start, "end": end, "children": []}
        if levels >= 2:
            for antar_lord, antar_start, antar_end in _children(index, start, end):
                antar_index = next(j for j, (name, _) in enumerate(DASHA_SEQUENCE) if name == antar_lord)
                antar = {"lord": antar_lord, "index": antar_index, "cycle": cycle,
                         "start": antar_start, "end": antar_end, "children": []}
                if levels >= 3:
                    antar["children"] = [
                        {"lord": praty_lord, "index": next(j for j, (n, _) in enumerate(DASHA_SEQUENCE) if n == praty_lord),
                         "cycle": cycle, "start": praty_start, "end": praty_end, "children": []}
                        for praty_lord, praty_start, praty_end in _children(antar_index, antar_start, antar_end)
                    ]
                node["children"].append(antar)
        tree.append(node)
        start = end
    return tree


# --- formatting -------------------------------------------------------------------------------

def _iso(moment: datetime, zone: tzinfo) -> str:
    return moment.astimezone(zone).date().isoformat()


def _period(node: dict, zone: tzinfo, level: str) -> dict:
    period = {
        "level": level,
        "lord": graha_name(node["lord"]),
        "start": _iso(node["start"], zone),
        "end": _iso(node["end"], zone),
    }
    if node.get("cycle", 1) > 1:  # only ever set on a chart that outlived the first 120 years
        period["cycle"] = node["cycle"]
        period["note"] = ("the Vimshottari sequence has begun again; this is round "
                          f"{node['cycle']} of the 120-year cycle")
    return period


# --- the two-level block /api/chart returns (unchanged shape) -----------------------------------

def vimshottari(moon_longitude: float, birth_utc: datetime, zone: tzinfo, as_of_utc: datetime) -> dict:
    cycles = cycles_needed(moon_longitude, birth_utc, as_of_utc)
    tree = dasha_tree(moon_longitude, birth_utc, levels=2, cycles=cycles)
    first_lord, first_years = DASHA_SEQUENCE[_first_lord_index(moon_longitude)]
    elapsed = moon_longitude % NAKSHATRA_SPAN / NAKSHATRA_SPAN

    mahadashas, current = [], None
    for node in tree:
        antardashas = []
        for child in node["children"]:
            if child["end"] <= birth_utc:  # skip sub-periods that were over before birth
                continue
            row = {"lord": graha_name(child["lord"]), "start": _iso(child["start"], zone), "end": _iso(child["end"], zone)}
            if node["cycle"] == 1:
                antardashas.append(row)
            if child["start"] <= as_of_utc < child["end"]:
                current = {"mahadasha": _period(node, zone, "mahadasha"), "antardasha": row}
        if node["cycle"] > 1:  # `mahadashas` is the classical 120-year table, always nine entries
            continue
        mahadashas.append({
            "lord": graha_name(node["lord"]),
            "years": DASHA_SEQUENCE[node["index"]][1],
            "start": _iso(node["start"], zone),
            "end": _iso(node["end"], zone),
            "antardashas": antardashas,
        })

    return {
        "system": "Vimshottari",
        "year_length_days": YEAR_DAYS,
        "balance_at_birth": {
            "lord": graha_name(first_lord),
            **_years_months_days((1 - elapsed) * first_years),
        },
        "as_of": _iso(as_of_utc, zone),
        "cycles_to_reach_as_of": cycles,  # >1 only for a chart that outlived the 120-year cycle
        "current": current if as_of_utc >= birth_utc else None,
        "mahadashas": mahadashas,
    }


# --- third level: queries ------------------------------------------------------------------------

def running_dasha(moon_longitude: float, birth_utc: datetime, zone: tzinfo, at_utc: datetime,
                  by_local_date: bool = False) -> dict | None:
    """The mahadasha / antardasha / pratyantardasha running at one instant.

    Returns None outside the 120-year cycle. `at_utc` before birth is still answered (the cycle
    starts before birth by the balance) - callers that care check the date themselves.

    `by_local_date=True` matches on the LOCAL CALENDAR DATE instead of the instant. Periods change at
    a time of day, but the report only ever shows dates, so a window that the timeline starts on the
    day an antardasha begins must be given the NEW antardasha even though the change happens at, say,
    14:00 that afternoon. Matching on the printed dates is what keeps a window's `range` and its
    `dasha` telling the reader the same story. Safe because the shortest possible pratyantardasha
    (Ketu in Ketu in Ketu) is still about nine days long, so no period is invisible to a date match.
    """
    cycles = cycles_needed(moon_longitude, birth_utc, at_utc)
    day = at_utc.astimezone(zone).date().isoformat() if by_local_date else None

    def covers(node: dict) -> bool:
        if day is None:
            return node["start"] <= at_utc < node["end"]
        return _iso(node["start"], zone) <= day < _iso(node["end"], zone)

    for node in dasha_tree(moon_longitude, birth_utc, levels=3, cycles=cycles):
        if not covers(node):
            continue
        antar = next(c for c in node["children"] if covers(c))
        praty = next(c for c in antar["children"] if covers(c))
        return {
            "at": _iso(at_utc, zone),
            "mahadasha": _period(node, zone, "mahadasha"),
            "antardasha": _period(antar, zone, "antardasha"),
            "pratyantardasha": _period(praty, zone, "pratyantardasha"),
        }
    return None


def _overlaps(node: dict, start_utc: datetime, end_utc: datetime) -> bool:
    return node["start"] < end_utc and node["end"] > start_utc


def antardashas_between(moon_longitude: float, birth_utc: datetime, zone: tzinfo,
                        start_utc: datetime, end_utc: datetime) -> list[dict]:
    """Every antardasha overlapping [start, end), each carrying its mahadasha. Sorted, contiguous."""
    out = []
    cycles = cycles_needed(moon_longitude, birth_utc, end_utc)
    for node in dasha_tree(moon_longitude, birth_utc, levels=2, cycles=cycles):
        if not _overlaps(node, start_utc, end_utc):
            continue
        for antar in node["children"]:
            if _overlaps(antar, start_utc, end_utc):
                out.append({"mahadasha": _period(node, zone, "mahadasha"),
                            "antardasha": _period(antar, zone, "antardasha")})
    return out


def pratyantardashas_between(moon_longitude: float, birth_utc: datetime, zone: tzinfo,
                             start_utc: datetime, end_utc: datetime) -> list[dict]:
    """Every pratyantardasha overlapping [start, end), each carrying its antardasha and mahadasha."""
    out = []
    cycles = cycles_needed(moon_longitude, birth_utc, end_utc)
    for node in dasha_tree(moon_longitude, birth_utc, levels=3, cycles=cycles):
        if not _overlaps(node, start_utc, end_utc):
            continue
        for antar in node["children"]:
            if not _overlaps(antar, start_utc, end_utc):
                continue
            for praty in antar["children"]:
                if _overlaps(praty, start_utc, end_utc):
                    out.append({"mahadasha": _period(node, zone, "mahadasha"),
                                "antardasha": _period(antar, zone, "antardasha"),
                                "pratyantardasha": _period(praty, zone, "pratyantardasha")})
    return out


def boundaries_between(moon_longitude: float, birth_utc: datetime, zone: tzinfo,
                       start_utc: datetime, end_utc: datetime, levels: int = 3) -> list[tuple[date, int, str]]:
    """(local date, level 0/1/2, lord) for every dasha period START strictly inside (start, end).

    Level 0 = mahadasha, 1 = antardasha, 2 = pratyantardasha - the priority the timeline builder uses
    when it has to drop boundaries. A date that is a boundary at several levels appears once, at its
    most important level. Sorted by date.
    """
    seen: dict[date, tuple[int, str]] = {}

    def add(node: dict, level: int):
        if start_utc < node["start"] < end_utc:
            when = node["start"].astimezone(zone).date()
            if when not in seen or level < seen[when][0]:
                seen[when] = (level, node["lord"])

    for node in dasha_tree(moon_longitude, birth_utc, levels=levels,
                           cycles=cycles_needed(moon_longitude, birth_utc, end_utc)):
        if not _overlaps(node, start_utc, end_utc):
            continue
        add(node, 0)
        for antar in node["children"]:
            if not _overlaps(antar, start_utc, end_utc):
                continue
            add(antar, 1)
            for praty in antar["children"]:
                if _overlaps(praty, start_utc, end_utc):
                    add(praty, 2)
    return sorted((when, level, lord) for when, (level, lord) in seen.items())
