"""The one mail to somebody who opened checkout and stopped.

THE STEP IT ADDRESSES is the only one in the funnel where somebody has already decided to buy and then
did not: an order row exists, with a product and an address, and no payment. As many orders were
abandoned there as were paid.

WHAT IT MUST NEVER BECOME is a campaign. One mail, the same link they already had, and the mail says it
is the only one. Most of this file is about the ways that could stop being true - a second send, a mail
to somebody who paid, a mail about an order from two months ago, a mail to the proprietor about his own
test purchases.
"""
from __future__ import annotations

import time

import pytest

from app.payments import store, unpaid

NOW = 1_800_000_000.0


def order(**overrides) -> dict:
    base = {"id": "order_Unpaid01", "status": "created", "email": "someone@example.com",
            "token": "U" * 32, "created_at": NOW - 24 * 3600, "live": 1, "language": "en"}
    return {**base, **overrides}


def test_an_abandoned_order_with_an_address_is_owed_one_mail():
    assert unpaid.should_mail(order(), now=NOW)


@pytest.mark.parametrize("why, changes", [
    ("they paid", {"status": "paid"}),
    ("they paid, status lagging", {"paid_at": NOW - 100}),
    ("already written to", {"unpaid_mailed_at": NOW - 3600}),
    ("no address", {"email": ""}),
    ("no link", {"token": ""}),
    ("a test-mode order", {"live": 0}),
    ("created an hour ago", {"created_at": NOW - 3600}),
    ("abandoned a month ago", {"created_at": NOW - 30 * 24 * 3600}),
])
def test_every_reason_to_say_no(why, changes):
    assert not unpaid.should_mail(order(**changes), now=NOW), why


def test_the_window_is_bounded_at_both_ends():
    """The far end is the one that matters. An order abandoned a fortnight ago is not a sale waiting to
    be recovered - it is somebody who decided no, and a mail about it reads as a company that has been
    watching."""
    just_inside = order(created_at=NOW - (unpaid.BEFORE_HOURS - 1) * 3600)
    just_outside = order(created_at=NOW - (unpaid.BEFORE_HOURS + 1) * 3600)
    assert unpaid.should_mail(just_inside, now=NOW)
    assert not unpaid.should_mail(just_outside, now=NOW)


def test_the_proprietors_own_test_purchases_are_not_customers():
    from app.payments import internal

    for reason in internal.INTERNAL_REASONS:
        assert not unpaid.should_mail(order(reason=reason), now=NOW), reason


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_mail_carries_the_link_they_already_had(lang):
    """Never a new link. A mail that introduced a second way in is a mail nobody can tell from a
    phishing attempt - the same reasoning app/payments/order_email.py already follows."""
    to, subject, body = unpaid.compose(order(language=lang))
    assert to == "someone@example.com" and subject.strip()
    assert f"/order/{'U' * 32}" in body
    assert body.count("http") == 1, "more than one link in a mail about one order"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_mail_says_it_is_the_only_one(lang):
    """Said in the mail, not only in our code. It is the promise that stops this becoming a sequence."""
    _to, _subject, body = unpaid.compose(order(language=lang))
    only = {"en": "only e-mail", "hi": "एकमात्र ई-मेल", "mr": "एकमेव ई-मेल"}[lang]
    assert only in body


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_mail_offers_no_discount_and_takes_no_payment(lang):
    """A discount to come back tells everybody who paid on time that they paid too much."""
    _to, _subject, body = unpaid.compose(order(language=lang))
    for banned in ("%", "discount", "coupon", "छूट", "सवलत", "offer code"):
        assert banned not in body.lower(), f"{lang} mail contains {banned}"


def test_the_mail_says_no_money_was_taken():
    """The first question somebody has about an unfinished payment."""
    _to, _subject, body = unpaid.compose(order())
    assert "no payment was taken" in body.lower()


def test_the_stamp_is_what_makes_once_true():
    """The lock is a conditional UPDATE, so two runs overlapping cannot both send."""
    store.insert_order(order_id="order_Lock01", product="kundali-report", kind="report",
                       amount_paise=29900, currency="INR", razorpay_order_id="order_rzpLock01",
                       user_id="u1", email="lock@example.com", language="en")
    assert store.mark_unpaid_mailed("order_Lock01") is True
    assert store.mark_unpaid_mailed("order_Lock01") is False


def test_the_loop_sends_nothing_it_should_not(monkeypatch):
    sent = []
    monkeypatch.setattr("app.mailer.send_recorded",
                        lambda to, subject, body: type("R", (), {"ok": True})())
    summary = unpaid.mail_abandoned(now=time.time(), dry_run=True)
    assert summary["dry_run"] is True and summary["sent"] >= 0
    assert sent == []


def test_a_dry_run_writes_no_stamp():
    """So that a rehearsal does not silently consume everybody's one mail."""
    store.insert_order(order_id="order_Dry01", product="kundali-report", kind="report",
                       amount_paise=29900, currency="INR", razorpay_order_id="order_rzpDry01",
                       user_id="u1", email="dry@example.com", language="en")
    unpaid.mail_abandoned(now=time.time() + 25 * 3600, dry_run=True)
    assert store.get_order("order_Dry01").get("unpaid_mailed_at") in (None, 0)


# ---------------------------------------------------------------------------------------------------
# The absolute floor: never mail an order placed before we decided to start mailing.


def test_an_order_older_than_the_floor_is_never_mailed():
    """THE RULE: the first live run reaches only orders created after it was switched on.

    The rolling window cannot express that. It answers "is this still live?", measured backwards from
    now - so a run a fortnight later would quietly sweep in orders that predate the decision entirely,
    people who abandoned a checkout long ago and have heard nothing since. They are exactly who must
    not be written to."""
    floor = NOW - 12 * 3600          # we decided to start mailing twelve hours ago
    before = order(created_at=NOW - 48 * 3600)   # placed two days ago: inside the rolling window
    after = order(created_at=NOW - 22 * 3600)    # ...but only one of them is after the floor

    assert unpaid.should_mail(before, now=NOW), "the rolling window alone would mail it"
    assert not unpaid.should_mail(before, now=NOW, created_after=floor)
    assert unpaid.should_mail(after, now=NOW, created_after=NOW - 30 * 3600)


def test_the_floor_is_read_as_ist():
    """Every other date this business states is IST - an invoice, a panchang, a rashifal day. A floor
    read as UTC is five and a half hours out, which on a date boundary is a different set of orders."""
    import datetime as dt
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("unpaid_cli", Path("scripts/unpaid_mail.py"))
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    assert cli._moment("2026-10-23") == dt.datetime(2026, 10, 23, tzinfo=ist).timestamp()
    assert cli._moment("2026-10-23 14:30") == dt.datetime(2026, 10, 23, 14, 30, tzinfo=ist).timestamp()


def test_a_real_send_without_a_floor_is_refused():
    """A SAFETY PROPERTY, not a convenience. --send alone cannot reach old orders because it will not
    run at all."""
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "scripts/unpaid_mail.py", "--send"],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "--created-after" in result.stderr


def test_the_query_applies_the_floor_too():
    """Both halves. The predicate refusing is not enough if the query hands back a thousand rows to
    refuse one at a time - and `considered` on the summary would then report a number that misleads."""
    rows = store.unpaid_with_an_address(after_hours=1, now=NOW, before_hours=24 * 365,
                                        created_after=NOW + 86400)
    assert rows == [], "the floor was not applied in the query"
