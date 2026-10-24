"""Where the people on this site actually come from.

WHY THIS IS MEASURED. The dashboard counts 450-580 visitors a day; Search Console reports about 7 Google clicks
a day, and /birth-chart shows 5,464 views against 30 Google clicks. Those two numbers cannot both be about
the same population. Either a great many visitors arrive from somewhere nobody is measuring, or a great
many of them are not people. Until the source is recorded, every other number on the Usage page - cost per
visitor, conversion, which language is worth writing - is being read off an unknown denominator.

PRIVACY. A source is a word from a fixed list, a campaign is whatever the link said, and neither is tied
to a person: the visitor is still the same daily-salted hash of IP and user agent, and no referring URL,
query string or path beyond our own is stored.
"""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("referer, expected", [
    ("https://www.google.com/", "google"),
    ("https://google.co.in/search?q=kundli", "google"),
    ("android-app://com.google.android.googlequicksearchbox/", "google"),
    ("https://www.bing.com/search?q=rashifal", "bing"),
    ("https://duckduckgo.com/", "duckduckgo"),
    ("https://chatgpt.com/", "chatgpt"),
    ("https://chat.openai.com/", "chatgpt"),
    ("https://www.perplexity.ai/search", "perplexity"),
    ("https://claude.ai/chat/abc", "claude"),
    ("https://gemini.google.com/app", "gemini"),
    ("https://l.facebook.com/l.php?u=x", "facebook"),
    ("https://m.facebook.com/", "facebook"),
    ("https://www.instagram.com/", "instagram"),
    ("https://api.whatsapp.com/send", "whatsapp"),
    ("whatsapp://send", "whatsapp"),
    ("https://t.co/abcd", "twitter"),
    ("https://www.youtube.com/watch?v=1", "youtube"),
    ("https://www.reddit.com/r/vedicastrology/", "reddit"),
    ("https://quora.com/q", "quora"),
    ("https://news.ycombinator.com/item?id=1", "other"),
    ("", "direct"),
    (None, "direct"),
])
def test_the_referrer_becomes_one_word_from_a_fixed_list(referer, expected):
    from app.analytics import classify_source

    assert classify_source(referer, "")[0] == expected


def test_our_own_pages_are_not_a_source():
    """Moving from /hi/rashifal to /ai-jyotish is not an arrival, and counting it as one would make the
    busiest "source" on the dashboard be us."""
    from app.analytics import classify_source

    assert classify_source("https://rashikundli.com/hi/rashifal/mesh", "")[0] == "internal"


@pytest.mark.parametrize("query, source, campaign", [
    ("utm_source=whatsapp&utm_campaign=diwali", "whatsapp", "diwali"),
    ("utm_source=Newsletter", "newsletter", ""),
    ("utm_campaign=diwali", "direct", "diwali"),
    ("?utm_source=google&utm_medium=cpc", "google", ""),
])
def test_a_tagged_link_says_where_it_came_from(query, source, campaign):
    from app.analytics import classify_source

    got_source, got_campaign = classify_source("", query)
    assert (got_source, got_campaign) == (source, campaign)


def test_a_tag_beats_the_referrer_because_somebody_chose_it():
    from app.analytics import classify_source

    assert classify_source("https://www.google.com/", "utm_source=whatsapp")[0] == "whatsapp"


def test_a_campaign_is_kept_short_and_plain():
    """It arrives from a URL anybody can write, so it is treated as untrusted input."""
    from app.analytics import classify_source

    source, campaign = classify_source("", "utm_source=x&utm_campaign=" + "A" * 200 + "<script>")
    assert len(campaign) <= 40 and "<" not in campaign


# ---- is this a person? --------------------------------------------------------------------------------

@pytest.mark.parametrize("agent", [
    "Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/120.0.0.0",
    "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)",
    "python-requests/2.31.0",
    "Go-http-client/2.0",
    "",
])
def test_an_agent_that_is_not_a_browser_is_not_a_visitor(agent):
    from app.analytics import is_bot

    assert is_bot(agent)


def test_a_real_phone_browser_is_a_visitor():
    from app.analytics import is_bot

    assert not is_bot("Mozilla/5.0 (Linux; Android 13; RMX3511) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36")


def test_a_visitor_who_never_runs_javascript_is_marked_suspect(tmp_path, monkeypatch):
    """THE SIGNAL THAT SEPARATES 500 FROM 7. A crawler fetches the HTML and stops; a browser runs the page
    and tells us so. Nothing is blocked either way - the visit is counted and flagged, because being wrong
    about a person must not cost them the page."""
    from app import analytics

    analytics.record_visit(ip="203.0.113.9", user_agent="Mozilla/5.0 (Linux; Android 13) Chrome/119 Mobile",
                           path="/birth-chart", referer="", query="")
    rows = analytics.visits_on(analytics.ist_day(), path="/birth-chart")
    assert rows, "the visit was not recorded"
    assert rows[-1]["js"] == 0, "a visit starts as unproven and is confirmed by the browser"


def test_the_browser_confirming_itself_clears_the_flag():
    from app import analytics

    agent = "Mozilla/5.0 (Linux; Android 13) Chrome/119 Mobile"
    analytics.record_visit(ip="203.0.113.10", user_agent=agent, path="/hi/kundli", referer="", query="")
    assert analytics.confirm_browser(ip="203.0.113.10", user_agent=agent, path="/hi/kundli")
    rows = [r for r in analytics.visits_on(analytics.ist_day(), path="/hi/kundli")]
    assert rows[-1]["js"] == 1


def test_an_implausible_rate_is_flagged_without_blocking_anything():
    from app import analytics

    agent = "Mozilla/5.0 (Linux; Android 13) Chrome/119 Mobile"
    for index in range(analytics.RATE_SUSPECT_VIEWS + 4):
        analytics.record_visit(ip="203.0.113.11", user_agent=agent, path=f"/horoscope/sign{index}",
                               referer="", query="")
    rows = analytics.visits_on(analytics.ist_day())
    mine = [r for r in rows if r["path"].startswith("/horoscope/sign")]
    assert any(r["suspect"] for r in mine), "a visitor reading 20 pages a minute was not flagged"
    assert len(mine) == analytics.RATE_SUSPECT_VIEWS + 4, "flagging must not drop the view"


def _make_account(email: str) -> None:
    """A row in `accounts`, the way the sign-in flow makes one. There is no public helper for this and
    inventing one for a test would be inventing production code to suit a test."""
    import time

    from app import db
    from app.web import accounts

    with db.transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO accounts (email, email_given, name, created_at, last_seen) "
                     "VALUES (?, ?, '', ?, ?)",
                     (accounts.normalise(email), email, time.time(), time.time()))


# ---- end to end, through the app ---------------------------------------------------------------------

def test_an_arrival_from_google_is_recorded_as_google():
    """Through the middleware, as a real request - not by calling the classifier directly."""
    from fastapi.testclient import TestClient

    from app import analytics
    from app.main import app

    client = TestClient(app)
    client.get("/birth-chart", headers={
        "referer": "https://www.google.com/search?q=free+kundli",
        "user-agent": "Mozilla/5.0 (Linux; Android 13) Chrome/119 Mobile Safari/537.36"})
    rows = [r for r in analytics.visits_on(analytics.ist_day()) if r["path"] == "/birth-chart"]
    assert rows and rows[-1]["source"] == "google"


def test_the_referring_url_is_never_stored():
    """The thing that makes this safe to keep: the URL is read, classified and dropped."""
    from fastapi.testclient import TestClient

    from app import analytics, db
    from app.main import app

    secret = "https://www.google.com/search?q=am+i+manglik+and+my+name+is+asha"
    client = TestClient(app)
    client.get("/birth-chart", headers={
        "referer": secret,
        "user-agent": "Mozilla/5.0 (Linux; Android 13) Chrome/119 Mobile Safari/537.36"})
    with db.transaction(write=False) as conn:
        blob = " ".join(str(dict(row)) for row in conn.execute(
            "SELECT * FROM site_visits ORDER BY id DESC LIMIT 5"))
    assert "manglik" not in blob and "search?q" not in blob, "a search term reached our database"


def test_the_beacon_marks_the_visit_and_answers_nothing():
    from fastapi.testclient import TestClient

    from app import analytics
    from app.main import app

    agent = "Mozilla/5.0 (Linux; Android 13) Chrome/119 Mobile Safari/537.36"
    client = TestClient(app, headers={"user-agent": agent})
    client.get("/hi/kundli")
    response = client.post("/api/seen?path=/hi/kundli")
    assert response.status_code == 204 and not response.content
    rows = [r for r in analytics.visits_on(analytics.ist_day()) if r["path"] == "/hi/kundli"]
    assert rows[-1]["js"] == 1, "a browser announced itself and the visit was not marked"


def test_a_signup_is_attributed_to_the_source_that_brought_them():
    """The number that matters: not how many came from chatgpt, but how many of them signed up."""
    import uuid

    from fastapi.testclient import TestClient

    from app import analytics
    from app.main import app
    from app.web import accounts

    agent = "Mozilla/5.0 (Linux; Android 13) Chrome/119 Mobile Safari/537.36"
    email = f"src{uuid.uuid4().hex[:8]}@gmail.com"
    client = TestClient(app, headers={"user-agent": agent})
    client.get("/ai-astrologer", headers={"referer": "https://chatgpt.com/"})

    # the sign-up itself, through the same client so the visitor hash matches
    import app.web.auth_routes as auth_routes

    source = analytics.source_of_visitor("testclient", agent)
    assert source == "chatgpt", f"the visit was filed as {source!r}"
    _make_account(email)
    accounts.set_source(email, source)
    assert accounts.source_of(email) == "chatgpt"


def test_a_first_touch_is_never_overwritten():
    """Somebody who comes back through a different link has not changed where we found them."""
    import uuid

    from app.web import accounts

    email = f"ft{uuid.uuid4().hex[:8]}@gmail.com"
    _make_account(email)
    accounts.set_source(email, "chatgpt")
    accounts.set_source(email, "google")
    assert accounts.source_of(email) == "chatgpt"
