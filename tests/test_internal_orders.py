"""Our own orders and usage out of the business metrics - marked, never deleted.

WHY NOT DELETED. The 29 September Rs 59 order and its Rs 57.60 credit note are accounting records: the
invoice was issued, the credit note was issued, and a CA and a GST return both need them. What they are
not is revenue. Marking changes what the dashboard COUNTS, not what the books contain.

THE DIRECTION THE CLASSIFIER MUST FAIL IN. Wrongly marking a real sale internal makes revenue quietly too
low, and nobody notices a number that is missing; wrongly counting an admin order as revenue shows up as
a figure that looks too good. Both are wrong, but only the second is visible - so an order that cannot be
judged counts as BUSINESS and is reported for a person to decide, rather than being hidden.
"""
from __future__ import annotations

import pytest

from app.payments import internal

ADMINS = frozenset({"owner@rashikundli.invalid"})


@pytest.mark.parametrize("order, expected, why", [
    ({"email": "owner@rashikundli.invalid", "live": 1}, True, "the proprietor's own purchase"),
    ({"email": "  Owner@RashiKundli.INVALID ", "live": 1}, True, "case and spacing must not matter"),
    ({"email": "someone@example.com", "live": 0}, True, "test-mode keys: a rehearsal, not a sale"),
    ({"email": "someone@example.com", "live": 1}, False, "a real customer"),
    ({"email": "someone@example.com", "live": None}, False, "unrecorded mode counts as business"),
    ({"email": "", "live": 1}, False, "no address is not evidence of anything"),
])
def test_the_classifier(order, expected, why):
    assert internal.is_internal(order, ADMINS) is expected, why


def test_a_stored_classification_wins_over_the_evidence():
    """Once a person has decided, the decision holds - including a decision to call one of ours a sale."""
    assert internal.is_internal({"email": "owner@rashikundli.invalid", "live": 1, "internal": 0}, ADMINS) is False
    assert internal.is_internal({"email": "someone@example.com", "live": 1, "internal": 1}, ADMINS) is True


def test_an_order_that_cannot_be_judged_is_reported_not_guessed():
    order = {"email": "someone@example.com", "live": None}
    assert internal.reason_for(order, ADMINS) == internal.UNDECIDED
    assert internal.is_internal(order, ADMINS) is False, "an unjudgeable row must not be hidden"


def test_an_empty_admin_list_is_a_refusal_not_a_silent_pass():
    """THE CONFIGURATION IN WHICH THIS MATTERS MOST. With ADMIN_EMAILS unset, no order can be recognised
    as the proprietor's - so a backfill would mark nothing, find nothing, and report success, which reads
    exactly like "there was nothing internal"."""
    import app.payments.internal as mod

    real = mod.admin_emails
    try:
        mod.admin_emails = lambda: frozenset()
        with pytest.raises(mod.NoAdminsConfigured):
            mod.require_admins()
    finally:
        mod.admin_emails = real


def test_an_admin_order_can_never_reach_business_revenue():
    """THE ASSERTION THE BRIEF ASKED FOR. If an ADMIN_EMAILS order ever lands in the business list, this
    fails - whatever else changed."""
    orders = [
        {"id": "a", "email": "owner@rashikundli.invalid", "live": 1, "status": "paid", "amount_paise": 29900},
        {"id": "b", "email": "customer@example.com", "live": 1, "status": "paid", "amount_paise": 10085},
    ]
    business, internal_rows = internal.split(orders, ADMINS)
    assert [o["id"] for o in business] == ["b"]
    assert [o["id"] for o in internal_rows] == ["a"]
    for order in business:
        assert (order.get("email") or "").strip().lower() not in ADMINS, order["id"]


def test_the_split_is_exhaustive_and_loses_nothing():
    """Marked, never deleted: every row must come out of the split on one side or the other."""
    orders = [{"id": str(n), "email": f"p{n}@example.com", "live": n % 3, "status": "paid"}
              for n in range(30)]
    business, internal_rows = internal.split(orders, ADMINS)
    assert len(business) + len(internal_rows) == len(orders)
    assert {o["id"] for o in business} | {o["id"] for o in internal_rows} == {o["id"] for o in orders}


def test_the_expected_business_revenue_after_the_backfill():
    """THE FOUR REAL ORDERS, as the brief states them: Rs 708.48 net.

    This is the arithmetic the backfill must produce, asserted as arithmetic. It is deliberately NOT a
    query against this machine's database - the local one holds invented test orders, and the four real
    ones live on the VPS. What it pins is that the four amounts the brief names do sum to the figure the
    brief names, so if the VPS total differs after --apply, the difference is in the data or the
    classifier and not in a number somebody mistyped here.
    """
    four_real_orders = [253.39, 100.85, 100.85, 253.39]
    assert round(sum(four_real_orders), 2) == 708.48


def test_the_mask_shows_enough_to_recognise_a_row_and_no_more():
    assert internal.mask("owner@rashikundli.invalid") == "o***"
    assert internal.mask("") == "(no email)"
    assert internal.mask(None) == "(no email)"
    assert "@" not in internal.mask("someone@example.com")


def test_the_backfill_writes_nothing_without_apply():
    """Read as source: a dry run that writes is the one bug this script must not have.

    WHAT IS CHECKED CHANGED WHEN THE SCRIPT BECAME ONE TRANSACTION. It used to read in one transaction
    and write in a second, so "no db.transaction(write=True) before the dry-run return" was a fair proxy.
    The whole run now opens ONE write transaction up front - which is what makes "nothing was written"
    true when it raises half way - so the write transaction legitimately precedes the guard and that
    proxy would now fail on correct code.

    The guarantee itself has not moved an inch: no UPDATE may be executed before the dry-run returns.
    That is what this asserts now, and tests/test_mark_internal_orders_script.py asserts the same thing
    behaviourally, by running the script on a database and reading the rows back.
    """
    import pathlib
    import re

    source = pathlib.Path("scripts/mark_internal_orders.py").read_text(encoding="utf-8")
    body = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    updates = [m.start() for m in re.finditer(r'conn\.execute\(\s*\n?\s*"UPDATE', body)]
    guard = body.index("if not apply:")
    assert updates, "the script must be able to write at all"
    for where in updates:
        assert where > guard, "every UPDATE must sit after the dry-run return"


def test_orders_and_events_both_carry_the_column():
    from app import analytics, db  # noqa: F401  - imported for register_columns
    from app.payments import store  # noqa: F401

    with db.transaction(write=False) as conn:
        for table in ("orders", "site_events"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert "internal" in columns, table
        assert "internal_reason" in {row[1] for row in conn.execute("PRAGMA table_info(orders)")}


# ---- the page ----------------------------------------------------------------------------------------

def test_the_overview_shows_internal_separately_and_never_hides_its_ai_cost(monkeypatch):
    """The brief's third requirement, on the page itself: business figures count customers only, internal
    gets its own collapsed section with its own totals, and internal AI cost is a line of its own because
    it is real money that left the account."""
    import base64
    import time

    from fastapi.testclient import TestClient

    from app.main import app
    from app.payments import store

    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-password-for-this-test-only")
    monkeypatch.setenv("SESSION_SECRET", "test-internal-orders-session-secret")
    monkeypatch.setenv("BASE_URL", "https://admin.test")
    monkeypatch.setenv("ADMIN_ALERTS_ON_VIEW", "0")
    # PATCHED ON THE CLASSIFIER, not through ADMIN_EMAILS. Two reasons. site.ADMIN_EMAILS is evaluated
    # once when app.web.site is imported, so the environment variable reaches nothing after the app has
    # loaded - correct for production, which restarts on deploy, and a trap here. And setting it would
    # switch the admin door to the allowlist and shut the password route this test comes in through, so
    # the page would 404 and prove nothing about the split.
    monkeypatch.setattr(internal, "admin_emails", lambda: frozenset({"owner@rashikundli.invalid"}))

    now = time.time()
    # One of ours and one customer's, both paid, in the same window.
    for order_id, email, amount in (("ord_internal_mine", "owner@rashikundli.invalid", 29900),
                                    ("ord_internal_theirs", "buyer@example.com", 10085)):
        store.insert_order(order_id=order_id, product="kundali-report", kind="report",
                           amount_paise=amount, currency="INR", request={}, names={},
                           email=email, language="en", user_id=f"user-{order_id}",
                           razorpay_order_id=f"order_{order_id}")
        with __import__("app").db.transaction(write=True) as conn:
            conn.execute("UPDATE orders SET status='paid', paid_at=?, created_at=?, live=1 WHERE id=?",
                         (now, now, order_id))

    client = TestClient(app, base_url="https://admin.test")
    headers = {"Authorization": "Basic " + base64.b64encode(
        b"admin:a-password-for-this-test-only").decode()}
    response = client.get("/admin/", headers=headers)
    assert response.status_code == 200, response.status_code
    html = response.text
    assert 'class="internal"' in html, "no internal section on the overview"
    assert "Internal AI cost" in html, "internal AI cost must be its own line, never folded away"
    assert "not counted above" in html
