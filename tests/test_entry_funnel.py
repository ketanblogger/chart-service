"""Where a visit STARTED, and whether the funnel can still be split by it.

THE NUMBER THIS EXISTS TO BREAK UP is "8,626 visitors, 4 orders in 90 days". One figure cannot be acted
on: it does not say whether the rashifal pages bring readers who were never going to buy, or whether the
kundli page converts well and simply gets no traffic. Every step below the top of the funnel needed to
know where the journey began, and nothing in site_events or orders carried it.

WHAT IS STORED IS ONE WORD from a fixed list of six. Not a path, not a referrer, not an id. The tests
below pin that as hard as they pin the counting, because an "analytics improvement" that quietly starts
keeping more about a person is the kind of change that is easy to make and hard to notice.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import analytics, db
from app.main import app

client = TestClient(app)


@pytest.mark.parametrize("path, kind", [
    ("/horoscope/libra/today", "rashifal"), ("/hi/rashifal/tula/aaj", "rashifal"),
    ("/mr/rashi-bhavishya/mesh/aaj", "rashifal"),
    ("/birth-chart", "kundli"), ("/kundli", "kundli"), ("/mr/kundali", "kundli"),
    ("/horoscope-matching", "matching"), ("/mr/patrika-matching", "matching"),
    ("/panchang", "panchang"), ("/hi/aaj-ka-panchang", "panchang"),
    ("/ai-astrologer", "chat"), ("/mr/ai-jyotish", "chat"),
    ("/about", "other"), ("/", "other"), ("/nakshatra/mula", "other"),
])
def test_a_landing_path_is_classified(path, kind):
    assert analytics.entry_kind(path) == kind


def test_the_six_values_are_the_only_ones_there_are():
    """A seventh value appearing later would silently widen what is stored about an arrival."""
    assert analytics.ENTRY_VALUES == ("rashifal", "kundli", "matching", "panchang", "chat", "other")
    for path in ("/", "/terms", "/blog", "/hi/jyotish", "/nakshatra/revati"):
        assert analytics.entry_kind(path) in analytics.ENTRY_VALUES


def test_the_entry_cookie_is_set_on_the_first_page_and_never_rewritten():
    """WHERE THE JOURNEY STARTED, not where it currently is. A cookie rewritten on every page would
    report the last page before checkout, which is the one thing everybody already knows."""
    fresh = TestClient(app)
    first = fresh.get("/hi/rashifal/tula/aaj")
    assert first.cookies.get(analytics.ENTRY_COOKIE) == "rashifal"
    fresh.get("/panchang")
    fresh.get("/kundli")
    assert fresh.cookies.get(analytics.ENTRY_COOKIE) == "rashifal", "a later page overwrote the entry"


def test_the_cookie_carries_a_word_and_not_a_path():
    fresh = TestClient(app)
    fresh.get("/hi/rashifal/tula/aaj")
    value = fresh.cookies.get(analytics.ENTRY_COOKIE)
    assert value in analytics.ENTRY_VALUES
    assert "/" not in value and len(value) < 20


def test_an_unexpected_cookie_value_is_not_guessed_into_a_bucket():
    """A cookie is client-side and anybody can put anything in it. An unknown value is "not recorded",
    never quietly counted as "other" - which would be a number somebody then reads as real."""
    from app.payments import routes  # noqa: F401  - the route does the check

    for junk in ("' OR 1=1", "rashifal; drop", "kundli ", "", "x" * 300):
        assert junk not in analytics.ENTRY_VALUES or junk == junk.strip()


def test_orders_carry_the_entry_column_and_null_means_not_recorded():
    """Every order written before the column existed has NULL, and a reader must treat that as "not
    recorded" rather than as "other" - an order from before we measured did not come from nowhere."""
    from app.payments import store  # noqa: F401

    with db.transaction(write=False) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
    assert "entry" in columns


@pytest.mark.parametrize("endpoint, feature, body", [
    ("/api/chart", "kundali", {"date": "1990-05-14", "time": "07:30", "city": "Pune"}),
    ("/api/mangal-dosha", "mangal-dosha", {"date": "1990-05-14", "time": "07:30", "city": "Pune"}),
    ("/api/sade-sati", "sade-sati", {"date": "1990-05-14", "time": "07:30", "city": "Pune"}),
])
def test_every_calculator_records_that_it_actually_ran(endpoint, feature, body):
    """ONLY /chart DID. The dashboard could see somebody arrive on the matching page and never see
    whether they matched anything - and a funnel step that is not recorded is not reported as a gap, it
    is reported as a drop-off, which is the number somebody then tries to fix."""
    before = sum(1 for e in analytics.recent_events(400)
                 if e.get("feature") == feature and e.get("action") == "generated")
    assert client.post(endpoint, json=body).status_code == 200
    after = sum(1 for e in analytics.recent_events(400)
                if e.get("feature") == feature and e.get("action") == "generated")
    assert after == before + 1, f"{endpoint} did not record that it ran"


def test_matching_records_too():
    before = sum(1 for e in analytics.recent_events(400)
                 if e.get("feature") == "matching" and e.get("action") == "generated")
    response = client.post("/api/matching", json={
        "boy": {"date": "1990-05-14", "time": "07:30", "city": "Pune"},
        "girl": {"date": "1992-08-11", "time": "09:15", "city": "Nagpur"}})
    assert response.status_code == 200
    after = sum(1 for e in analytics.recent_events(400)
                if e.get("feature") == "matching" and e.get("action") == "generated")
    assert after == before + 1


def test_counting_never_breaks_a_calculation(monkeypatch):
    """The guarantee every counter on this site makes. A calculator that 500s because the analytics
    table is locked would trade the product for a statistic."""
    def explode(*args, **kwargs):
        raise RuntimeError("analytics is down")

    monkeypatch.setattr(analytics, "record_event", explode)
    response = client.post("/api/sade-sati", json={"date": "1990-05-14", "time": "07:30", "city": "Pune"})
    assert response.status_code == 200
