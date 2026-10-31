"""Vimshottari at three levels: the tree must tile the 120-year cycle exactly, at every level."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.engine.constants import DASHA_SEQUENCE
from app.engine.core import parse_tz, to_utc
from app.engine.dasha import (
    TOTAL_YEARS,
    YEAR_DAYS,
    antardashas_between,
    boundaries_between,
    cycle_start,
    cycles_needed,
    dasha_tree,
    pratyantardashas_between,
    running_dasha,
    vimshottari,
)

from tests.reference_charts import AS_OF, CHARTS, KALAM, NEHRU

ZONE = parse_tz(KALAM.tz)
BIRTH = to_utc(KALAM.born, KALAM.at, KALAM.tz)
MOON = KALAM.chart()["grahas"]["Moon"]["longitude"]  # 223.0308, Vrishchika 13°01'50"

# A spread of Moon longitudes: nakshatra start, nakshatra end, every dasha lord in turn.
MOONS = [0.0, 13.3, 13.34, 99.9, 180.0, 262.58955, 359.99] + [i * 13.333333 + 4 for i in range(27)]


@pytest.fixture(scope="module")
def reference():
    return KALAM.chart()


@pytest.mark.parametrize("moon", MOONS)
def test_every_level_tiles_its_parent_exactly(moon):
    """No gaps, no overlaps, and the last child ends exactly where its parent ends - all 9x9x9."""
    tree = dasha_tree(moon, BIRTH, levels=3)
    assert len(tree) == 9
    for maha in tree:
        antars = maha["children"]
        assert len(antars) == 9
        assert antars[0]["start"] == maha["start"]
        assert antars[-1]["end"] == maha["end"]
        for a, b in zip(antars, antars[1:]):
            assert a["end"] == b["start"]
        for antar in antars:
            pratys = antar["children"]
            assert len(pratys) == 9
            assert pratys[0]["start"] == antar["start"]
            assert pratys[-1]["end"] == antar["end"]
            for a, b in zip(pratys, pratys[1:]):
                assert a["end"] == b["start"]


@pytest.mark.parametrize("moon", MOONS)
def test_the_cycle_is_120_years_and_the_mahadashas_are_contiguous(moon):
    tree = dasha_tree(moon, BIRTH, levels=1)
    assert tree[0]["start"] == cycle_start(moon, BIRTH)
    for a, b in zip(tree, tree[1:]):
        assert a["end"] == b["start"]
    total = tree[-1]["end"] - tree[0]["start"]
    assert total == timedelta(days=TOTAL_YEARS * YEAR_DAYS)


def test_sub_period_lengths_follow_the_proportional_rule():
    """length(sub) = length(parent) * sub_lord_years / 120, to the second."""
    years = dict(DASHA_SEQUENCE)
    for maha in dasha_tree(MOON, BIRTH, levels=3):
        parent = (maha["end"] - maha["start"]).total_seconds()
        for antar in maha["children"][:-1]:  # the last absorbs the rounding, by design
            expected = parent * years[antar["lord"]] / TOTAL_YEARS
            assert (antar["end"] - antar["start"]).total_seconds() == pytest.approx(expected, abs=1)
            inner = (antar["end"] - antar["start"]).total_seconds()
            for praty in antar["children"][:-1]:
                assert (praty["end"] - praty["start"]).total_seconds() == pytest.approx(
                    inner * years[praty["lord"]] / TOTAL_YEARS, abs=1)


def test_sub_periods_sum_to_the_parent_to_the_microsecond():
    for maha in dasha_tree(MOON, BIRTH, levels=3):
        assert sum((a["end"] - a["start"] for a in maha["children"]), timedelta()) == maha["end"] - maha["start"]
        for antar in maha["children"]:
            assert sum((p["end"] - p["start"] for p in antar["children"]), timedelta()) == \
                   antar["end"] - antar["start"]


def test_antardasha_order_starts_with_the_parent_lord():
    order = [lord for lord, _ in DASHA_SEQUENCE]
    for maha in dasha_tree(MOON, BIRTH, levels=3):
        start = order.index(maha["lord"])
        assert [a["lord"] for a in maha["children"]] == [order[(start + i) % 9] for i in range(9)]
        for antar in maha["children"]:
            inner = order.index(antar["lord"])
            assert [p["lord"] for p in antar["children"]] == [order[(inner + i) % 9] for i in range(9)]


def test_running_dasha_agrees_with_the_tree_at_a_thousand_instants():
    tree = dasha_tree(MOON, BIRTH, levels=3)
    span = tree[-1]["end"] - tree[0]["start"]
    for i in range(1, 1000):
        moment = tree[0]["start"] + span * i / 1000
        running = running_dasha(MOON, BIRTH, ZONE, moment)
        maha = next(m for m in tree if m["start"] <= moment < m["end"])
        antar = next(a for a in maha["children"] if a["start"] <= moment < a["end"])
        praty = next(p for p in antar["children"] if p["start"] <= moment < p["end"])
        assert running["mahadasha"]["lord"]["key"] == maha["lord"]
        assert running["antardasha"]["lord"]["key"] == antar["lord"]
        assert running["pratyantardasha"]["lord"]["key"] == praty["lord"]
        assert running["mahadasha"]["level"] == "mahadasha"
        assert running["pratyantardasha"]["level"] == "pratyantardasha"


def test_running_dasha_is_none_before_the_sequence_begins():
    tree = dasha_tree(MOON, BIRTH, levels=1)
    assert running_dasha(MOON, BIRTH, ZONE, tree[0]["start"] - timedelta(days=1)) is None


def test_the_sequence_repeats_past_120_years_instead_of_stopping():
    """The nine mahadashas total 120 years, which the texts take as a full lifespan - but the
    sequence is periodic, so it begins again rather than ending. Before this, a chart whose cycle had
    expired made `running_dasha` return None and the timeline builder crash on it."""
    one = dasha_tree(MOON, BIRTH, levels=1)
    two = dasha_tree(MOON, BIRTH, levels=1, cycles=2)
    assert len(two) == 18
    assert [n["lord"] for n in two[9:]] == [n["lord"] for n in one]        # the same order again
    assert two[9]["start"] == one[-1]["end"]                               # and contiguous with it
    assert [n["cycle"] for n in two[:9]] == [1] * 9
    assert [n["cycle"] for n in two[9:]] == [2] * 9
    for a, b in zip(two, two[1:]):
        assert a["end"] == b["start"]


def test_a_period_from_the_second_round_says_so():
    after = dasha_tree(MOON, BIRTH, levels=1)[-1]["end"] + timedelta(days=30)
    running = running_dasha(MOON, BIRTH, ZONE, after)
    assert running is not None
    assert running["mahadasha"]["cycle"] == 2
    assert "begun again" in running["mahadasha"]["note"]
    # a first-round period carries neither key, so nothing is cluttered for an ordinary chart
    assert "cycle" not in running_dasha(MOON, BIRTH, ZONE, AS_OF)["mahadasha"]


def test_cycles_needed_always_reaches_strictly_past_the_moment_asked_about():
    """Periods are half-open and window lookups compare printed DATES, so a sequence that ends
    exactly at the moment asked about answers "nothing covers this"."""
    start = cycle_start(MOON, BIRTH)
    full = timedelta(days=TOTAL_YEARS * YEAR_DAYS)
    for moment in (start, start + full / 2, start + full, start + full + timedelta(days=1),
                   start + full * 2, start + full * 2 + timedelta(seconds=1)):
        count = cycles_needed(MOON, BIRTH, moment)
        tree = dasha_tree(MOON, BIRTH, levels=1, cycles=count)
        assert tree[-1]["end"] > moment, moment
        assert running_dasha(MOON, BIRTH, ZONE, moment, by_local_date=True) is not None, moment


@pytest.mark.parametrize("reference", CHARTS, ids=lambda r: r.key)
def test_mahadashas_is_always_exactly_the_nine_of_the_classical_table(reference):
    """`mahadashas` IS the 120-year table, so it stays nine entries long however old the chart is -
    otherwise anything rendering it (the PDF's Vimshottari grid above all) would silently start
    showing eighteen rows for a pre-1906 birth. The repeat shows up in `current`, never here."""
    block = reference.chart()["dasha"]
    assert len(block["mahadashas"]) == 9, reference.key
    assert sum(m["years"] for m in block["mahadashas"]) == TOTAL_YEARS
    assert all("cycle" not in m for m in block["mahadashas"])
    # and the block says plainly whether the sequence had to run round again to reach as_of
    assert block["cycles_to_reach_as_of"] >= 1
    if block["cycles_to_reach_as_of"] > 1:
        assert block["current"]["mahadasha"]["cycle"] == block["cycles_to_reach_as_of"]


def test_a_chart_whose_cycle_expired_still_produces_a_full_report():
    """Jawaharlal Nehru, born 1889: his 120-year cycle ran out in 2009, so every part of the report
    is being answered from the second round. This used to raise TypeError."""
    chart = NEHRU.chart(detail="full")
    assert chart["dasha"]["cycles_to_reach_as_of"] == 2
    assert chart["dasha"]["current"]["mahadasha"]["cycle"] == 2
    assert len(chart["dasha"]["mahadashas"]) == 9, "the classical table stays nine entries long"
    timeline = chart["report"]["timeline"]
    assert timeline["window_count"] > 0
    assert timeline["coverage"]["dasha_cycles_used"] >= 2
    for earlier, later in zip(timeline["windows"], timeline["windows"][1:]):
        assert earlier["range"]["end"] == later["range"]["start"]


def test_pratyantardashas_in_a_window_are_contiguous_and_cover_it():
    start, end = datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2029, 1, 1, tzinfo=timezone.utc)
    rows = pratyantardashas_between(MOON, BIRTH, ZONE, start, end)
    assert rows
    for a, b in zip(rows, rows[1:]):
        assert a["pratyantardasha"]["end"] == b["pratyantardasha"]["start"]
    assert rows[0]["pratyantardasha"]["start"] <= start.date().isoformat()
    assert rows[-1]["pratyantardasha"]["end"] >= end.date().isoformat()
    # every row names all three levels
    assert all(set(row) == {"mahadasha", "antardasha", "pratyantardasha"} for row in rows)


def test_antardashas_in_a_window_are_contiguous_and_cover_it():
    start, end = datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2040, 1, 1, tzinfo=timezone.utc)
    rows = antardashas_between(MOON, BIRTH, ZONE, start, end)
    for a, b in zip(rows, rows[1:]):
        assert a["antardasha"]["end"] == b["antardasha"]["start"]
    assert rows[0]["antardasha"]["start"] <= start.date().isoformat()
    assert rows[-1]["antardasha"]["end"] >= end.date().isoformat()


def test_boundaries_are_sorted_unique_and_keep_the_most_important_level():
    start, end = datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2045, 1, 1, tzinfo=timezone.utc)
    rows = boundaries_between(MOON, BIRTH, ZONE, start, end)
    dates = [when for when, _, _ in rows]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))
    # The Guru -> Shani mahadasha change is a boundary at all three levels; it must appear as level 0.
    change = date(2037, 12, 19)
    assert (change, 0, "Saturn") in rows
    assert all(start.date() < when < end.date() for when, _, _ in rows)


def test_the_two_level_block_is_unchanged_and_matches_the_tree(reference):
    block = reference["dasha"]
    assert block["system"] == "Vimshottari"
    assert block["year_length_days"] == YEAR_DAYS
    assert block["current"]["mahadasha"]["lord"]["key"] == "Jupiter"
    assert block["current"]["mahadasha"]["start"] == "2021-12-19"
    assert block["current"]["antardasha"]["lord"]["key"] == "Mercury"
    assert [m["lord"]["key"] for m in block["mahadashas"]] == [
        "Saturn", "Mercury", "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter"]
    # the two-level block and the tree agree on every mahadasha start
    tree = dasha_tree(MOON, BIRTH, levels=1)
    assert [m["start"] for m in block["mahadashas"]] == \
           [node["start"].astimezone(ZONE).date().isoformat() for node in tree]


def test_running_matches_the_two_level_block(reference):
    running = running_dasha(MOON, BIRTH, ZONE, AS_OF)
    current = reference["dasha"]["current"]
    for level in ("mahadasha", "antardasha"):
        assert running[level]["lord"]["key"] == current[level]["lord"]["key"]
        assert running[level]["start"] == current[level]["start"]
        assert running[level]["end"] == current[level]["end"]


def test_vimshottari_is_deterministic():
    first = vimshottari(MOON, BIRTH, ZONE, AS_OF)
    assert first == vimshottari(MOON, BIRTH, ZONE, AS_OF)
