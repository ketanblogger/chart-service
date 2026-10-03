"""The three read-only aggregators: the cost ledger, the quality page and rashifal ops.

What is pinned here is the judgement calls, not the arithmetic - the places where the honest answer and the
convenient answer differ:

- the ledger's **failed-work bucket stays empty**, because nothing records the cost of a generation that
  burned tokens and then failed. It reports the size of that hole instead of estimating it;
- a report's cost is counted on the day its order was **paid**, so cost and revenue in "cost per rupee of
  revenue" come from the same day;
- "stale" comes from `window_for`, the same function the refresh uses, so this page cannot disagree with
  what the next run will actually regenerate;
- per-language rashifal figures are only the checker's rejections, because that is the only per-language
  number a run report carries.

Invented data only; `tests/` is published.
"""

import datetime as dt
import json
import time

import pytest

from app import db
from app.admin import ledger, metrics, quality, rashifal_ops
from app.payments import store

RUN = {"run_id": "aaaa1111-20260928T000500", "periods": ["today"], "languages": ["en", "hi", "mr"],
       "model": "claude-haiku-4-5", "batch": False, "calls": 36, "wall_clock_seconds": 180.0,
       "cost_estimate_inr": 18.0, "counts": {"generated": 12, "partial": 0, "skipped": 0, "failed": 0},
       "failed_checks_by_language": {"mr": 2},
       "rejections": [{"rashi": "dhanu", "period": "today", "attempt": 1, "language": "mr",
                       "message": "the Marathi version writes a word this checker rejects"}]}


def earlier_today(now, seconds: float) -> float:
    """`seconds` ago, but never before the start of the IST day `now` falls in.

    A bare `now.timestamp() - 600` is a test with a shelf life: the ledger buckets by IST DAY, so ten minutes
    before 00:08 IST is 23:58 YESTERDAY and falls outside `window(1, now)`. This test failed at 00:08 on
    2026-09-29 for exactly that reason, having passed all day, with nothing having changed - the same shape as
    the first-sale marker that expired by the calendar. Clamped, the intent ("a few minutes ago, today")
    survives midnight.
    """
    return max(now.timestamp() - seconds, metrics.day_start(now.date()) + 60)


def paid(order_id: str, *, cost_inr: float | None, paid_at: float, amount_paise: int = 29382,
         language: str = "mr", attempts: int = 1, fulfilment: str = "ready", usage: dict | None = None):
    store.insert_order(order_id=order_id, product="kundali-report", kind="report", amount_paise=amount_paise,
                       currency="INR", razorpay_order_id=f"order_{order_id}", user_id="user-under-test",
                       report_id=order_id.ljust(32, "d")[:32], language=language, as_of="2026-09-20")
    base = int(amount_paise / 1.18)
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET status='paid', payment_id='pay_test', paid_via='verify', paid_at=?, "
                     "updated_at=?, fulfilment=?, attempts=?, cost_inr=?, usage_json=?, base_paise=?, "
                     "gst_paise=?, gst_rate_bp=1800 WHERE id=?",
                     (paid_at, paid_at + 300, fulfilment, attempts, cost_inr,
                      json.dumps(usage) if usage else None, base, amount_paise - base, order_id))


# ---- the cost ledger ---------------------------------------------------------------------------------


def test_report_cost_is_counted_on_the_day_the_order_was_paid():
    now = metrics.now_ist()
    yesterday = now.date() - dt.timedelta(days=1)
    paid("ord_ledger000001", cost_inr=22.5, paid_at=metrics.day_start(yesterday) + 3600)
    view = ledger.daily(7, now)
    rows = {row["day"]: row for row in view["rows"]}
    assert rows[yesterday.isoformat()]["spend"][ledger.REPORTS] == pytest.approx(22.5)
    assert rows[now.date().isoformat()]["spend"][ledger.REPORTS] == 0.0


def test_the_failed_work_bucket_is_always_empty_and_the_hole_is_measured_instead():
    """`finish_fulfilment` writes `cost_inr` only on success, so a failed generation leaves no cost behind.
    A bucket reading "failed work: Rs 0" in a month with failed books is worse than an empty one."""
    now = metrics.now_ist()
    paid("ord_ledger000002", cost_inr=None, paid_at=earlier_today(now, 600), fulfilment="failed", attempts=3)
    view = ledger.daily(7, now)
    assert view["totals"][ledger.FAILED] is None
    assert all(row["spend"][ledger.FAILED] is None for row in view["rows"])
    assert view["blind_spot"]["orders_failed"] == 1
    assert view["blind_spot"]["retried_attempts"] == 2
    assert view["blind_spot"]["orders_without_cost"] == 1


def test_cost_per_rupee_of_revenue_is_none_on_a_day_with_no_revenue():
    """Spend with no sales is not an infinite ratio, it is a day the ratio does not describe."""
    now = metrics.now_ist()
    view = ledger.daily(3, now)
    assert all(row["cost_per_rupee"] is None for row in view["rows"])
    assert view["cost_per_rupee"] is None


def test_cost_per_rupee_of_revenue_divides_spend_by_net_revenue():
    now = metrics.now_ist()
    paid("ord_ledger000003", cost_inr=24.9, paid_at=earlier_today(now, 600))
    view = ledger.daily(1, now)
    assert view["net_revenue_inr"] == pytest.approx(24900 / 100, rel=0.01)
    assert view["cost_per_rupee"] == pytest.approx(24.9 / 249.0, rel=0.01)


def test_a_rashifal_run_report_is_read_for_its_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("RASHIFAL_RUNS_DIR", str(tmp_path))
    (tmp_path / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
    now = metrics.now_ist()
    view = ledger.daily(1, now)
    assert view["totals"][ledger.RASHIFAL] == pytest.approx(18.0)
    assert ("claude-haiku-4-5", 18.0) in [(row["model"], row["cost_inr"]) for row in view["by_model"]]


def test_an_unreadable_run_report_is_skipped_rather_than_taking_the_page_down(tmp_path, monkeypatch):
    monkeypatch.setenv("RASHIFAL_RUNS_DIR", str(tmp_path))
    (tmp_path / "good.json").write_text(json.dumps(RUN), encoding="utf-8")
    (tmp_path / "truncated.json").write_text("{not json", encoding="utf-8")
    assert len(ledger.rashifal_runs()) == 1


def test_by_language_counts_orders_even_when_their_cost_is_not_recorded():
    now = metrics.now_ist()
    paid("ord_ledger000004", cost_inr=None, paid_at=earlier_today(now, 300), language="hi")
    paid("ord_ledger000005", cost_inr=10.0, paid_at=earlier_today(now, 200), language="hi")
    rows = {row["language"]: row for row in ledger.daily(1, now)["by_language"]}
    assert rows["hi"]["orders"] == 2
    assert rows["hi"]["cost_inr"] == pytest.approx(10.0), "the recorded part only, and the count says why"


def test_the_month_projection_is_straight_line_on_the_days_elapsed():
    now = dt.datetime(2026, 9, 10, 12, 0, tzinfo=metrics.IST)   # 10 of 30 days elapsed
    paid("ord_ledger000006", cost_inr=100.0, paid_at=metrics.day_start(dt.date(2026, 9, 3)) + 3600)
    projection = ledger.month_projection(now)
    assert (projection["elapsed_days"], projection["days_in_month"]) == (10, 30)
    assert projection["spent_inr"] == pytest.approx(100.0)
    assert projection["projected_inr"] == pytest.approx(300.0)


# ---- generation and quality --------------------------------------------------------------------------


def _book_usage(attempts_per_part, cuts=None):
    return {"model": "claude-sonnet-5", "usage": {},
            "calls": [{"call": f"part-{index}", "attempts": attempts, "redactions": 0, "repairs": 0,
                       "cut_by_chapter": (cuts or {}), "cost_estimate_inr": 5.0 * attempts}
                      for index, attempts in enumerate(attempts_per_part)]}


def test_the_pass_rate_series_leaves_a_gap_on_a_day_with_no_calls():
    """A day nobody bought anything is not a day the pass rate collapsed, so the series carries None and
    the chart draws a gap. A zero there would read as an outage."""
    now = metrics.now_ist()
    paid("ord_quality00001", cost_inr=10.0, paid_at=earlier_today(now, 300), usage=_book_usage([1, 1, 2]))
    series = {row["day"]: row for row in quality.pass_rate_by_day(3, now)}
    today = series[now.date().isoformat()]
    assert (today["calls"], today["first"]) == (3, 2)
    assert today["rate"] == pytest.approx(200 / 3)
    older = series[(now.date() - dt.timedelta(days=2)).isoformat()]
    assert older["calls"] == 0 and older["rate"] is None


def test_durations_are_grouped_by_product_and_language():
    now = metrics.now_ist()
    paid("ord_quality00002", cost_inr=10.0, paid_at=earlier_today(now, 600), language="mr")
    paid("ord_quality00003", cost_inr=10.0, paid_at=earlier_today(now, 600), language="hi")
    rows = quality.overview(7, now)["by_product_language"]
    assert {(row["product"], row["language"]) for row in rows} == {("kundali-report", "mr"), ("kundali-report", "hi")}
    assert all(row["p50"] == pytest.approx(300) for row in rows)


def test_redactions_are_summed_per_chapter_across_sales():
    """A chapter cut on every sale of one product matters more than one cut once, and only the order rows
    know how many sales there were."""
    now = metrics.now_ist()
    paid("ord_quality00004", cost_inr=10.0, paid_at=earlier_today(now, 400), usage=_book_usage([1], {"3.2": 2}))
    paid("ord_quality00005", cost_inr=10.0, paid_at=earlier_today(now, 300), usage=_book_usage([1], {"3.2": 1}))
    assert quality.overview(7, now)["redactions"][0] == {"chapter": "3.2", "cut": 3}


def test_the_most_expensive_calls_exclude_the_ones_with_no_recorded_cost():
    """A None must not sort to the bottom as a zero and must not be presented as a cheap call - it is a
    call whose cost nobody wrote down."""
    now = metrics.now_ist()
    usage = _book_usage([1, 2])
    usage["calls"][0]["cost_estimate_inr"] = None
    paid("ord_quality00006", cost_inr=10.0, paid_at=earlier_today(now, 300), usage=usage)
    expensive = quality.overview(7, now)["expensive"]
    assert [call["call"] for call in expensive] == ["part-1"]


def test_failure_kinds_reads_only_the_meta_of_a_report_file(tmp_path, monkeypatch):
    """The report file also holds the whole engine chart of a real customer. Only `meta` is parsed out, and
    only that is cached, so a customer's chart never lives in the dashboard's memory."""
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    (tmp_path / "report.json").write_text(json.dumps({
        "id": "e" * 32, "product": "kundali-report", "language": "mr",
        "data": {"birth": {"date": "1988-11-30", "city": "Nagpur"}},
        "meta": {"model": "claude-sonnet-5", "attempts": 2, "checks": {"rejected_drafts": [
            {"attempt": 1, "problems": [{"kind": "unverifiable_date", "where": "career paragraph 2",
                                         "message": "the date does not appear anywhere in the data"}]}]}}}),
        encoding="utf-8")
    quality._meta_cache.clear()
    kinds = quality.failure_kinds()
    assert kinds[0]["kind"] == "unverifiable_date" and kinds[0]["count"] == 1
    assert "career paragraph 2" in kinds[0]["examples"][0]
    assert kinds[0]["languages"] == {"mr": 1}
    cached = next(iter(quality._meta_cache.values()))[1]
    assert "data" not in cached, "the chart must not be cached by the dashboard"


def test_a_structure_only_rejection_is_still_counted(tmp_path, monkeypatch):
    """The flat report and the book record a rejected draft differently. Skipping either shape would make
    whichever product is quieter look like the clean one."""
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    (tmp_path / "report.json").write_text(json.dumps({
        "product": "kundali-report-simple", "language": "en",
        "meta": {"checks": {"rejected_drafts": [{"attempt": 1, "structure": ["remedies: expected 3, got 1"],
                                                 "problems": []}]}}}), encoding="utf-8")
    quality._meta_cache.clear()
    assert quality.failure_kinds()[0]["kind"] == "structure"


# ---- rashifal ops ------------------------------------------------------------------------------------


def test_a_page_written_for_the_current_window_is_not_stale(monkeypatch):
    from app.rashifal.periods import window_for

    now = metrics.now_ist()
    current = window_for("today", now)
    monkeypatch.setattr(rashifal_ops, "stored_pages", lambda: {
        ("dhanu", "today"): {"period_start": current.start.date().isoformat(),
                            "period_end": current.end.date().isoformat(),
                            "languages": ["en", "hi", "mr"], "generated_at": "2026-09-28T00:10:00+00:00"}})
    state = rashifal_ops.page_state(now)["today"]
    assert state["fresh"] == 1
    assert state["stale"] == []
    assert len(state["missing"]) == 11, "the other eleven rashis have no page at all"


def test_a_page_from_an_earlier_window_is_stale_and_staleness_uses_the_refreshs_own_function(monkeypatch):
    """Compared on the window START. Comparing ends would call a page fresh on the last day of a window it
    was written for two windows ago, because two windows can share an end date."""
    now = metrics.now_ist()
    monkeypatch.setattr(rashifal_ops, "stored_pages", lambda: {
        ("dhanu", "today"): {"period_start": "2020-01-01", "period_end": "2020-01-02",
                            "languages": ["en", "hi", "mr"], "generated_at": "2020-01-01T00:10:00+00:00"}})
    assert rashifal_ops.page_state(now)["today"]["stale"] == ["dhanu"]


def test_a_page_missing_a_language_is_reported_as_incomplete(monkeypatch):
    from app.rashifal.periods import window_for

    now = metrics.now_ist()
    current = window_for("today", now)
    monkeypatch.setattr(rashifal_ops, "stored_pages", lambda: {
        ("dhanu", "today"): {"period_start": current.start.date().isoformat(),
                            "period_end": current.end.date().isoformat(),
                            "languages": ["en", "hi"], "generated_at": "2026-09-28T00:10:00+00:00"}})
    state = rashifal_ops.page_state(now)["today"]
    assert state["incomplete"] == [{"rashi": "dhanu", "missing": ["mr"]}]


def test_the_next_figure_is_a_window_boundary_and_the_page_says_which_refresh_runs(monkeypatch):
    """The daily window is never later than any other, so it is always the one to name - but on the last day
    of a month it is not SOONER either, it is exactly equal to the monthly one. This test passed every day
    until 30 September 2026, when the tie was broken alphabetically and the page announced "monthly".
    Asserted on a fixed month-end date as well as on today, so it cannot go back to passing by calendar luck."""
    now = metrics.now_ist()
    upcoming = rashifal_ops.next_boundary(now)
    assert upcoming["period"] == "today", "the daily window is never later than another, so it is the one to name"
    assert upcoming["at"] > now

    month_end = now.replace(year=2026, month=9, day=30, hour=0, minute=25, second=0, microsecond=0)
    tied = rashifal_ops.next_boundary(month_end)
    assert tied["period"] == "today", "a tie with the monthly window still names the daily one"
    assert tied["at"] == rashifal_ops.page_state(month_end)["monthly"]["next_boundary"], "they really are tied"
    monkeypatch.delenv("RASHIFAL_SCHEDULER", raising=False)
    assert "cannot see" in rashifal_ops.how_it_runs(), "it must not invent a next run time it cannot know"


def test_cost_per_generated_page_is_none_for_a_run_that_generated_nothing(tmp_path, monkeypatch):
    """A run where every page already covered its window did nothing correctly; it is not infinitely
    expensive."""
    monkeypatch.setenv("RASHIFAL_RUNS_DIR", str(tmp_path))
    (tmp_path / "run.json").write_text(json.dumps({
        **RUN, "counts": {"generated": 0, "partial": 0, "skipped": 12, "failed": 0},
        "cost_estimate_inr": 0.0}), encoding="utf-8")
    row = rashifal_ops.runs_by_period_language(ledger.rashifal_runs())[0]
    assert row["cost_per_page"] is None


def test_per_language_rashifal_figures_are_only_the_checkers_rejections(tmp_path, monkeypatch):
    """The only per-language number a run report carries. A per-language "generated" would have to be
    invented by division, and Marathi is exactly the column somebody would act on."""
    monkeypatch.setenv("RASHIFAL_RUNS_DIR", str(tmp_path))
    (tmp_path / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
    row = rashifal_ops.runs_by_period_language(ledger.rashifal_runs())[0]
    assert row["failed_by_language"] == {"mr": 2}
    assert row["generated"] == 12, "a per-page count, across all three languages"
    assert "generated_by_language" not in row


def test_the_checkers_own_words_are_shown_rather_than_counted(tmp_path, monkeypatch):
    monkeypatch.setenv("RASHIFAL_RUNS_DIR", str(tmp_path))
    (tmp_path / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
    rejections = rashifal_ops.recent_rejections(ledger.rashifal_runs())
    assert rejections[0]["language"] == "mr"
    assert "rejects" in rejections[0]["message"]


def test_rashifal_ops_survives_an_empty_runs_directory_and_an_empty_store():
    view = rashifal_ops.overview()
    assert view["run_count"] == 0 and view["last_run"] is None
    assert view["missing_total"] == 60, "nothing has been generated, and the page says so"


# ---- the error recorder ------------------------------------------------------------------------------


def test_a_logged_warning_is_queued_and_not_written_from_the_logging_call(monkeypatch):
    """The property that keeps `emit` off the database: a warning must not open a write transaction in
    whichever thread logged it. If it did, a warning logged from inside a `db.transaction()` block would
    wait on a lock its own thread holds, for the whole 15-second busy timeout, and look like a hung request.
    """
    import logging

    from app.admin import errors

    writes = []
    monkeypatch.setattr(errors, "_write", lambda events: writes.append(len(events)))
    handler = errors._Recorder(level=logging.WARNING)
    handler.emit(logging.LogRecord("app.mailer", logging.WARNING, __file__, 1,
                                   "e-mail to someone@example.invalid refused: HTTP 403", (), None))
    assert writes == [], "emit must not have written anything itself"
    assert errors.flush() == 1, "the event is queued, and flushing is what writes it"
    assert writes == [1]


def test_an_address_in_a_log_line_is_masked_before_it_reaches_our_table():
    """The mailer's own lines name the customer's address, and this table is read by a page and a CSV."""
    import logging

    from app.admin import errors

    handler = errors._Recorder(level=logging.WARNING)
    handler.emit(logging.LogRecord("app.mailer", logging.WARNING, __file__, 1,
                                   "e-mail to %s refused: HTTP 403", ("buyer.one@example.invalid",), None))
    errors.flush()
    messages = [event["message"] for event in errors.recent()]
    assert any("b***@example.invalid" in message for message in messages)
    assert not any("buyer.one@example.invalid" in message for message in messages)


def test_an_order_token_in_a_logged_path_never_reaches_our_table():
    """End to end, through the real handler: a 500 under /order/{token} is logged with the path, and the
    path is a credential. This is the assertion that stops it being displayed on the health page."""
    import logging

    from app.admin import errors

    token = "Xk3mQp7rT9vB2nL8wZ4yC1dF"
    handler = errors._Recorder(level=logging.WARNING)
    handler.emit(logging.LogRecord("app.hardening", logging.ERROR, __file__, 1,
                                   "unhandled error on %s %s", ("GET", f"/order/{token}"), None))
    errors.flush()
    messages = [event["message"] for event in errors.recent()]
    assert messages and not any(token in message for message in messages)
    assert any("<token redacted>" in message for message in messages)


def test_identical_errors_inside_the_dedupe_window_become_one_row_with_a_count():
    """A loop that logs the same failure a thousand times costs one row and still reports a thousand."""
    from app.admin import errors

    now = time.time()
    for _ in range(5):
        errors.note(errors.SERVER_ERROR, "ERROR", "app.hardening", "unhandled error on GET /same", now)
    rows = errors.recent()
    assert len(rows) == 1 and rows[0]["times"] == 5
    assert errors.count_since(errors.SERVER_ERROR, now - 1) == 5, "the count is events, not rows"


def test_only_this_applications_warnings_are_kept():
    """Not a copy of the log. A third-party library's warnings are somebody else's diagnostics."""
    import logging

    from app.admin import errors

    handler = errors._Recorder(level=logging.WARNING)
    handler.emit(logging.LogRecord("httpx", logging.ERROR, __file__, 1, "connection reset", (), None))
    handler.emit(logging.LogRecord("app.ai.client", logging.INFO, __file__, 1, "a routine note", (), None))
    assert errors.flush() == 0


def test_a_log_line_is_classified_by_the_phrase_that_writes_it():
    """The phrases are the contract with the modules that log them. A rewording falls back to `other`, which
    still COUNTS the error - so a rewording blurs a category and never loses an error."""
    from app.admin import errors

    assert errors.classify("app.hardening", "unhandled error on GET /x") == errors.SERVER_ERROR
    assert errors.classify("app.mailer", "e-mail to x refused: HTTP 403") == errors.EMAIL_REFUSED
    assert errors.classify("app.payments.routes", "REJECTED webhook: bad or missing signature") == errors.WEBHOOK_SIGNATURE
    assert errors.classify("app.ai.report", "the model returned nothing usable") == errors.AI_ERROR
    assert errors.classify("app.web.routes", "something nobody anticipated") == errors.OTHER
