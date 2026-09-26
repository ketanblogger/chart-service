"""The timeline builder: contiguity, real date ranges everywhere, both house counts, determinism."""

import json
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.engine import compute_chart, find_city
from app.engine.dignity import graha_dignities
from app.engine.constants import LANGUAGES, MONTHS
from app.engine.timeline import AREAS, DAY_PRECISION_DAYS, KNOBS, build_timeline, date_range, timeline_windows
from app.engine.varga import navamsa_chart
from tests.reference_charts import AS_OF, KALAM


def _chart(as_of=AS_OF):
    return KALAM.chart(as_of=as_of)


def _timeline(chart, as_of=AS_OF, knobs=None):
    return build_timeline(chart, graha_dignities(chart), navamsa_chart(chart), as_of=as_of, knobs=knobs)


@pytest.fixture(scope="module")
def chart():
    return _chart()


@pytest.fixture(scope="module")
def timeline(chart):
    return _timeline(chart)


# --- the canonical date range -------------------------------------------------------------------
def test_date_range_shape_and_label():
    row = date_range(date(2028, 1, 1), date(2028, 6, 1))
    assert row == {
        "start": "2028-01-01", "end": "2028-06-01",
        "label": "Jan 2028 – May 2028",
        "labels": {"en": "Jan 2028 – May 2028",
                   "hi": "जनवरी 2028 – मई 2028",
                   "mr": "जानेवारी 2028 – मे 2028"},
        "precision": "month", "start_ym": "2028-01", "end_ym": "2028-05", "days": 152}


def test_date_range_end_is_exclusive_so_the_label_names_the_last_month_covered():
    """The interval is half-open, so a range ending on 1 Feb is labelled January, never February."""
    assert date_range(date(2026, 1, 1), date(2026, 2, 1))["label"] == "Jan 2026"
    assert date_range(date(2026, 1, 1), date(2026, 3, 1))["label"] == "Jan 2026 – Feb 2026"
    assert date_range(date(2026, 1, 15), date(2026, 3, 1))["label"] == "Jan 2026 – Feb 2026"
    assert date_range(date(2026, 1, 31), date(2026, 2, 2))["label"] == "31 Jan – 1 Feb 2026"


@pytest.mark.parametrize("start,end,expected", [
    ((2026, 1, 1), (2026, 3, 1), "Jan 2026 – Feb 2026"),
    ((2026, 1, 10), (2026, 4, 1), "Jan 2026 – Mar 2026"),
    ((2026, 2, 1), (2026, 3, 20), "Feb 2026 – Mar 2026"),
    ((2026, 1, 1), (2026, 2, 1), "Jan 2026"),                       # exactly one calendar month
    ((2026, 10, 3), (2026, 10, 27), "3 – 26 Oct 2026"),
    ((2026, 10, 3), (2026, 11, 15), "3 Oct – 14 Nov 2026"),
    ((2026, 12, 20), (2027, 1, 10), "20 Dec 2026 – 9 Jan 2027"),
    ((2026, 10, 3), (2026, 10, 4), "3 Oct 2026"),                   # a single day
])
def test_label_forms(start, end, expected):
    assert date_range(date(*start), date(*end))["label"] == expected


def test_the_day_precision_threshold_is_the_documented_one():
    long_enough = date_range(date(2026, 1, 10), date(2026, 1, 10) + timedelta(days=DAY_PRECISION_DAYS))
    one_short = date_range(date(2026, 1, 10), date(2026, 1, 10) + timedelta(days=DAY_PRECISION_DAYS - 1))
    assert long_enough["precision"] == "month"
    assert one_short["precision"] == "day"
    # ... but a range that is exactly whole calendar months always reads as months
    assert date_range(date(2026, 1, 1), date(2026, 2, 1))["precision"] == "month"


def test_labels_are_localised_with_latin_digits_and_a_spaced_en_dash():
    row = date_range(date(2026, 9, 1), date(2026, 12, 1))
    assert set(row["labels"]) == set(LANGUAGES)
    assert row["labels"]["en"] == "Sep 2026 – Nov 2026"
    assert row["labels"]["hi"] == f"{MONTHS['hi'][8]} 2026 – {MONTHS['hi'][10]} 2026"
    assert row["labels"]["mr"] == f"{MONTHS['mr'][8]} 2026 – {MONTHS['mr'][10]} 2026"
    assert row["labels"]["mr"] != row["labels"]["hi"]     # Marathi is Marathi, not Hindi
    assert MONTHS["mr"][8] == "सप्टेंबर"
    assert MONTHS["hi"][8] == "सितंबर"
    for language, label in row["labels"].items():
        assert "2026" in label, language                  # Latin digits, never Devanagari
        assert " – " in label, language                 # en dash with spaces
        assert not any("०" <= ch <= "९" for ch in label), language


@pytest.mark.parametrize("month", range(1, 13))
def test_no_month_name_leaks_between_hindi_and_marathi(month):
    """Regression: the live rashifal run once printed a Hindi month name in a Marathi page. Every
    month, in every language: the label must carry THAT language's name and none of the others'."""
    row = date_range(date(2026, month, 1), date(2027 if month == 12 else 2026, month % 12 + 1, 1))
    for language in LANGUAGES:
        label = row["labels"][language]
        mine = MONTHS[language][month - 1]
        assert mine in label, (language, month, label)
        for other in LANGUAGES:
            theirs = MONTHS[other][month - 1]
            if theirs != mine:
                assert theirs not in label, f"{other} name {theirs!r} leaked into the {language} label {label!r}"


def test_the_two_spellings_that_actually_leaked_before():
    """September and January, the pairs that differ most visibly between the two languages."""
    september = date_range(date(2026, 9, 1), date(2026, 10, 1))["labels"]
    assert september["hi"] == "सितंबर 2026"
    assert september["mr"] == "सप्टेंबर 2026"
    january = date_range(date(2026, 1, 1), date(2026, 2, 1))["labels"]
    assert january["hi"] == "जनवरी 2026"
    assert january["mr"] == "जानेवारी 2026"
    assert january["hi"] != january["mr"] and september["hi"] != september["mr"]


@pytest.mark.parametrize("start,end", [
    ((2026, 1, 1), (2027, 1, 1)),       # month precision, one year
    ((2026, 10, 3), (2026, 10, 27)),    # day precision, inside one month
    ((2026, 12, 20), (2027, 1, 10)),    # day precision, across a year boundary
    ((2030, 6, 1), (2035, 6, 1)),       # a far block
])
def test_no_devanagari_digit_ever_reaches_a_label(start, end):
    """Regression: the live rashifal run leaked Devanagari digits; we standardised on Latin."""
    row = date_range(date(*start), date(*end))
    for language, label in row["labels"].items():
        assert not any("०" <= ch <= "९" for ch in label), (language, label)
        assert any(ch.isdigit() and ch.isascii() for ch in label), (language, label)
        assert str(start[0]) in label or str(end[0]) in label or str(end[0] - 1) in label


def test_every_range_in_a_whole_timeline_is_clean(timeline):
    """The same two checks applied to EVERY range the builder emits - windows, past entries, the
    year table, far-block ranges, saturn phases, the clipped antardasha spans - by walking the
    output rather than by listing the places, so a range added later is covered automatically."""
    ranges = list(_walk_ranges(timeline))
    assert len(ranges) > 100, "the walker should be finding every range in the timeline"
    hindi_only = {MONTHS["hi"][i] for i in range(12)} - {MONTHS["mr"][i] for i in range(12)}
    marathi_only = {MONTHS["mr"][i] for i in range(12)} - {MONTHS["hi"][i] for i in range(12)}
    for row in ranges:
        assert set(row["labels"]) == set(LANGUAGES)
        assert row["label"] == row["labels"]["en"]
        for language, label in row["labels"].items():
            assert label, (language, row)
            assert not any("०" <= ch <= "९" for ch in label), (language, label)
            assert " – " in label or label.count(" ") <= 2, (language, label)
        assert not (marathi_only & set(_words(row["labels"]["hi"]))), row["labels"]
        assert not (hindi_only & set(_words(row["labels"]["mr"]))), row["labels"]


def _words(label):
    return set(label.replace("–", " ").split())


def _walk_ranges(node):
    """Every date-range object anywhere in the structure."""
    if isinstance(node, dict):
        if "labels" in node and "start" in node and "end" in node:
            yield node
        for value in node.values():
            yield from _walk_ranges(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_ranges(item)


def test_saturn_phase_ranges_carry_labels_too(timeline):
    phases = [phase for window in timeline["windows"] for phase in window["saturn_phases"]]
    assert phases
    for phase in phases:
        assert set(phase["range"]["labels"]) == set(LANGUAGES)
        assert phase["range"]["start"] == phase["start"] and phase["range"]["end"] == phase["end"]


def test_past_entries_and_year_table_rows_carry_labels(timeline):
    for entry in timeline["past"]["entries"]:
        assert set(entry["range"]["labels"]) == set(LANGUAGES)
        assert set(entry["full_mahadasha"]["labels"]) == set(LANGUAGES)
    for row in timeline["year_table"]:
        assert set(row["range"]["labels"]) == set(LANGUAGES)
        for spell in row["dashas"]:
            assert set(spell["range"]["labels"]) == set(LANGUAGES)
    for section in [timeline["current_year"], *timeline["near_years"], *timeline["far_blocks"]]:
        assert set(section["range"]["labels"]) == set(LANGUAGES)
    for key, span in timeline["coverage"].items():
        if isinstance(span, dict):
            assert set(span["labels"]) == set(LANGUAGES), key


def test_date_range_rejects_an_empty_or_backwards_range():
    with pytest.raises(ValueError):
        date_range(date(2026, 1, 1), date(2026, 1, 1))
    with pytest.raises(ValueError):
        date_range(date(2026, 2, 1), date(2026, 1, 1))


# --- structure ------------------------------------------------------------------------------------

def test_windows_are_sorted_contiguous_and_non_overlapping(timeline):
    windows = timeline["windows"]
    assert windows
    assert len(windows) == timeline["window_count"]
    for earlier, later in zip(windows, windows[1:]):
        assert earlier["range"]["end"] == later["range"]["start"]
        assert earlier["range"]["start"] < earlier["range"]["end"]
    assert windows[0]["range"]["start"] == timeline["coverage"]["current_year"]["start"]
    assert windows[0]["range"]["start"] == timeline["today_boundary"]


def test_every_window_has_a_real_dated_range_never_an_age_band(timeline):
    for window in timeline["windows"]:
        span = window["range"]
        assert date.fromisoformat(span["end"]) > date.fromisoformat(span["start"])
        assert span["days"] >= 1
        assert span["days"] == (date.fromisoformat(span["end"]) - date.fromisoformat(span["start"])).days
        assert span["precision"] in ("day", "month")
        assert set(span["labels"]) == set(LANGUAGES)
        assert all(span["labels"][language] for language in LANGUAGES)
        assert span["label"] == span["labels"]["en"]
        # a month name from some language is always in there; nothing is ever an age band
        assert any(month in span["label"] for month in MONTHS["en"])


def test_sections_index_into_the_flat_list_without_repeating_it(timeline):
    seen = []
    for section in [timeline["current_year"], *timeline["near_years"], *timeline["far_blocks"]]:
        assert "windows" not in section
        seen.extend(section["window_indexes"])
        covered = [timeline["windows"][i] for i in section["window_indexes"]]
        assert covered[0]["range"]["start"] == section["range"]["start"]
        assert covered[-1]["range"]["end"] == section["range"]["end"]
        assert all(w["section"] == section["section"] for w in covered)
    assert seen == list(range(timeline["window_count"]))
    labels = [s["section"] for s in
              [timeline["current_year"], *timeline["near_years"], *timeline["far_blocks"]]]
    assert len(labels) == len(set(labels)), "section labels must identify one block each"


def test_the_sections_themselves_are_contiguous(timeline):
    coverage = timeline["coverage"]
    assert coverage["past"]["end"] == coverage["current_year"]["start"]
    assert coverage["current_year"]["end"] == coverage["near_years"]["start"]
    assert coverage["near_years"]["end"] == coverage["far_years"]["start"]
    assert coverage["past"]["start"] == KALAM.born.isoformat()


def test_near_years_are_whole_calendar_years_with_two_to_four_windows(timeline):
    assert len(timeline["near_years"]) == KNOBS["near_years"]
    for section in timeline["near_years"]:
        assert section["range"]["start"].endswith("-01-01")
        assert section["range"]["end"].endswith("-01-01")
        count = len(section["window_indexes"])
        assert KNOBS["near_min_ranges_per_year"] <= count <= KNOBS["near_max_ranges_per_year"]


def test_no_window_is_longer_than_its_rule_allows(timeline):
    """`max_days` is honoured only while the window budget allows: `_split` grows to `min_count`,
    shrinks to `max_count`, then splits over-long windows - so a section already at `max_count` can
    keep a long window rather than exceed the cap. Both limits are asserted, in that precedence."""
    limits = {
        "current_year": (None, KNOBS["current_year_max_windows"]),
        "near": (KNOBS["near_max_window_days"], KNOBS["near_max_ranges_per_year"]),
        "far": (KNOBS["far_max_window_days"], KNOBS["far_max_ranges_per_block"]),
    }
    for section in [timeline["current_year"], *timeline["near_years"], *timeline["far_blocks"]]:
        max_days, max_count = limits[section["kind"]]
        count = len(section["window_indexes"])
        assert count <= max_count, section["section"]
        if max_days is None or count >= max_count:
            continue   # the cap was reached first; see the docstring above
        for index in section["window_indexes"]:
            assert timeline["windows"][index]["range"]["days"] <= max_days, section["section"]


def test_current_year_windows_respect_the_window_cap(timeline):
    assert len(timeline["current_year"]["window_indexes"]) <= KNOBS["current_year_max_windows"]


def test_the_knobs_are_echoed_and_actually_bite(chart):
    tight = _timeline(chart, knobs={"current_year_max_windows": 4, "near_years": 2, "far_blocks": 1})
    assert tight["knobs"]["current_year_max_windows"] == 4
    assert len(tight["current_year"]["window_indexes"]) <= 4
    assert len(tight["near_years"]) == 2
    assert len(tight["far_blocks"]) == 1
    assert tight["window_count"] < _timeline(chart)["window_count"]


# --- payload ----------------------------------------------------------------------------------------

def test_every_graha_mentioned_carries_both_house_counts(timeline):
    """The bug this prevents: a house counted from the Moon written up as "your Nth house"."""
    def check(graha):
        assert "house_from_lagna" in graha and "house_from_moon" in graha
        assert isinstance(graha["house_from_lagna"], int) and 1 <= graha["house_from_lagna"] <= 12
        assert isinstance(graha["house_from_moon"], int) and 1 <= graha["house_from_moon"] <= 12
        assert "house" not in graha  # a bare, unqualified house key must never appear

    for window in timeline["windows"]:
        assert window["active_lords"]
        for lord in window["active_lords"]:
            check(lord)
        for transit in window["transits"]:
            assert 1 <= transit["house_from_lagna"] <= 12
            assert 1 <= transit["house_from_moon"] <= 12
            assert 1 <= transit["natal_house_from_lagna"] <= 12
            assert 1 <= transit["natal_house_from_moon"] <= 12
            assert "house" not in transit
    for entry in timeline["past"]["entries"]:
        check(entry["lord_facts"])
    for row in timeline["year_table"]:
        for spell in row["dashas"]:
            check(spell["mahadasha"])
            check(spell["antardasha"])


def test_pratyantardasha_is_present_only_in_the_current_year(timeline):
    for index in timeline["current_year"]["window_indexes"]:
        window = timeline["windows"][index]
        assert window["dasha"]["pratyantardasha"]["level"] == "pratyantardasha"
    for section in [*timeline["near_years"], *timeline["far_blocks"]]:
        for index in section["window_indexes"]:
            assert timeline["windows"][index]["dasha"]["pratyantardasha"] is None


def test_the_running_dasha_of_a_window_really_covers_its_start(timeline):
    for window in timeline["windows"]:
        start = window["range"]["start"]
        for level in ("mahadasha", "antardasha"):
            period = window["dasha"][level]
            assert period["start"] <= start < period["end"]


def test_antardashas_in_window_are_clipped_and_contiguous(timeline):
    for window in timeline["windows"]:
        spells = window["dasha"]["antardashas_in_window"]
        assert spells
        assert spells[0]["range"]["start"] == window["range"]["start"]
        assert spells[-1]["range"]["end"] == window["range"]["end"]
        for a, b in zip(spells, spells[1:]):
            assert a["range"]["end"] == b["range"]["start"]


def test_transits_fall_inside_their_window(timeline):
    for window in timeline["windows"]:
        for transit in window["transits"]:
            assert window["range"]["start"] <= transit["date"] < window["range"]["end"]


def test_every_boundary_after_the_first_explains_itself(timeline):
    for window in timeline["windows"][1:]:
        assert window["why_it_starts_here"]
        assert all(isinstance(reason, str) and reason for reason in window["why_it_starts_here"])


def test_past_is_mahadasha_only_and_stops_at_today(timeline):
    entries = timeline["past"]["entries"]
    assert [e["mahadasha_lord"]["key"] for e in entries] == [
        "Saturn", "Mercury", "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter"]
    assert entries[0]["range"]["start"] == KALAM.born.isoformat()
    assert entries[-1]["range"]["end"] == timeline["today_boundary"]
    for a, b in zip(entries, entries[1:]):
        assert a["range"]["end"] == b["range"]["start"]
    assert entries[0]["partial"] is True          # the Shani mahadasha began before birth
    assert entries[0]["age_years"] == [0, 5]
    assert all("transits" not in e for e in entries)


def test_year_table_covers_the_current_year_and_the_near_years(timeline):
    years = [row["year"] for row in timeline["year_table"]]
    assert years == sorted(years) == list(range(2026, 2032))
    for row in timeline["year_table"]:
        assert row["dashas"]
        assert row["range"]["start"] <= f"{row['year']}-12-31"
        assert row["age_at_year_start"] >= 94
        for spell in row["dashas"]:
            assert spell["range"]["days"] >= 1


def test_saturn_phases_name_the_phase_and_carry_dates(timeline):
    phases = [p for window in timeline["windows"] for p in window["saturn_phases"]]
    assert phases
    named = [p for p in phases if p["phase"]]
    assert named, "Shani crosses a sade-sati or dhaiya sign from this Moon inside the strip"
    for phase in named:
        assert phase["phase_label"]
        assert phase["range"]["days"] > 0
        assert 1 <= phase["house_from_moon"] <= 12


# --- as_of behaviour ---------------------------------------------------------------------------------

@pytest.mark.parametrize("month", [1, 4, 7, 9, 11, 12])
def test_the_current_year_stretch_is_never_a_stub(month):
    as_of = datetime(2027, month, 20, tzinfo=timezone.utc)
    timeline = _timeline(KALAM.chart(as_of=as_of), as_of)
    span = timeline["coverage"]["current_year"]
    assert span["start"] == f"2027-{month:02d}-01"
    assert span["end"].endswith("-01-01")
    assert span["days"] >= KNOBS["current_year_min_months"] * 30
    assert timeline["windows"][0]["range"]["start"] == span["start"]


def test_a_chart_whose_dasha_cycle_has_expired_still_gets_a_contiguous_strip():
    """The Vimshottari sequence repeats rather than stopping, so a chart older than 120 years is
    answered from the second round instead of crashing - which is what it used to do."""
    from tests.reference_charts import NEHRU
    timeline = _timeline(NEHRU.chart(), AS_OF)
    assert timeline["coverage"]["dasha_cycles_used"] >= 2
    assert timeline["windows"][-1]["range"]["end"] > timeline["coverage"]["dasha_cycle_ends"]
    assert timeline["window_count"] > 0
    for earlier, later in zip(timeline["windows"], timeline["windows"][1:]):
        assert earlier["range"]["end"] == later["range"]["start"]


# --- determinism and serialisability ------------------------------------------------------------------

def test_same_input_same_output(chart):
    assert json.dumps(_timeline(chart), sort_keys=True) == json.dumps(_timeline(chart), sort_keys=True)


def test_a_second_chart_object_gives_the_same_timeline():
    assert json.dumps(_timeline(_chart()), sort_keys=True) == \
           json.dumps(_timeline(_chart()), sort_keys=True)


def test_output_is_json_serialisable(timeline):
    json.dumps(timeline)


def test_a_day_later_shifts_nothing_inside_the_same_month(chart):
    """`today_boundary` is the 1st of the as_of month, so the strip is stable within a month -
    which is what makes a cached report still correct tomorrow."""
    one = _timeline(chart, AS_OF)
    two = _timeline(chart, AS_OF + timedelta(days=5))
    assert [w["range"] for w in one["windows"]] == [w["range"] for w in two["windows"]]


# --- window ids, areas, and the lean grouped view -------------------------------------------------

def test_window_ids_are_unique_stable_and_self_checking(timeline):
    """The AI names a window by id and never writes a date, so an id must be verifiable."""
    ids = [window["id"] for window in timeline["windows"]]
    assert len(ids) == len(set(ids))
    for window in timeline["windows"]:
        assert window["id"] == "w-" + window["range"]["start"]
    for entry in timeline["past"]["entries"]:
        assert entry["id"] == "p-" + entry["range"]["start"]
    past_ids = [entry["id"] for entry in timeline["past"]["entries"]]
    assert len(past_ids) == len(set(past_ids))
    assert not set(ids) & set(past_ids)


def test_window_ids_are_stable_across_rebuilds(chart):
    assert [w["id"] for w in _timeline(chart)["windows"]] == [w["id"] for w in _timeline(chart)["windows"]]


def test_sections_carry_window_ids_alongside_window_indexes(timeline):
    for section in [timeline["current_year"], *timeline["near_years"], *timeline["far_blocks"]]:
        assert len(section["window_ids"]) == len(section["window_indexes"])
        assert section["window_ids"] == [timeline["windows"][i]["id"] for i in section["window_indexes"]]


def test_no_two_windows_share_a_printed_label(timeline):
    """A duplicate label would print two different periods under one heading in the book."""
    for language in LANGUAGES:
        labels = [window["range"]["labels"][language] for window in timeline["windows"]]
        assert len(labels) == len(set(labels)), language


def test_areas_use_the_agreed_vocabulary_and_are_never_empty_entries(timeline):
    allowed = set(AREAS)
    assert allowed == {"career", "money", "marriage", "family", "health",
                       "education", "property", "travel", "study", "spiritual"}
    for window in timeline["windows"]:
        for area in window["areas"]:
            assert area["area"] in allowed
            assert area["houses"], "an area with no house behind it must be omitted, not emitted empty"
            assert area["weight"] == len(area["houses"])
            assert set(area["houses"]) <= set(AREAS[area["area"]])
            assert set(area["houses"]) <= set(window["houses_lit"])
        keys = [area["area"] for area in window["areas"]]
        assert keys == sorted(set(keys), key=lambda k: (-len(set(window["houses_lit"]) & set(AREAS[k])), k))


def test_the_interval_convention_is_stated_in_the_output(timeline):
    assert "EXCLUSIVE" in timeline["interval"]
    assert timeline["languages"] == list(LANGUAGES)


def test_lean_view_groups_the_same_windows_and_keeps_both_house_counts(chart, timeline):
    lean = timeline_windows(chart, timeline=timeline)
    assert [w["id"] for w in lean["current_year"]] == timeline["current_year"]["window_ids"]
    assert [y["year"] for y in lean["years"]] == [s["year"] for s in timeline["near_years"]]
    assert len(lean["blocks"]) == len(timeline["far_blocks"])
    assert lean["window_ids"] == [w["id"] for w in timeline["windows"]]
    assert lean["past_ids"] == [e["id"] for e in timeline["past"]["entries"]]

    flat = lean["past"] + lean["current_year"] + \
        [w for y in lean["years"] for w in y["windows"]] + \
        [w for b in lean["blocks"] for w in b["windows"]]
    for window in flat:
        assert window["start"] < window["end"]
        assert set(window["labels"]) == set(LANGUAGES)
        assert window["label"] == window["labels"]["en"]
        assert window["lords"]
        for lord in window["lords"]:
            assert "house_from_lagna" in lord and "house_from_moon" in lord
            assert "house" not in lord
        for transit in window["transits"]:
            assert "house_from_lagna" in transit and "house_from_moon" in transit
            assert "house" not in transit
        assert set(window["areas"]) <= set(AREAS)


def test_lean_view_is_much_smaller_than_the_full_timeline(chart, timeline):
    lean = len(json.dumps(timeline_windows(chart, timeline=timeline), ensure_ascii=False))
    full = len(json.dumps(timeline, ensure_ascii=False))
    assert lean < full / 2


def test_lean_view_builds_its_own_timeline_when_not_given_one(chart):
    built = timeline_windows(chart, as_of=AS_OF)
    assert built["window_ids"] == timeline_windows(chart, timeline=_timeline(chart))["window_ids"]
