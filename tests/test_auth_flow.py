"""Signing in, end to end, and the gate it puts in front of the AI astrologer.

The unit-level limits are in tests/test_accounts.py and the money in tests/test_account_credits.py. This is
the join: that the gate actually closes, that a code signs you through it, that the sign-in form cannot be
used to ask whether somebody is a customer, and that one setting opens it all again.
"""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.ai import chat_store
from app.main import app
from app.web import accounts, site

client = TestClient(app)
BIRTH = {"date": "1990-01-01", "time": "10:00", "city": "Pune", "language": "en"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("MAIL_TEST_MODE", "1")
    with db.transaction() as conn:
        for table in ("login_codes", "accounts", "rate_events", "chat_adoptions", "chat_users"):
            conn.execute(f"DELETE FROM {table}")
    yield


def code_for(email: str, caplog) -> str:
    """The code, read from the journal line test mode writes. Nothing returns it to a caller."""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.mailer"):
        response = client.post("/api/auth/request-code", json={"email": email, "name": "Reader", "language": "en"})
    assert response.status_code == 200, response.text
    import re

    for record in reversed(caplog.records):
        found = re.search(r"is (\d{6})", record.getMessage())
        if found and "sign-in code" in record.getMessage():
            return found.group(1)
    raise AssertionError("test mode did not write the code to the journal")


def test_the_ai_astrologer_is_closed_without_a_sign_in():
    response = client.post("/api/consultation/start", json=BIRTH)
    assert response.status_code == 401
    assert response.json()["detail"]["login_required"] is True


def test_the_free_tools_stay_open():
    """The tools are what brings people here. Nothing but the chat may ask for an address."""
    for path in ("/", "/birth-chart", "/horoscope/libra/today", "/hi/kundli", "/mr/kundali"):
        assert client.get(path).status_code == 200, path
    chart = client.post("/api/chart", json={"date": "1990-01-01", "time": "10:00", "city": "Pune"})
    assert chart.status_code == 200, chart.text


def test_a_code_signs_you_in_and_opens_the_chat(caplog):
    email = "reader@example.com"
    code = code_for(email, caplog)
    signed = client.post("/api/auth/verify-code", json={"email": email, "code": code})
    assert signed.status_code == 200 and signed.json()["signed_in"] is True
    assert client.cookies.get("sid")

    opened = client.post("/api/consultation/start", json=BIRTH)
    assert opened.status_code == 200, opened.text
    client.cookies.clear()


def test_the_two_free_answers_follow_the_account_and_not_the_browser(caplog):
    """THE WHOLE POINT. A second browser with no cookies, signing in as the same person, continues the same
    allowance - it does not get a fresh pair."""
    email = "shared@example.com"
    code = code_for(email, caplog)
    client.post("/api/auth/verify-code", json={"email": email, "code": code})
    account = accounts.account_id(email)
    with db.transaction() as conn:                       # the account has already spent its two
        conn.execute("INSERT INTO chat_users (user_id, free_used, paid_balance, busy_until, created_at) "
                     "VALUES (?, 2, 0, 0, 0) ON CONFLICT(user_id) DO UPDATE SET free_used = 2", (account,))
    client.cookies.clear()

    fresh = TestClient(app)                              # a different browser, no cookies at all
    code = code_for(email, caplog)
    fresh.post("/api/auth/verify-code", json={"email": email, "code": code})
    started = fresh.post("/api/consultation/start", json=BIRTH)
    assert started.status_code == 200
    assert started.json()["quota"]["free_left"] == 0, "a new browser handed the same account a fresh trial"


def test_a_wrong_code_does_not_sign_you_in(caplog):
    email = "wrong@example.com"
    code = code_for(email, caplog)
    bad = "000000" if code != "000000" else "111111"
    assert client.post("/api/auth/verify-code", json={"email": email, "code": bad}).status_code == 400
    assert not client.cookies.get("sid")


def test_the_form_never_says_whether_an_address_is_a_customer(caplog):
    """A form that answered differently for a known address would be a way to ask this site who its
    customers are. Both answers are the same object."""
    known = client.post("/api/auth/request-code", json={"email": "a-customer@example.com", "name": "", "language": "en"})
    other = client.post("/api/auth/request-code", json={"email": "never-heard-of@example.com", "name": "", "language": "en"})
    assert known.status_code == other.status_code == 200
    assert known.json() == other.json() == {"sent": True}


@pytest.mark.parametrize("address,reason", [("x@mailinator.com", "disposable"), ("not-an-address", "invalid")])
def test_the_form_refuses_what_the_person_can_fix(address, reason):
    response = client.post("/api/auth/request-code", json={"email": address, "name": "", "language": "en"})
    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == reason


def test_asking_twice_in_a_row_is_rate_limited():
    first = client.post("/api/auth/request-code", json={"email": "fast@example.com", "name": "", "language": "en"})
    second = client.post("/api/auth/request-code", json={"email": "fast@example.com", "name": "", "language": "en"})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["retry_after"] > 0


def test_signing_in_adopts_a_pack_bought_before_the_login_existed(caplog):
    """The route-level half of tests/test_account_credits.py: the cookie that is about to stop being the
    identity is still on the request, which is the only moment this can happen."""
    from app.ai import chat_identity

    buyer = TestClient(app)
    cookie_user = chat_identity.new_user_id()            # the browser that bought the pack, before login
    buyer.cookies.set(chat_identity.COOKIE_NAME, chat_identity.sign_user_id(cookie_user))
    chat_store.credit_messages(cookie_user, 10)

    email = "adopt@example.com"
    code = code_for(email, caplog)
    signed = buyer.post("/api/auth/verify-code", json={"email": email, "code": code})
    assert signed.status_code == 200
    assert signed.json()["adopted"] == 10

    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT paid_balance FROM chat_users WHERE user_id = ?",
                           (accounts.account_id(email),)).fetchone()
    assert row["paid_balance"] == 10


def test_one_setting_opens_the_chat_again(monkeypatch):
    """`CHAT_LOGIN=off` and a restart: no sign-in anywhere, exactly as before. The rollback."""
    monkeypatch.setattr(site, "CHAT_LOGIN", False)
    anonymous = TestClient(app)
    assert anonymous.post("/api/consultation/start", json=BIRTH).status_code == 200


def test_the_sign_in_and_orders_pages_are_not_indexable():
    """They are forms, not destinations. An indexed sign-in page competes with the pages that answer a search
    - and /orders would be a crawler's view of somebody's purchases."""
    for path in ("/login", "/hi/login", "/mr/login"):
        assert 'content="noindex, nofollow"' in client.get(path).text, path
    sitemap = client.get("/sitemap.xml").text
    assert "/login" not in sitemap and "/orders" not in sitemap


# ---- the gate as a VISITOR meets it ------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/ai-astrologer", "/hi/ai-jyotish", "/mr/ai-jyotish"])
def test_the_chat_page_says_a_sign_in_is_needed_before_the_form_is_filled(path):
    """THE BUG THIS EXISTS FOR, found on the live site. With the gate on and no session, the page said
    nothing: a visitor filled in their birth details, pressed the button, got "We could not calculate a
    result from these details. Please check them and try again." - which was FALSE (the calculation was
    never attempted), blamed them for it, and offered no way forward.

    Every chat test until now either ran with CHAT_LOGIN off or carried a session cookie, so not one of them
    ever saw what a visitor sees. This one has no cookie, on purpose."""
    anonymous = TestClient(app)
    page = anonymous.get(path)
    assert page.status_code == 200
    assert 'id="chat-signin"' in page.text, f"{path} does not say a sign-in is needed"
    assert "/login" in page.text, f"{path} says a sign-in is needed and offers no way to do it"


@pytest.mark.parametrize("path", ["/ai-astrologer", "/hi/ai-jyotish", "/mr/ai-jyotish"])
def test_the_chat_page_promises_no_sign_up_only_when_that_is_true(path):
    """The form note said "Free · no sign-up". With the gate on that is a promise the page breaks two clicks
    later, which is worse than no promise."""
    anonymous = TestClient(app)
    assert "no sign-up" not in anonymous.get(path).text

    signed = TestClient(app)
    signed.cookies.set(accounts.COOKIE_NAME, accounts.sign("note@example.com"))
    assert 'id="chat-signin"' not in signed.get(path).text, "a signed-in reader is still told to sign in"


def test_the_gate_answers_with_something_the_page_can_act_on():
    """401 carries `login_required` and the path. Without both, the browser cannot tell a locked chat from a
    bad birth date - which is exactly how this failed: `parseApiError` saw a detail dict with no `message`
    and fell through to the generic "could not calculate" text."""
    anonymous = TestClient(app)
    response = anonymous.post("/api/consultation/start", json=BIRTH)
    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["login_required"] is True
    assert detail["login_path"].endswith("/login")


def test_the_browser_is_told_a_401_is_not_a_bad_birth_detail():
    """The mapping lives in static/js/render.js, where no Python test runs - so the two things that make it
    work are asserted on the source: the 401 branch, and a message of its own in all three trees."""
    import pathlib

    source = pathlib.Path("app/static/js/render.js").read_text()
    assert "body.detail.login_required" in source, "render.js no longer special-cases the sign-in"
    assert source.count("signInNeeded:") == 3, "the sign-in message is missing from a language"
    assert "cityNotChosen:" in source and source.count("cityNotChosen:") == 3
