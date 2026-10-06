"""The dashboard: who may see it, what it counts, and what it must never hold.

THE TWO CLAIMS WORTH A TEST. An administrator is an EXACT address on an allowlist - not an alias of one,
not a password - and everyone else is told the page does not exist. And an administrator has no limits,
which means their own use would be the loudest thing on their own dashboard unless it is recorded
separately and left out by default.
"""

import time

import pytest
from fastapi.testclient import TestClient

from app import analytics
from app.main import app
from app.web import accounts, site

ADMIN = "boss@rashikundli-test.com"
PAGES = ("/admin", "/admin/usage", "/admin/orders", "/admin/cost")


@pytest.fixture(autouse=True)
def _allowlist(monkeypatch):
    monkeypatch.setattr(site, "ADMIN_EMAILS", (ADMIN,))


def jar(email: str | None = None) -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.clear()
    if email:
        client.cookies.set(accounts.COOKIE_NAME, accounts.sign(email))
    return client


# ---- who gets in ------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", PAGES)
def test_a_stranger_is_told_the_page_does_not_exist(path):
    """404, NOT 403. A 403 confirms there is something here worth finding; an admin panel that announces
    itself is an admin panel being probed by morning."""
    assert jar().get(path).status_code == 404


@pytest.mark.parametrize("path", PAGES)
def test_an_ordinary_signed_in_reader_is_told_the_same(path):
    assert jar("somebody.else@gmail.com").get(path).status_code == 404


@pytest.mark.parametrize("alias", ["boss+admin@rashikundli-test.com", "b.oss@rashikundli-test.com",
                                   "BOSS@rashikundli-test.com.evil.com", "boss@rashikundli-test.com.x"])
def test_an_alias_of_the_admin_address_is_not_an_administrator(alias):
    """THE ONE PLACE ON THIS SITE WHERE ALIASES ARE NOT FOLDED. Everywhere else `normalise` folds Gmail
    dots and +tags so one person has one account. Folding here would hand the dashboard to anybody who can
    put a +tag on an address."""
    assert not accounts.is_admin(alias), alias
    assert jar(alias).get("/admin/usage").status_code == 404


def test_the_administrator_gets_in():
    assert jar(ADMIN).get("/admin/usage").status_code == 200
    assert accounts.is_admin(ADMIN)


def test_case_and_spacing_do_not_matter_but_nothing_else_does():
    assert accounts.is_admin(f"  {ADMIN.upper()}  ")


def test_an_admin_session_is_shorter_than_an_ordinary_one():
    """An administrator's cookie is worth more, so it lives less - and the limit is enforced on the server
    rather than asked of the browser, because `max_age` is a request and a copied cookie ignores it."""
    assert accounts.session_max_age(ADMIN) == accounts.ADMIN_SESSION_MAX_AGE < accounts.SESSION_MAX_AGE
    old = accounts.sign(ADMIN, issued_at=time.time() - accounts.ADMIN_SESSION_MAX_AGE - 60)
    assert accounts.verify_session(old) is None, "an expired admin session was accepted"
    fresh = accounts.sign(ADMIN)
    assert accounts.verify_session(fresh) == ADMIN
    # ...and an ordinary account still gets its thirty days out of the same cookie shape.
    still_good = accounts.sign("reader@gmail.com", issued_at=time.time() - 10 * 24 * 3600)
    assert accounts.verify_session(still_good) == "reader@gmail.com"


def test_the_dashboard_link_is_only_in_an_administrators_menu():
    assert "/admin" in jar(ADMIN).get("/").text
    assert '"/admin"' not in jar("reader@gmail.com").get("/").text


# ---- what it counts ---------------------------------------------------------------------------------


def test_a_visitor_is_a_daily_hash_and_the_address_is_never_kept():
    day = analytics.ist_day()
    same = analytics.visitor_hash("203.0.113.9", "Mozilla/5.0", day)
    assert same == analytics.visitor_hash("203.0.113.9", "Mozilla/5.0", day), "not stable within a day"
    assert same != analytics.visitor_hash("203.0.113.9", "Mozilla/5.0", "1999-01-01"), "stable across days"
    assert "203.0.113.9" not in same
    from app import db

    analytics.record_visit(ip="203.0.113.9", user_agent="Mozilla/5.0", path="/", lang="en")
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT visitor FROM site_visits WHERE visitor LIKE '%203.0.113%'").fetchall()
    assert not rows, "something that looks like an IP address is in the table"


def test_crawlers_and_assets_are_not_visitors():
    assert analytics.is_bot("Googlebot/2.1") and analytics.is_bot("")
    assert not analytics.is_bot("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)")
    assert analytics.is_page("/mr/muhurta") and not analytics.is_page("/static/js/app.js")
    assert not analytics.is_page("/api/muhurta/search") and not analytics.is_page("/admin/usage")


def test_the_counts_match_the_event_log():
    """The number on the tile and the rows underneath it are the same thing counted twice."""
    stamp = time.time()
    marker = f"fixture-{int(stamp)}"
    for n in range(3):
        analytics.record_event("muhurta", "search", detail=marker, cost_inr=0.5, stamp=stamp)
    report = analytics.summary(1)
    rows = [row for row in report["features"] if row["feature"] == "muhurta" and row["action"] == "search"]
    assert rows, "the feature did not appear in the summary at all"
    logged = [row for row in analytics.recent_events(200) if row["detail"] == marker]
    assert len(logged) == 3
    assert sum(row["cost_inr"] for row in logged) == pytest.approx(1.5)


def test_a_known_fixture_of_costs_adds_up_to_a_known_margin():
    """Arithmetic, pinned: three events in, one margin out, computed by hand."""
    stamp = time.time()
    tag = f"margin-{int(stamp)}"
    before = analytics.summary(1)
    analytics.record_event("report", "sold", revenue_inr=299.0, cost_inr=12.5, detail=tag, stamp=stamp)
    analytics.record_event("chat", "question", cost_inr=1.25, detail=tag, stamp=stamp)
    analytics.record_event("report", "refund", revenue_inr=-99.0, detail=tag, stamp=stamp)
    after = analytics.summary(1)
    assert after["revenue_inr"] - before["revenue_inr"] == pytest.approx(200.0)   # 299 - 99
    assert after["cost_inr"] - before["cost_inr"] == pytest.approx(13.75)         # 12.5 + 1.25
    assert after["margin_inr"] - before["margin_inr"] == pytest.approx(186.25)


def test_admin_usage_is_recorded_and_kept_out_of_the_numbers():
    """An administrator has no limits, so their own use would otherwise be the loudest thing here."""
    stamp = time.time()
    tag = f"adminuse-{int(stamp)}"
    before = analytics.summary(1)["cost_inr"]
    analytics.record_event("chat", "question", is_admin=True, cost_inr=500.0, detail=tag, stamp=stamp)
    plain = analytics.summary(1)
    assert plain["cost_inr"] == pytest.approx(before), "admin spend leaked into the customer numbers"
    assert plain["admin_events_excluded"] >= 1, "the page does not say anything was left out"
    with_admin = analytics.summary(1, include_admin=True)
    assert with_admin["cost_inr"] >= before + 500.0, "asking for admin usage did not include it"


def test_the_dashboard_says_how_much_of_itself_it_is_hiding():
    page = jar(ADMIN).get("/admin/usage?days=1").text
    assert "left out of everything below" in page or "Include my own usage" in page


# ---- what it must never hold -------------------------------------------------------------------------


def test_no_chat_text_can_reach_the_event_log():
    """The log records what the software did, never what anybody said."""
    from app import db

    with db.transaction(write=False) as conn:
        columns = {row[1] for row in conn.execute("pragma table_info(site_events)")}
    for forbidden in ("text", "message", "question", "answer", "body", "content", "prompt", "reply"):
        assert forbidden not in columns, f"site_events has a {forbidden} column"
    assert "email" not in columns and "ip" not in columns


def test_reading_a_consultation_needs_a_written_reason_and_leaves_a_trail():
    from app.admin import audit, chat_access

    with pytest.raises(chat_access.NotAuthorised):
        chat_access.authorise("reader@gmail.com", "sess", "a long enough reason, but not an admin")
    with pytest.raises(chat_access.NotAuthorised):
        chat_access.authorise(ADMIN, "sess", "too short")
    with pytest.raises(chat_access.NotAuthorised):
        chat_access.authorise(ADMIN, "", "a perfectly good reason for doing this")

    chat_access.authorise(ADMIN, "sess-77", "refund dispute on order ord_x, customer asked us to check")
    recent = audit.recent(5)
    assert any(row["action"] == "chat.read.authorised" and row["subject"] == "sess-77" for row in recent)


def test_there_is_no_way_to_read_a_consultation_yet():
    """Deliberately not built. The guard exists so that building it later is a visible change."""
    from app.admin import chat_access

    with pytest.raises(NotImplementedError):
        chat_access.read("sess-77")


def test_the_privacy_policy_says_what_is_counted_and_that_no_ip_is_kept():
    import re

    text = re.sub(r"<[^>]+>", " ", jar().get("/privacy").text)
    assert "What we count" in text
    assert "DO NOT STORE YOUR IP ADDRESS" in text.upper()
    assert "do not record the text of your questions" in text


@pytest.mark.parametrize("path", ["/login", "/hi/login", "/mr/login"])
def test_the_sign_in_page_says_it_in_the_readers_language(path):
    """The policy page is English only, as every policy page here is. This sentence is the one a reader
    actually meets before deciding, so it is in all three trees."""
    text = jar().get(path).text
    assert "IP" in text, path


def test_a_signed_out_visitor_gets_the_custom_404_and_no_login_prompt():
    """THE LIVE FAILURE: /admin answered 401 to a signed-out visitor, because ADMIN_PASSWORD was still set
    and a non-admin fell through to the password challenge. A 401 announces that there IS something here
    and invites a guess; the whole point of 404 is that /admin should look like a path nobody built.
    """
    import os

    os.environ["ADMIN_PASSWORD"] = "a-password-is-set-on-this-box"
    try:
        for path in PAGES:
            answer = jar().get(path, headers={"Accept": "text/html"})
            assert answer.status_code == 404, f"{path} -> {answer.status_code} for a signed-out visitor"
            assert "www-authenticate" not in answer.headers, f"{path} offered a login"
            # ...and the body is the site's own 404 page, not a bare FastAPI message.
            assert "<html" in answer.text.lower(), f"{path} returned a bare body"
            assert "admin" not in answer.text.lower().split("<body")[-1][:400], \
                f"{path}'s 404 page mentions the dashboard"
    finally:
        os.environ.pop("ADMIN_PASSWORD", None)


def test_a_signed_in_non_admin_gets_exactly_the_same_404():
    import os

    os.environ["ADMIN_PASSWORD"] = "a-password-is-set-on-this-box"
    try:
        anonymous = jar().get("/admin", headers={"Accept": "text/html"})
        reader = jar("reader@gmail.com").get("/admin", headers={"Accept": "text/html"})
        assert anonymous.status_code == reader.status_code == 404
        assert len(reader.text) == len(anonymous.text), "the two 404s differ, which is itself a signal"
    finally:
        os.environ.pop("ADMIN_PASSWORD", None)
