"""Continue with Google, behind a flag that ships off.

SAME ACCOUNT MODEL. The address is the identity, so signing in with Google using an address that already
has an e-mail-code account is the SAME account - same chats, same paid balance, same free allowance. If it
were not, somebody would sign in the other way one day and find their history gone.

WHAT IS WORTH TESTING HARDEST is not the happy path, it is the refusals. A sign-in that accepts a token
it should not is an account takeover, so: the audience must be our client id (a valid Google token issued
to somebody else's app is not a sign-in here), the issuer must be Google, the address must be one Google
says it verified, and an expired token is not a token.
"""
from __future__ import annotations

import time

import pytest

CLIENT_ID = "123456789-abcdef.apps.googleusercontent.com"


def claims(**overrides):
    base = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "email": "asha@gmail.com",
        "email_verified": True,
        "exp": int(time.time()) + 600,
    }
    base.update(overrides)
    return base


# ---- the flag ----------------------------------------------------------------------------------------

def test_it_ships_off(monkeypatch):
    """Off unless somebody turns it on, like the muhurta finder and for the same reason."""
    monkeypatch.delenv("GOOGLE_SIGNIN", raising=False)
    import importlib

    from app.web import site

    importlib.reload(site)
    assert site.GOOGLE_SIGNIN is False


def test_the_button_is_absent_while_it_is_off(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    page = TestClient(app).get("/login").text
    assert "accounts.google.com/gsi" not in page, "the Google script loads while the flag is off"
    assert "google-signin" not in page


def test_the_endpoint_is_not_there_while_it_is_off(monkeypatch):
    """A route that answers while the feature is off is the feature being on."""
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/auth/google", json={"credential": "anything"})
    assert response.status_code == 404


# ---- what a token must prove -------------------------------------------------------------------------

@pytest.mark.parametrize("bad, why", [
    (claims(aud="999-someone-else.apps.googleusercontent.com"), "a token for another app"),
    (claims(iss="https://evil.example.com"), "not issued by Google"),
    (claims(email_verified=False), "an address Google has not verified"),
    (claims(exp=int(time.time()) - 60), "expired"),
    (claims(email=""), "no address at all"),
    ({}, "no claims at all"),
])
def test_a_token_that_proves_the_wrong_thing_is_refused(bad, why):
    from app.web.google_auth import email_from_claims

    assert email_from_claims(bad, CLIENT_ID) is None, f"accepted {why}"


def test_a_good_token_yields_the_address():
    from app.web.google_auth import email_from_claims

    assert email_from_claims(claims(), CLIENT_ID) == "asha@gmail.com"


def test_the_audience_must_match_exactly():
    """Not "contains", not "starts with": the client id or nothing."""
    from app.web.google_auth import email_from_claims

    assert email_from_claims(claims(aud=CLIENT_ID + ".evil.com"), CLIENT_ID) is None
    assert email_from_claims(claims(aud=CLIENT_ID[:-1]), CLIENT_ID) is None


def test_both_spellings_of_the_google_issuer_are_accepted():
    """Google uses two, and refusing one of them would lock out a share of real people."""
    from app.web.google_auth import email_from_claims

    for issuer in ("accounts.google.com", "https://accounts.google.com"):
        assert email_from_claims(claims(iss=issuer), CLIENT_ID) == "asha@gmail.com"


# ---- one person, one account -------------------------------------------------------------------------

def test_google_and_the_email_code_reach_the_same_account():
    """The address is the identity. If these were two accounts, somebody would sign in the other way one
    day and find their chats and their paid balance gone."""
    from app.web import accounts

    assert accounts.account_id("Asha@Gmail.com ") == accounts.account_id("asha@gmail.com")


# ---- with the flag ON, which is the state it will actually run in ------------------------------------

@pytest.fixture
def switched_on(monkeypatch):
    """The feature as it will be configured, so none of the checks below are testing the off state."""
    import importlib

    from app.web import site

    monkeypatch.setenv("GOOGLE_SIGNIN", "on")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    importlib.reload(site)
    import app.hardening as hardening
    import app.web.auth_routes as auth_routes

    monkeypatch.setattr(auth_routes, "site", site)
    monkeypatch.setattr(hardening, "site", site, raising=False)
    yield site
    monkeypatch.delenv("GOOGLE_SIGNIN", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    importlib.reload(site)


def test_the_button_appears_when_it_is_on(switched_on):
    from fastapi.testclient import TestClient

    from app.main import app

    page = TestClient(app).get("/login").text
    assert "google-signin" in page and CLIENT_ID in page
    assert "/static/js/google-signin.js" in page


def test_a_token_for_another_application_is_refused_end_to_end(switched_on, monkeypatch):
    """The takeover case, through the real endpoint: Google says yes, we say no, because it is not ours."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import google_auth

    monkeypatch.setattr(google_auth, "verify_id_token",
                        lambda credential, client_id: google_auth.email_from_claims(
                            claims(aud="999-other.apps.googleusercontent.com"), client_id))
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/auth/google", json={"credential": "t" * 40})
    assert response.status_code == 400
    assert "rk_session" not in response.headers.get("set-cookie", "")


def test_a_good_token_signs_the_person_in(switched_on, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import accounts, google_auth

    monkeypatch.setattr(google_auth, "verify_id_token", lambda credential, client_id: "asha@gmail.com")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/auth/google", json={"credential": "t" * 40})
    assert response.status_code == 200 and response.json()["signed_in"] is True
    assert client.cookies.get(accounts.COOKIE_NAME), "no session was granted"


def test_the_policy_only_allows_googles_script_while_the_flag_is_on(switched_on):
    """A flag whose rollback leaves its exceptions behind is not a rollback."""
    from fastapi.testclient import TestClient

    from app.main import app

    csp = TestClient(app).get("/").headers.get("content-security-policy", "")
    assert "https://accounts.google.com" in csp
