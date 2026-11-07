"""Did the e-mail arrive, and did they ever open what they paid for?

TWO QUESTIONS NOBODY COULD ANSWER. A customer pays, a link is e-mailed, and from that moment the service
knew nothing: not whether Resend accepted the message, not whether it bounced, not whether the person ever
downloaded the report. A report paid for and never opened is the worst outcome there is - the money is
taken, the work is done, and the customer has nothing - and it was invisible.

So: the provider's answer is recorded against the order, the first download is recorded against the order,
and an order still undownloaded after a day gets ONE reminder. One, ever, enforced by a stored stamp
rather than by a schedule nobody can see - a reminder that can fire twice is a reminder that will.
"""
from __future__ import annotations

import time
import uuid

import pytest


# ---- the provider's answer ---------------------------------------------------------------------------

def test_a_sent_mail_records_the_providers_id(monkeypatch):
    """Resend answers with an id. Without it there is nothing to look up when somebody says they never
    got the e-mail, and "we sent it" is an assertion rather than a fact."""
    from app import mailer

    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "_key", lambda: "test-key")

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "msg_abc123"}

        text = ""

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(mailer.httpx, "Client", Client)
    result = mailer.send_recorded("asha@example.invalid", "subject", "body")
    assert result.ok and result.message_id == "msg_abc123"


def test_a_refused_mail_records_why(monkeypatch):
    from app import mailer

    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "_key", lambda: "test-key")

    class Response:
        status_code = 422
        text = '{"message":"Invalid `to` field"}'

        @staticmethod
        def json():
            return {}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(mailer.httpx, "Client", Client)
    result = mailer.send_recorded("bad@example.invalid", "subject", "body")
    assert not result.ok and "422" in (result.detail or "")


def test_the_recorded_detail_never_carries_the_address():
    """It is shown on an admin page and exported; the address belongs in the order row, not in a status."""
    from app.mailer import MailResult

    result = MailResult(ok=False, message_id="", detail="HTTP 422 Invalid `to` field")
    assert "@" not in result.detail


# ---- was it ever opened? -----------------------------------------------------------------------------

def seed_paid_order(*, paid_hours_ago: float, downloaded: bool = False, live: int = 1) -> dict:
    """A paid order with a report, written the way the payment path writes one."""
    import time

    from app import db

    order_id = f"ord_{uuid.uuid4().hex[:16]}"
    report_id = f"rep_{uuid.uuid4().hex[:12]}"
    now = time.time()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO orders (id, token, product, kind, amount_paise, currency, status, "
            "                    razorpay_order_id, user_id, messages, fulfilment, attempts, "
            "                    next_retry_at, lease_until, created_at, updated_at, "
            "                    email, language, report_id, paid_at, downloaded_at, live) "
            "VALUES (?, ?, ?, 'report', 5900, 'INR', 'paid', ?, ?, 0, 'done', 0, 0, 0, ?, ?, "
            "        ?, 'en', ?, ?, ?, ?)",
            (order_id, uuid.uuid4().hex, "kundali-report-simple",
             f"rzp_{uuid.uuid4().hex[:14]}", f"user_{uuid.uuid4().hex[:10]}",
             now - paid_hours_ago * 3600, now,
             "asha@example.invalid", report_id,
             now - paid_hours_ago * 3600,
             now - 3600 if downloaded else None, live))
    return {"id": order_id, "report_id": report_id}


def test_downloading_the_report_is_recorded_once():
    """The FIRST download is the one that matters - it answers "did they get it". Later ones are the same
    person opening it again, which is not news, and must not move the answer."""
    from app.payments import store

    order = seed_paid_order(paid_hours_ago=30)
    assert store.mark_downloaded(order["report_id"]) is True, "the first download was not recorded"
    assert store.mark_downloaded(order["report_id"]) is False, "a later download moved the first one"


def test_an_order_paid_and_never_downloaded_is_listed_after_a_day():
    from app.payments import store

    waiting = seed_paid_order(paid_hours_ago=30)
    opened = seed_paid_order(paid_hours_ago=30, downloaded=True)
    fresh = seed_paid_order(paid_hours_ago=2)

    listed = {row["id"] for row in store.paid_but_not_downloaded(after_hours=24)}
    assert waiting["id"] in listed
    assert opened["id"] not in listed, "an order that was downloaded is being chased"
    assert fresh["id"] not in listed, "an order from two hours ago is being chased"


def test_a_rehearsal_order_is_never_chased():
    """Test-mode orders are not customers who are missing something."""
    from app.payments import store

    rehearsal = seed_paid_order(paid_hours_ago=30, live=0)
    listed = {row["id"] for row in store.paid_but_not_downloaded(after_hours=24)}
    assert rehearsal["id"] not in listed


def test_the_reminder_is_stamped_before_it_is_sent(monkeypatch):
    """The safer way round: a send that fails costs one missing e-mail, a stamp that fails costs a
    customer the same nudge three times."""
    from app.payments import delivery, store

    order = seed_paid_order(paid_hours_ago=30)
    order_ids = []
    monkeypatch.setattr(delivery, "_send_reminder", lambda o: order_ids.append(o["id"]) or False)
    delivery.remind_undownloaded(after_hours=24)
    assert order["id"] in order_ids
    assert store.mark_reminded(order["id"]) is False, "the stamp was not taken before the send"


def test_the_whole_loop_sends_exactly_one_reminder(monkeypatch):
    from app.payments import delivery

    order = seed_paid_order(paid_hours_ago=30)
    sent = []
    monkeypatch.setattr(delivery, "_send_reminder", lambda o: sent.append(o["id"]) or True)
    delivery.remind_undownloaded(after_hours=24)
    delivery.remind_undownloaded(after_hours=24)
    delivery.remind_undownloaded(after_hours=24)
    assert sent.count(order["id"]) == 1, f"the reminder went {sent.count(order['id'])} times"


def test_a_reminder_is_sent_once_and_only_once(monkeypatch):
    """A reminder that can fire twice is a reminder that will: somebody runs the job again, or two workers
    overlap, and a paying customer gets the same nudge three times."""
    from app.payments import delivery

    sent = []
    monkeypatch.setattr(delivery, "_send_reminder", lambda order: sent.append(order["id"]) or True)

    order = {"id": "ord_once", "email": "asha@example.invalid", "token": "t", "language": "en",
             "reminded_at": None}
    assert delivery.should_remind(order, now=time.time(), after_hours=24, state=delivery.NEVER,
                                  paid_at=time.time() - 30 * 3600) is True
    assert delivery.should_remind({**order, "reminded_at": time.time() - 3600},
                                  now=time.time(), after_hours=24, state=delivery.NEVER,
                                  paid_at=time.time() - 30 * 3600) is False


def test_nothing_is_reminded_before_the_day_is_up():
    from app.payments import delivery

    order = {"id": "ord_young", "email": "a@b.invalid", "token": "t", "language": "en", "reminded_at": None}
    assert delivery.should_remind(order, now=time.time(), after_hours=24,
                                  paid_at=time.time() - 2 * 3600) is False


def test_a_downloaded_order_is_never_reminded():
    from app.payments import delivery

    order = {"id": "ord_done", "email": "a@b.invalid", "token": "t", "language": "en",
             "reminded_at": None, "downloaded_at": time.time() - 3600}
    # No `state` passed ON PURPOSE: this order carries its own download stamp, and download_state reads
    # that before it consults anything else, so the answer comes from the order itself.
    assert delivery.should_remind(order, now=time.time(), after_hours=24,
                                  paid_at=time.time() - 30 * 3600) is False
