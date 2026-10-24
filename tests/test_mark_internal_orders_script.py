"""scripts/mark_internal_orders.py, run end to end against a database built the way production builds one.

WHY THIS FILE EXISTS. The script's --apply crashed on production with

    sqlite3.OperationalError: no such table: users

at the statement that marks usage events. There is no `users` table in this application and never has
been: the identity table is `accounts`, keyed by e-mail, and site_events stores a HASHED account_id so
that an address cannot be recovered from it. The SQL had been written against an imagined schema, and
nothing caught it because nothing had ever executed that statement against a real database.

So these tests run the script's own main() on a database whose tables come from the same
db.register_schema calls production runs at import time - not from DDL typed into a fixture, which would
be a second imagined schema and would have passed just as happily.
"""
from __future__ import annotations

import datetime as dt
import time
import uuid

import pytest

# Imported for their schema registration, which is what builds the tables - exactly as the application
# does it at import time. app.analytics owns site_events; app.payments.store owns orders.
from app import analytics, db  # noqa: F401
from app.payments import internal as payments_internal
from app.payments import store  # noqa: F401
from app.web import accounts  # noqa: F401  (owns `accounts`, the table the broken SQL thought was `users`)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
BEFORE = dt.datetime(2026, 9, 26, 12, 0, tzinfo=IST).timestamp()
AFTER = dt.datetime(2026, 10, 5, 12, 0, tzinfo=IST).timestamp()


def _order(*, created_at: float, live, email: str, order_id: str = "", amount: int = 17712) -> str:
    oid = order_id or f"ord_{uuid.uuid4().hex[:16]}"
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO orders (id, token, product, kind, amount_paise, currency, status, "
            "                    razorpay_order_id, user_id, messages, fulfilment, attempts, "
            "                    next_retry_at, lease_until, created_at, updated_at, email, language, "
            "                    live) "
            "VALUES (?, ?, 'kundali-report-simple', 'report', ?, 'INR', 'paid', ?, ?, 0, 'done', 0, 0, "
            "        0, ?, ?, ?, 'en', ?)",
            (oid, uuid.uuid4().hex, amount, f"rzp_{uuid.uuid4().hex[:14]}",
             f"user_{uuid.uuid4().hex[:10]}", created_at, created_at, email, live))
    return oid


@pytest.fixture
def admins(monkeypatch):
    from app.web import site

    monkeypatch.setattr(site, "ADMIN_EMAILS", frozenset({"owner@rashikundli.invalid"}))
    return frozenset({"owner@rashikundli.invalid"})


def test_the_script_runs_to_completion_against_the_real_schema(admins, capsys, monkeypatch):
    """THE REGRESSION. --apply must not raise on the schema this application actually has."""
    _order(created_at=BEFORE, live=None, email="someone@example.invalid")
    _order(created_at=AFTER, live=1, email="customer@example.invalid")
    _order(created_at=AFTER, live=0, email="rehearsal@example.invalid")
    _order(created_at=AFTER, live=1, email="owner@rashikundli.invalid")

    import scripts.mark_internal_orders as script

    monkeypatch.setattr("sys.argv", ["mark_internal_orders.py", "--apply"])
    assert script.main() == 0
    assert "APPLIED" in capsys.readouterr().out


def test_usage_events_are_marked_by_the_column_that_exists(admins, monkeypatch):
    """is_admin is written at the point of the event by the same accounts.is_admin() that reads
    ADMIN_EMAILS - including on the chat path, which is where the AI money is."""
    analytics.record_event("chat", "question", is_admin=True, cost_inr=4.0)
    analytics.record_event("chat", "question", is_admin=False, cost_inr=4.0)

    import scripts.mark_internal_orders as script

    monkeypatch.setattr("sys.argv", ["mark_internal_orders.py", "--apply"])
    assert script.main() == 0
    with db.transaction(write=False) as conn:
        ours = conn.execute("SELECT COUNT(*) AS n FROM site_events WHERE internal = 1").fetchone()["n"]
        theirs = conn.execute("SELECT COUNT(*) AS n FROM site_events "
                              "WHERE internal IS NULL AND is_admin = 0").fetchone()["n"]
    assert ours >= 1, "an admin's own usage was not marked"
    assert theirs >= 1, "somebody else's usage was marked, which would hide real cost"


def test_a_dry_run_writes_nothing(admins, monkeypatch):
    _order(created_at=AFTER, live=0, email="rehearsal@example.invalid")

    import scripts.mark_internal_orders as script

    monkeypatch.setattr("sys.argv", ["mark_internal_orders.py"])
    assert script.main() == 0
    with db.transaction(write=False) as conn:
        marked = conn.execute("SELECT COUNT(*) AS n FROM orders "
                              "WHERE internal IS NOT NULL").fetchone()["n"]
    assert marked == 0, "a dry run wrote a classification"


def test_everything_before_the_first_live_sale_is_internal(admins, monkeypatch):
    """Item 0c. The four 25-28 September orders could not be judged by address or by razorpay mode; what
    decides them is that the site had not yet sold anything to anybody who was not us."""
    early = _order(created_at=BEFORE, live=None, email="someone@example.invalid")
    first = _order(created_at=payments_internal.FIRST_LIVE_SALE_AT, live=1,
                   email="customer@example.invalid",
                   order_id=payments_internal.FIRST_LIVE_SALE_ID)
    later = _order(created_at=AFTER, live=1, email="customer2@example.invalid")

    import scripts.mark_internal_orders as script

    monkeypatch.setattr("sys.argv", ["mark_internal_orders.py", "--apply"])
    assert script.main() == 0
    with db.transaction(write=False) as conn:
        rows = {r["id"]: r for r in conn.execute(
            "SELECT id, internal, internal_reason FROM orders").fetchall()}
    assert rows[early]["internal"] == 1
    assert rows[early]["internal_reason"] == payments_internal.BEFORE_FIRST_SALE
    assert rows[first]["internal"] == 0, "the first real sale is not before itself"
    assert rows[later]["internal"] == 0, "an October sale is real business"


def test_the_october_business_revenue_is_unchanged(admins, monkeypatch):
    """Rs 708.48 net is the figure the brief states for the four real orders, and the point of every rule
    above is that it does not move. A classification that quietly swallows a real sale makes revenue too
    low, and nobody notices a number that is missing."""
    four = [17712, 17712, 17712, 17712]
    for amount in four:
        _order(created_at=AFTER, live=1, email="customer@example.invalid", amount=amount)
    _order(created_at=BEFORE, live=None, email="someone@example.invalid")

    import scripts.mark_internal_orders as script

    monkeypatch.setattr("sys.argv", ["mark_internal_orders.py", "--apply"])
    assert script.main() == 0
    with db.transaction(write=False) as conn:
        total = conn.execute("SELECT SUM(amount_paise) AS p FROM orders "
                             "WHERE status = 'paid' AND internal = 0").fetchone()["p"]
    assert round((total or 0) / 100, 2) == 708.48
