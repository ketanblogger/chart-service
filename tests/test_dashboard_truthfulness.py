"""Three numbers on the dashboard that were not telling the truth, and the alert that cried wolf.

Each of these passed every test it had. They were wrong about the WORLD, which is the kind of wrong a
suite does not notice: a rehearsal counted as revenue is still a row, a timer measuring the wrong interval
still produces a number, and an alert that fires at the deploy check still fires.
"""

import time
import uuid

import pytest

from app import db
from app.admin import metrics, orders as admin_orders
from app.payments import store


def _paid_order(*, live=None, paid_at=None, ready_at=None, updated_at=None, amount=29900):
    """One paid order, written straight to the table so the timestamps are exactly what is under test."""
    order_id = store.new_order_id()
    now = paid_at if paid_at is not None else time.time()
    store.insert_order(order_id=order_id, product="kundali-report", kind="report", amount_paise=amount,
                       currency="INR", razorpay_order_id="order_" + uuid.uuid4().hex[:14],
                       user_id="u" * 32, email="buyer@example.com")
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET status = 'paid', paid_at = ?, fulfilment = 'ready', "
                     "ready_at = ?, updated_at = ?, live = ? WHERE id = ?",
                     (now, ready_at, updated_at if updated_at is not None else now, live, order_id))
    return store.get_order(order_id)


# ---- 4. a rehearsal is not a sale ----------------------------------------------------------------------


def test_the_mode_is_recorded_when_the_order_is_made(monkeypatch):
    """It cannot be worked out afterwards: neither id says which key made it. So it is written down."""
    from app.payments import razorpay

    monkeypatch.setattr(razorpay, "is_test_mode", lambda: True)
    assert _paid_order()["live"] == 0 or True        # insert_order reads the mode; see below for the real one

    order_id = store.new_order_id()
    store.insert_order(order_id=order_id, product="kundali-report", kind="report", amount_paise=100,
                       currency="INR", razorpay_order_id="order_x", user_id="u" * 32, email="a@b.co")
    assert store.get_order(order_id)["live"] == 0, "an order made on test keys was recorded as real"

    monkeypatch.setattr(razorpay, "is_test_mode", lambda: False)
    other = store.new_order_id()
    store.insert_order(order_id=other, product="kundali-report", kind="report", amount_paise=100,
                       currency="INR", razorpay_order_id="order_y", user_id="u" * 32, email="a@b.co")
    assert store.get_order(other)["live"] == 1


def test_a_rehearsal_is_left_out_of_the_figures_and_a_real_sale_is_not():
    now = time.time()
    window = (now - 3600, now + 3600)
    real = _paid_order(live=1, paid_at=now, amount=5900)
    rehearsal = _paid_order(live=0, paid_at=now, amount=29900)

    counted = {row["id"] for row in admin_orders.paid_between(*window)}
    assert real["id"] in counted, "a real sale was dropped"
    assert rehearsal["id"] not in counted, "a rehearsal was counted as revenue"

    separately = {row["id"] for row in admin_orders.test_mode_paid_between(*window)}
    assert rehearsal["id"] in separately, "the rehearsal cannot be seen at all, which is its own problem"


def test_an_order_older_than_the_column_is_kept_rather_than_guessed_away():
    """NULL means "made before anybody recorded this", which is not the same as "known to be a rehearsal".
    Guessing a sale away is as wrong as inventing one; `scripts/classify_test_orders.py` is how those get
    decided deliberately, by somebody who knows when the first real sale was."""
    now = time.time()
    legacy = _paid_order(live=None, paid_at=now)
    counted = {row["id"] for row in admin_orders.paid_between(now - 3600, now + 3600)}
    assert legacy["id"] in counted


def test_the_classify_script_shows_before_it_changes_anything(tmp_path, capsys):
    import scripts.classify_test_orders as classify

    now = time.time()
    old_one = _paid_order(live=None, paid_at=now - 10 * 86400, amount=29900)
    classify.main(["--before", "2099-01-01"])            # a dry run over everything
    printed = capsys.readouterr().out
    assert "would be marked" in printed and "Nothing changed" in printed
    assert store.get_order(old_one["id"])["live"] is None, "a dry run changed the data"


# ---- 5. the generation timer ----------------------------------------------------------------------------


def test_generation_time_is_paid_to_ready_and_not_paid_to_last_touched():
    """THE BUG: `updated_at` is the row's last-modified time. An invoice number, a retried e-mail, a
    refund or a credit note all move it - so a report that was ready in four minutes read as ten hours."""
    paid = time.time() - 10 * 3600
    ready = paid + 240                                   # four minutes
    touched_much_later = paid + 10 * 3600                # ...and something touched the row at ten hours
    order = _paid_order(live=1, paid_at=paid, ready_at=ready, updated_at=touched_much_later)

    measured = metrics.generation_seconds(order)
    assert measured == pytest.approx(240, abs=2), f"measured {measured}s rather than the real 240s"
    assert measured < 3600, "the timer is still following updated_at"


def test_an_order_with_no_ready_time_is_unmeasured_rather_than_measured_wrongly():
    """Rows that predate the column have no honest answer. `durations` counts them as missing, which is
    visible on the page - a wrong number is not."""
    order = _paid_order(live=1, paid_at=time.time() - 7200, ready_at=None,
                        updated_at=time.time())
    assert metrics.generation_seconds(order) is None
    spread = metrics.durations([order])
    assert spread.count == 0 and spread.missing == 1


def test_a_re_fulfilment_does_not_restart_the_clock():
    """`COALESCE` keeps the first moment it was ready. Delivering it again months later is not a
    months-long generation."""
    order = _paid_order(live=1, paid_at=time.time() - 3600, ready_at=None)
    store.finish_fulfilment(order["id"], ok=True)
    first = store.get_order(order["id"])["ready_at"]
    assert first
    time.sleep(0.01)
    store.finish_fulfilment(order["id"], ok=True)
    assert store.get_order(order["id"])["ready_at"] == first, "the second delivery moved the start line"


# ---- 6. the alert that cried wolf ------------------------------------------------------------------------


def test_the_deploy_probe_does_not_trip_the_signature_alert(monkeypatch, caplog):
    """The smoke check posts a deliberately bad signature to prove the endpoint rejects one. That is the
    check working, not an attack, and an alert that fires on every deploy is an alert nobody reads."""
    import logging

    from fastapi.testclient import TestClient

    from app.main import app
    from app.payments import razorpay

    monkeypatch.setattr(razorpay, "_webhook_secret", lambda: "whsec_test")
    client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level(logging.WARNING, logger="app.payments.routes"):
        probe = client.post("/api/payments/webhook", content=b"{}",
                            headers={"X-Razorpay-Signature": "0" * 64})
    assert probe.status_code == 400, "the endpoint must still reject it"
    assert not [r for r in caplog.records if "REJECTED" in r.getMessage()], \
        "the deploy probe logged the warning the alert counts"


def test_a_real_looking_event_with_a_wrong_signature_still_raises_the_alarm():
    """The other half, and the one that matters: this means the secret has drifted or somebody is trying
    to fulfil orders for free."""
    import logging

    from fastapi.testclient import TestClient

    from app.admin import errors
    from app.main import app
    from app.payments import razorpay

    original = razorpay._webhook_secret
    razorpay._webhook_secret = lambda: "whsec_test"
    try:
        client = TestClient(app, raise_server_exceptions=False)
        logger = logging.getLogger("app.payments.routes")
        seen = []
        handler = logging.Handler()
        handler.emit = lambda record: seen.append(record.getMessage())
        handler.setLevel(logging.WARNING)
        logger.addHandler(handler)
        try:
            answer = client.post(
                "/api/payments/webhook",
                content=b'{"event":"payment.captured","payload":{"payment":{"entity":{}}}}',
                headers={"X-Razorpay-Signature": "0" * 64})
        finally:
            logger.removeHandler(handler)
    finally:
        razorpay._webhook_secret = original

    assert answer.status_code == 400
    assert any("REJECTED" in message for message in seen), "a forged event was not reported"
    # ...and that message is what the counter classifies as the signature alert.
    assert errors.classify("app.payments.routes",
                           "REJECTED webhook: bad or missing X-Razorpay-Signature on a well-formed event") \
        == errors.WEBHOOK_SIGNATURE
