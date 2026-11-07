"""The two cookies this site sets, and the flags that make them safe - in BOTH states of the sign-in flag.

There are exactly two: `uid`, the anonymous identity that carries free questions and owns purchases, and
`sid`, the signed-in session. Each must be HttpOnly (a script can never read it), SameSite=Lax (it is not
sent on a cross-site POST) and, on https, Secure.

BOTH FLAG STATES, because that is what the smoke check could not see: with `CHAT_LOGIN` on, the endpoint it
used to probe the cookie answers 401 before any cookie is set, so it was checking a response that carries no
cookie at all.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.ai import chat_identity
from app.main import app
from app.web import accounts, site

BIRTH = {"date": "1988-03-11", "time": "19:30", "city": "Pune", "language": "en"}
THIRTY_DAYS = 30 * 24 * 3600


@pytest.fixture(autouse=True)
def _https(monkeypatch):
    """Production is https, and `Secure` is conditional on that - a local http dev server could not set a
    Secure cookie at all. The flag is only meaningful under the production setting, so that is what is
    tested."""
    monkeypatch.setenv("BASE_URL", "https://rashikundli.com")
    yield


def attributes(header: str) -> dict:
    parts = [part.strip() for part in header.split(";")]
    found = {"name": parts[0].split("=")[0]}
    for part in parts[1:]:
        key, _, value = part.partition("=")
        found[key.lower()] = value or True
    return found


def test_the_sign_in_cookie_is_httponly_lax_secure_and_lasts_thirty_days(caplog, monkeypatch):
    """The session carries a verified e-mail address. HttpOnly keeps it out of reach of any script on the
    page; Lax keeps it off cross-site POSTs; Secure keeps it off plain http."""
    import logging

    client = TestClient(app)
    # monkeypatch, NOT os.environ: set directly it leaked out of this test and into the whole run, and
    # MAIL_TEST_MODE stops the order e-mail sending - so it failed a payments test two files away.
    monkeypatch.setenv("MAIL_TEST_MODE", "1")
    with caplog.at_level(logging.WARNING, logger="app.mailer"):
        client.post("/api/auth/request-code", json={"email": "cookie@example.com", "name": "C", "language": "en"})
    code = next(m.group(1) for r in reversed(caplog.records)
                if (m := re.search(r"is (\d{6})", r.getMessage())))
    response = client.post("/api/auth/verify-code", json={"email": "cookie@example.com", "code": code})
    assert response.status_code == 200

    found = attributes(response.headers["set-cookie"])
    assert found["name"] == accounts.COOKIE_NAME == "sid"
    assert found.get("httponly") is True, "a script can read the session cookie"
    assert str(found.get("samesite", "")).lower() == "lax"
    assert found.get("secure") is True, "the session cookie would travel over plain http"
    assert found.get("path") == "/"
    assert int(found["max-age"]) == THIRTY_DAYS == accounts.SESSION_MAX_AGE


def test_signing_out_sends_a_deletion_that_matches_the_cookie_it_deletes():
    """A browser matches a deletion on name, domain and path, and a deletion sent WITHOUT Secure on an https
    site is itself an insecure cookie that some browsers refuse. Sent with only Path and SameSite - as this
    was - signing out could leave the session in place."""
    found = attributes(TestClient(app).post("/api/auth/sign-out").headers["set-cookie"])
    assert found["name"] == "sid"
    assert found.get("httponly") is True
    assert str(found.get("samesite", "")).lower() == "lax"
    assert found.get("secure") is True
    assert found.get("path") == "/"
    assert found.get("max-age") in ("0", 0)


@pytest.mark.parametrize("chat_login", [False, True])
def test_the_anonymous_cookie_is_httponly_lax_secure_whenever_it_is_set(chat_login, monkeypatch):
    """`uid` carries free questions and owns purchases, so the same three flags apply to it.

    WITH THE GATE ON it is simply not set by the chat, because the 401 is raised before the line that sets
    it - see the test below, which pins that as deliberate rather than letting it drift."""
    monkeypatch.setattr(site, "CHAT_LOGIN", chat_login)
    client = TestClient(app)
    if chat_login:
        client.cookies.set(accounts.COOKIE_NAME, accounts.sign("uid@example.com"))
    response = client.post("/api/consultation/start", json=BIRTH)
    assert response.status_code == 200, response.text

    header = response.headers.get("set-cookie", "")
    assert "uid=" in header, "the chat did not set the anonymous identity"
    found = attributes([part for part in header.split(", ") if part.startswith("uid=")][0])
    assert found.get("httponly") is True
    assert str(found.get("samesite", "")).lower() == "lax"
    assert found.get("secure") is True
    assert found.get("path") == "/"


def test_a_visitor_who_cannot_chat_is_given_no_anonymous_cookie(monkeypatch):
    """DELIBERATE, and pinned here because it is the thing that quietly broke the smoke check.

    With the sign-in required, `_require_login` raises before `_identify` runs, so a gated request never
    reaches the line that sets `uid`. That is the right outcome and not merely an accident of ordering: the
    cookie exists to carry free questions and to own purchases, a visitor who cannot start a chat has
    neither, and a site that sets fewer cookies for people who get nothing from them is the better site.

    Every path that genuinely needs a `uid` still sets its own - a purchase does, which is why somebody can
    buy a report without ever signing in - and that is asserted below rather than assumed.
    """
    monkeypatch.setattr(site, "CHAT_LOGIN", True)
    visitor = TestClient(app)
    response = visitor.post("/api/consultation/start", json=BIRTH)
    assert response.status_code == 401
    assert "uid=" not in response.headers.get("set-cookie", "")
    assert not visitor.cookies.get("uid")

    # ...and a page view never set one either, before or after this change.
    assert "uid=" not in visitor.get("/ai-astrologer").headers.get("set-cookie", "")


def test_a_purchase_still_gets_an_identity_without_any_sign_in(monkeypatch):
    """The other half of the claim above: nothing that NEEDS a uid depends on the chat having set one."""
    monkeypatch.setattr(site, "CHAT_LOGIN", True)
    from app.payments import routes as payment_routes

    class FakeResponse:
        def __init__(self):
            self.cookies = {}

        def set_cookie(self, key, value, **kwargs):
            self.cookies[key] = value

    class FakeRequest:
        cookies: dict = {}

    response = FakeResponse()
    buyer = payment_routes._buyer_id(FakeRequest(), response)
    assert buyer and len(buyer) == 32
    assert chat_identity.COOKIE_NAME in response.cookies, "a buyer with no session was given no identity"
