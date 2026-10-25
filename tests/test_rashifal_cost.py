"""What the rashifal pages cost, and which of the three terms is actually worth attacking.

    monthly bill = (page-languages per month) x (1 + refusal rate) x (cost per call)

The first term is the publishing cadence and cannot move without publishing less. The third is the
model's price. Only the middle one is a defect.

WHAT THE BRIEF ASKED FOR AND WHAT WAS ALREADY TRUE. "Skip regenerating unchanged windows" is already
implemented - and these tests prove it rather than taking the code comment's word for it, because the
alternative was to build a second skip on top of a working one and report a saving that was never there.
"""
from __future__ import annotations

import datetime as dt

import pytest


def test_a_window_that_has_not_moved_is_not_regenerated():
    """The skip the brief asked for, exercised THROUGH plan() - not by calling the helper.

    The first version of this called generate.is_current directly, which proves the helper works and
    says nothing about whether anything uses it: deleting the call in plan() - the actual skip, and the
    whole saving this item rests on - left it green. The same shape of mistake as a test that exercised
    a writer function while the only call to it had been removed.

    It also branched on hasattr(generate, "IST"), which is ALWAYS FALSE, so it silently took a
    naive-datetime path; and window_for reads a naive datetime as already-IST, so that path is not
    equivalent in general. The moment is explicit now.
    """
    from app.rashifal import generate, store
    from app.rashifal.periods import IST, window_for

    moment = dt.datetime(2026, 10, 20, 9, 0, tzinfo=IST)
    window = window_for("today", moment)
    languages = ("en", "hi", "mr")

    jobs, skipped = generate.plan(["today"], ["mesha"], moment, languages, False, True, None)
    before = len(jobs)

    # Now with a stored page that already covers this window in every language.
    store.save_page("mesha", "today", period_start=window.start_date.isoformat(),
                    period_end=window.end_date.isoformat(), generated_at=moment.isoformat(),
                    model="test", brief_hash="any", brief={}, meta={},
                    content={code: {"headline": "x", "summary": "x", "overview": "x",
                                    "sections": {}, "tip": "x", "key_dates": []}
                             for code in languages})
    jobs_after, skipped_after = generate.plan(["today"], ["mesha"], moment, languages, False, True, None)

    assert before > 0, "nothing was planned even with no stored page"
    # The jobs carry the whole brief, so printing them buries the failure in several screens of chart
    # data. The languages are what the reader needs.
    assert not jobs_after, ("a page covering this window was still planned for "
                            f"{[job.languages for job in jobs_after]}")
    assert skipped_after and "already covers" in skipped_after[0].detail, \
        [outcome.detail for outcome in skipped_after]


def test_a_window_that_has_moved_is_regenerated():
    """The other direction, so the skip cannot be satisfied by always returning True."""
    from app.rashifal import generate
    from app.rashifal.periods import window_for

    window = window_for("today", dt.datetime(2026, 10, 20, 9, 0))
    stale = {"period_start": "2020-01-01", "languages": ("en", "hi", "mr"), "brief_hash": "x"}
    assert generate.is_current(stale, window, ("en", "hi", "mr")) is False
    missing_language = {"period_start": window.key, "languages": ("en",), "brief_hash": "x"}
    assert generate.is_current(missing_language, window, ("en", "hi", "mr")) is False


def test_each_language_is_generated_in_its_own_call_by_default():
    """So a Marathi refusal rewrites Marathi alone. If languages shared a call, one language's refusal
    would pay to rewrite the other two, and the refusal rate would cost three times what it does."""
    from app.rashifal import config

    assert config.RashifalSettings.__dataclass_fields__["split_languages"].default is True


def test_the_cadence_the_cost_model_uses_matches_the_periods_module():
    """The model's monthly volume is only right if its refresh frequencies are the real ones. A number
    typed here that drifted from periods.py would quietly misprice everything."""
    from app.rashifal.periods import PERIOD_SLUGS
    from scripts import rashifal_cost

    assert set(rashifal_cost.REFRESHES_PER_MONTH) == set(PERIOD_SLUGS), (
        set(rashifal_cost.REFRESHES_PER_MONTH) ^ set(PERIOD_SLUGS))
    # today is daily, weekly is weekly, yearly is once a year: the shape, not just the keys
    assert rashifal_cost.REFRESHES_PER_MONTH["today"] > 28
    assert 4 <= rashifal_cost.REFRESHES_PER_MONTH["weekly"] <= 5
    assert rashifal_cost.REFRESHES_PER_MONTH["yearly"] < 0.2


def test_the_daily_pages_dominate_the_volume():
    """83% of generations are the daily readings. That is why the refusal rate, which is the only term
    we control, is still the smaller lever - and the reason this is measured rather than assumed."""
    from scripts import rashifal_cost

    per_month = rashifal_cost.REFRESHES_PER_MONTH
    total = sum(per_month.values())
    assert per_month["today"] / total > 0.8, per_month


@pytest.mark.parametrize("model, expected_output_price", [
    ("claude-haiku-4-5", 5.0), ("claude-sonnet-5", 10.0)])
def test_the_marathi_model_costs_twice_the_other_two(model, expected_output_price):
    """The finding the cost model exists to surface: Marathi is a third of the calls and about half the
    bill. Pinned so that a price change or a model swap shows up here rather than in a surprise."""
    from app.ai.config import PRICES_PER_MTOK

    assert PRICES_PER_MTOK[model][1] == expected_output_price


def test_the_saving_the_cost_script_described_has_now_been_taken():
    """This asserted that Marathi was still on the stronger model, and said that if it ever changed,
    "the saving it describes has either been taken or no longer exists". It has been taken: every
    language is on claude-haiku-5-5, so there is no per-language override left and no dearer language to
    move. The cost script's own recommendation disappears with it, because its weights are now equal."""
    from app.rashifal.config import LANGUAGE_MODEL_DEFAULTS, get_rashifal_settings

    assert LANGUAGE_MODEL_DEFAULTS == {}, LANGUAGE_MODEL_DEFAULTS
    settings = get_rashifal_settings()
    assert len({settings.model_for((lang,)) for lang in ("en", "hi", "mr")}) == 1


def test_the_cost_scripts_make_no_ai_calls_and_write_nothing():
    """Both are meant to be safe to run on the VPS at any time, so neither may call a model or touch the
    store. Read as source, because importing them is not the same as proving what they do not do."""
    import pathlib

    for name in ("rashifal_cost.py", "pass_rate.py"):
        source = pathlib.Path("scripts", name).read_text(encoding="utf-8")
        body = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
        for forbidden in ("generate_json", "ClaudeClient", "Anthropic", "refresh(", "save_page", "db.transaction(write=True"):
            assert forbidden not in body, (name, forbidden)
