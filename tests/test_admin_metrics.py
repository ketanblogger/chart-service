"""The metric definitions in app/admin/metrics.py, one test per definition, NULL cases included.

The point of this file is the NULL cases. Every metric on the dashboard has an underlying column that can
be NULL - `cost_inr` for a cache hit or a pre-column order, the GST split for anything paid before GST was
recorded, `updated_at` for an order that never became ready - and NULL means "not recorded", never zero. A
metric that silently reads a NULL as 0 reports a 100% margin on a real sale, which is the most flattering
possible wrong answer and therefore the one nobody questions. So each definition is pinned twice: once with
the figure recorded and once without.

Invented data only. There is no real person, no real birth detail and no real name in this file: `tests/`
is published, and a fixture is as public as a comment.
"""

import datetime as dt
import json
import time

import pytest

from app import db
from app.admin import metrics
from app.payments import store

IST = metrics.IST
# A whole rupee price with 18% GST on top: 249 + 44.82 = 293.82. Chosen because it is the real launch
# arithmetic of the detailed book, so a rounding change in app/payments/gst.py shows up here too.
BOOK_BASE_PAISE, BOOK_GST_PAISE, BOOK_TOTAL_PAISE = 24900, 4482, 29382


def make_order(order_id: str, **overrides) -> dict:
    """One paid order row, with only the columns the dashboard reads. Invented birth details."""
    paid_at = overrides.pop("paid_at", time.time())
    clock = paid_at if paid_at is not None else time.time()
    fields = {
        "id": order_id, "product": "kundali-report", "kind": "report", "language": "mr",
        "amount_paise": BOOK_TOTAL_PAISE, "status": "paid", "fulfilment": "ready", "attempts": 1,
        "error": None, "cost_inr": 22.5, "usage_json": None, "email": "first.buyer@example.com",
        "report_id": "a" * 32, "created_at": clock - 30, "paid_at": paid_at, "updated_at": clock + 540,
        # `ready_at` is when it BECAME ready. `updated_at` is when the row was last touched, and anything
        # afterwards - an invoice number, a retried e-mail, a refund - moves that; one live order read as
        # ten hours of generation because of it. The two are equal here so the figures below still mean
        # what they meant, and the tests under them now say WHICH one is being measured.
        "ready_at": clock + 540,
        "base_paise": BOOK_BASE_PAISE, "gst_paise": BOOK_GST_PAISE, "gst_rate_bp": 1800,
    }
    fields.update(overrides)
    return fields


# ---- revenue -----------------------------------------------------------------------------------------


def test_net_revenue_is_the_recorded_gst_exclusive_base():
    net, recorded = metrics.net_revenue_paise(make_order("o1"))
    assert (net, recorded) == (BOOK_BASE_PAISE, True)


def test_net_revenue_falls_back_to_the_gross_when_the_gst_split_is_null_and_says_so():
    """The whole reason the helper returns a boolean. An order paid before GST was recorded has NULL there,
    and NULL is not zero tax and not a zero sale - the honest answer is the gross, flagged."""
    order = make_order("o2", base_paise=None, gst_paise=None, gst_rate_bp=None)
    net, recorded = metrics.net_revenue_paise(order)
    assert net == BOOK_TOTAL_PAISE
    assert recorded is False, "a fallback that cannot be distinguished from a real split is a silent lie"


def test_a_split_that_does_not_add_up_to_the_charge_counts_as_not_recorded():
    """A breakdown that disagrees with the money is worse than no breakdown: it would be printed."""
    net, recorded = metrics.net_revenue_paise(make_order("o3", base_paise=24900, gst_paise=1))
    assert (net, recorded) == (BOOK_TOTAL_PAISE, False)


def test_gross_revenue_is_the_amount_charged_including_gst():
    totals = metrics.summarise([make_order("o4")])
    assert totals.gross_paise == BOOK_TOTAL_PAISE
    assert totals.net_paise == BOOK_BASE_PAISE


def test_summarise_counts_the_orders_it_could_not_split_rather_than_hiding_them():
    totals = metrics.summarise([make_order("o5"), make_order("o6", base_paise=None, gst_paise=None)])
    assert totals.orders == 2
    assert totals.gst_unknown == 1
    assert totals.net_paise == BOOK_BASE_PAISE + BOOK_TOTAL_PAISE


def test_an_unpaid_order_contributes_nothing_to_revenue():
    totals = metrics.summarise([make_order("o7", status="created", paid_at=None, fulfilment="none")])
    assert (totals.orders, totals.net_paise) == (0, 0)


# ---- the payment fee ---------------------------------------------------------------------------------


def test_the_payment_fee_is_charged_on_the_gross_not_on_the_net(monkeypatch):
    """2% plus 18% GST on the fee = 2.36% of what actually moved through the gateway. Taking it off the
    net would understate it by the fee on the tax, which is the drift that makes a modelled margin wrong."""
    monkeypatch.setenv("PAYMENT_FEE_PERCENT", "2.0")
    monkeypatch.setenv("PAYMENT_FEE_GST_PERCENT", "18.0")
    assert metrics.payment_fee_paise(BOOK_TOTAL_PAISE) == round(BOOK_TOTAL_PAISE * 0.0236)
    assert metrics.payment_fee_paise(BOOK_TOTAL_PAISE) > metrics.payment_fee_paise(BOOK_BASE_PAISE)


def test_the_fee_rate_is_configurable(monkeypatch):
    monkeypatch.setenv("PAYMENT_FEE_PERCENT", "3")
    monkeypatch.setenv("PAYMENT_FEE_GST_PERCENT", "0")
    assert metrics.payment_fee_paise(10000) == 300


# ---- AI cost and margin ------------------------------------------------------------------------------


def test_ai_cost_is_none_when_the_column_is_null():
    assert metrics.ai_cost_inr(make_order("o8", cost_inr=None)) is None
    assert metrics.ai_cost_inr(make_order("o9", cost_inr=0.0)) == 0.0, "a recorded zero is a figure, not a gap"


def test_margin_is_net_minus_fee_minus_ai_cost(monkeypatch):
    monkeypatch.setenv("PAYMENT_FEE_PERCENT", "2.0")
    monkeypatch.setenv("PAYMENT_FEE_GST_PERCENT", "18.0")
    fee = metrics.payment_fee_paise(BOOK_TOTAL_PAISE) / 100
    margin = metrics.margin_inr(BOOK_TOTAL_PAISE, BOOK_BASE_PAISE, 22.5)
    assert margin == pytest.approx(BOOK_BASE_PAISE / 100 - fee - 22.5)
    assert metrics.margin_percent(BOOK_TOTAL_PAISE, BOOK_BASE_PAISE, 22.5) == pytest.approx(margin / 249 * 100)


def test_margin_is_none_when_the_ai_cost_is_not_recorded_and_never_a_100_percent_margin():
    """The defect this whole rule exists for: a NULL cost read as 0 makes a cache hit look like pure profit."""
    assert metrics.margin_inr(BOOK_TOTAL_PAISE, BOOK_BASE_PAISE, None) is None
    assert metrics.margin_percent(BOOK_TOTAL_PAISE, BOOK_BASE_PAISE, None) is None


def test_margin_percent_of_a_zero_sale_is_undefined_not_zero():
    assert metrics.margin_percent(0, 0, 5.0) is None


def test_a_window_margin_is_withheld_entirely_while_any_order_lacks_a_cost():
    """All-or-nothing on purpose. A margin summed over the orders that happen to have a cost has an
    unstated denominator, and the missing orders are exactly the ones that would pull it down."""
    totals = metrics.summarise([make_order("o10"), make_order("o11", cost_inr=None)])
    assert totals.cost_unknown == 1
    assert totals.margin_inr is None
    assert totals.margin_percent is None
    assert not hasattr(totals, "partial_margin_inr"), (
        "there is deliberately no partial margin: the only one that can be built here divides the net "
        "revenue of ALL the orders by the cost of SOME of them, which is the full figure wearing a "
        "smaller label")


def test_average_order_value_is_net_per_paid_order_and_none_with_no_orders():
    totals = metrics.summarise([make_order("o12"), make_order("o13")])
    assert totals.average_order_inr == pytest.approx(BOOK_BASE_PAISE / 100)
    assert metrics.Totals().average_order_inr is None


# ---- generation time ---------------------------------------------------------------------------------


def test_generation_time_is_ready_at_minus_paid_at():
    now = time.time()
    order = make_order("o14", paid_at=now, ready_at=now + 540, updated_at=now + 540, fulfilment="ready")
    assert metrics.generation_seconds(order) == pytest.approx(540)


def test_generation_time_ignores_anything_that_touches_the_row_afterwards():
    """THE LIVE BUG. An order ready in nine minutes read as ten hours because an invoice number, an
    e-mail retry or a refund moved `updated_at` long after the report was sitting there finished."""
    now = time.time()
    order = make_order("o14b", paid_at=now, ready_at=now + 540, updated_at=now + 10 * 3600,
                       fulfilment="ready")
    assert metrics.generation_seconds(order) == pytest.approx(540)


def test_an_order_with_no_ready_time_is_unmeasured_rather_than_guessed():
    """Rows written before the column existed have no honest answer; `durations` reports them as missing,
    which is visible. A wrong number is not."""
    now = time.time()
    order = make_order("o14c", paid_at=now, ready_at=None, updated_at=now + 10 * 3600, fulfilment="ready")
    assert metrics.generation_seconds(order) is None
    spread = metrics.durations([order])
    assert spread.count == 0 and spread.missing == 1


def test_generation_time_is_none_unless_the_order_is_ready():
    """An order that is not ready has not finished generating, whatever its timestamps say."""
    now = time.time()
    for state in ("failed", "generating", "pending", "none"):
        order = make_order("o15", paid_at=now, ready_at=now + 540, updated_at=now + 540, fulfilment=state)
        assert metrics.ready_at(order) is None
        assert metrics.generation_seconds(order) is None, state


def test_a_backwards_duration_is_dropped_not_clamped_to_zero():
    """It can only come from timestamps written by different hands, and a zero folded into a p50 makes the
    whole percentile quietly optimistic."""
    now = time.time()
    backwards = make_order("o16", paid_at=now, ready_at=now - 10, updated_at=now - 10)
    assert metrics.generation_seconds(backwards) is None


def test_percentiles_are_nearest_rank_and_none_for_an_empty_set():
    assert metrics.percentile([], 0.5) is None
    assert metrics.percentile([10], 0.9) == 10, "with one sample, p90 is that sample"
    assert metrics.percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert metrics.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9) == 9
    assert metrics.percentile([1, 2, 3], 0.9) in (3, 3.0), "never a value no sample ever had"


def test_durations_reports_how_many_orders_had_no_usable_duration():
    now = time.time()
    spread = metrics.durations([make_order("o17", paid_at=now, ready_at=now + 60, updated_at=now + 60),
                               make_order("o18", fulfilment="failed")])
    assert spread.count == 1 and spread.missing == 1
    assert spread.p50 == pytest.approx(60) and spread.longest == pytest.approx(60)


# ---- AI calls and the first-attempt pass rate ---------------------------------------------------------


def _usage(calls=None, attempts=None, model="claude-sonnet-5") -> str:
    payload = {"model": model, "usage": {}}
    if calls is not None:
        payload["calls"] = calls
    if attempts is not None:
        payload["attempts"] = attempts
    return json.dumps(payload)


def test_a_book_contributes_one_call_per_part_and_a_flat_report_exactly_one():
    """Both shapes, because whichever one a call site forgets gets dropped from the pass rate - and dropping
    the flat reports silently RAISES it, since the book is what retries."""
    book = make_order("o19", usage_json=_usage(calls=[{"call": "part-a", "attempts": 1},
                                                      {"call": "part-b", "attempts": 3}]))
    flat = make_order("o20", usage_json=_usage(attempts=2))
    assert [call["attempts"] for call in metrics.calls_of(book)] == [1, 3]
    assert [call["attempts"] for call in metrics.calls_of(flat)] == [2]


def test_an_order_with_no_usage_recorded_contributes_no_calls_rather_than_a_passing_one():
    assert metrics.calls_of(make_order("o21", usage_json=None)) == []
    assert metrics.calls_of(make_order("o22", usage_json="not json at all")) == []


def test_first_attempt_pass_rate_is_calls_with_one_attempt_over_all_calls():
    calls = [{"attempts": 1}, {"attempts": 1}, {"attempts": 3}, {"attempts": 2}]
    rate, first, total = metrics.first_attempt_pass_rate(calls)
    assert (rate, first, total) == (50.0, 2, 4)


def test_a_pass_rate_over_zero_calls_is_none_not_100_percent():
    assert metrics.first_attempt_pass_rate([]) == (None, 0, 0)


# ---- IST windows -------------------------------------------------------------------------------------


def test_a_window_of_one_day_is_the_current_ist_calendar_day():
    now = dt.datetime(2026, 9, 28, 23, 58, tzinfo=IST)
    start, end = metrics.window(1, now)
    assert metrics.to_ist(start) == dt.datetime(2026, 9, 28, 0, 0, tzinfo=IST)
    assert metrics.to_ist(end) == dt.datetime(2026, 9, 29, 0, 0, tzinfo=IST)


def test_a_thirty_day_window_includes_today_and_has_thirty_labels():
    now = dt.datetime(2026, 9, 28, 12, 0, tzinfo=IST)
    labels = metrics.day_labels(30, now)
    assert len(labels) == 30
    assert labels[-1] == "2026-09-28" and labels[0] == "2026-08-30"


def test_the_day_boundary_is_ist_not_utc():
    """18:40 UTC on the 27th is 00:10 IST on the 28th. A UTC-bucketed dashboard puts that sale on the
    wrong day, and the operator reconciles against IST."""
    moment = dt.datetime(2026, 9, 27, 18, 40, tzinfo=dt.timezone.utc)
    assert metrics.ist_day(moment.timestamp()) == "2026-09-28"


# ---- masking -----------------------------------------------------------------------------------------


def test_an_address_is_masked_to_one_leading_character_and_the_domain():
    assert metrics.mask_email("kalpana@gmail.com") == "k***@gmail.com"
    assert metrics.mask_email("  A.Buyer@Example.COM ") == "A***@Example.COM"


def test_the_local_part_length_is_not_preserved_by_the_mask():
    """Three stars always. With a fixed domain, the length of the local part is a real narrowing of who
    this is, and it is free to withhold."""
    assert metrics.mask_email("ab@x.com") == "a***@x.com"
    assert metrics.mask_email("abcdefghijkl@x.com") == "a***@x.com"


def test_an_absent_or_malformed_address_never_produces_something_that_looks_like_one():
    assert metrics.mask_email(None) == "-"
    assert metrics.mask_email("") == "-"
    assert metrics.mask_email("not-an-address") == "***"


def test_the_order_token_is_stripped_out_of_any_text_we_keep():
    """The leak this scrub exists for. `app/hardening.py` logs the request path of every unhandled error,
    and a path under /order/ IS a bearer credential: whoever holds that token can open the customer's
    purchase and download their report. app/admin/errors.py keeps those log lines in a table that a web page
    prints and a CSV downloads, so without this the system-health page would publish working credentials."""
    token = "Xk3mQp7rT9vB2nL8wZ4yC1dF"
    scrubbed = metrics.scrub(f"unhandled error on GET /order/{token}")
    assert token not in scrubbed
    assert "<token redacted>" in scrubbed


def test_a_token_query_parameter_is_stripped_too():
    """The report and PDF URLs carry the same credential as `?token=`, and a 500 on a download logs it."""
    token = "Xk3mQp7rT9vB2nL8wZ4yC1dF"
    scrubbed = metrics.scrub(f"unhandled error on GET /api/report/abc/pdf?name=A&token={token}")
    assert token not in scrubbed and "<redacted>" in scrubbed


# A real token, generated the way app/web/routes.py mints one, so these cases cannot pass against a
# hand-written string that happens to be shorter or tamer than the real thing.
TOKEN = "6YySs8S7BmyNpk3-oWmr7p_cGUNp6JFk"   # the shape of secrets.token_urlsafe(24): 32 urlsafe characters
REPORT_ID = "7f3a9b2c1d4e5f60718293a4b5c6d7e8"  # 32 hex - the SAME length and character class as a token


@pytest.mark.parametrize("line", [
    f"unhandled error on GET /order/{TOKEN}",
    f"unhandled error on GET /hi/order/{TOKEN}/download",
    f"unhandled error on GET //order/{TOKEN}.",
    f"unhandled error on GET /ORDER/{TOKEN}",              # case: a 404 in practice, closed anyway
    f"link https://rashikundli.com/mr/order/{TOKEN} sent",  # the URL the order-link e-mail carries
    f"token={TOKEN}",
    f"order_token: {TOKEN}",
    f'access_token="{TOKEN}"',
    '{"token": "%s"}' % TOKEN,
    f"order ord_x token {TOKEN} failed",                   # named in the text, no path around it
])
def test_no_shape_the_token_can_arrive_in_survives_the_scrub(line):
    """Every bypass found in review, kept as a case so the next person cannot quietly narrow the pattern.

    The last two are the ones that were open: a token named in a log line rather than sitting in a path. No
    line in the app writes one that way today, which is exactly why it is pinned - this module's premise is
    that it captures what the app logs in FUTURE."""
    scrubbed = metrics.scrub(line)
    assert TOKEN not in scrubbed
    assert "redacted" in scrubbed


@pytest.mark.parametrize("line", [
    f"unhandled error on GET /api/report/{REPORT_ID}/pdf",
    f"PDF uses non-bundled fonts for report {REPORT_ID}",
    f"unreadable cached report {REPORT_ID}; ignoring",
    "token generation failed",
    "token expired",
])
def test_the_scrub_is_keyed_on_the_word_and_not_on_the_values_shape(line):
    """A report id is 32 characters of the same class as a token, so a shape rule would blank it out of every
    line on the health page - and the report id is how an operator finds the failing report. A scrub that
    destroys the diagnostic it protects gets switched off, which leaves the token exposed again. So the rule
    is keyed on the word "token", and this is the test that stops it becoming a shape rule later."""
    assert metrics.scrub(line) == line


def test_scrub_leaves_an_ordinary_path_alone():
    """A scrub that mangles every path makes the health page useless for finding the failing route."""
    assert metrics.scrub("unhandled error on GET /hi/kundali") == "unhandled error on GET /hi/kundali"


def test_scrub_does_both_jobs_at_once():
    assert metrics.scrub("order /order/Xk3mQp7rT9vB2nL8wZ4yC1dF for buyer@example.com") == (
        "order /order/<token redacted> for b***@example.com")


def test_addresses_inside_a_free_text_string_are_masked_too():
    """The mailer's own log lines name the address, and those lines are kept in our table."""
    masked = metrics.mask_emails_in("e-mail to buyer.one@example.com refused: HTTP 403")
    assert "buyer.one@example.com" not in masked
    assert "b***@example.com" in masked


# ---- against a real database -------------------------------------------------------------------------


def test_gst_status_reports_the_column_it_is_using(monkeypatch):
    """The banner on the overview. It has to be able to say "there is no GST column yet", because a
    dashboard that prints the gross under a net label is how a tax liability gets spent."""
    store.insert_order(order_id=store.new_order_id(), product="kundali-report", kind="report",
                       amount_paise=BOOK_TOTAL_PAISE, currency="INR", razorpay_order_id="order_GstStatus",
                       user_id="u1")
    status = metrics.gst_status()
    assert status["recorded"] is True and "base_paise" not in status["columns"]
    assert "net revenue" in status["how"].lower()

    monkeypatch.setattr(metrics, "order_columns", lambda: {"id", "amount_paise"})
    absent = metrics.gst_status()
    assert absent["recorded"] is False
    assert "EQUALS" in absent["how"], "the fallback has to be stated in words, not implied"


def test_net_revenue_of_a_row_written_before_the_gst_columns_existed():
    """The real pre-GST shape: the row exists, the columns exist, the values are NULL."""
    order_id = store.new_order_id()
    store.insert_order(order_id=order_id, product="kundali-report-simple", kind="report", amount_paise=4900,
                       currency="INR", razorpay_order_id="order_PreGst", user_id="u2")
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET status='paid', paid_at=? WHERE id=?", (time.time(), order_id))
    row = store.get_order(order_id)
    assert row["base_paise"] is None
    net, recorded = metrics.net_revenue_paise(row)
    assert (net, recorded) == (4900, False)


def test_refunds_are_asked_about_in_exactly_one_place():
    """Nothing writes a refund back today, so this is False for everyone - and it is a single function, so
    the day a refund column appears one edit removes refunds from every figure at once."""
    assert metrics.is_refunded(make_order("o23")) is False
    assert metrics.is_refunded({**make_order("o24"), "refunded_at": time.time()}) is True
