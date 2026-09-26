"""The flagship Kundali book. No network: a fake LLM client throughout.

The fake answers each part call from the book plan itself, so these tests exercise the real prompts,
the real schema, the real checks and the real assembly - only the model is replaced.
"""

import copy
import datetime as dt
import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.ai import book_report, engine_facts
from app.ai.book import LIFE_AREA_CHAPTERS, TABLE, WINDOWS, build_book, plan
from app.ai.client import LLMResult
from app.ai.prompts import BOOK_SYSTEM_PROMPT, INTERPRET_ONLY
from app.ai.report import Birth, _chart, book_facts, generate_report
from app.ai.safety import screen_text
from app.ai.schema import CALL_SCHEMA, call_problems
from app.ai.validator import filler_issues, untraceable_issues
from app.main import app

http = TestClient(app)

# Public reference charts - see tests/reference_charts.py. KALAM is the feature-rich primary
# (Karka lagna, Vrishchika rashi, 9 yogas, mangal dosha "high"); NEHRU is the second person for
# matching, and is also a second-Vimshottari-cycle chart. AS_OF is pinned so these do not change
# meaning as real time passes.
from tests.reference_charts import AS_OF as REFERENCE_AS_OF
from tests.reference_charts import KALAM as PRIMARY
from tests.reference_charts import NEHRU

AS_OF = REFERENCE_AS_OF.date()
KALAM = Birth(dt.date.fromisoformat(PRIMARY.request()["date"]),
              dt.time.fromisoformat(PRIMARY.request()["time"]),
              PRIMARY.request()["lat"], PRIMARY.request()["lon"],
              PRIMARY.request()["timezone"], PRIMARY.place)
NEHRU_BIRTH = Birth(dt.date.fromisoformat(NEHRU.request()["date"]),
                    dt.time.fromisoformat(NEHRU.request()["time"]),
                    NEHRU.request()["lat"], NEHRU.request()["lon"],
                    NEHRU.request()["timezone"], NEHRU.place)
KALAM_JSON = {"date": PRIMARY.request()["date"], "time": PRIMARY.request()["time"],
              "lat": PRIMARY.request()["lat"], "lon": PRIMARY.request()["lon"]}
NEHRU_JSON = {"date": NEHRU.request()["date"], "time": NEHRU.request()["time"],
              "lat": NEHRU.request()["lat"], "lon": NEHRU.request()["lon"]}


# A sentence anchored in the reference chart (Kalam: Karka lagna, Guru exalted in the 1st, Chandra
# in Vrishchika in the 5th), so the fact validator and the filler check both pass it.
GOOD = ("With Guru in the 1st house in Karka, this chart leads with judgement rather than force, "
        "and the Guru mahadasha running now keeps rewarding patience.")


@pytest.fixture(scope="module")
def chart():
    return _chart(KALAM, AS_OF)


@pytest.fixture(scope="module")
def facts(chart):
    return engine_facts.report_facts(chart, AS_OF)


@pytest.fixture(scope="module")
def book(facts):
    return build_book(facts)


class BookFake:
    """Answers each part call the way a well-behaved model would, from the call plan itself.

    `mutate(call, body, attempt)` may damage one call's output, which is how the check, retry and
    redaction paths are tested. `attempt` is 1 on that call's first try, 2 on its regeneration.
    """

    def __init__(self, book, mutate=None, paragraph=GOOD, headings="en", tier=None):
        # The Simple tier has its own call plan; infer it from the book so callers rarely say so.
        tier = tier or ("detailed" if any(part.id == "life_areas" for part in book) else "simple")
        self.tier = tier
        self.calls_planned = {call.key: call for call in plan(book, tier)}
        self.mutate, self.paragraph, self.headings = mutate, paragraph, headings
        self.calls, self.attempts, self.batches = [], {}, []

    def _heading(self, label: str) -> str:
        """English by default - which is the defect the heading check exists to catch."""
        return f"प्रकरण {label}" if self.headings == "mr" else label.replace("_", " ").title()

    def _chapter_heading(self, chapter) -> str:
        """A theme only. The engine's span label is prepended at assembly, never written here."""
        if chapter.labels:
            # No date in a theme - the engine's span is prepended at assembly. The fake deliberately
            # gives every span chapter the SAME theme, to prove the composition keeps them distinct.
            return "संयमाची वर्षे" if self.headings == "mr" else "Years That Ask For Patience"
        return self._heading(chapter.id)

    def _which(self, user: str):
        wanted = set(re.findall(r"chapter id `([\w]+)`", user))
        for call in self.calls_planned.values():
            if {chapter.id for part in call.parts for chapter in part.chapters} == wanted:
                return call
        raise AssertionError(f"no planned call matches the chapters in this prompt: {sorted(wanted)}")

    def _chapter(self, chapter, user: str) -> dict:
        body = {"id": chapter.id, "heading": self._chapter_heading(chapter),
                "paragraphs": [], "bullets": [], "windows": [], "table": None}
        if chapter.shape == WINDOWS:
            body["windows"] = [{"window_id": wid, "headline": "A steady stretch",
                                "paragraphs": [self.paragraph], "areas": ["career"],
                                "area_lines": ["Work asks for patience in this stretch."]}
                               for wid in chapter.window_ids]
        elif chapter.shape == TABLE:
            columns = (["वर्ष", "दशा", "विषय"] if self.headings == "mr" else ["Year", "Dasha", "Theme"])
            body["table"] = {"columns": columns, "rows": [["2028", "Rahu-Guru", "Steady building"]]}
        else:
            body["paragraphs"] = [self.paragraph]
            if chapter.id == "at_a_glance":
                body["bullets"] = ["Simha lagna.", "Dhanu Moon rashi.", "Purvashadha nakshatra, pada 3."]
        return body

    @staticmethod
    def _highlights() -> dict:
        """The FLAT shape the schema asks for; the report publishes the nested one."""
        return {
            "mangal_verdict": "Mangal dosha is present and softened.",
            "mangal_remedy": "Serve on Tuesdays.",
            "sade_sati_verdict": "Sade sati is not running.",
            "sade_sati_guidance": "Keep the routine steady.",
            "dasha_mood": "Guru mahadasha with the Budha antardasha: studious and steady.",
            "strengths": ["Guru in the 1st house in Karka.", "Chandra in the 5th house.",
                          "Shukra in the 4th house."],
            "cautions": ["Mangal asks for patience.", "Shani in the 6th house asks for routine.",
                         "Budha in the 3rd house asks for care with words."],
            "yoga_names": ["Hamsa Yoga"],
            "yoga_lines": ["Guru in the 1st house gives judgement and standing."],
        }

    @staticmethod
    def _gemstone() -> dict:
        return {"stone": "Manikya (Ruby)", "finger": "ring finger", "day": "Sunday", "metal": "gold",
                "avoid": "Neelam, Moti", "note": "Traditional and entirely optional."}

    @staticmethod
    def _empty_highlights() -> dict:
        return {"mangal_verdict": "", "mangal_remedy": "", "sade_sati_verdict": "",
                "sade_sati_guidance": "", "dasha_mood": "", "strengths": [], "cautions": [],
                "yoga_names": [], "yoga_lines": []}

    @staticmethod
    def _empty_gemstone() -> dict:
        return {k: "" for k in ("stone", "finger", "day", "metal", "avoid", "note")}

    def generate_json_batch(self, requests, **kwargs):
        """The Message Batches path. Same answers, keyed by custom_id, order deliberately shuffled -
        the real API returns results in any order and keying by position would be a live-only bug."""
        self.batches.append([r["custom_id"] for r in requests])
        out = {}
        for request in reversed(requests):
            out[request["custom_id"]] = self.generate_json(
                system=request["system"], user=request["user"], schema=request["schema"])
        return out

    def generate_json(self, *, system, user, schema):
        call = self._which(user)
        self.attempts[call.key] = attempt = self.attempts.get(call.key, 0) + 1
        self.calls.append({"system": system, "user": user, "schema": schema, "key": call.key,
                           "attempt": attempt})
        body = {
            "title": (self._heading("Your Kundali") if call.wants_front_matter else ""),
            "summary": self.paragraph if call.wants_front_matter else "",
            "highlights": self._highlights() if call.wants_highlights else self._empty_highlights(),
            "gemstone": self._gemstone() if call.wants_gemstone else self._empty_gemstone(),
            "parts": [{"id": part.id, "heading": self._heading(f"Part {part.label}"), "intro": "",
                       "chapters": [self._chapter(chapter, user) for chapter in part.chapters]}
                      for part in call.parts],
            "remedies": [{"title": f"Remedy {n}", "type": "mantra",
                          "description": "Steadies Guru in the 1st house.",
                          "how_to": "Chant Om Namah Shivaya 108 times.", "frequency": "Saturday mornings"}
                         for n in range(1, 6)] if call.wants_remedies else [],
        }
        if self.mutate:
            self.mutate(call, body, attempt)
        return LLMResult(data=json.loads(json.dumps(body)), model="claude-sonnet-5", stop_reason="end_turn",
                         usage={"input_tokens": 700, "output_tokens": 2500,
                                "cache_creation_input_tokens": 16000 if len(self.calls) == 1 else 0,
                                "cache_read_input_tokens": 0 if len(self.calls) == 1 else 16000},
                         request_id=f"req_{len(self.calls)}")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.delenv("REPORTS_UNLOCKED", raising=False)
    for name in ("REPORT_MODEL", "REPORT_MAX_ATTEMPTS", "REPORT_EFFORT", "REPORT_CONCURRENCY"):
        monkeypatch.delenv(name, raising=False)


def window_call(book, which: int = 0):
    """The nth call that writes timeline windows. Selected by property, not by key, so re-splitting
    the timeline into different calls does not break every test that needs a windowed one."""
    windowed = [call for call in plan(book)
                if any(chapter.windows for part in call.parts for chapter in part.chapters)]
    return windowed[which].key


def make(book, **kwargs):
    fake = BookFake(book, **kwargs)
    return fake, generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=fake, use_cache=False)


# ---- structure: the eight parts -----------------------------------------------------------------------------


def test_the_book_has_parts_a_to_h_in_order(book):
    _, report = make(book)
    assert [part["label"] for part in report["parts"]] == list("ABCDEFGH")
    assert [part["id"] for part in report["parts"]] == [
        "highlights", "chart_basics", "personality", "timeline", "life_areas", "doshas_remedies",
        "year_table", "closing"]  # the eight parts A-H, in print order
    for part in report["parts"]:
        assert part["heading"] and part["chapters"] and "intro" in part
        for chapter in part["chapters"]:
            assert set(chapter) >= {"id", "heading", "paragraphs", "bullets", "subsections",
                                    "windows", "table"}
            assert "highlights" not in chapter  # Part A's cards are a top-level object now


def test_part_a_is_the_seven_spec_items(book):
    """Part A: item 1 is the chapter's bullets, items 2-7 the top-level `highlights` object."""
    _, report = make(book)
    (chapter,) = report["parts"][0]["chapters"]
    assert len(chapter["bullets"]) == 3 and chapter["paragraphs"]          # item 1
    highlights = report["highlights"]
    assert set(highlights) == {"mangal", "sade_sati", "dasha", "strengths", "cautions", "yogas"}
    assert highlights["mangal"]["verdict"] and highlights["mangal"]["remedy"]
    assert highlights["sade_sati"]["verdict"] and highlights["sade_sati"]["guidance"]
    assert highlights["dasha"]["mood"]
    assert len(highlights["strengths"]) == 3 and len(highlights["cautions"]) == 3   # never a fourth
    assert all(y["name"] and y["text"] for y in highlights["yogas"])


def test_part_d_is_past_then_current_year_then_years_then_blocks(book, facts):
    _, report = make(book)
    timeline = next(part for part in report["parts"] if part["id"] == "timeline")
    ids = [chapter["id"] for chapter in timeline["chapters"]]
    assert ids[0] == "past" and ids[1] == "current_year"
    years = [i for i in ids if i.startswith("year_")]
    blocks = [i for i in ids if i.startswith("block_")]
    assert years == sorted(years) and len(years) == len(facts["timeline"]["near_years"])
    assert blocks == sorted(blocks) and len(blocks) == len(facts["timeline"]["far_blocks"])
    # the current year is the most detailed section: more windows than any single later year
    counts = {chapter["id"]: len(chapter["windows"]) for chapter in timeline["chapters"]}
    assert counts["current_year"] > max(counts[year] for year in years)


def test_part_e_covers_the_six_pillars_and_part_g_is_a_table(book):
    _, report = make(book)
    areas = next(part for part in report["parts"] if part["id"] == "life_areas")
    assert [chapter["id"] for chapter in areas["chapters"]] == [
        "career", "money", "marriage", "health", "education", "family_property"]  # the six Part E deep dives
    # a window's `areas` are {area, text} pairs keyed on the vocabulary platform's renderer knows
    tagged = {a["area"] for part in report["parts"] for c in part["chapters"]
              for w in c["windows"] for a in w["areas"]}
    assert tagged and tagged <= set(engine_facts.AREAS)
    assert all(a["text"] for part in report["parts"] for c in part["chapters"]
               for w in c["windows"] for a in w["areas"])
    table = next(part for part in report["parts"] if part["id"] == "year_table")["chapters"][0]
    assert table["table"]["columns"] and not table["paragraphs"]


# ---- the timeline is the product (Part D) -----------------------------------------------------


def test_every_prediction_is_pinned_to_an_engine_date_range(book, facts):
    _, report = make(book)
    engine_windows = engine_facts.all_windows(facts["timeline"])
    seen = 0
    for part in report["parts"]:
        for chapter in part["chapters"]:
            for window in chapter["windows"]:
                source = engine_windows[window["window_id"]]
                assert window["start"] == source["range"]["start"]
                assert window["end"] == source["range"]["end"]
                assert window["label"] == source["range"]["labels"]["en"]  # engine's own label
                assert window["paragraphs"] and "dasha" in window and "transits" in window
                seen += 1
    assert seen == len(engine_windows) >= 30


def test_a_window_id_the_engine_never_issued_is_rejected_and_retried(book):
    target = window_call(book, 1)

    def invent(call, body, attempt):
        if call.key == target and attempt == 1:  # the retry gets it right
            body["parts"][0]["chapters"][0]["windows"][0]["window_id"] = "w9999"

    fake, report = make(book, mutate=invent)
    rejected = report["meta"]["checks"]["rejected_drafts"]
    assert rejected and all("w9999" in json.dumps(draft) for draft in rejected)
    assert "w9999" not in json.dumps(report["parts"])
    # only the offending part was re-asked, not the whole book
    assert sum(1 for call in fake.calls if call["key"] == target) == 2
    assert sum(1 for call in fake.calls if call["key"] == "E1") == 1


def test_dates_in_the_report_come_from_the_engine_not_from_the_model(book, facts):
    """The model returns an id; the printed range is looked up. It cannot shift a date if it tries."""
    _, report = make(book)
    windows = engine_facts.all_windows(facts["timeline"])
    labels = {window["range"]["labels"]["en"] for window in windows.values()}
    printed = {w["label"] for part in report["parts"] for c in part["chapters"] for w in c["windows"]}
    assert printed <= labels
    assert not re.search(r"in your (?:early |late |mid )?(?:twenties|thirties|forties|30s|40s)",
                         json.dumps(report["parts"]), re.I)


# ---- checks: the AI never calculates, and nothing generic is pasted in -------------------------------------------------------------------------------


def test_generic_filler_is_cut_and_reported():
    empty = ("You have a great deal of potential within you, and if you keep working steadily the "
             "results will come in time, because honest effort is always rewarded in the end.")
    assert [issue.kind for issue in filler_issues(empty)] == ["filler"]
    assert filler_issues(GOOD) == []
    assert [i.kind for i in filler_issues("In conclusion, Shani in the 7th house rewards patience.")] == ["boilerplate"]


def test_filler_survives_a_retry_only_by_being_removed(book):
    def pad(call, body, attempt):
        if call.key == "E1":
            body["parts"][0]["chapters"][0]["paragraphs"].append(
                "You have a great deal of potential within you, and if you keep working steadily and "
                "believe in yourself the results will surely come in time, because honest effort is "
                "always rewarded in the end and good things come to those who are patient and kind.")

    _, report = make(book, mutate=pad)
    everything = json.dumps(report["parts"])
    assert "a great deal of potential" not in everything
    kinds = {r["kind"] for r in report["meta"]["checks"]["redactions"]}
    assert "filler" in kinds


@pytest.mark.parametrize("text, kind", [
    ("Your dashamsha (D10) points to administration.", "untraceable"),
    ("The ashtakavarga gives this house six bindus.", "untraceable"),
    ("There is a planetary war between Shani and Mangal.", "untraceable"),
    ("शनी आणि मंगळ यांच्यात ग्रहयुद्ध आहे.", "untraceable"),
])
def test_fact_types_the_engine_never_computes_are_blocked(text, kind, chart, facts):
    checker = book_facts({"chart": chart, **facts})
    assert kind in {issue.kind for issue in untraceable_issues(text, checker)}


def test_fact_types_the_engine_does_compute_are_allowed(chart, facts):
    checker = book_facts({"chart": chart, **facts})
    for text in ["Guru aspects your 8th, 10th and 12th houses.", "Mangal is debilitated in Karka.",
                 "Surya is vargottama in the navamsa.", "Your Neecha Bhanga Raja Yoga lifts Mangal.",
                 "Shani is not combust in this chart.", "Budha sits in a friendly sign here."]:
        assert untraceable_issues(text, checker) == [], text


def test_the_house_convention_and_transit_rules_still_hold(chart, facts):
    from app.ai.validator import check_text

    checker = book_facts({"chart": chart, **facts})
    # Simha is this chart's LAGNA; it is the 9th only from the Dhanu Moon (the defect that once shipped)
    assert "house_sign" in {i.kind for i in check_text("Your 9th house is Simha, so fortune matters.", checker)}
    assert check_text("Guru sits in the 1st house in Karka.", checker) == []
    assert {i.kind for i in check_text("Chandra in Vrishabha makes you steady.", checker)} == {"sign"}


def test_mangal_dosha_is_never_cancelled_in_the_book(chart, facts):
    from app.ai.validator import check_text

    checker = book_facts({"chart": chart, **facts})
    assert checker.mangal_present
    assert [i.kind for i in check_text("So the dosha is cancelled for your chart.", checker)] == ["wording"]
    assert check_text("The mitigating factors soften the dosha considerably.", checker) == []


def test_unsafe_text_is_removed_from_the_book(book):
    target = window_call(book, 1)

    def scare(call, body, attempt):
        if call.key == target:
            body["parts"][0]["chapters"][0]["windows"][0]["paragraphs"].append(
                "There is a danger of a serious illness for a family member in this window.")

    _, report = make(book, mutate=scare)
    assert "serious illness" not in json.dumps(report["parts"])
    assert {r["type"] for r in report["meta"]["checks"]["redactions"]} == {"safety"}


# ---- gemstones: the deliberate policy reversal (Part F) --------------------------------------


def test_the_engine_gemstone_is_allowed_but_the_sales_pitch_is_not():
    allowed = ["Tradition suggests Manikya (Ruby) for Surya, set in gold and first worn on a Sunday.",
               "Neelam is best avoided for this chart, since Shani rules the 6th.",
               "तुमच्यासाठी माणिक्य सुचवले जाते, ते रविवारी सोन्यात अनामिकेत घालावे."]
    for text in allowed:
        assert screen_text(text, allow_gemstone=True) == [], text
    blocked = [("A good ruby costs around 12000 rupees from a reputable jeweller.", "hard_sell"),
               ("Buy a 5 carat Manikya online and have it energised.", "hard_sell"),
               ("Without this stone your career will stall.", "gem_fear"),
               ("You must wear this stone for the dosha to soften.", "gem_fear"),
               ("Consult an astrologer before you wear it.", "hard_sell"),
               ("नीलम रत्नाची किंमत साधारण बारा हजार रुपये असते.", "hard_sell")]
    for text, category in blocked:
        assert category in {hit.category for hit in screen_text(text, allow_gemstone=True)}, text


def test_gemstones_stay_blocked_everywhere_else():
    for text in ["Wear a blue sapphire.", "नीलम धारण करें।", "पुष्कराज रत्न धारण करा."]:
        assert "gemstone" in {hit.category for hit in screen_text(text)}, text


def test_only_the_gemstone_chapter_may_name_a_stone(book):
    def sell(call, body, attempt):
        if call.key == "F":  # the same line in every Part F chapter: only the gemstone one may keep it
            for chapter in body["parts"][0]["chapters"]:
                chapter["paragraphs"].append(
                    "Tradition suggests Manikya (Ruby) for Surya, worn on a Sunday.")

    _, report = make(book, mutate=sell)
    part_f = next(part for part in report["parts"] if part["id"] == "doshas_remedies")
    chapters = {chapter["id"]: chapter for chapter in part_f["chapters"]}
    assert "Manikya" in json.dumps(chapters["gemstone"])
    assert "Manikya" not in json.dumps(chapters["mangal_dosha"])
    assert {r["kind"] for r in report["meta"]["checks"]["redactions"]} == {"gemstone"}


# ---- prompts and caching ---------------------------------------------------------------------------------


def test_the_system_prompt_keeps_the_interpret_only_sentence_and_the_hard_won_rules():
    assert INTERPRET_ONLY == (
        "Use ONLY the provided chart/transit data; do not calculate positions, dates or degrees yourself.")
    assert INTERPRET_ONLY in BOOK_SYSTEM_PROMPT
    for rule in ["Rahu and Ketu rule no sign and are never \"in their own sign\"",
                 "`rules_houses`", "`in_own_sign`", "house_from_lagna", "house_from_moon",
                 "9th from your Moon sign", "never cancelled, nullified, ineffective",
                 "Never predict or hint at death", "Marathi is not Hindi"]:
        assert rule in BOOK_SYSTEM_PROMPT, rule


def test_both_cached_blocks_are_byte_identical_across_every_call_of_one_report(book):
    fake, _ = make(book)
    systems = {json.dumps(call["system"], ensure_ascii=False) for call in fake.calls}
    assert len(systems) == 1, "the cached prefix moved between calls - every call after the first misses"
    (system,) = [call["system"] for call in fake.calls[:1]]
    assert len(system) == 2 and all(block["cache_control"] == {"type": "ephemeral"} for block in system)
    assert system[0]["text"] == BOOK_SYSTEM_PROMPT
    assert "<chart>" in system[1]["text"] and "dignity" in system[1]["text"]
    # the timeline is deliberately NOT in the cached prefix - it travels per call
    assert "far_blocks" not in system[1]["text"] and "year_table" not in system[1]["text"]
    # one schema for every call, so the structured-output format never varies either
    assert {id(call["schema"]) for call in fake.calls} == {id(CALL_SCHEMA)}


def test_the_frozen_block_is_shared_by_every_chart_and_language(book, facts, chart):
    english, _ = make(book)
    marathi = BookFake(book, headings="mr")
    generate_report("kundali-report", "mr", [KALAM], as_of=AS_OF, client=marathi, use_cache=False)
    assert english.calls[0]["system"][0] == marathi.calls[0]["system"][0]
    # the windows travel per call, and carry the engine's printed range in that report's language
    def timeline_text(fake):
        return "\n".join(call["user"] for call in fake.calls if "<windows>" in call["user"])

    assert "सप्टेंबर" in timeline_text(marathi) and "सप्टेंबर" not in timeline_text(english)
    assert re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", timeline_text(english))


def test_each_call_asks_for_its_own_parts_only(book):
    fake, _ = make(book)
    for call in fake.calls:
        planned = fake.calls_planned[call["key"]]
        for part in planned.parts:
            assert f"part id `{part.id}`" in call["user"]
            for chapter in part.chapters:
                assert f"chapter id `{chapter.id}`" in call["user"]
                for wid in chapter.window_ids:
                    assert f"`{wid}`" in call["user"]
        assert "English" in call["user"] and AS_OF.isoformat() in call["user"]


def test_the_cached_prefix_stays_small_and_excludes_the_timeline(book, facts, chart):
    """The engine's facts are ~370 KB. Putting the timeline in the cached prefix would cost a ~₹22
    cache write before a word is written, so only the chart-wide facts go there."""
    from app.ai.compact import book_prefix

    text = json.dumps(book_prefix(chart, facts, "mr", AS_OF.isoformat()), ensure_ascii=False)
    assert len(text) < 40_000, "the cached prefix is growing; check what was added to book_prefix"
    assert len(text) > 4_000
    for timeline_only in ("far_blocks", "year_table", "window_indexes", "why_it_starts_here"):
        assert timeline_only not in text, f"{timeline_only} belongs in the per-call message"


# ---- cost, meta and the PDF contract -------------------------------------------------------------------


def test_cost_is_tracked_per_part_and_in_total(book):
    fake, report = make(book)
    meta = report["meta"]
    assert meta["model"] == "claude-sonnet-5" and len(fake.calls) == len(meta["calls"])
    assert {row["call"] for row in meta["calls"]} == set(fake.calls_planned)
    assert all(row["attempts"] == 1 and row["usage"]["output_tokens"] == 2500 for row in meta["calls"])
    assert meta["usage"]["output_tokens"] == 2500 * len(fake.calls)
    # exactly one cache write, then a read on every later call: this is what the sectioning buys
    assert meta["usage"]["cache_creation_input_tokens"] == 16000
    assert meta["usage"]["cache_read_input_tokens"] == 16000 * (len(fake.calls) - 1)
    assert meta["cost_estimate_inr"] > 0 and meta["checks"]["clean"]


def test_the_flat_sections_view_still_renders_for_the_current_pdf(book):
    _, report = make(book)
    assert len(report["sections"]) == sum(len(part["chapters"]) for part in report["parts"])
    for section in report["sections"]:
        assert set(section) == {"id", "heading", "paragraphs", "subsections", "bullets", "table"}
        assert section["heading"]
        assert section["paragraphs"] or section["subsections"] or section["bullets"] or section["table"]
    timeline = [s for s in report["sections"] if s["id"].startswith("timeline.")]
    assert all(sub["heading"] and sub["paragraphs"] for s in timeline for sub in s["subsections"])


def test_the_report_carries_the_engine_data_the_pdf_draws_from(book):
    _, report = make(book)
    data = report["data"]
    assert set(data) >= {"chart", "navamsa", "dignity", "aspects", "yogas", "highlights", "gemstone",
                         "dhaiya", "timeline"}
    assert data["chart"]["lagna"]["sign"]["name"] == "Karka"   # the reference chart
    assert data["timeline"]["windows"] and data["timeline"]["year_table"]
    assert report["disclaimer"] and report["remedies"] and report["title"] and report["summary"]


def test_one_bad_part_never_costs_the_whole_book(book):
    """A part that cannot be written cleanly fails on its own; the book is not sold half-written."""
    def wreck(call, body, attempt):
        if call.key == "E2":
            body["parts"][0]["chapters"] = body["parts"][0]["chapters"][:1]

    with pytest.raises(book_report.SectionFailed) as failure:
        make(book, mutate=wreck)
    assert "E2" in str(failure.value)


def test_a_chart_with_no_gemstone_or_yogas_simply_has_fewer_chapters(facts):
    lean = {**facts, "yogas": [], "gemstone": {"recommended": []}}
    parts = {part.id: part for part in build_book(lean)}
    assert [chapter.id for chapter in parts["doshas_remedies"].chapters] == ["mangal_dosha", "sade_sati"]
    from app.ai.book import highlight_keys

    assert "yogas" not in highlight_keys(lean) and "yogas" in highlight_keys(facts)
    assert len(plan(build_book(lean))) == len(plan(build_book(facts)))


def test_schema_fits_the_structured_output_limits():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for banned in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "pattern"):
                assert banned not in node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(CALL_SCHEMA)


def test_call_problems_catches_what_the_schema_cannot(book):
    call = plan(book)[0]
    good = BookFake(book)
    body = good.generate_json(system="s", user=good_prompt(call), schema=CALL_SCHEMA).data
    assert call_problems(call, body, 5) == ([], [])
    body["highlights"]["strengths"] = ["only one"]
    fatal, repairable = call_problems(call, body, 5)
    assert any("strengths" in problem for problem in fatal) and repairable == []
    assert call_problems(call, {"parts": []}, 5) == (
        ["parts must be exactly ['highlights'] in this order; got []"], [])


def good_prompt(call) -> str:
    from app.ai.prompts import build_call_prompt

    return build_call_prompt(call, "en", AS_OF.isoformat(),
                             extra={"highlights": "fill `highlights`"} if call.wants_highlights else None)


def test_cache_hit_avoids_every_ai_call(book, tmp_path):
    fake = BookFake(book)
    first = generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=fake)
    made = len(fake.calls)
    second = generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=fake)
    assert len(fake.calls) == made and second["meta"]["cache_hit"] is True
    assert second["parts"] == first["parts"]


def test_chapters_promoted_to_parts_are_re_nested_rather_than_thrown_away(book):
    """The first real run returned PART D's two chapters as three top-level parts. The writing was
    fine; only the nesting was wrong, so it is repaired instead of costing a whole book."""
    target = window_call(book, 2)
    call = next(c for c in plan(book) if c.key == target)

    def mis_nest(made, body, attempt):
        if made.key == target and attempt == 1:
            part = body["parts"][0]
            first, second = part["chapters"][0], part["chapters"][-1]
            body["parts"] = [{"id": part["id"], "heading": part["heading"], "chapters": [first]},
                             {"id": second["id"], "heading": "stray", "chapters": [second]},
                             {"id": second["id"], "heading": "stray again", "chapters": []}]

    fake, report = make(book, mutate=mis_nest)
    timeline = next(p for p in report["parts"] if p["id"] == "timeline")
    ids = [chapter["id"] for chapter in timeline["chapters"]]
    for chapter in call.parts[0].chapters:
        assert chapter.id in ids
    assert len(ids) == len(set(ids))
    # repaired in place: no second call was needed for that part
    assert sum(1 for c in fake.calls if c["key"] == target) == 1
    assert report["meta"]["checks"]["clean"]


# ---- guarantees that must never be quietly loosened -----------------------------------------------
#
# The three tests below exist because each one guards a defect that actually shipped, or would have.
# If a future change makes one of them fail, the fix is the code, not the test.


def test_GUARANTEE_transit_claims_are_scoped_to_their_own_window_not_the_whole_book(facts, chart):
    """Over a ~20-year book a slow graha visits EVERY sign, so a whole-span check accepts anything.

    "Guru enters your 9th house" is a real event somewhere in this book - but in the window where Guru
    enters the 1st it is the exact defect that shipped in the chat layer. Scoping each window's prose
    to that window's own transits is what stops it. Do not widen this back to the full fact set.
    """
    from app.ai.validator import check_text, narrow_to_window

    checker = book_facts({"chart": chart, **facts})
    windows = engine_facts.all_windows(facts["timeline"])
    guru_window = next(w for w in windows.values()
                       if any(t["graha"]["key"] == "Jupiter" and t["date"].startswith("2027-01")
                              for t in w.get("transits") or []))
    scoped = narrow_to_window(checker, guru_window)

    # unscoped, the claim passes - that is precisely why scoping exists
    assert check_text("Guru enters your 9th house around 25 January 2027.", checker) == []
    assert "house" in {i.kind for i in
                       check_text("Guru enters your 9th house around 25 January 2027.", scoped)}
    assert check_text("Guru enters Karka, your 1st house (9th from your Moon sign), on 25 January 2027.",
                      scoped) == []


def test_GUARANTEE_a_wrong_sign_is_caught_after_a_movement_verb_not_only_after_in(facts, chart):
    """The sign check used to fire only on "in Mesha", so "enters Mesha" walked straight past it."""
    from app.ai.validator import check_text, narrow_to_window

    checker = book_facts({"chart": chart, **facts})
    windows = engine_facts.all_windows(facts["timeline"])
    window = next(w for w in windows.values()
                  if any(t["graha"]["key"] == "Jupiter" and t["date"].startswith("2027-01")
                         for t in w.get("transits") or []))
    scoped = narrow_to_window(checker, window)
    for wrong in ["Shani enters Mesha in this window.", "Guru moves into Kanya now.",
                  "Shani shifts into Vrishabha here.", "Guru returns to Meena this month."]:
        assert "sign" in {i.kind for i in check_text(wrong, scoped)}, wrong
    assert check_text("Guru enters Karka on 25 January 2027.", scoped) == []


def test_GUARANTEE_the_model_never_writes_a_windows_date_range(book):
    """platform prints the one canonical label from the engine's ISO pair. A second, model-written
    range can only duplicate or contradict it, so it is blocking inside window prose."""
    from app.ai.validator import written_range_issues

    for wrong in ["Jan 2028 – May 2028 brings steady work.", "From Jan to May 2028 things settle.",
                  "जानेवारी 2028 ते मे 2028 या काळात प्रगती आहे."]:
        assert [i.kind for i in written_range_issues(wrong)] == ["date_range"], wrong
    assert written_range_issues("The Rahu-Guru antardasha turns over during this stretch.") == []

    target = window_call(book, 1)

    def restate(call, body, attempt):
        if call.key == target:
            body["parts"][0]["chapters"][0]["windows"][0]["paragraphs"].append(
                "Jan 2028 – May 2028 is the stretch that matters here.")

    _, report = make(book, mutate=restate)
    assert "Jan 2028 – May 2028" not in json.dumps(report["parts"])
    assert "date_range" in {r["kind"] for r in report["meta"]["checks"]["redactions"]}


def test_GUARANTEE_engine_iso_dates_pass_through_untouched(book, facts):
    """start/end are the engine's ISO strings, byte for byte. The AI never formats a date."""
    _, report = make(book)
    windows = engine_facts.all_windows(facts["timeline"])
    checked = 0
    for part in report["parts"]:
        for chapter in part["chapters"]:
            for written in chapter["windows"]:
                source = windows[written["window_id"]]["range"]
                assert written["start"] == source["start"] and written["end"] == source["end"]
                assert written["label"] == source["labels"]["en"]
                checked += 1
    assert checked >= 30


def test_GUARANTEE_the_output_schema_stays_inside_the_api_grammar_limit():
    """The API compiles the structured-output schema into a grammar and 400s when it is too big:
    "The compiled grammar is too large, which would cause performance issues."

    This is not theoretical - it happened, and because ONE schema is shared by every call of every
    report, it failed the whole product rather than one section. The limit cannot be checked offline,
    so `schema_weight` stands in for it, calibrated against the real API: 24 compiles, 27 does not.

    If this fails, do not just raise the budget. Take something out, or probe a real request first.
    """
    from app.ai.schema import GRAMMAR_BUDGET, schema_weight

    weight = schema_weight(CALL_SCHEMA)
    assert weight <= GRAMMAR_BUDGET, (
        f"The output schema now weighs {weight}, over the {GRAMMAR_BUDGET} the API was measured to "
        f"accept. It will 400 with \"compiled grammar is too large\" on EVERY call, so no Kundali "
        f"report can be produced at all.\n"
        f"Do not just raise this number, and do not give each call its own schema - "
        f"`output_config.format` is part of the prompt-cache key, so per-call schemas cost ~₹18 a "
        f"report in lost caching.\n"
        f"The fix is to split into TWO cache groups: the calls that need `highlights` share one "
        f"schema, the rest share another. Two cache writes instead of one is ~₹1.8 a report and puts "
        f"both schemas far below the ceiling. See the comment above GRAMMAR_BUDGET in app/ai/schema.py.")


def test_the_flat_schema_shapes_are_rebuilt_into_the_published_contract():
    """`highlights` and a window's `areas` are flat in the schema purely to keep the grammar small;
    the report publishes the nested shape platform reads."""
    from app.ai.schema import nest_highlights, pair_areas

    flat = {"mangal_verdict": "present", "mangal_remedy": "serve", "sade_sati_verdict": "not running",
            "sade_sati_guidance": "steady", "dasha_mood": "restless",
            "strengths": ["a", "b", "c"], "cautions": ["d", "e", "f"],
            "yoga_names": ["Sasa Yoga"], "yoga_lines": ["staying power"]}
    assert nest_highlights(flat) == {
        "mangal": {"verdict": "present", "remedy": "serve"},
        "sade_sati": {"verdict": "not running", "guidance": "steady"},
        "dasha": {"mood": "restless"},
        "strengths": ["a", "b", "c"], "cautions": ["d", "e", "f"],
        "yogas": [{"name": "Sasa Yoga", "text": "staying power"}]}
    assert nest_highlights({}) == {} and nest_highlights(None) == {}
    assert pair_areas({"areas": ["career", "money"], "area_lines": ["work", "savings"]}) == [
        {"area": "career", "text": "work"}, {"area": "money", "text": "savings"}]
    assert pair_areas({"areas": [], "area_lines": []}) == []


def test_GUARANTEE_no_heading_in_a_hindi_or_marathi_book_is_left_in_english(book):
    """The contents page is auto-generated from the headings and is page two of a paid book.

    Found live: the year and block chapters came back headed "Year 2028" / "Block 2032" in a Marathi
    book. Nothing failed - body text was Devanagari and every other check passed - so this test
    covers every heading the TOC can print: the title, part headings, chapter headings and table
    headers.
    """
    from app.ai.validator import untranslated_heading

    english_headings = BookFake(book)
    with pytest.raises(book_report.SectionFailed):
        # the fake heads chapters off their English ids, which is exactly the defect
        generate_report("kundali-report", "mr", [KALAM], as_of=AS_OF, client=english_headings,
                        use_cache=False)

    # and the check itself: Latin words fail, Latin digits and bracketed glosses do not
    for bad in ["Year 2028", "Block 2032", "Doshas Remedies", "Career and Profession"]:
        assert untranslated_heading(bad, "mr") is not None, bad
        assert untranslated_heading(bad, "hi") is not None, bad
        assert untranslated_heading(bad, "en") is None, bad
    for fine in ["वर्ष 2028", "2032 – 2036", "2028", "मीन (Pisces) मधील प्रवास", "करिअर आणि व्यवसाय", ""]:
        assert untranslated_heading(fine, "mr") is None, fine


def test_a_devanagari_book_passes_the_heading_check_end_to_end(book):
    """The same book with Devanagari headings generates cleanly - the check is not just always-fail."""
    marathi = BookFake(book, headings="mr")
    report = generate_report("kundali-report", "mr", [KALAM], as_of=AS_OF, client=marathi,
                             use_cache=False)
    from app.ai.validator import untranslated_heading

    headings = [report["title"]]
    for part in report["parts"]:
        headings.append(part["heading"])
        headings += [chapter["heading"] for chapter in part["chapters"]]
        headings += [" | ".join((chapter["table"] or {}).get("columns") or [])
                     for chapter in part["chapters"]]
    assert len(headings) > 20
    assert [h for h in headings if untranslated_heading(h, "mr")] == []


def test_challenging_yogas_carry_the_engines_own_framing_into_the_prompt(facts, chart):
    """The engine attaches `framing` to a challenging yoga and it is specific to that yoga - Pitra
    Dosha's says to frame it as remembrance of ancestors. Our generic fallback is strictly worse, so
    it must never quietly replace the real one."""
    from app.ai.compact import book_prefix

    challenging = [y for y in facts["yogas"] if y.get("nature") == "challenging"]
    assert challenging, "the reference chart is supposed to have at least one challenging yoga"
    prefix = json.dumps(book_prefix(chart, facts, "en", AS_OF.isoformat()), ensure_ascii=False)
    for yoga in challenging:
        framing = (yoga.get("framing") or "").strip()
        assert framing, f"{yoga['name']} has no engine framing - check the engine, not this test"
        assert framing in prefix, f"{yoga['name']}'s own framing never reached the prompt"


def test_every_caution_carries_its_tone_and_a_health_one_carries_the_health_framing(facts, chart):
    """`frame` and `framing` are different engine fields and both matter; reading one loses safety
    wording the engine deliberately attached."""
    from app.ai.compact import book_prefix

    prefix = json.dumps(book_prefix(chart, facts, "en", AS_OF.isoformat()), ensure_ascii=False)
    cautions = facts["highlights"]["top_cautions"]
    assert cautions
    for caution in cautions:
        assert caution["frame"] in prefix
        if caution.get("health_related"):
            assert (caution.get("framing") or facts["highlights"]["health_framing"]) in prefix
    assert facts["highlights"]["safety"] in prefix


def test_the_writer_reads_areas_not_the_deprecated_pillars_alias(facts, chart):
    """calc-engine-2 keeps `pillars` only because this layer used to read it. Nothing here may."""
    import app.ai.compact as compact_module
    import app.ai.engine_facts as engine_facts_module

    for module in (compact_module, engine_facts_module):
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert '"pillars"' not in source, f"{module.__name__} still reads the deprecated alias"

    stripped = copy.deepcopy(facts)
    for window in stripped["timeline"]["windows"]:
        window.pop("pillars", None)
    tagged = {area for window in stripped["timeline"]["windows"]
              for area in engine_facts.window_areas(window)}
    assert tagged, "area tags vanished once the deprecated alias was removed"
    assert tagged <= set(engine_facts.AREAS)


def test_GUARANTEE_headings_are_short_and_distinct_because_they_are_the_contents_page(book):
    """platform's TOC runs to ~97 entries, each a heading beside leader dots and a page number.

    A heading that runs to a sentence wraps and pushes that layout around; two identical headings
    leave the reader no way to tell the entries apart. Neither is visible until a real chart makes
    one, so both are checked rather than hoped for.
    """
    from app.ai.schema import (
        MAX_COMPOSED_HEADING_CHARS,
        MAX_COMPOSED_HEADING_WORDS,
        MAX_HEADING_CHARS,
        MAX_HEADING_WORDS,
        heading_problems,
    )

    assert heading_problems("x", "वर्ष 2028") == [] and heading_problems("x", "2032 – 2036") == []
    assert heading_problems("x", "What this year asks of you across career, money and marriage too")
    assert heading_problems("x", "अ " * (MAX_HEADING_WORDS + 1))
    assert heading_problems("x", "अ" * (MAX_HEADING_CHARS + 1))

    _, report = make(book)
    headings = [report["title"]]
    for part in report["parts"]:
        headings.append(part["heading"])
        headings += [chapter["heading"] for chapter in part["chapters"]]
    assert len(headings) > 20
    for heading in headings:
        # A span chapter's printed heading is the engine's label plus the model's theme, so the
        # ceiling here is the composed one; `call_problems` caps the model's own part more tightly.
        assert len(heading) <= MAX_COMPOSED_HEADING_CHARS, heading
        assert len(heading.split()) <= MAX_COMPOSED_HEADING_WORDS, heading
    folded = [" ".join(h.split()).casefold() for h in headings if h.strip()]
    assert len(folded) == len(set(folded)), "two entries in the contents page read the same"


def test_two_chapters_headed_the_same_in_one_call_are_rejected_and_retried(book):
    """Part E's chapters carry no engine span, so nothing can tell two identical headings apart."""
    def clash(call, body, attempt):
        if call.key == "E1" and attempt == 1:
            for chapter in body["parts"][0]["chapters"]:
                chapter["heading"] = "Work And Money"

    fake, report = make(book, mutate=clash)
    rejected = report["meta"]["checks"]["rejected_drafts"]
    assert any("word for word the same" in json.dumps(draft) for draft in rejected)
    assert sum(1 for c in fake.calls if c["key"] == "E1") == 2


def test_span_chapters_may_share_a_theme_because_the_engine_label_tells_them_apart(book):
    """Two years can honestly have the same theme. The printed heading is the engine's span plus that
    theme, so they still read distinctly - and the model never writes the span itself."""
    same_theme = BookFake(book)   # the fake gives every span chapter the same theme on purpose
    report = generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=same_theme,
                             use_cache=False)
    timeline = next(p for p in report["parts"] if p["id"] == "timeline")
    spans = [c["heading"] for c in timeline["chapters"] if c["id"].startswith(("year_", "block_"))]
    assert len(spans) == len(set(spans)) and len(spans) >= 8
    assert all(" — " in heading for heading in spans), spans
    assert report["meta"]["checks"]["clean"] or not [
        w for w in report["meta"]["checks"]["warnings"] if w["kind"] == "duplicate_heading"]


def test_a_duplicate_heading_across_calls_is_reported_not_thrown_away(book):
    """Across calls the collision is found only at assembly, when every call is already paid for.
    Nine good parts are worth more than a tidy contents page, so it is a warning, not a failure."""
    from app.ai.book_report import duplicate_headings

    clashes = duplicate_headings("Your Kundali", [
        {"id": "timeline", "heading": "The Years Ahead",
         "chapters": [{"id": "year_2028", "heading": "Steady Ground"}]},
        {"id": "life_areas", "heading": "Steady Ground", "chapters": []},
    ])
    assert [c["kind"] for c in clashes] == ["duplicate_heading"]
    assert "Steady Ground" in clashes[0]["found"]
    assert duplicate_headings("A", [{"id": "p", "heading": "B", "chapters": [
        {"id": "c", "heading": "C"}]}]) == []


def test_a_chapter_that_comes_back_empty_fails_loudly_rather_than_shipping_thin(book):
    """The worst failure seen live: the model wrote a call's first chapter properly and returned the
    rest empty - no error, no truncation, no refusal. That is indistinguishable from a chart with
    little to say, so it would have shipped as a quietly thin book at full price.

    This used to empty `chapters[1:]`, the "rest" of a multi-chapter call. Timeline calls carry ONE
    chapter each now (app/ai/book.py `plan`, and the test below), precisely because the second chapter
    was the one being abandoned - so that slice is empty and the mutation did nothing. What has to stay
    true is the general form: a chapter that comes back empty fails the order, whichever chapter it is.
    """
    target = window_call(book, 2)

    def go_quiet(call, body, attempt):
        if call.key == target:
            for chapter in body["parts"][0]["chapters"]:
                chapter["windows"] = []

    with pytest.raises(book_report.SectionFailed):
        make(book, mutate=go_quiet)


def test_no_timeline_call_asks_for_more_than_one_chapter(facts):
    """Measured against the live API in both languages: asked for `year_2030` + `year_2031` in one
    call, Sonnet wrote 2030 in full and abandoned 2031 - in Marathi as a part with a heading and no
    body, in English as a part it named `year_2031_placeholder_unused`. `stop_reason` was `end_turn`
    and the output a sixth of the cap, so nothing was truncated: the SECOND chapter is what gets
    dropped, and a paid book died on it.

    Window count is not the variable and this is why the old cap is gone: `D-now` writes fifteen
    windows reliably in one chapter, while the call that failed carried five across two.
    """
    for tier in ("detailed", "simple"):
        for call in plan(build_book(facts, tier), tier):   # each tier builds its own parts
            chapters = [chapter for part in call.parts for chapter in part.chapters]
            if any(chapter.windows for chapter in chapters):
                assert len(chapters) == 1, (tier, call.key, [c.id for c in chapters])


def test_the_batched_path_produces_the_same_book_as_the_threaded_one(book, monkeypatch):
    """`REPORT_BATCH=1` changes price and latency, not the model, the prompt or the checks.

    Both paths share `judge_draft` and `finish_call`, so this asserts they really do agree - if they
    ever diverge, one of them is running a different rulebook, which is exactly the bug that would
    be invisible until a customer got a book the other path would have refused.
    """
    threaded = BookFake(book)
    a = generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=threaded, use_cache=False)

    monkeypatch.setenv("REPORT_BATCH", "1")
    batchy = BookFake(book)
    b = generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=batchy, use_cache=False)

    assert batchy.batches, "the batch path never called generate_json_batch"
    assert len(batchy.batches) == 1, "a clean book should need exactly one batch round"
    # one call is made synchronously first to write the prompt cache - measured, 8 of 12 requests
    # missed it without that - so the batch itself carries every call but that one
    warmed = set(threaded.calls_planned) - set(batchy.batches[0])
    assert len(warmed) == 1, f"expected exactly one warm-up call outside the batch, got {warmed}"
    assert sorted(batchy.batches[0]) == sorted(set(threaded.calls_planned) - warmed)
    for key in ("parts", "sections", "highlights", "gemstone", "remedies", "title", "summary"):
        assert a[key] == b[key], key


def test_a_failed_part_in_a_batch_is_retried_in_the_next_round_only(book, monkeypatch):
    """A retry is a whole extra round, so only the parts that failed may be in it - re-sending the
    clean ones would double the bill for nothing."""
    monkeypatch.setenv("REPORT_BATCH", "1")
    target = window_call(book, 1)

    def invent(call, body, attempt):
        if call.key == target and attempt == 1:
            body["parts"][0]["chapters"][0]["windows"][0]["window_id"] = "w9999"

    fake = BookFake(book, mutate=invent)
    report = generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=fake, use_cache=False)
    assert len(fake.batches) == 2
    assert fake.batches[1] == [target], f"round 2 should be only the failed part, got {fake.batches[1]}"
    assert "w9999" not in json.dumps(report["parts"])
    assert report["meta"]["checks"]["clean"]


def test_a_batch_item_that_never_returns_fails_the_book_rather_than_shipping_without_it(book, monkeypatch):
    from app.ai.client import AIUnavailable

    monkeypatch.setenv("REPORT_BATCH", "1")
    monkeypatch.setenv("BOOK_PART_ATTEMPTS", "1")

    class Dropping(BookFake):
        def generate_json_batch(self, requests, **kwargs):
            out = super().generate_json_batch(requests, **kwargs)
            out[requests[-1]["custom_id"]] = AIUnavailable("batch item expired")
            return out

    with pytest.raises(book_report.SectionFailed):
        generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=Dropping(book),
                        use_cache=False)


@pytest.mark.parametrize("areas, lines", [
    (["career"], ["a", "b", "c"]),      # more lines than areas - crashed a live batch round
    (["career", "money"], []),          # areas with no lines at all
    ([], ["a"]),                        # a line with no area
    (["career", "money", "health"], ["a"]),
])
def test_ragged_area_pairs_never_crash_or_lose_the_book(book, areas, lines):
    """`areas` and `area_lines` are paired by index and the model does not always return them the
    same length. A live batch round died with IndexError in `text_slots` on the first case - a whole
    paid round lost to a zip that assumed they matched. Every consumer must zip defensively."""
    from app.ai.book_report import text_slots
    from app.ai.schema import pair_areas

    def ragged(call, body, attempt):
        for part in body["parts"]:
            for chapter in part["chapters"]:
                for window in chapter["windows"]:
                    window["areas"], window["area_lines"] = list(areas), list(lines)

    _, report = make(book, mutate=ragged)
    for part in report["parts"]:
        for chapter in part["chapters"]:
            for window in chapter["windows"]:
                assert len(window["areas"]) <= min(len(areas), len(lines))
                assert all(a["area"] and a["text"] for a in window["areas"])

    # and the slot walker itself, directly
    body = {"parts": [{"id": "timeline", "heading": "h", "intro": "", "chapters": [
        {"id": "past", "heading": "h", "paragraphs": [], "bullets": [], "table": None,
         "windows": [{"window_id": "w", "headline": "h", "paragraphs": ["p"],
                      "areas": list(areas), "area_lines": list(lines)}]}]}]}

    class _Chapter:
        id, shape, windows, labels = "past", "windows", (), {}

    class _Part:
        id, label, brief, chapters = "timeline", "D", "", (_Chapter(),)

    class _Call:
        key, parts = "D", (_Part(),)
        wants_front_matter = wants_remedies = wants_highlights = wants_gemstone = False

    assert len(list(text_slots(_Call(), body))) >= 1
    assert len(pair_areas(body["parts"][0]["chapters"][0]["windows"][0])) <= min(len(areas), len(lines))


# =====================================================================================================
# THE FAKE EXISTS TO BE A DIFFICULT MODEL, NOT A COOPERATIVE ONE.
#
# `BookFake` returns what we INTENDED the model to return, so it can only find bugs in code that
# handles correct input. Every plumbing bug this project has paid to discover live came from output
# that was valid JSON but ragged: chapters promoted to parts, more area lines than areas, a heading
# one word over, chapters returned empty, results out of order. None of those are exotic - they are
# what a real model does routinely - and a cooperative fake cannot find the code that mishandles them.
#
# A cooperative fake gives false confidence in proportion to how much you rely on it, and this project
# relies on it heavily precisely because live runs cost money. So: ragged everywhere at once, driven
# end to end through generation, checking, assembly, repair and render.
#
# AND IT MUST BE DETERMINISTIC. An adversarial fake keyed off a nondeterministic counter is worse than
# no fake at all, because it teaches you to re-run rather than to look - a real failure then hides
# behind "try it again". This one keys off each call's position in the plan, which is stable across
# threads and covers the whole mutation catalogue whatever the call set is.
# =====================================================================================================


class AwkwardFake(BookFake):
    """Valid JSON, ragged in every way a real model has actually been ragged.

    Everything here is RECOVERABLE on purpose - the book must still come out complete. The
    unrecoverable shapes (a chapter that stays empty, a batch item that never returns) have their own
    tests asserting they fail loudly instead.
    """

    # Every raggedness this fake can produce. A call draws from here by its POSITION in the plan, so
    # the set is covered whatever the calls are called and however many there are - keying off the
    # call name meant the Simple tier's three keys happened to draw only the mild ones, and its
    # duplicate-window-id case was hard-coded to a call id that tier does not even have.
    MUTATIONS = ("long_heading", "blank_heading", "clashing_heading")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.applied = set()

    def generate_json(self, *, system, user, schema):
        result = super().generate_json(system=system, user=user, schema=schema)
        body = result.data
        # Keyed off the call's POSITION, never off len(self.calls): the threaded path runs calls
        # concurrently, so a counter makes the fake behave differently run to run - which showed up
        # as a flaky test and would have hidden a real failure behind "try it again".
        call = self._which(user)
        order = sorted(self.calls_planned)
        index = order.index(call.key)
        attempt = self.attempts.get(call.key, 1)

        for part in body.get("parts") or []:
            for chapter_index, chapter in enumerate(part.get("chapters") or []):
                mutation = self.MUTATIONS[(index + chapter_index) % len(self.MUTATIONS)]
                if mutation == "clashing_heading" and chapter_index:
                    mutation = "long_heading"   # a clash is plausible once per part, not everywhere
                self.applied.add(mutation)
                if mutation == "long_heading":
                    chapter["heading"] = ("An Extremely Long Chapter Heading For "
                                          f"{chapter['id']} That Goes Well Past Any Sensible "
                                          "Contents Page Limit Indeed")
                elif mutation == "blank_heading":
                    chapter["heading"] = ""
                else:
                    chapter["heading"] = "The Same Heading Twice"   # an exact clash, to be repaired
                for w, window in enumerate(chapter.get("windows") or []):
                    # ragged area pairs, in BOTH directions, within every windowed chapter
                    if w % 2:
                        window["areas"], window["area_lines"] = ["career", "money"], ["only one line"]
                        self.applied.add("fewer_lines_than_areas")
                    else:
                        window["areas"], window["area_lines"] = ["career"], ["one", "two", "three"]
                        self.applied.add("more_lines_than_areas")
                # a duplicated window id, in whatever call actually has a chapter with two windows
                if attempt == 1 and len(chapter.get("windows") or []) > 1:
                    chapter["windows"][1]["window_id"] = chapter["windows"][0]["window_id"]
                    self.applied.add("duplicate_window_id")

        # Mis-nesting, in whichever direction this call's shape allows. Both are things `normalise`
        # must repair, and which one is even POSSIBLE depends on the call: a one-part call can have
        # its chapters promoted to parts (seen live), while a multi-part call can have them all
        # collapsed under the first parent. The Simple tier only ever has the second shape.
        parts_out = body.get("parts") or []
        if len(parts_out) == 1 and len(parts_out[0].get("chapters") or []) > 1:
            part = parts_out[0]
            first, rest = part["chapters"][0], part["chapters"][1:]
            body["parts"] = [{"id": part["id"], "heading": part["heading"], "intro": part.get("intro", ""),
                              "chapters": [first]}]
            body["parts"] += [{"id": c["id"], "heading": "stray", "intro": "", "chapters": [c]}
                              for c in rest]
            self.applied.add("mis_nested_chapters")
        elif len(parts_out) > 1:
            everything = [c for part in parts_out for c in part.get("chapters") or []]
            body["parts"] = [{"id": parts_out[0]["id"], "heading": parts_out[0]["heading"],
                              "intro": parts_out[0].get("intro", ""), "chapters": everything}]
            body["parts"] += [{"id": part["id"], "heading": "", "intro": "", "chapters": []}
                              for part in parts_out[1:]]
            self.applied.add("mis_nested_chapters")

        # every part heading blank - platform's contract allows it and falls back
        for part in body["parts"]:
            part["heading"] = ""
        self.applied.add("blank_part_heading")
        return result


def test_an_awkward_model_still_produces_a_complete_valid_book(book):
    """The whole path - generation, checking, assembly, repair, the flat view and the renderer -
    against a model that is ragged everywhere at once. Nothing may crash, and nothing may be
    silently dropped."""
    import sys

    sys.path.insert(0, "scripts")
    from live_report_check import book_words, to_markdown

    fake = AwkwardFake(book)
    report = generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=fake, use_cache=False)

    # every chapter the plan asked for survived
    planned = {(part.id, chapter.id) for part in book for chapter in part.chapters}
    got = {(part["id"], chapter["id"]) for part in report["parts"] for chapter in part["chapters"]}
    assert planned == got, f"content was dropped: {sorted(planned - got)}"

    # the published shape is still well formed
    for part in report["parts"]:
        assert set(part) == {"id", "label", "heading", "intro", "chapters"}
        for chapter in part["chapters"]:
            assert set(chapter) == {"id", "heading", "paragraphs", "bullets", "subsections",
                                    "windows", "table"}
            for window in chapter["windows"]:
                assert window["start"] and window["end"] and window["label"]
                assert all(a["area"] and a["text"] for a in window["areas"]), "half-empty area pair"
                assert len({a["area"] for a in window["areas"]}) == len(window["areas"])
            ids = [w["window_id"] for w in chapter["windows"]]
            assert len(ids) == len(set(ids)), "a duplicated window id reached the book"

    # Headings: the contract is "repaired when we have the means, reported when we do not" - a
    # chapter with an engine span label is disambiguated with it, and one without has nothing to be
    # told apart by, so the collision is recorded rather than hidden. Never silently duplicated.
    headings = [(f"{p['id']}.{c['id']}", c["heading"]) for p in report["parts"] for c in p["chapters"]]
    seen, unrepaired = {}, set()
    for where, heading in headings:
        key = " ".join(heading.split()).casefold()
        if not key:
            continue
        if key in seen:
            unrepaired.add(where)
        seen[key] = where
    reported = {w["where"].split(" chapter ")[-1]
                for w in report["meta"]["checks"]["warnings"] if w["kind"] == "duplicate_heading"}
    for where in unrepaired:
        assert where.split(".")[-1] in reported, (
            f"{where} duplicates another heading and was not reported in meta.checks")

    # the flat compatibility view and the renderer both survive it
    assert len(report["sections"]) == len(got)
    markdown = to_markdown(report)
    assert len(markdown) > 2000 and book_words(report) > 100


def test_the_awkward_model_is_actually_awkward(book):
    """Guard against the fake quietly becoming cooperative again - if this passes trivially, the
    test above is no longer testing anything."""
    fake = AwkwardFake(book)
    generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=fake, use_cache=False)
    assert len(fake.calls) > len(fake.calls_planned), "no call was retried - the fake is too easy"
    rejected = json.dumps(fake and [c["key"] for c in fake.calls])
    assert "D-now" in rejected


# ---- the Simple tier (Rs 49) --------------------------------------------------------------------


@pytest.fixture(scope="module")
def simple_book(facts):
    return build_book(facts, "simple")


def simple(book_simple, **kwargs):
    fake = BookFake(book_simple, **kwargs)
    return fake, generate_report("kundali-report-simple", "en", [KALAM], as_of=AS_OF, client=fake,
                                 use_cache=False)


def test_the_simple_tier_is_its_own_product_not_a_truncated_book(simple_book):
    fake, report = simple(simple_book)
    assert report["product"] == "kundali-report-simple" and report["tier"] == "simple"
    assert [part["id"] for part in report["parts"]] == [
        "highlights", "chart_basics", "timeline", "doshas_remedies", "closing"]
    # what it deliberately does NOT carry is what the Detailed tier sells
    ids = {part["id"] for part in report["parts"]}
    assert "personality" not in ids and "life_areas" not in ids and "year_table" not in ids
    timeline = next(p for p in report["parts"] if p["id"] == "timeline")
    assert [c["id"] for c in timeline["chapters"]] == ["current_year"]
    assert not any(c["id"].startswith(("year_", "block_", "past")) for c in timeline["chapters"])
    assert len(fake.calls) == 3, "the Simple tier is three calls"
    assert report["title"] and report["summary"] and report["highlights"] and report["remedies"]


def test_the_simple_tier_shares_every_correctness_guarantee(simple_book, facts):
    """A wrong Rs 49 report is worse than no Rs 49 report, so nothing is relaxed for the cheap tier.
    Dates still come from the engine, and the same checks still fire."""
    _, report = simple(simple_book)
    windows = engine_facts.all_windows(facts["timeline"])
    seen = 0
    for part in report["parts"]:
        for chapter in part["chapters"]:
            for window in chapter["windows"]:
                source = windows[window["window_id"]]["range"]
                assert window["start"] == source["start"] and window["end"] == source["end"]
                assert window["label"] == source["labels"]["en"]
                seen += 1
    assert seen >= 10

    # the same blocking checks, on the cheap tier
    def scare(call, body, attempt):
        if call.key == "S-now":
            body["parts"][0]["chapters"][0]["windows"][0]["paragraphs"].append(
                "There is a danger of a serious illness in this window.")

    _, scared = simple(simple_book, mutate=scare)
    assert "serious illness" not in json.dumps(scared["parts"])
    assert {r["type"] for r in scared["meta"]["checks"]["redactions"]} == {"safety"}


def test_the_simple_tier_reuses_the_same_cached_prefix_as_the_detailed_one(simple_book, book):
    """Both tiers read a byte-identical prefix, because the engine computes once per chart and a
    Simple report only SELECTS from it.

    This is a correctness property, not a cost one. In practice almost nobody buys both tiers for
    the same chart inside the 5-minute cache TTL, so the Simple tier must be costed standalone -
    its own cache write plus its three calls - and never as a marginal add-on to a Detailed book.
    """
    detailed, simple_fake = BookFake(book), BookFake(simple_book)
    generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=detailed, use_cache=False)
    generate_report("kundali-report-simple", "en", [KALAM], as_of=AS_OF, client=simple_fake,
                    use_cache=False)
    assert detailed.calls[0]["system"] == simple_fake.calls[0]["system"]


def test_the_two_tiers_do_not_share_a_cache_entry(simple_book, book, tmp_path):
    """Different products, different report ids - buying one must never serve the other."""
    a = generate_report("kundali-report-simple", "en", [KALAM], as_of=AS_OF, client=BookFake(simple_book))
    b = generate_report("kundali-report", "en", [KALAM], as_of=AS_OF, client=BookFake(book))
    assert a["id"] != b["id"]
    assert len(a["parts"]) < len(b["parts"])


def test_the_simple_tier_is_gated_and_priced_separately(monkeypatch):
    from app.ai.products import PRODUCTS

    assert PRODUCTS["kundali-report-simple"].tier == "simple"
    assert PRODUCTS["kundali-report"].tier == "detailed"
    response = http.post("/api/report", json={"product": "kundali-report-simple", "language": "en",
                                              "birth": KALAM_JSON, "as_of": "2026-09-21"})
    assert response.status_code == 402, "the cheap tier is still a paid product"


@pytest.mark.parametrize("tier", ["detailed", "simple"])
def test_the_awkward_fake_covers_every_raggedness_in_BOTH_tiers(facts, tier):
    """The Simple tier has three calls where the Detailed one has twelve.

    An earlier version of this fake picked mutations by hashing the CALL NAME, so which raggedness a
    tier met depended on what its calls happened to be called - the Simple tier drew only the mild
    ones, and its duplicate-window-id case was hard-coded to `D-now`, a call id that tier does not
    even have. It passed, and tested almost nothing. Coverage is now asserted, not hoped for.
    """
    tier_book = build_book(facts, tier)
    fake = AwkwardFake(tier_book, tier=tier)
    product = "kundali-report" if tier == "detailed" else "kundali-report-simple"
    generate_report(product, "en", [KALAM], as_of=AS_OF, client=fake, use_cache=False)

    expected = {"long_heading", "blank_heading", "clashing_heading", "blank_part_heading",
                "more_lines_than_areas", "fewer_lines_than_areas", "duplicate_window_id",
                "mis_nested_chapters"}
    missing = expected - fake.applied
    assert not missing, f"the {tier} tier never met: {sorted(missing)}"


@pytest.mark.parametrize("tier", ["detailed", "simple"])
def test_an_awkward_model_produces_a_complete_book_in_BOTH_tiers(facts, tier):
    """The end-to-end awkward run, for the cheap tier too - a Rs 49 report that silently loses a
    chapter is exactly as bad as a Rs 249 one that does."""
    tier_book = build_book(facts, tier)
    product = "kundali-report" if tier == "detailed" else "kundali-report-simple"
    report = generate_report(product, "en", [KALAM], as_of=AS_OF,
                             client=AwkwardFake(tier_book, tier=tier), use_cache=False)
    planned = {(part.id, chapter.id) for part in tier_book for chapter in part.chapters}
    got = {(part["id"], chapter["id"]) for part in report["parts"] for chapter in part["chapters"]}
    assert planned == got, f"{tier}: content was dropped: {sorted(planned - got)}"
    for part in report["parts"]:
        for chapter in part["chapters"]:
            for window in chapter["windows"]:
                assert all(a["area"] and a["text"] for a in window["areas"])
                ids = [w["window_id"] for w in chapter["windows"]]
                assert len(ids) == len(set(ids))
