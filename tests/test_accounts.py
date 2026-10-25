"""The login core: normalisation, the code, and every limit that stands between it and abuse.

The free allowance is two AI answers. Before this, those two were counted against a cookie, so they were
available again in every incognito window - which is the hole this feature exists to close. Closing it moves
the whole problem onto the address, and an address has its own ways of being multiplied: aliases of one
inbox, throwaway domains, and simply opening more real inboxes. Each has its own control and each is tested
here, because a control that is not tested is a control nobody will notice has stopped working.
"""

import time

import pytest

from app import db
from app.web import accounts


@pytest.fixture(autouse=True)
def _clean():
    with db.transaction() as conn:
        conn.execute("DELETE FROM login_codes")
        conn.execute("DELETE FROM accounts")
        conn.execute("DELETE FROM rate_events")
    yield


# ---- the address is the identity ---------------------------------------------------------------------


@pytest.mark.parametrize("spelling", [
    "ashavernekar@gmail.com", "Asha.Vernekar@gmail.com", "a.s.h.a.vernekar@gmail.com",
    "ashavernekar+chat@gmail.com", "Asha.Vernekar+anything@GoogleMail.com", "  ASHAVERNEKAR@GMAIL.COM  ",
])
def test_every_spelling_of_one_gmail_inbox_is_one_account(spelling):
    """WITHOUT THIS THE WHOLE FEATURE IS DECORATIVE. Gmail documents dots and +suffixes as the same mailbox,
    so one Gmail account would otherwise yield unlimited free trials - the exact thing being closed."""
    assert accounts.normalise(spelling) == "ashavernekar@gmail.com"
    assert accounts.account_id(spelling) == accounts.account_id("ashavernekar@gmail.com")


def test_folding_is_applied_only_where_the_provider_documents_it():
    """At most providers `a.b@` and `ab@` are DIFFERENT PEOPLE. Folding everywhere would merge strangers,
    which is a worse failure than missing an alias."""
    assert accounts.normalise("a.b@example.com") == "a.b@example.com"
    assert accounts.normalise("a.b@outlook.com") == "a.b@outlook.com"      # dots kept
    assert accounts.normalise("a.b+tag@outlook.com") == "a.b@outlook.com"  # +tag dropped
    assert accounts.account_id("a.b@example.com") != accounts.account_id("ab@example.com")


@pytest.mark.parametrize("address", ["x@mailinator.com", "a@10minutemail.com", "b@yopmail.com", "c@trashmail.com"])
def test_throwaway_inboxes_are_refused(address):
    with pytest.raises(accounts.Rejected) as caught:
        accounts.check(address)
    assert caught.value.reason == "disposable"


@pytest.mark.parametrize("address", ["", "nope", "a@b", "a b@example.com", "@example.com", "a@@b.com"])
def test_a_malformed_address_is_refused(address):
    with pytest.raises(accounts.Rejected) as caught:
        accounts.check(address)
    assert caught.value.reason == "invalid"


def test_the_account_id_is_the_shape_the_chat_tables_already_use():
    """32 hex characters, like chat_identity.new_user_id(), so every quota rule keyed by `user_id` applies to
    the account unchanged - and an HMAC, so the consultation tables never hold an address."""
    account = accounts.account_id("someone@example.com")
    assert len(account) == 32 and all(c in "0123456789abcdef" for c in account)
    assert "someone" not in account and "@" not in account


# ---- the code -----------------------------------------------------------------------------------------


def test_the_code_is_six_digits_and_is_never_stored_in_the_clear():
    code = accounts.request_code("reader@example.com", "Reader", "ip1")
    assert len(code) == 6 and code.isdigit()
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT code_hash FROM login_codes").fetchone()
    assert code not in row["code_hash"], "the code is recoverable from the database"
    assert len(row["code_hash"]) == 64


def test_the_right_code_signs_in_and_can_only_be_used_once():
    code = accounts.request_code("once@example.com", "Once", "ip1")
    assert accounts.verify_code("once@example.com", code, "ip1") == "once@example.com"
    assert accounts.verify_code("once@example.com", code, "ip1") is None, "the code worked a second time"


def test_the_code_works_for_any_spelling_of_the_same_inbox():
    code = accounts.request_code("A.B+x@gmail.com", "A", "ip1")
    assert accounts.verify_code("ab@gmail.com", code, "ip1") == "ab@gmail.com"


def test_a_wrong_code_fails_and_five_wrong_codes_kill_the_right_one():
    """Six digits is a million guesses; five attempts is what makes that a wall rather than a speed bump.
    The counter is on the CODE, so starting a new session does not reset it."""
    code = accounts.request_code("guess@example.com", "G", "ip1")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(accounts.MAX_ATTEMPTS):
        assert accounts.verify_code("guess@example.com", wrong, "ip1") is None
    assert accounts.verify_code("guess@example.com", code, "ip1") is None, "the real code still worked after 5 wrong ones"


def test_a_code_expires(monkeypatch):
    code = accounts.request_code("slow@example.com", "S", "ip1")
    later = time.time() + accounts.CODE_TTL_SECONDS + 1     # read the real clock BEFORE replacing it
    monkeypatch.setattr(accounts.time, "time", lambda: later)
    assert accounts.verify_code("slow@example.com", code, "ip1") is None


def test_a_new_code_replaces_the_old_one(monkeypatch):
    first = accounts.request_code("replace@example.com", "R", "ip1")
    later = time.time() + accounts.RESEND_COOLDOWN_SECONDS + 1
    monkeypatch.setattr(accounts.time, "time", lambda: later)
    second = accounts.request_code("replace@example.com", "R", "ip1")
    assert accounts.verify_code("replace@example.com", first, "ip1") is None, "the superseded code still worked"
    assert accounts.verify_code("replace@example.com", second, "ip1") == "replace@example.com"


# ---- the limits ---------------------------------------------------------------------------------------


def test_codes_cannot_be_resent_immediately():
    accounts.request_code("cooldown@example.com", "C", "ip1")
    with pytest.raises(accounts.RateLimited) as caught:
        accounts.request_code("cooldown@example.com", "C", "ip1")
    assert 0 < caught.value.retry_after <= accounts.RESEND_COOLDOWN_SECONDS


def test_one_address_cannot_be_mail_bombed(monkeypatch):
    """The limit protects the OWNER of the address, who may not be the person at the keyboard."""
    now = [time.time()]
    monkeypatch.setattr(accounts.time, "time", lambda: now[0])
    for _ in range(accounts.CODES_PER_ADDRESS_PER_HOUR):
        accounts.request_code("bomb@example.com", "B", "ip1")
        now[0] += accounts.RESEND_COOLDOWN_SECONDS + 1
    with pytest.raises(accounts.RateLimited):
        accounts.request_code("bomb@example.com", "B", "ip1")


def test_one_network_cannot_walk_a_list_of_addresses(monkeypatch):
    now = [time.time()]
    monkeypatch.setattr(accounts.time, "time", lambda: now[0])
    for n in range(accounts.CODES_PER_IP_PER_HOUR):
        accounts.request_code(f"walk{n}@example.com", "W", "onebucket")
        now[0] += 1
    with pytest.raises(accounts.RateLimited):
        accounts.request_code("walklast@example.com", "W", "onebucket")


def test_one_network_cannot_open_unlimited_new_accounts(monkeypatch):
    """THE THIRD LAYER, and the one the other two do not cover: alias folding and the disposable list stop
    one inbox being reused, neither stops somebody opening real inboxes, and every new account is a fresh
    pair of free answers. Soft and generous - the cost of being wrong is a real customer turned away."""
    now = [time.time()]
    monkeypatch.setattr(accounts.time, "time", lambda: now[0])
    for n in range(accounts.NEW_ACCOUNTS_PER_IP_PER_DAY):
        code = accounts.request_code(f"new{n}@example.com", "N", "samebucket")
        assert accounts.verify_code(f"new{n}@example.com", code, "samebucket")
        now[0] += accounts.RESEND_COOLDOWN_SECONDS + 1
    code = accounts.request_code("onemore@example.com", "N", "samebucket")
    with pytest.raises(accounts.RateLimited):
        accounts.verify_code("onemore@example.com", code, "samebucket")


def test_the_cap_never_locks_out_an_account_that_already_exists(monkeypatch):
    """A household over the cap must still be able to SIGN IN. The limit is on creating accounts, not on
    using them, or a shared office would lock out its own customers."""
    now = [time.time()]
    monkeypatch.setattr(accounts.time, "time", lambda: now[0])
    code = accounts.request_code("resident@example.com", "R", "busybucket")
    assert accounts.verify_code("resident@example.com", code, "busybucket")
    with db.transaction() as conn:                      # the bucket is already far over its cap
        for _ in range(accounts.NEW_ACCOUNTS_PER_IP_PER_DAY * 3):
            conn.execute("INSERT INTO rate_events (key, ts) VALUES (?, ?)", ("newacct:busybucket", now[0]))
    now[0] += accounts.RESEND_COOLDOWN_SECONDS + 1
    code = accounts.request_code("resident@example.com", "R", "busybucket")
    assert accounts.verify_code("resident@example.com", code, "busybucket") == "resident@example.com"


# ---- the session --------------------------------------------------------------------------------------


def test_a_session_cookie_cannot_be_forged_or_edited():
    signed = accounts.sign("reader@example.com")
    assert accounts.verify_session(signed) == "reader@example.com"
    assert accounts.verify_session("reader@example.com.deadbeef") is None
    assert accounts.verify_session("attacker@example.com." + signed.rpartition(".")[2]) is None
    assert accounts.verify_session(None) is None
    assert accounts.verify_session("nodot") is None
