"""Phase 7: the refresh job - prompt, checks, store, idempotency, failure handling, lease, batch, scheduler, CLI.
No network: the AI client is tests/rashifal_fake.py (or a stub SDK for the batch wrapper)."""

import datetime as dt
import threading
import time

import pytest

from app.ai.client import AINotConfigured, AIUnavailable, ClaudeClient
from app.ai.prompts import INTERPRET_ONLY, compact_json
from app.rashifal import config, generate, scheduler, store
from app.rashifal.brief import build_brief
from app.rashifal.generate import LEASE_NAME, RefreshBusy, check_output, refresh
from app.rashifal.periods import IST, PERIOD_SLUGS, RASHI_SLUGS
from app.rashifal.prompts import SYSTEM_PROMPT, build_user_prompt, rashifal_schema
from app.ai.validator import collect_facts
from tests.rashifal_fake import FakeBatchClient, FakeRashifalClient, brief_from_prompt, write_page

NOW = dt.datetime(2026, 9, 21, 10, 0, tzinfo=IST)  # Monday
ALL = [(rashi, period) for rashi in RASHI_SLUGS for period in PERIOD_SLUGS]


@pytest.fixture(autouse=True)
def _one_call_per_page(monkeypatch):
    """Most tests here count calls per PAGE; production defaults to one call per language (tested separately)."""
    monkeypatch.setenv("RASHIFAL_SPLIT_LANGUAGES", "0")


def counts(summary):
    return {status: summary.count(status) for status in ("generated", "partial", "skipped", "failed")}


# ---- prompt --------------------------------------------------------------------------------------


def test_prompt_has_the_verbatim_rule_and_the_brief_json():
    verbatim = "Use ONLY the provided chart/transit data; do not calculate positions, dates or degrees yourself."
    assert INTERPRET_ONLY == verbatim and verbatim in SYSTEM_PROMPT
    for phrase in ("NOT a birth-chart", "Never predict or hint at death", "Do not write a disclaimer", "Marathi is not Hindi"):
        assert phrase in SYSTEM_PROMPT

    client = FakeRashifalClient()
    refresh(["weekly"], ["dhanu"], moment=NOW, client=client)
    (call,) = client.calls
    refresh(["yearly"], ["mesha"], moment=NOW + dt.timedelta(days=40), client=client)
    assert client.calls[1]["system"] == call["system"]  # frozen prefix for every page and run (prompt caching)
    assert call["system"] == SYSTEM_PROMPT
    brief = build_brief("dhanu", "weekly", NOW)
    assert "<data>\n" + compact_json(brief) + "\n</data>" in call["user"]
    assert brief_from_prompt(call["user"]) == brief
    assert "Dhanu rashi" in call["user"] and "2026-09-21 to 2026-09-27" in call["user"]
    assert "English (`en`), Hindi (`hi`), Marathi (`mr`)" in call["user"]
    assert call["schema"] == rashifal_schema(("en", "hi", "mr"))
    assert list(call["schema"]["properties"]) == ["en", "hi", "mr"] and call["schema"]["additionalProperties"] is False
    assert "rejected" in build_user_prompt(brief, ("en",), ["[en] overview: bad"]) and "[en] overview: bad" in \
        build_user_prompt(brief, ("en",), ["[en] overview: bad"])


def test_languages_setting(monkeypatch):
    assert config.languages() == ("en", "hi", "mr")
    monkeypatch.setenv("RASHIFAL_LANGUAGES", "mr, xx")
    assert config.languages() == ("en", "mr")  # en always, unknown ignored
    monkeypatch.setenv("RASHIFAL_MODEL", "claude-sonnet-5")
    settings = config.get_rashifal_settings()
    assert config.client_settings(settings).model == "claude-sonnet-5" and config.client_settings(settings).effort == "low"
    client = FakeRashifalClient()
    refresh(["today"], ["mesha"], moment=NOW, client=client)
    assert list(client.calls[0]["schema"]["properties"]) == ["en", "mr"]
    assert store.get_page("mesha", "today")["languages"] == ["en", "mr"]


# ---- the done-when behaviour ---------------------------------------------------------------------


def test_refresh_populates_all_60_then_skips_then_force_changes_content_not_urls(monkeypatch):
    clock = iter(dt.datetime(2026, 9, 21, 5, 0, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=n) for n in range(10_000))
    monkeypatch.setattr(generate, "_utcnow", lambda: next(clock))
    client = FakeRashifalClient()

    first = refresh(moment=NOW, client=client)
    assert counts(first) == {"generated": 60, "partial": 0, "skipped": 0, "failed": 0} and first.ok
    assert len(client.calls) == 60  # exactly one AI call per page, all languages in it
    assert sorted(store.list_pages()) == sorted(ALL)
    before = {key: store.get_page(*key) for key in ALL}
    assert all(page["languages"] == ["en", "hi", "mr"] and page["model"] == "fake-model" for page in before.values())
    assert before[("mesha", "weekly")]["period_start"] == "2026-09-21" and before[("mesha", "weekly")]["period_end"] == "2026-09-27"
    assert before[("mesha", "yearly")]["period_end"] == "2026-12-31"   # the calendar year, not twelve rolling months
    assert first.cost_usd > 0 and before[("mesha", "today")]["meta"]["usage"]["output_tokens"] == 1500

    again = refresh(moment=NOW + dt.timedelta(hours=3), client=client)  # same windows: idempotent
    assert counts(again) == {"generated": 0, "partial": 0, "skipped": 60, "failed": 0} and len(client.calls) == 60

    forced = refresh(moment=NOW + dt.timedelta(hours=3), client=client, force=True)
    assert counts(forced)["generated"] == 60 and len(client.calls) == 120
    after = {key: store.get_page(*key) for key in ALL}
    assert sorted(after) == sorted(before)  # same 60 keys = same 60 URLs
    for key in ALL:
        assert after[key]["content"] != before[key]["content"]
        assert after[key]["generated_at"] > before[key]["generated_at"]
        assert after[key]["first_published_at"] == before[key]["first_published_at"]
        assert after[key]["has_previous"] and after[key]["brief_hash"] == before[key]["brief_hash"]


def test_each_period_regenerates_only_when_its_window_rolls_over():
    client = FakeRashifalClient()
    refresh(moment=NOW, client=client)
    tuesday = refresh(moment=dt.datetime(2026, 9, 22, 0, 5, tzinfo=IST), client=client)
    assert [(o.period, o.status) for o in tuesday.outcomes if o.status == "generated"] == [("today", "generated")] * 12
    next_monday = refresh(moment=dt.datetime(2026, 9, 28, 0, 5, tzinfo=IST), client=client)
    assert {o.period for o in next_monday.outcomes if o.status == "generated"} == {"today", "weekly"}
    first_of_month = refresh(moment=dt.datetime(2026, 10, 1, 0, 5, tzinfo=IST), client=client)
    # yearly is NOT here any more: it is a calendar year now, so the 1st of a month rolls nothing for it.
    assert {o.period for o in first_of_month.outcomes if o.status == "generated"} == {"today", "monthly", "6-months"}
    assert store.get_page("kanya", "yearly")["period_start"] == "2026-01-01"

    # ... it rolls on 20 November, once, and to NEXT year - the early publish that catches "rashifal 2027"
    # while the searches for it are happening. The day before changes nothing.
    eve = refresh(moment=dt.datetime(2026, 11, 19, 0, 5, tzinfo=IST), client=client)
    assert "yearly" not in {o.period for o in eve.outcomes if o.status == "generated"}
    turnover = refresh(moment=dt.datetime(2026, 11, 20, 0, 5, tzinfo=IST), client=client)
    assert "yearly" in {o.period for o in turnover.outcomes if o.status == "generated"}
    assert store.get_page("kanya", "yearly")["period_start"] == "2027-01-01"
    assert store.get_page("kanya", "yearly")["period_end"] == "2027-12-31"
    # and then not again for a year: the 1st of January is not a turnover any more
    new_year = refresh(moment=dt.datetime(2027, 1, 1, 0, 5, tzinfo=IST), client=client)
    assert "yearly" not in {o.period for o in new_year.outcomes if o.status == "generated"}


def test_readings_differ_across_rashis_and_key_dates_come_from_the_brief():
    refresh(["weekly"], moment=NOW, client=FakeRashifalClient())
    pages = [store.get_page(rashi, "weekly") for rashi in RASHI_SLUGS]
    assert len({page["content"]["en"]["overview"] for page in pages}) == 12
    page = pages[0]
    event_ids = [event["id"] for event in page["brief"]["events"]]
    assert [item["event_id"] for item in page["content"]["en"]["key_dates"]] == event_ids[:3]
    assert set(page["content"]["en"]["key_dates"][0]) == {"event_id", "note"}  # no AI-written date anywhere


# ---- checks and failure handling -----------------------------------------------------------------


def _unsafe_everywhere(data, brief, call):
    for page in data.values():
        page["sections"]["health_wellbeing"].append("There is a risk of a heart attack this week.")
    return data


def test_unsafe_output_is_regenerated_once_then_the_previous_content_is_kept():
    good = FakeRashifalClient()
    refresh(["today"], ["mesha", "simha"], moment=NOW, client=good)
    before = store.get_page("mesha", "today")

    bad = FakeRashifalClient(mutate=_unsafe_everywhere)
    summary = refresh(["today"], ["mesha", "simha"], moment=NOW, client=bad, force=True)
    assert counts(summary)["failed"] == 2 and not summary.ok
    assert len(bad.calls) == 4  # one regeneration each, no more
    assert "forbidden topic (illness)" in bad.calls[2]["user"] and "rejected" in bad.calls[2]["user"]  # feedback sent
    assert "previous content kept" in summary.outcomes[0].detail
    assert store.get_page("mesha", "today") == before  # untouched: content, generated_at, everything


def test_unsafe_output_with_nothing_stored_publishes_nothing():
    summary = refresh(["today"], ["mesha"], moment=NOW, client=FakeRashifalClient(mutate=_unsafe_everywhere))
    assert counts(summary)["failed"] == 1 and store.get_page("mesha", "today") is None


def test_a_wrong_fact_is_sent_back_and_the_fixed_draft_is_published():
    def wrong_house_first_time(data, brief, call):
        if call == 1:
            saturn = next(p for p in brief["positions_at_start"] if p["graha"]["key"] == "Saturn")
            data["en"]["overview"] += f" Shani in your {saturn['house'] % 12 + 1}th house asks for patience."
        return data

    client = FakeRashifalClient(mutate=wrong_house_first_time)
    summary = refresh(["today"], ["kanya"], moment=NOW, client=client)
    assert counts(summary)["generated"] == 1 and summary.outcomes[0].attempts == 2 and len(client.calls) == 2
    assert "does not place Saturn in house" in client.calls[1]["user"]
    page = store.get_page("kanya", "today")
    assert page["meta"]["attempts"] == 2 and page["meta"]["usage"]["output_tokens"] == 3000  # both calls are paid for


def test_a_language_that_stays_unsafe_is_dropped_and_the_clean_ones_are_published():
    def hindi_unsafe(data, brief, call):
        data["hi"]["tip"] = "दुर्घटना से बचने के लिए नीलम पहनें।"
        return data

    summary = refresh(["today"], ["tula"], moment=NOW, client=FakeRashifalClient(mutate=hindi_unsafe))
    assert counts(summary) == {"generated": 0, "partial": 1, "skipped": 0, "failed": 0}
    page = store.get_page("tula", "today")
    assert page["languages"] == ["en", "mr"] and "hi" not in page["content"]
    assert "hi" in page["meta"]["dropped_languages"]
    # a partial page is not complete, so the next scheduled run fills in ONLY the missing language
    retry = FakeRashifalClient()
    assert counts(refresh(["today"], ["tula"], moment=NOW, client=retry))["generated"] == 1
    assert list(retry.calls[0]["schema"]["properties"]) == ["hi"] and "Languages: Hindi (`hi`)." in retry.calls[0]["user"]
    filled = store.get_page("tula", "today")
    assert filled["languages"] == ["en", "hi", "mr"]
    assert filled["content"]["en"] == page["content"]["en"] and filled["content"]["mr"] == page["content"]["mr"]  # untouched
    assert filled["first_published_at"] == page["first_published_at"] and not filled["has_previous"]
    assert filled["meta"]["languages_written"] == ["hi"] and filled["meta"]["merged_from"][0]["languages_written"] == ["en", "mr"]
    assert counts(refresh(["today"], ["tula"], moment=NOW, client=retry))["skipped"] == 1 and len(retry.calls) == 1


def test_structure_and_language_checks():
    brief = build_brief("mesha", "weekly", NOW)
    facts = collect_facts(brief)
    data = {code: write_page(brief, code, 1) for code in ("en", "hi", "mr")}
    assert all(not report["blocking"] for report in check_output(data, ("en", "hi", "mr"), brief, facts).values())

    broken = {code: write_page(brief, code, 1) for code in ("en", "hi", "mr")}
    broken["en"]["key_dates"] = [{"event_id": "e99", "note": "x"}]
    broken["en"]["overview"] += " Expect a change on 3 October 2026."
    broken["mr"] = write_page(brief, "hi", 1)  # Hindi passed off as Marathi
    broken["hi"]["sections"]["love_family"] = []
    report = check_output(broken, ("en", "hi", "mr"), brief, facts)
    assert any("e99" in message for message in report["en"]["blocking"])
    assert any("3 October 2026" in message for message in report["en"]["blocking"])
    assert any("contains Hindi" in message for message in report["mr"]["blocking"])
    assert any("love_family has no text" in message for message in report["hi"]["blocking"])
    assert check_output({"en": data["en"]}, ("en", "mr"), brief, facts)["mr"]["blocking"] == ["missing"]
    short = write_page(brief, "en", 1)
    short["overview"], short["sections"] = "Short.", {k: ["Short."] for k in short["sections"]}
    assert any("too short" in m for m in check_output({"en": short}, ("en",), brief, facts)["en"]["blocking"])


def test_one_failing_rashi_does_not_stop_the_rest():
    class Flaky(FakeRashifalClient):
        def generate_json(self, *, system, user, schema):
            if "Karka rashi" in user:
                self.calls.append({"user": user})
                raise AIUnavailable("Claude API error 529: overloaded")
            return super().generate_json(system=system, user=user, schema=schema)

    summary = refresh(["today"], moment=NOW, client=Flaky())
    assert counts(summary) == {"generated": 11, "partial": 0, "skipped": 0, "failed": 1} and not summary.ok
    failed = next(o for o in summary.outcomes if o.status == "failed")
    assert failed.rashi == "karka" and failed.attempts == 2 and "overloaded" in failed.detail
    assert store.get_page("karka", "today") is None and store.get_page("simha", "today") is not None


def test_no_api_key_generates_nothing_and_says_so(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(AINotConfigured):
        refresh(["today"], moment=NOW)
    assert store.list_pages() == {} and store.lease_info(LEASE_NAME) is None  # lease released

    import sys

    from scripts import rashifal_refresh

    monkeypatch.setattr(sys, "argv", ["rashifal_refresh.py", "--period", "all", "--force"])
    assert rashifal_refresh.main() == 2
    out = capsys.readouterr().out
    assert "NOTHING WAS GENERATED" in out and "ANTHROPIC_API_KEY" in out
    assert store.list_pages() == {}


def test_cli_reports_failures_with_a_non_zero_exit(monkeypatch, capsys):
    import sys

    from scripts import rashifal_refresh

    monkeypatch.setattr(generate, "ClaudeClient", lambda settings: FakeRashifalClient(mutate=_unsafe_everywhere))
    monkeypatch.setattr(sys, "argv", ["rashifal_refresh.py", "--period", "today", "--rashi", "mesha"])
    assert rashifal_refresh.main() == 1
    assert "1 FAILED" in capsys.readouterr().out
    monkeypatch.setattr(generate, "ClaudeClient", lambda settings: FakeRashifalClient())
    assert rashifal_refresh.main() == 0
    assert "1 generated" in capsys.readouterr().out
    assert rashifal_refresh.main() == 0 and "1 skipped" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["rashifal_refresh.py", "--estimate"])
    assert rashifal_refresh.main() == 0
    out = capsys.readouterr().out
    assert "calls per day: 14.9" in out and "monthly" in out and "3-months" not in out and "claude-haiku-4-5" in out


# ---- store ---------------------------------------------------------------------------------------


def test_store_keeps_the_previous_version_and_can_roll_back():
    client = FakeRashifalClient()
    refresh(["today"], ["mesha"], moment=NOW, client=client)
    first = store.get_page("mesha", "today")
    assert not first["has_previous"] and store.rollback("mesha", "today") is False
    refresh(["today"], ["mesha"], moment=NOW, client=client, force=True)
    assert store.get_page("mesha", "today")["content"] != first["content"]
    assert store.rollback("mesha", "today") is True
    restored = store.get_page("mesha", "today")
    assert restored["content"] == first["content"] and restored["generated_at"] == first["generated_at"]
    with pytest.raises(ValueError):
        store.save_page("mesha", "daily", period_start="", period_end="", generated_at="", model="", brief_hash="",
                        content={"en": {"x": 1}}, brief={}, meta={})
    with pytest.raises(ValueError):
        store.save_page("mesha", "today", period_start="", period_end="", generated_at="", model="", brief_hash="",
                        content={}, brief={}, meta={})


# ---- lease / scheduler ---------------------------------------------------------------------------


def test_lease_allows_one_holder_until_it_expires():
    assert store.acquire_lease("x", "a", 60, now=1000) is True
    assert store.acquire_lease("x", "b", 60, now=1030) is False
    assert store.acquire_lease("x", "a", 60, now=1030) is True  # renewal by the owner
    assert store.acquire_lease("x", "b", 60, now=1089) is False
    assert store.acquire_lease("x", "b", 60, now=1091) is True  # expired: a crashed holder cannot block forever
    store.release_lease("x", "a")  # not the owner any more: no effect
    assert store.lease_info("x")["holder"] == "b"
    store.release_lease("x", "b")
    assert store.lease_info("x") is None


def test_refresh_refuses_to_run_twice_at_once():
    assert store.acquire_lease(LEASE_NAME, "another-worker", 600)
    client = FakeRashifalClient()
    with pytest.raises(RefreshBusy):
        refresh(["today"], ["mesha"], moment=NOW, client=client)
    assert client.calls == []
    store.release_lease(LEASE_NAME, "another-worker")
    assert counts(refresh(["today"], ["mesha"], moment=NOW, client=client))["generated"] == 1
    assert store.lease_info(LEASE_NAME) is None


def test_two_workers_starting_together_run_one_refresh():
    class Slow(FakeRashifalClient):
        def generate_json(self, **kwargs):
            time.sleep(0.05)
            return super().generate_json(**kwargs)

    client, results = Slow(), []

    def worker():
        try:
            results.append(refresh(["today"], moment=NOW, client=client))
        except RefreshBusy:
            results.append("busy")

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("busy") == 2 and len(client.calls) == 12  # 12 pages generated once, not 36 calls


def test_in_process_scheduler_is_opt_in_and_runs_in_ist(monkeypatch):
    assert scheduler.start_if_enabled() is None
    monkeypatch.setenv("RASHIFAL_SCHEDULER", "1")
    started = scheduler.start_if_enabled()
    try:
        assert scheduler.start_if_enabled() is started  # idempotent
        jobs = {job.id: job for job in started.get_jobs()}
        assert set(jobs) == {"rashifal-midnight", "rashifal-retry", "rashifal-startup"}
        after = dt.datetime(2026, 9, 21, 12, 0, tzinfo=IST)
        fire = jobs["rashifal-midnight"].trigger.get_next_fire_time(None, after)
        assert fire.astimezone(IST) == dt.datetime(2026, 9, 22, 0, 5, tzinfo=IST)
    finally:
        scheduler.stop()
    calls = []
    monkeypatch.setattr(scheduler, "refresh", lambda: calls.append(1) or (_ for _ in ()).throw(RefreshBusy("held")))
    scheduler.run_once()  # a busy lease or an AI error never raises out of the scheduler thread
    monkeypatch.setattr(scheduler, "refresh", lambda: (_ for _ in ()).throw(AINotConfigured("no key")))
    scheduler.run_once()
    assert calls == [1]


# ---- batch mode ----------------------------------------------------------------------------------


def test_batch_is_the_default_for_big_rounds_and_small_runs_go_direct(monkeypatch):
    assert config.get_rashifal_settings().batch is True and config.get_rashifal_settings().model == "claude-haiku-4-5"
    small = FakeBatchClient()
    refresh(["today"], ["dhanu", "mesha", "simha"], moment=NOW, client=small)  # under BATCH_MIN_JOBS: direct calls
    assert small.batches == [] and len(small.calls) == 3 and store.get_page("dhanu", "today")["meta"]["batch"] is False
    monkeypatch.setenv("RASHIFAL_BATCH", "0")
    never = FakeBatchClient()
    refresh(["weekly"], moment=NOW, client=never)
    assert never.batches == [] and len(never.calls) == 12


def test_batch_mode_sends_one_batch_per_round(monkeypatch):

    def first_draft_of_mesha_is_unsafe(data, brief, call):
        if brief["rashi"]["name"] == "Mesha" and "fixed" not in seen:
            seen.add("fixed")
            data["en"]["tip"] = "Consult an astrologer about the lawsuit."
        return data

    seen: set = set()
    client = FakeBatchClient(mutate=first_draft_of_mesha_is_unsafe)
    summary = refresh(["today"], moment=NOW, client=client)
    assert counts(summary)["generated"] == 12
    assert [len(batch) for batch in client.batches] == [12]  # the 1-page retry round is called directly
    assert client.batches[0][0] == "mesha__today__en-hi-mr" and len(client.calls) == 13
    assert summary.batches == 1 and summary.calls == 13 and summary.usage["output_tokens"] == 13 * 1500
    assert {(r["rashi"], r["language"], r["attempt"]) for r in summary.rejections} == {("mesha", "en", 1)}  # 2 hits, 1 draft
    page = store.get_page("mesha", "today")
    assert page["meta"]["batch"] is True and page["meta"]["attempts"] == 2
    single = store.get_page("simha", "today")["meta"]["cost_estimate_usd"]
    monkeypatch.setenv("RASHIFAL_BATCH", "0")
    refresh(["today"], ["simha"], moment=NOW, client=FakeRashifalClient(), force=True)
    assert store.get_page("simha", "today")["meta"]["cost_estimate_usd"] == pytest.approx(single * 2)  # batch = 50%


class _StubBatches:
    def __init__(self, results):
        self.created, self._results, self._polls = None, results, 0

    def create(self, requests):
        self.created = requests
        return type("Batch", (), {"id": "msgbatch_1", "processing_status": "in_progress"})()

    def retrieve(self, batch_id):
        self._polls += 1
        return type("Batch", (), {"id": batch_id, "processing_status": "ended" if self._polls >= 2 else "in_progress"})()

    def results(self, batch_id):
        return iter(self._results)


def _entry(custom_id, kind, **fields):
    return type("Entry", (), {"custom_id": custom_id, "result": type("Result", (), {"type": kind, **fields})()})()


def _message(text='{"ok": true}', stop_reason="end_turn"):
    block = type("Block", (), {"type": "text", "text": text})()
    usage = type("Usage", (), {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})()
    return type("Message", (), {"content": [block], "stop_reason": stop_reason, "model": "claude-opus-5", "usage": usage,
                                "_request_id": "req_b"})()


def test_split_languages_mode_builds_each_page_from_three_jobs(monkeypatch):
    monkeypatch.setenv("RASHIFAL_SPLIT_LANGUAGES", "1")
    client = FakeBatchClient()
    summary = refresh(["today"], ["mesha", "simha"], moment=NOW, client=client)
    # One batch per MODEL, and Marathi has its own by default (LANGUAGE_MODEL_DEFAULTS), so the six jobs
    # arrive as two batches rather than one. Order within each is the planner's: page, then language.
    assert client.batches == [["mesha__today__en", "mesha__today__hi", "simha__today__en", "simha__today__hi"],
                              ["mesha__today__mr", "simha__today__mr"]]
    assert all(list(schema["properties"]) in (["en"], ["hi"], ["mr"]) for schema in client.batch_schemas)
    assert counts(summary)["generated"] == 6 and store.get_page("mesha", "today")["languages"] == ["en", "hi", "mr"]
    first = store.get_page("mesha", "today")
    forced = refresh(["today"], ["mesha"], moment=NOW, client=client, force=True)  # a forced run replaces, never tops up
    again = store.get_page("mesha", "today")
    assert counts(forced)["generated"] == 3 and again["languages"] == ["en", "hi", "mr"] and again["has_previous"]
    assert all(again["content"][code] != first["content"][code] for code in ("en", "hi", "mr"))


def test_per_language_model_override(monkeypatch):
    monkeypatch.setenv("RASHIFAL_SPLIT_LANGUAGES", "1")
    monkeypatch.setenv("RASHIFAL_MODEL_MR", "claude-sonnet-5")
    settings = config.get_rashifal_settings()
    assert settings.split_languages and settings.model_for(("mr",)) == "claude-sonnet-5"
    assert settings.model_for(("hi",)) == "claude-haiku-4-5" == settings.model_for(("en", "hi", "mr"))
    made = {}

    class PerModel(FakeBatchClient):
        def __init__(self, client_settings):
            super().__init__(model=client_settings.model)
            made[client_settings.model] = self

    monkeypatch.setattr(generate, "ClaudeClient", PerModel)
    summary = refresh(["today"], ["mesha", "simha"], moment=NOW)
    assert set(made) == {"claude-haiku-4-5", "claude-sonnet-5"} and summary.batches == 2
    assert made["claude-sonnet-5"].batches == [["mesha__today__mr", "simha__today__mr"]]
    assert sorted(made["claude-haiku-4-5"].batches[0]) == ["mesha__today__en", "mesha__today__hi", "simha__today__en", "simha__today__hi"]
    assert store.get_page("mesha", "today")["languages"] == ["en", "hi", "mr"]
    monkeypatch.delenv("RASHIFAL_SPLIT_LANGUAGES")
    assert config.get_rashifal_settings().split_languages is True  # the production default


def test_every_language_gets_a_hub_summary():
    refresh(["today", "weekly"], moment=NOW, client=FakeRashifalClient())
    rows = store.hub_rows("today")
    assert set(rows) == set(RASHI_SLUGS) and set(store.hub_rows("weekly")) == set(RASHI_SLUGS) and store.hub_rows("yearly") == {}
    row = rows["tula"]
    assert row["period_start"] == "2026-09-21" and row["languages"] == ["en", "hi", "mr"]
    assert all(row["summaries"][code] and row["headlines"][code] for code in ("en", "hi", "mr"))
    assert len({rows[r]["summaries"]["hi"] for r in RASHI_SLUGS}) == 12

    def no_summary(data, brief, call):
        data["mr"]["summary"] = " "
        return data

    summary = refresh(["today"], ["tula"], moment=NOW, client=FakeRashifalClient(mutate=no_summary), force=True)
    assert summary.outcomes[0].status == "partial" and "summary is empty" in summary.outcomes[0].detail


def test_old_quarterly_rows_are_dropped_from_the_store():
    from app import db

    refresh(["monthly"], ["mesha"], moment=NOW, client=FakeRashifalClient())
    with db.transaction() as conn:
        conn.execute("UPDATE rashifal_pages SET period = '3-months'")
    db._ready.clear()  # a new process applies the schema script again
    assert store.list_pages() == {}


def test_claude_client_batch_wrapper(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("RASHIFAL_MODEL", "claude-opus-5")
    client = ClaudeClient(config.client_settings(config.get_rashifal_settings()))
    error = type("Err", (), {"error": type("Inner", (), {"type": "invalid_request_error", "message": "bad schema"})()})()
    batches = _StubBatches([_entry("c", "expired"), _entry("b", "errored", error=error), _entry("a", "succeeded", message=_message()),
                            _entry("d", "succeeded", message=_message(stop_reason="refusal"))])
    client._client = type("SDK", (), {"messages": type("Messages", (), {"batches": batches})()})()
    polls = []
    items = [{"custom_id": cid, "system": "s", "user": f"u-{cid}", "schema": {"type": "object"}} for cid in "abcde"]
    results = client.generate_json_batch(items, poll_seconds=0, on_poll=lambda: polls.append(1))

    assert results["a"].data == {"ok": True} and results["a"].usage["output_tokens"] == 5
    assert type(results["b"]).__name__ == "AIBadOutput" and "bad schema" in str(results["b"])
    assert isinstance(results["c"], AIUnavailable) and type(results["d"]).__name__ == "AIBadOutput"
    assert isinstance(results["e"], AIUnavailable)  # missing from the results: never silently dropped
    assert len(polls) == 2
    first = batches.created[0]
    assert first["custom_id"] == "a" and first["params"]["model"] == "claude-opus-5"
    assert first["params"]["output_config"] == {"format": {"type": "json_schema", "schema": {"type": "object"}}, "effort": "low"}
    assert first["params"]["thinking"] == {"type": "adaptive"} and first["params"]["max_tokens"] == 16000
    assert "fallbacks" not in first["params"] and "betas" not in first["params"]  # rejected by the Batches API
    assert first["params"]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert client.generate_json_batch([]) == {}

    monkeypatch.delenv("RASHIFAL_MODEL")  # the default, Haiku 4.5: no adaptive thinking, no effort
    haiku = ClaudeClient(config.client_settings(config.get_rashifal_settings()))
    request = haiku._request("s", "u", {"type": "object"})
    assert request["model"] == "claude-haiku-4-5" and "thinking" not in request
    assert request["output_config"] == {"format": {"type": "json_schema", "schema": {"type": "object"}}}


# ---- what the web layer and Phase 8 consume: URL slugs, titles, sitemap --------------------------------------


def test_url_vocabulary_per_language_tree():
    from app.rashifal.periods import URL_PERIOD_SLUGS, URL_RASHI_SLUGS, url_path

    assert url_path("en", "tula", "today") == "/horoscope/libra/today"
    assert url_path("hi", "tula", "today") == "/hi/rashifal/tula/aaj"
    assert url_path("mr", "simha", "monthly") == "/mr/rashi-bhavishya/singh/masik"
    assert url_path("hi", "kumbha", "6-months") == "/hi/rashifal/kumbh/6-mahine" and url_path("en", "meena", "yearly") == "/horoscope/pisces/yearly"
    assert (url_path("en"), url_path("hi"), url_path("mr")) == ("/horoscope", "/hi/rashifal", "/mr/rashi-bhavishya")
    assert url_path("hi", period="weekly") == "/hi/rashifal/saptahik" and url_path("en", period="weekly") == "/horoscope/weekly"
    assert list(URL_RASHI_SLUGS["hi"].values()) == ["mesh", "vrishabh", "mithun", "kark", "singh", "kanya", "tula", "vrishchik",
                                                    "dhanu", "makar", "kumbh", "meen"]  # the rashi slugs the URLs use
    assert list(URL_PERIOD_SLUGS["mr"].values()) == ["aaj", "saptahik", "masik", "6-mahine", "varshik"]
    urls = {url_path(code, rashi, period) for code in ("en", "hi", "mr") for rashi in RASHI_SLUGS for period in PERIOD_SLUGS}
    assert len(urls) == 180 and not any(ch.isdigit() for url in urls for ch in url.replace("6-m", ""))  # never date-stamped


def test_titles_and_h1s_are_code_in_each_languages_vocabulary():
    from app.rashifal import i18n

    assert i18n.page_h1("tula", "today", "hi") == "Tula Rashi Today – तुला राशिफल आज"  # the keyword map's own example
    assert i18n.page_title("tula", "today", "en") == "Libra Horoscope Today – Tula Rashi Daily Horoscope"
    assert i18n.page_h1("tula", "today", "mr") == "Tula Rashi Bhavishya – आजचे तूळ राशिभविष्य"
    keys = [(code, rashi, period) for code in ("en", "hi", "mr") for rashi in RASHI_SLUGS for period in PERIOD_SLUGS]
    for make in (i18n.page_title, i18n.page_h1, i18n.page_meta):
        assert len({make(rashi, period, code) for code, rashi, period in keys}) == 180
    for code, rashi, period in keys:
        title, h1, meta = (make(rashi, period, code) for make in (i18n.page_title, i18n.page_h1, i18n.page_meta))
        assert i18n.KEYWORD[code] in title.lower() and i18n.KEYWORD[code] in h1.lower() and 70 <= len(meta) <= 220
        assert not any(ch.isdigit() for ch in title.replace("6", "").replace("12", ""))  # permanent: no dates
        if code == "mr":
            assert "राशिफल" not in title + h1 + meta  # Marathi readers say राशिभविष्य
        if code == "en":
            assert "rashifal" not in (title + h1).lower()
    assert i18n.rashi_names("simha") == {**i18n.rashi_names("simha"), "en": "Leo", "hi": "सिंह", "sanskrit": "Simha", "latin": "Singh"}
    assert i18n.rashi_names("tula")["mr"] == "तूळ"
    for code in ("en", "hi", "mr"):
        for period in ("today", "weekly"):
            assert i18n.hub_title(period, code) and i18n.hub_h1(period, code) and 70 <= len(i18n.hub_meta(period, code)) <= 220
    assert "Aaj Ka Rashifal" in i18n.hub_title("today", "hi") and "आजचे राशिभविष्य" in i18n.hub_h1("today", "mr")


def test_sitemap_helper_lists_180_pages_and_6_hubs(monkeypatch):
    from app.rashifal.sitemap import rashifal_hub_entries, rashifal_sitemap_entries

    monkeypatch.setenv("BASE_URL", "https://example.test/")
    monkeypatch.setattr(generate, "_utcnow", lambda: dt.datetime(2026, 9, 20, 18, 37, tzinfo=dt.timezone.utc))
    refresh(["today"], ["mesha"], moment=NOW, client=FakeRashifalClient())
    entries = rashifal_sitemap_entries(moment=NOW)
    assert len(entries) == 180 == len({entry["loc"] for entry in entries})
    first = entries[0]
    assert first["loc"] == "https://example.test/horoscope/aries/today" and first["lastmod"] == "2026-09-20T18:37:00+00:00"
    assert first["alternates"] == {"en": "https://example.test/horoscope/aries/today", "hi": "https://example.test/hi/rashifal/mesh/aaj",
                                   "mr": "https://example.test/mr/rashi-bhavishya/mesh/aaj",
                                   "x-default": "https://example.test/horoscope/aries/today"}
    assert entries[1]["lastmod"] == "2026-09-20T18:30:00+00:00" and entries[1]["changefreq"] == "weekly"  # nothing stored: window start
    assert entries[2]["lastmod"] == "2026-08-31T18:30:00+00:00"  # monthly window began 1 September IST
    assert [entry["language"] for entry in entries[::60]] == ["en", "hi", "mr"]
    hubs = rashifal_hub_entries(moment=NOW)
    assert [hub["loc"].removeprefix("https://example.test") for hub in hubs] == [
        "/horoscope", "/horoscope/weekly", "/hi/rashifal", "/hi/rashifal/saptahik", "/mr/rashi-bhavishya", "/mr/rashi-bhavishya/saptahik"]
    assert hubs[0]["lastmod"] == "2026-09-20T18:37:00+00:00" and hubs[1]["lastmod"] == "2026-09-20T18:30:00+00:00"


def test_bracketed_latin_names_and_dandas_are_tidied_before_the_checks_instead_of_costing_a_regeneration():
    def glossy(data, brief, call):
        data["hi"]["overview"] = data["hi"]["overview"].replace("शनि ", "शनि (Shani) ", 1)
        data["mr"]["tip"] = "रोज संध्याकाळी दिवा लावा। शांत बसा।"
        return data

    client = FakeRashifalClient(mutate=glossy)
    summary = refresh(["today"], ["mesha"], moment=NOW, client=client)
    assert counts(summary)["generated"] == 1 and len(client.calls) == 1 and summary.rejections == []
    page = store.get_page("mesha", "today")
    assert "Shani" not in page["content"]["hi"]["overview"] and "शनि मीन" in page["content"]["hi"]["overview"]
    assert page["content"]["mr"]["tip"] == "रोज संध्याकाळी दिवा लावा. शांत बसा."

    def english_words(data, brief, call):
        data["hi"]["overview"] += " यह love और family का समय है।"
        return data

    assert refresh(["today"], ["simha"], moment=NOW, client=FakeRashifalClient(mutate=english_words)).outcomes[0].status == "partial"


# ---- Marathi quality -----------------------------------------------------------------------------
#
# Three defences, and they are not interchangeable. The BRIEF stops us handing the model the Hindi spelling
# and then blaming it; the GATE refuses the recurring Hindi substitutions; the MODEL is the only thing that
# helps with an invented word nobody has seen yet. The live readings failed on all three at once.


def test_the_brief_gives_marathi_its_own_spellings_for_the_grahas_and_signs():
    """The engine keeps ONE Devanagari spelling per graha and it is the Hindi one. The prompt tells the model
    to take names from the brief, so until the brief carried `devanagari_mr` the model was being instructed to
    write मंगल and गुरु in Marathi - which is exactly what the published pages did."""
    hindi_to_marathi = {"मंगल": "मंगळ", "शनि": "शनी", "गुरु": "गुरू", "राहु": "राहू", "केतु": "केतू", "तुला": "तूळ"}
    seen = {}

    def walk(node):
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return None
        for key in hindi_to_marathi:
            if node.get("devanagari") == key:
                seen[key] = node.get("devanagari_mr")
        return [walk(value) for value in node.values()]

    for rashi in ("tula", "mesha", "meena"):
        for period in ("today", "yearly"):
            walk(build_brief(rashi, period, NOW))
    assert seen, "no brief named any of the grahas or signs whose Marathi spelling differs"
    for hindi, marathi in hindi_to_marathi.items():
        if hindi in seen:
            assert seen[hindi] == marathi, f"the brief offers {seen[hindi]!r} for {hindi}, Marathi writes {marathi}"


def test_the_brief_and_the_rendered_page_agree_on_every_marathi_name():
    """Two places name a graha in Marathi - the brief the model writes from, and i18n, which the pages and the
    PDF render through. They are one mapping in i18n; this is what stops a second copy drifting from it."""
    from app.rashifal import i18n
    brief = build_brief("tula", "today", NOW)
    assert brief["rashi"]["devanagari_mr"] == i18n.rashi_name(brief["rashi"]["index"], "mr")
    for position in brief["positions_at_start"]:
        graha, sign = position["graha"], position["sign"]
        expected = i18n.graha_name(graha, "mr")
        assert graha.get("devanagari_mr", graha["devanagari"]) == expected, graha
        assert sign.get("devanagari_mr", sign["devanagari"]) == i18n.rashi_name(sign["index"], "mr"), sign


@pytest.mark.parametrize("wrong, names", [
    ("सदे साती", "साडेसाती"),          # the user-visible misspelling of Saturn's seven-and-a-half years
    ("गुरु", "गुरू"),                   # the Hindi spelling the brief used to hand over
    ("धीरे", "हळूहळू"),                 # Hindi adverb
    ("शिक्षा", "शिक्षण"),               # same word, different meaning: punishment, not education
    ("लांबमेय", "दीर्घकालीन"),          # not a word in any language
])
def test_hindi_and_invented_words_block_a_marathi_page_and_the_message_names_the_fix(wrong, names):
    """Blocking, not a warning: these went out to readers while the prompt was already asking for Marathi.
    The message carries the replacement because it is fed back to the model as retry feedback."""
    brief = build_brief("mesha", "weekly", NOW)
    facts = collect_facts(brief)
    page = write_page(brief, "mr", 1)
    page["overview"] += f" या काळात {wrong} लक्षात ठेवा."
    blocking = check_output({"mr": page}, ("mr",), brief, facts)["mr"]["blocking"]
    assert any(wrong in message for message in blocking), f"{wrong} was accepted: {blocking}"
    assert any(names in message for message in blocking), f"no replacement offered for {wrong}: {blocking}"


def test_good_marathi_passes_the_word_gate():
    """The control. A gate that rejects everything would satisfy the test above and be worthless, and the cost
    of a false positive here is real: two rejected attempts drop the language and the page loses its Marathi."""
    brief = build_brief("tula", "weekly", NOW)
    facts = collect_facts(brief)
    page = write_page(brief, "mr", 1)
    page["overview"] += (" तूळ राशीसाठी हा काळ संयमाचा आहे. गुरू आणि शनी यांच्या स्थितीमुळे कामात हळूहळू प्रगती होईल."
                         " शिक्षण, प्रवास आणि वैयक्तिक नात्यांकडे लक्ष द्या. मंगल कार्य पुढे ढकलण्याची गरज नाही.")
    assert not check_output({"mr": page}, ("mr",), brief, facts)["mr"]["blocking"]


def test_marathi_is_written_by_a_stronger_model_than_the_other_languages(monkeypatch):
    """The quality lever lives in the repository, not in one server's .env, so this can assert it."""
    for code in ("EN", "HI", "MR"):
        monkeypatch.delenv(f"RASHIFAL_MODEL_{code}", raising=False)
    settings = config.get_rashifal_settings()
    assert settings.model_for(("mr",)) == "claude-sonnet-5"
    assert "haiku" not in settings.model_for(("mr",)).lower()
    assert settings.model_for(("en",)) == settings.model
    monkeypatch.setenv("RASHIFAL_MODEL_MR", "claude-opus-5")
    assert config.get_rashifal_settings().model_for(("mr",)) == "claude-opus-5", "the env var must still win"


def test_regenerating_one_language_leaves_the_others_exactly_as_they_were(monkeypatch):
    """"Regenerate the Marathi" must not re-pay for English and Hindi, and must not blank them either. A job
    that writes a subset saves with merge=True, so the versions it did not write are left as they are.

    One client throughout: the fake numbers its runs by call count, so a fresh instance would rewrite the same
    text and the test would pass without proving anything changed."""
    monkeypatch.setenv("RASHIFAL_SPLIT_LANGUAGES", "1")
    client = FakeRashifalClient()
    refresh(["today"], ["mesha"], moment=NOW, client=client)
    before = store.get_page("mesha", "today")
    assert sorted(before["languages"]) == ["en", "hi", "mr"]
    calls_for_all_three = len(client.calls)

    summary = refresh(["today"], ["mesha"], moment=NOW, client=client, force=True, only_languages=("mr",))

    after = store.get_page("mesha", "today")
    assert summary.count("failed") == 0, summary.outcomes
    assert len(client.calls) == calls_for_all_three + 1, "a one-language run must make exactly one call"
    assert sorted(after["languages"]) == ["en", "hi", "mr"], "a language was lost"
    assert after["content"]["mr"] != before["content"]["mr"], "the Marathi was not rewritten"
    assert after["content"]["en"] == before["content"]["en"], "English was rewritten or blanked"
    assert after["content"]["hi"] == before["content"]["hi"], "Hindi was rewritten or blanked"


def test_one_language_runs_need_split_mode(monkeypatch):
    """Without split mode a single call writes every language, so there is no way to regenerate one of them -
    and silently regenerating all three would be a bill, not a bug report."""
    monkeypatch.setenv("RASHIFAL_SPLIT_LANGUAGES", "0")
    with pytest.raises(ValueError, match="SPLIT_LANGUAGES"):
        refresh(["today"], ["mesha"], moment=NOW, client=FakeRashifalClient(), only_languages=("mr",))
