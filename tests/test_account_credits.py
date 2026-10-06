"""Paid credits across the login boundary: nobody loses one, nobody spends one twice.

WRITTEN BEFORE THE FEATURE, because these two are the only bugs here that cost real money and the only ones
that cannot be confidently retrofitted once it is live and balances exist.

The situation that creates them: consultation credits live on `chat_users.user_id`, which was the COOKIE.
Compulsory login makes a request's identity the ACCOUNT instead. So every customer who bought a pack before
the flip has a balance on an id nothing will read again, and the bridge that rescues it is the one thing that
could also mint credits out of nothing if it ran twice.
"""

import pytest

from app.ai import chat_store as store
from app.web import accounts


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    """Each test gets its own balances, so one test's adoption cannot pay for another's."""
    from app import db

    with db.transaction() as conn:
        conn.execute("DELETE FROM chat_adoptions")
        conn.execute("DELETE FROM chat_users")
    yield


def credit(user_id: str, messages: int) -> None:
    store.credit_messages(user_id, messages)


def spend(user_id: str, n: int) -> None:
    """Take n paid messages off a balance the way a delivered reply does."""
    from app import db

    with db.transaction() as conn:
        conn.execute("UPDATE chat_users SET paid_balance = MAX(0, paid_balance - ?) WHERE user_id = ?",
                     (n, user_id))


def balance(user_id: str) -> int:
    from app import db

    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT paid_balance FROM chat_users WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["paid_balance"]) if row else 0


def test_a_pack_bought_before_the_login_is_not_lost_when_the_buyer_signs_in():
    """THE LOST-CREDIT CASE. Somebody buys ten questions as a cookie, asks none, and then has to log in
    because chat now requires it. The ten must follow them."""
    cookie = "a" * 32
    account = accounts.account_id("buyer@example.com")
    credit(cookie, 10)

    moved = store.adopt_paid_balance(cookie, account)

    assert moved == 10
    assert balance(account) == 10, "the customer's paid questions did not follow them to their account"
    assert balance(cookie) == 0, "the balance is readable from BOTH identities - it can be spent twice"


def test_a_partly_used_pack_carries_over_what_is_left_and_not_what_was_spent():
    cookie = "b" * 32
    account = accounts.account_id("partly@example.com")
    credit(cookie, 10)
    spend(cookie, 4)

    assert store.adopt_paid_balance(cookie, account) == 6
    assert balance(account) == 6
    assert balance(cookie) == 0


def test_the_same_cookie_cannot_be_adopted_twice():
    """THE DOUBLE-SPEND CASE, and the reason the adoption table has a PRIMARY KEY rather than a check. Two
    sign-ins on one cookie - two tabs, a retry, a refresh of the verify POST - must not mint a second pack."""
    cookie = "c" * 32
    account = accounts.account_id("twice@example.com")
    credit(cookie, 10)

    first = store.adopt_paid_balance(cookie, account)
    second = store.adopt_paid_balance(cookie, account)
    third = store.adopt_paid_balance(cookie, accounts.account_id("someone.else@example.com"))

    assert first == 10
    assert second == 0, "signing in twice on one cookie doubled the balance"
    assert third == 0, "a second account claimed a cookie that had already been adopted"
    assert balance(account) == 10


def test_adoption_adds_to_an_account_that_already_has_credits():
    """A customer who bought on a phone and again on a laptop ends with both, not the larger of the two."""
    account = accounts.account_id("both@example.com")
    credit(account, 5)
    cookie = "d" * 32
    credit(cookie, 10)

    assert store.adopt_paid_balance(cookie, account) == 15 - 5
    assert balance(account) == 15


def test_adoption_moves_nothing_when_there_is_nothing_to_move():
    cookie = "e" * 32
    account = accounts.account_id("empty@example.com")
    assert store.adopt_paid_balance(cookie, account) == 0
    assert balance(account) == 0


def test_adoption_refuses_to_move_a_balance_onto_itself():
    """Defensive: the account id and the cookie id are both 32 hex characters, so a caller that passed the
    same value twice would otherwise zero the balance and add it back - and on the unlucky ordering, lose it."""
    same = accounts.account_id("self@example.com")
    credit(same, 7)
    assert store.adopt_paid_balance(same, same) == 0
    assert balance(same) == 7


def test_the_free_allowance_is_carried_by_max_and_can_never_be_reset():
    """CHANGED DELIBERATELY on 4 October, and this is the whole of the argument.

    This test used to assert that a cookie's used count is NOT carried, on the grounds that carrying it
    would let a fresh cookie hand a new account a spent trial or - the direction that costs us - let a
    returning visitor RESET one. Both of those are properties of ASSIGNING the count. `MAX` has neither:
    it can only ever move the number up.

    Not carrying it had its own cost, which is what was actually happening: answers spent on this browser
    before signing in disappeared from the account, so the allowance quietly depended on which window you
    were in. So the count follows the browser onto the account, and never the other way.
    """
    from app import db

    cookie = "f" * 32
    account = accounts.account_id("free@example.com")
    with db.transaction() as conn:
        conn.execute("INSERT INTO chat_users (user_id, free_used, paid_balance, busy_until, created_at) "
                     "VALUES (?, 2, 3, 0, 0)", (cookie,))
    store.adopt_paid_balance(cookie, account)

    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT free_used FROM chat_users WHERE user_id = ?", (account,)).fetchone()
    assert (row["free_used"] if row else 0) == 2, "answers spent before signing in vanished from the account"

    # ...and the direction that would cost us: a clean cookie must never lower a count already there.
    clean = "g" * 32
    with db.transaction() as conn:
        conn.execute("INSERT INTO chat_users (user_id, free_used, paid_balance, busy_until, created_at) "
                     "VALUES (?, 0, 0, 0, 0)", (clean,))
    store.adopt_paid_balance(clean, account)
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT free_used FROM chat_users WHERE user_id = ?", (account,)).fetchone()
    assert row["free_used"] == 2, "a fresh cookie reset the account's trial"
