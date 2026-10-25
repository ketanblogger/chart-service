"""Gemstone, highlights, and the assembled `chart["report"]` end to end - including the API route."""

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.engine import compute_chart, report_facts
from app.engine.gemstone import STONES, gemstones
from app.engine.highlights import HEALTH_FRAMING, SAFETY, TOP_N, highlights
from app.engine.varga import navamsa_chart
from app.engine.dignity import graha_dignities
from app.engine.yogas import yogas
from app.main import app
from tests import synthetic
from tests.reference_charts import AS_OF, KALAM, STATES

BIRTH = KALAM.request()


@pytest.fixture(scope="module")
def chart():
    return KALAM.chart()


@pytest.fixture(scope="module")
def facts(chart):
    return report_facts(chart, as_of=AS_OF)


# --- gemstone --------------------------------------------------------------------------------

def test_every_graha_has_a_complete_stone_entry():
    for graha, stone in STONES.items():
        assert stone["stone"] and stone["sanskrit"] and stone["devanagari"]
        assert stone["metal"] and stone["finger"] and stone["day"]
        assert stone["mantra"].startswith("ॐ")  # the beej mantras all open with OM
        low, high = stone["ratti"]
        assert 0 < low < high <= 12, graha


def test_reference_chart_gemstone_follows_the_lagna_lord_rule(chart):
    """Karka lagna: 1st Chandra, 5th Mangal (Vrishchika), 9th Guru (Meena);
    6th Guru (Dhanu), 8th Shani (Kumbha), 12th Budha (Mithuna).
    Guru is both the 9th and the 6th lord, so the favourable lordship wins and Pukhraj is
    recommended, not avoided. Shani and Budha rule no favourable house, so Neelam and Panna go on
    the avoid list."""
    stones = gemstones(chart)
    assert stones["primary"]["stone"] == "Pearl"
    assert stones["primary"]["role"] == "life_stone"
    assert stones["primary"]["graha"]["key"] == "Moon"
    assert stones["primary"]["finger"] == "little finger" and stones["primary"]["day"] == "Monday"
    assert [s["stone"] for s in stones["recommended"]] == ["Pearl", "Yellow Sapphire", "Red Coral"]
    assert [s["role"] for s in stones["recommended"]] == ["life_stone", "fortune_stone", "benefic_stone"]
    assert [s["stone"] for s in stones["avoid"]] == ["Blue Sapphire", "Emerald"]
    assert [o["graha"]["key"] for o in stones["precedence_applied"]] == ["Jupiter"]
    assert stones["precedence_applied"][0]["also_rules"] == [9]


def test_a_stone_is_never_both_recommended_and_avoided():
    for lagna in range(1, 13):
        stones = gemstones(synthetic.chart(lagna, {}))
        recommended = {s["graha"]["key"] for s in stones["recommended"]}
        avoided = {s["graha"]["key"] for s in stones["avoid"]}
        assert not recommended & avoided, lagna
        assert stones["primary"]["role"] == "life_stone"
        assert stones["not_selected_by_this_rule"]["grahas"] == ["Rahu", "Ketu"]
        assert "Rahu" not in recommended | avoided and "Ketu" not in recommended | avoided


def test_gemstone_carries_the_rule_and_the_presentation_wording(chart):
    stones = gemstones(chart)
    assert "lagna lord" in stones["rule_set"]
    assert "never as a purchase instruction" in stones["presentation"]
    assert "shukla paksha" in stones["wearing_note"]
    for stone in stones["recommended"]:
        assert stone["because"].startswith(stone["graha"]["name"])
        assert stone["weight"]["carats"][0] < stone["weight"]["carats"][1]


def test_gemstone_is_deterministic(chart):
    assert json.dumps(gemstones(chart), sort_keys=True) == json.dumps(gemstones(chart), sort_keys=True)


# --- highlights -------------------------------------------------------------------------------

def test_reference_chart_top_three(chart, facts):
    """Regression pin, not external proof: the ranking is ours, so what this guards is that the
    weights in app/engine/highlights.py keep picking the same three for the same chart."""
    ranked = facts["highlights"]
    assert [f["key"] for f in ranked["top_strengths"]] == [
        "yoga:mahapurusha_hamsa:Jupiter", "yoga:yogakaraka:Mars", "yoga:vipreeta_sarala:Saturn"]
    assert [f["score"] for f in ranked["top_strengths"]] == [11, 11, 10]
    assert [f["key"] for f in ranked["top_cautions"]] == [
        "dasha_lord_damaged:antardasha:Mercury", "mangal_dosha", "yoga:pitra_dosha"]
    assert [f["score"] for f in ranked["top_cautions"]] == [6, 6, 6]


@pytest.mark.parametrize("state", sorted(STATES))
def test_sade_sati_and_dhaiya_reach_the_highlights_when_they_are_running(state):
    """These are functions of the Moon sign AND the moment, not of the birth, so each phase is
    exercised by asking a published chart about the moment Shani is actually there - see STATES in
    tests/reference_charts.py. Shani's transit dates are as checkable as any other."""
    reference, moment = STATES[state]
    facts = report_facts(reference.chart(as_of=moment), as_of=moment)
    keys = {f["key"] for f in facts["highlights"]["all_cautions"]}
    if state.startswith("dhaiya"):
        assert facts["dhaiya"]["active"] is True
        assert facts["dhaiya"]["kind"] == state.split("_")[1]
        assert f"dhaiya:{facts['dhaiya']['kind']}" in keys
    else:
        chart = reference.chart(as_of=moment)
        assert chart["sade_sati"]["active"] is True
        assert chart["sade_sati"]["phase"] == state.replace("sade_sati_", "")
        assert f"sade_sati:{chart['sade_sati']['phase']}" in keys
    # whichever fired, it must be framed as timing and flagged health-related
    fired = next(f for f in facts["highlights"]["all_cautions"]
                 if f["key"].startswith(("dhaiya:", "sade_sati:")))
    assert fired["frame"] == "timing"
    assert fired["health_related"] is True
    assert "never name a condition" in fired["framing"].lower()


def test_at_most_three_of_each_and_they_come_from_the_full_list(facts):
    ranked = facts["highlights"]
    assert len(ranked["top_strengths"]) <= TOP_N
    assert len(ranked["top_cautions"]) <= TOP_N
    assert ranked["top_strengths"] == ranked["all_strengths"][:len(ranked["top_strengths"])]
    assert ranked["top_cautions"] == ranked["all_cautions"][:len(ranked["top_cautions"])]


def test_factors_are_sorted_by_score_then_key(facts):
    for bucket in ("all_strengths", "all_cautions"):
        rows = facts["highlights"][bucket]
        assert [(-f["score"], f["key"]) for f in rows] == sorted((-f["score"], f["key"]) for f in rows)
        assert len({f["key"] for f in rows}) == len(rows)  # keys are unique, so the sort is total


def test_every_caution_carries_the_safety_wording_and_health_ones_carry_the_framing(facts):
    for factor in facts["highlights"]["all_cautions"]:
        assert factor["kind"] == "caution"
        assert factor["safety"] == SAFETY
        assert factor["frame"] in ("timing", "lifestyle", "effort", "opportunity")
        assert isinstance(factor["health_related"], bool)
        assert ("framing" in factor) == factor["health_related"]
        if factor["health_related"]:
            assert factor["framing"] == HEALTH_FRAMING
    assert "never death" in SAFETY.lower() or "never death" in SAFETY
    assert "never name a condition" in HEALTH_FRAMING.lower()


def test_no_caution_text_mentions_death_or_illness(facts):
    forbidden = ("death", "die", "dying", "fatal", "cancer", "disease", "illness", "tumour", "surgery")
    for factor in facts["highlights"]["all_cautions"]:
        text = f"{factor['title']} {factor['reason']}".lower()
        assert not any(word in text for word in forbidden), factor["key"]


def test_every_factor_names_its_grahas_with_both_house_counts(facts):
    for bucket in ("all_strengths", "all_cautions"):
        for factor in facts["highlights"][bucket]:
            assert factor["reason"] and factor["title"]
            assert factor["grahas"]
            for graha in factor["grahas"]:
                assert "house_from_lagna" in graha and "house_from_moon" in graha
                assert "house" not in graha


def test_a_cancelled_debilitation_is_a_strength_not_a_caution(facts):
    """Chandra is debilitated in the reference chart - the published analysis says so too - but the
    debilitation is cancelled, so it must appear under strengths as a Neecha Bhanga yoga and NOT
    under cautions as a bare debilitation."""
    assert "yoga:neecha_bhanga_raja_yoga:Moon" in {f["key"] for f in facts["highlights"]["all_strengths"]}
    assert "debilitated:Moon" not in {f["key"] for f in facts["highlights"]["all_cautions"]}


def test_an_uncancelled_debilitation_is_a_caution():
    quiet = synthetic.chart(1, {"Jupiter": (10, 5.0), "Saturn": 2, "Mars": 2,
                                "Moon": 6, "Sun": 6, "Mercury": 6, "Venus": 6, "Rahu": 11, "Ketu": 5})
    quiet["dasha"] = {"current": None}
    quiet["mangal_dosha"] = {"present": False}
    quiet["sade_sati"] = {"active": False, "cycle": {"which": "current"}}
    navamsa, dignities = synthetic.facts(quiet)
    ranked = highlights(quiet, dignities, navamsa, yogas(quiet, navamsa, dignities))
    caution = next(f for f in ranked["all_cautions"] if f["key"] == "debilitated:Jupiter")
    assert "no neecha bhanga" in caution["evidence"]["modifiers"]


def test_highlights_are_deterministic(chart):
    navamsa, dignities = navamsa_chart(chart), graha_dignities(chart)
    detected = yogas(chart, navamsa, dignities)
    one = highlights(chart, dignities, navamsa, detected)
    two = highlights(chart, dignities, navamsa, detected)
    assert json.dumps(one, sort_keys=True) == json.dumps(two, sort_keys=True)


# --- the assembled report block -------------------------------------------------------------------

def test_report_facts_has_exactly_the_documented_blocks(facts):
    assert set(facts) == {"as_of", "navamsa", "dignity", "aspects", "yogas",
                          "highlights", "gemstone", "dhaiya", "timeline"}
    assert facts["as_of"].startswith(AS_OF.date().isoformat())


def test_detail_full_adds_only_the_report_key():
    basic = compute_chart(*KALAM.args, as_of=AS_OF)
    full = compute_chart(*KALAM.args, as_of=AS_OF, detail="full")
    assert set(full) - set(basic) == {"report"}
    assert {k: v for k, v in full.items() if k != "report"} == basic


def test_detail_must_be_basic_or_full():
    with pytest.raises(ValueError, match="detail"):
        compute_chart(*KALAM.args, detail="everything")


def test_report_facts_is_json_serialisable_and_deterministic(chart):
    one = json.dumps(report_facts(chart, as_of=AS_OF), sort_keys=True)
    assert one == json.dumps(report_facts(chart, as_of=AS_OF), sort_keys=True)


def test_dhaiya_block_matches_the_engine_helper(chart, facts):
    from app.engine import dhaiya
    assert facts["dhaiya"] == dhaiya(chart["grahas"]["Moon"]["sign"]["index"], AS_OF, KALAM.tz)
    # Shani is in Meena in 2026, the 5th from this Vrishchika Moon - neither dhaiya nor sade-sati.
    assert facts["dhaiya"]["active"] is False
    assert facts["dhaiya"]["kind"] is None and facts["dhaiya"]["period"] is None


def test_timeline_knobs_pass_through_report_facts(chart):
    tight = report_facts(chart, as_of=AS_OF, timeline_knobs={"near_years": 1, "far_blocks": 1})
    assert len(tight["timeline"]["near_years"]) == 1
    assert tight["timeline"]["knobs"]["near_years"] == 1


def test_full_detail_works_from_a_worker_thread():
    """swisseph settings are thread-local (see app/engine/core.py). The report facts add transit
    scans and Shani segment scans, so they have to be exercised off the main thread too."""
    import threading
    out = {}

    def run():
        out["chart"] = compute_chart(*KALAM.args, as_of=AS_OF, detail="full")

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    main = compute_chart(*KALAM.args, as_of=AS_OF, detail="full")
    assert json.dumps(out["chart"], sort_keys=True) == json.dumps(main, sort_keys=True)


# --- the API route ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_chart_route_defaults_to_basic(client):
    response = client.post("/api/chart", json=BIRTH)
    assert response.status_code == 200
    assert "report" not in response.json()


def test_chart_route_detail_full(client):
    response = client.post("/api/chart?detail=full&as_of=2026-09-22T00:00:00%2B05:30", json=BIRTH)
    assert response.status_code == 200
    report = response.json()["report"]
    assert set(report) == {"as_of", "navamsa", "dignity", "aspects", "yogas",
                           "highlights", "gemstone", "dhaiya", "timeline"}
    assert report["navamsa"]["lagna"]["sign"]["name"] == "Vrishchika"
    assert report["gemstone"]["primary"]["stone"] == "Pearl"
    assert report["timeline"]["windows"][0]["range"]["start"] == "2026-09-01"
    assert report["timeline"]["window_count"] == len(report["timeline"]["windows"])


def test_chart_route_rejects_an_unknown_detail(client):
    assert client.post("/api/chart?detail=everything", json=BIRTH).status_code == 422


def test_chart_route_as_of_moves_the_timeline(client):
    early = client.post("/api/chart?detail=full&as_of=2027-03-05T00:00:00%2B05:30", json=BIRTH).json()
    assert early["report"]["timeline"]["today_boundary"] == "2027-03-01"
    assert early["report"]["timeline"]["windows"][0]["range"]["start"] == "2027-03-01"


# --- what the renderers asked for ----------------------------------------------------------------

def test_combust_and_dignity_ride_on_every_graha_row(chart):
    """platform renders the combust column straight off chart["grahas"]; ai-layer reads `dignity`."""
    labels = {"exalted", "moolatrikona", "own_sign", "friendly_sign", "neutral_sign",
              "enemy_sign", "debilitated"}
    for key, graha in chart["grahas"].items():
        assert "combust" in graha and "dignity" in graha
        if key in ("Sun", "Rahu", "Ketu"):
            assert graha["combust"] is None          # the rule does not apply
        else:
            assert isinstance(graha["combust"], bool)
        if key in ("Rahu", "Ketu"):
            assert graha["dignity"] is None          # disputed, so nothing is asserted
        else:
            assert graha["dignity"] in labels
    assert chart["grahas"]["Mercury"]["combust"] is True
    assert chart["grahas"]["Moon"]["dignity"] == "debilitated"


def test_graha_rows_agree_with_the_full_dignity_block(chart, facts):
    for key, graha in chart["grahas"].items():
        assert graha["combust"] == facts["dignity"][key]["combustion"]["combust"]
        assert graha["dignity"] == facts["dignity"][key]["dignity"]["label"]


def test_transits_carry_combust_and_dignity_too():
    from app.engine import current_transits
    for graha in current_transits(datetime(2026, 9, 21, tzinfo=timezone.utc))["grahas"].values():
        assert "combust" in graha and "dignity" in graha


def test_navamsa_has_the_same_shape_as_the_d1_chart(chart, facts):
    """One renderer must draw both charts, so the D9 field names are the D1 field names."""
    d9 = facts["navamsa"]
    assert [h["house"] for h in d9["houses"]] == [h["house"] for h in chart["houses"]]
    for house in d9["houses"]:
        assert set(house) == {"house", "sign", "grahas"}
        assert set(house["sign"]) >= {"index", "key", "name", "devanagari"}
    for key, graha in d9["grahas"].items():
        assert {"sign", "house", "retrograde", "graha"} <= set(graha)
        assert graha["retrograde"] == chart["grahas"][key]["retrograde"]
        assert 1 <= graha["house"] <= 12
    assert d9["lagna"]["sign"]["name"] == d9["houses"][0]["sign"]["name"]


def test_navamsa_alias():
    from app.engine import navamsa, navamsa_chart
    assert navamsa is navamsa_chart


def test_highlight_factors_use_the_area_vocabulary(facts):
    from app.engine.timeline import AREAS
    for bucket in ("all_strengths", "all_cautions"):
        for factor in facts["highlights"][bucket]:
            assert set(factor["areas"]) <= set(AREAS)
            assert factor["pillars"] == factor["areas"]   # deprecated alias, same content


def test_every_range_in_the_whole_report_is_localised(facts):
    """Walks the entire `report` block - timeline, highlight factor periods, dhaiya, everything -
    and checks each date range carries all three languages with Latin digits."""
    from app.engine.constants import LANGUAGES, MONTHS
    from tests.test_timeline import _walk_ranges

    ranges = list(_walk_ranges(facts))
    assert len(ranges) > 100
    for row in ranges:
        assert set(row["labels"]) == set(LANGUAGES)
        assert row["label"] == row["labels"]["en"]
        assert row["precision"] in ("day", "month")
        for language, label in row["labels"].items():
            assert not any("०" <= ch <= "९" for ch in label), (language, label)
            assert any(MONTHS[language][i] in label for i in range(12)), (language, label)
