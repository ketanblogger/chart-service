"""The alerts and the daily digest, proved to fire - with a delivery function that cannot send anything.

WHY DELIVERY IS INJECTED RATHER THAN MOCKED OUT. `fire_due(deliver=...)` takes the sending function as an
argument, so these tests hand it a list to append to. The alternative - relying on `REPORT_EMAIL_ENABLED`
being unset - is a test that passes because the environment happens to be empty, and this suite runs on a
developer's box where a real `.env` sits next to it. A test that must be trusted not to send e-mail is a
test somebody eventually runs with a live key.

Every rule is exercised with a condition that makes it fire and a condition that makes it stay silent,
because an alert that fires for everything is filtered by its reader and is then the same as no alert.

Invented data only; `tests/` is published.
"""

import datetime as dt
import json
import time

import pytest

from app import db
from app.admin import alerts, errors, metrics
from app.payments import store


@pytest.fixture(autouse=True)
def alert_env(monkeypatch):
    monkeypatch.setenv("ALERT_READY_MINUTES", "15")
    monkeypatch.setenv("ALERT_COST_LIMIT_BOOK_INR", "150")
    monkeypatch.setenv("ALERT_COST_LIMIT_REPORT_INR", "40")
    monkeypatch.setenv("AI_DAILY_LIMIT_INR", "300")
    monkeypatch.setenv("ALERT_5XX_IN_10_MIN", "5")
    monkeypatch.setenv("ALERT_EMAIL_TO", "operations@example.invalid")
    monkeypatch.setenv("BASE_URL", "https://admin.test")
    # Belt as well as braces: delivery is injected in every test below, and the mailer is also off.
    monkeypatch.setenv("REPORT_EMAIL_ENABLED", "")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)


class Recorder:
    """The injected delivery. Records what would have been sent and reports success."""

    def __init__(self, succeed: bool = True):
        self.sent: list[tuple[str, str]] = []
        self.succeed = succeed

    def __call__(self, subject: str, body: str) -> bool:
        self.sent.append((subject, body))
        return self.succeed


def order(order_id: str, *, paid_ago: float = 60, fulfilment: str = "ready", amount_paise: int = 29382,
          cost_inr: float | None = 22.5, attempts: int = 1, error: str | None = None) -> dict:
    store.insert_order(order_id=order_id, product="kundali-report", kind="report", amount_paise=amount_paise,
                       currency="INR", razorpay_order_id=f"order_{order_id}", user_id="user-under-test",
                       report_id=order_id.ljust(32, "c")[:32], language="mr", as_of="2026-09-20",
                       email="buyer@example.invalid")
    now = time.time()
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET status='paid', payment_id='pay_test', paid_via='verify', "
                     "paid_at=?, updated_at=?, fulfilment=?, attempts=?, cost_inr=?, error=?, "
                     "base_paise=?, gst_paise=?, gst_rate_bp=1800 WHERE id=?",
                     (now - paid_ago, now - paid_ago + 30, fulfilment, attempts, cost_inr, error,
                      int(amount_paise / 1.18), amount_paise - int(amount_paise / 1.18), order_id))
    return store.get_order(order_id)


# ---- the proof that an alert fires --------------------------------------------------------------------


def test_a_paid_order_not_ready_after_fifteen_minutes_fires_an_alert():
    """The alert that costs money if it does not arrive: a customer has paid and has nothing."""
    order("ord_late000000001", paid_ago=20 * 60, fulfilment="generating")
    recorder = Recorder()
    sent = alerts.fire_due(deliver=recorder)
    assert [alert.key for alert in sent] == ["order_late"]
    subject, body = recorder.sent[0]
    assert "ord_late000000001" in subject
    assert "not ready" in subject
    assert "CRITICAL" in subject
    assert "15 min" in body


def test_an_order_paid_ten_minutes_ago_does_not_fire():
    order("ord_recent00000001", paid_ago=10 * 60, fulfilment="generating")
    recorder = Recorder()
    assert alerts.fire_due(deliver=recorder) == []
    assert recorder.sent == []


def test_a_ready_order_never_fires_however_old_it_is():
    order("ord_old0000000001", paid_ago=40 * 86400, fulfilment="ready")
    assert alerts.fire_due(deliver=Recorder()) == []


def test_a_failed_order_fires_its_own_alert_with_the_error_in_it():
    order("ord_failed00000001", paid_ago=30 * 60, fulfilment="failed", attempts=3,
          error="AIUnavailable: upstream connect error")
    recorder = Recorder()
    sent = alerts.fire_due(deliver=recorder)
    assert [alert.key for alert in sent] == ["order_failed"]
    assert "upstream connect error" in recorder.sent[0][1]


def test_a_book_over_its_cost_limit_fires_and_one_under_it_does_not():
    """Two limits, because a ₹249 book and a ₹49 report have nothing in common - one rupee figure would
    either never fire on a book or fire on every report."""
    order("ord_dear000000001", amount_paise=29382, cost_inr=180.0)
    order("ord_cheap0000001", amount_paise=29382, cost_inr=20.0)
    sent = alerts.fire_due(deliver=Recorder())
    assert [(alert.key, alert.subject) for alert in sent] == [("cost_over", "ord_dear000000001")]


def test_a_small_report_is_judged_against_the_small_limit():
    order("ord_small0000001", amount_paise=5782, cost_inr=45.0)   # Rs 49 + GST, cost over Rs 40
    sent = alerts.fire_due(deliver=Recorder())
    assert [alert.key for alert in sent] == ["cost_over"]


def test_an_order_with_no_recorded_cost_never_fires_a_cost_alert():
    """NULL is not a large number either. A cache hit records nothing and must not be read as expensive."""
    order("ord_nocost000001", cost_inr=None)
    assert alerts.fire_due(deliver=Recorder()) == []


def test_daily_spend_over_the_limit_fires_once_for_the_day(monkeypatch):
    monkeypatch.setenv("AI_DAILY_LIMIT_INR", "50")
    order("ord_spend00000001", cost_inr=80.0)
    recorder = Recorder()
    keys = [alert.key for alert in alerts.fire_due(deliver=recorder)]
    assert "spend_over" in keys
    assert alerts.fire_due(deliver=recorder) == [], "the same day must not raise it twice"


def test_a_rashifal_run_that_left_failed_pages_fires(tmp_path, monkeypatch):
    monkeypatch.setenv("RASHIFAL_RUNS_DIR", str(tmp_path))
    (tmp_path / "run.json").write_text(json.dumps({
        "run_id": "abc12345-20260928T000500", "periods": ["today"], "languages": ["en", "hi", "mr"],
        "model": "claude-haiku-4-5", "calls": 36, "wall_clock_seconds": 120.0,
        "cost_estimate_inr": 15.3, "counts": {"generated": 9, "partial": 0, "skipped": 0, "failed": 3},
        "failed_checks_by_language": {"mr": 5}}), encoding="utf-8")
    recorder = Recorder()
    sent = alerts.fire_due(deliver=recorder)
    assert [alert.key for alert in sent] == ["rashifal_failed"]
    assert "mr:5" in recorder.sent[0][1], "the language breakdown is the actionable part"
    assert "old content was kept" in recorder.sent[0][1]


def test_a_clean_rashifal_run_does_not_fire(tmp_path, monkeypatch):
    monkeypatch.setenv("RASHIFAL_RUNS_DIR", str(tmp_path))
    (tmp_path / "run.json").write_text(json.dumps({
        "run_id": "def12345-20260928T000500", "counts": {"generated": 12, "failed": 0},
        "cost_estimate_inr": 15.3}), encoding="utf-8")
    assert alerts.fire_due(deliver=Recorder()) == []


def test_a_burst_of_server_errors_fires_once_per_ten_minute_bucket():
    # Anchored ten seconds into a bucket rather than at `time.time()`. The alert is deduplicated per
    # ten-minute wall-clock bucket, so a test that starts at an arbitrary moment and then steps forward a
    # minute crosses the boundary roughly one run in ten - which is how this test failed once before it was
    # anchored, and a suite that fails one run in ten is a suite whose failures get re-run rather than read.
    now = (time.time() // 600) * 600 + 10
    for index in range(6):
        errors.note(errors.SERVER_ERROR, "ERROR", "app.hardening", f"unhandled error on GET /page-{index}", now)
    recorder = Recorder()
    sent = alerts.fire_due(now=now, deliver=recorder)
    assert [alert.key for alert in sent] == ["errors_5xx"]
    assert "6 server errors" in recorder.sent[0][0]
    assert alerts.fire_due(now=now + 60, deliver=recorder) == [], "same bucket, one alert"


def test_errors_under_the_threshold_do_not_fire():
    now = (time.time() // 600) * 600 + 10
    for index in range(3):
        errors.note(errors.SERVER_ERROR, "ERROR", "app.hardening", f"unhandled error on GET /x-{index}", now)
    assert alerts.fire_due(now=now, deliver=Recorder()) == []


def test_a_refused_resend_send_fires():
    now = (time.time() // 3600) * 3600 + 10   # anchored in an hour bucket, like the ten-minute one above
    errors.note(errors.EMAIL_REFUSED, "WARNING", "app.mailer", "e-mail to b***@example.invalid refused: HTTP 403", now)
    recorder = Recorder()
    sent = alerts.fire_due(now=now, deliver=recorder)
    assert [alert.key for alert in sent] == ["email_refused"]
    assert "order page itself is permanent" in recorder.sent[0][1]


def test_a_rejected_webhook_signature_fires():
    now = (time.time() // 3600) * 3600 + 10
    errors.note(errors.WEBHOOK_SIGNATURE, "WARNING", "app.payments.routes",
                "REJECTED webhook: bad or missing X-Razorpay-Signature", now)
    sent = alerts.fire_due(now=now, deliver=Recorder())
    assert [alert.key for alert in sent] == ["webhook_signature"]


def test_a_failing_readiness_check_fires(monkeypatch):
    from app.admin import health

    monkeypatch.setattr(health, "readiness", lambda check_chromium=False: {
        "status": "fail", "checks": {"ephemeris": {"ok": False, "detail": "no .se1 files"}}})
    recorder = Recorder()
    sent = alerts.fire_due(deliver=recorder)
    assert [alert.key for alert in sent] == ["health_fail"]
    assert "no .se1 files" in recorder.sent[0][1]


# ---- deduplication and retry -------------------------------------------------------------------------


def test_the_same_alert_is_not_sent_twice():
    """Without this, the overview page e-mailed on every refresh, which teaches the reader to filter the
    alerts, which is the same as not having any."""
    order("ord_dupe000000001", paid_ago=20 * 60, fulfilment="generating")
    recorder = Recorder()
    assert len(alerts.fire_due(deliver=recorder)) == 1
    assert alerts.fire_due(deliver=recorder) == []
    assert len(recorder.sent) == 1


def test_a_failed_delivery_is_not_recorded_as_sent_so_the_next_run_retries():
    """The opposite of "mark it done and move on". The whole value of these messages is that the FIRST one
    arrives, so a Resend outage must not swallow the alert."""
    order("ord_retry00000001", paid_ago=20 * 60, fulfilment="generating")
    failing = Recorder(succeed=False)
    assert alerts.fire_due(deliver=failing) == []
    assert len(failing.sent) == 1
    working = Recorder()
    assert len(alerts.fire_due(deliver=working)) == 1


def test_a_delivery_that_raises_does_not_stop_the_other_alerts():
    order("ord_raise00000001", paid_ago=20 * 60, fulfilment="generating")
    order("ord_raise00000002", paid_ago=25 * 60, fulfilment="failed", error="boom")
    calls = []

    def exploding(subject, body):
        calls.append(subject)
        raise RuntimeError("the provider fell over")

    assert alerts.fire_due(deliver=exploding) == []
    assert len(calls) == 2, "both alerts were attempted"


def test_one_broken_rule_does_not_silence_the_others(monkeypatch):
    """The late-order alert is the one that costs money; an unreadable run report must not take it down."""
    order("ord_robust0000001", paid_ago=20 * 60, fulfilment="generating")
    monkeypatch.setattr(alerts, "rashifal_failures",
                        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("unreadable run report")))
    assert [alert.key for alert in alerts.fire_due(deliver=Recorder())] == ["order_late"]


def test_nothing_fires_on_a_quiet_system():
    order("ord_quiet00000001", fulfilment="ready", cost_inr=20.0)
    assert alerts.evaluate() == []


# ---- the daily digest ---------------------------------------------------------------------------------


def test_the_digest_reports_yesterday_and_not_the_last_twenty_four_hours():
    """Read against a calendar day and reconciled against a calendar day. "Since 9 a.m. yesterday" is a
    window nobody else's numbers use."""
    now = metrics.now_ist()
    yesterday = now.date() - dt.timedelta(days=1)
    order_id = "ord_digest0000001"
    order(order_id, cost_inr=22.5)
    with db.transaction() as conn:
        # `ready_at` is what the generation time is measured from now: `updated_at` is the row's last
        # modification, and an invoice number or a retried e-mail moves that long after the report was
        # finished. Both are set here so the five minutes below is five minutes of GENERATION.
        conn.execute("UPDATE orders SET paid_at=?, ready_at=?, updated_at=? WHERE id=?",
                     (metrics.day_start(yesterday) + 3600, metrics.day_start(yesterday) + 3900,
                      metrics.day_start(yesterday) + 3900, order_id))
    subject, body, figures = alerts.digest_body(now=now)
    assert figures["day"] == yesterday.isoformat()
    assert figures["orders"] == 1
    assert "Paid orders        1" in body
    assert "p50 generation     5.0 min" in body
    assert "Rs 249.00" in body, "net revenue, not the Rs 293.82 charged"


def test_the_digest_says_the_margin_is_not_computable_rather_than_printing_one():
    now = metrics.now_ist()
    yesterday = now.date() - dt.timedelta(days=1)
    order("ord_digest0000002", cost_inr=None)
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET paid_at=? WHERE id=?", (metrics.day_start(yesterday) + 3600,
                                                                "ord_digest0000002"))
    _, body, figures = alerts.digest_body(now=now)
    assert figures["margin_inr"] is None
    assert "not computable" in body
    assert "1 of 1 orders have no recorded AI cost" in body


def test_the_digest_renders_on_a_day_with_no_sales():
    _, body, figures = alerts.digest_body(now=metrics.now_ist())
    assert figures["orders"] == 0
    assert "no order became ready" in body


def test_the_digest_is_sent_once_per_day():
    recorder = Recorder()
    assert alerts.send_digest(deliver=recorder) is True
    assert alerts.send_digest(deliver=recorder) is False
    assert len(recorder.sent) == 1


def test_the_digest_states_that_the_payment_fee_is_modelled():
    """It sits next to real figures in an e-mail somebody budgets from."""
    _, body, _ = alerts.digest_body(now=metrics.now_ist())
    assert "modelled, not from a settlement report" in body


# ---- the entry point that a timer calls ---------------------------------------------------------------


def test_the_module_can_be_run_as_a_command_without_sending_anything(capsys):
    """`python -m app.admin.alerts --dry-run` is what an operator runs before trusting the timer, and a dry
    run must not record anything as sent - otherwise the real alert never arrives."""
    order("ord_dryrun0000001", paid_ago=20 * 60, fulfilment="generating")
    assert alerts.main(["--dry-run"]) == 0
    printed = capsys.readouterr().out
    assert "would send" in printed and "ord_dryrun0000001" in printed
    recorder = Recorder()
    assert len(alerts.fire_due(deliver=recorder)) == 1, "a dry run must not have consumed the alert"


def test_the_digest_command_dry_runs_too(capsys):
    assert alerts.main(["--digest", "--dry-run"]) == 0
    assert "Yesterday" in capsys.readouterr().out
    recorder = Recorder()
    assert alerts.send_digest(deliver=recorder) is True


def test_the_default_delivery_goes_through_the_mailer_and_sends_nothing_when_it_is_off(monkeypatch):
    """The default path, exercised - with the master switch off, which is app/mailer.py's own guarantee that
    a key alone can never start sending."""
    sent = []
    from app import mailer

    monkeypatch.setattr(mailer, "send", lambda to, subject, text: sent.append(to) or False)
    assert alerts.email_delivery("subject", "body") is False
    assert sent == ["operations@example.invalid"]


def test_no_alert_is_delivered_when_no_recipient_is_configured(monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL_TO", "")
    monkeypatch.setenv("SUPPORT_EMAIL", "")
    from app.web import site

    monkeypatch.setattr(site, "SUPPORT_EMAIL", "")
    assert alerts.email_delivery("subject", "body") is False
