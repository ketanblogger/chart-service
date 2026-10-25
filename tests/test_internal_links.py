"""The rashifal pages' job: sending people to a chart and to the astrologer.

Most of the traffic lands on a rashifal page. Whether any of it goes anywhere was the question the funnel
could not answer - every arrival from our own pages was filed as "internal" and stopped there, so the
busiest section of the site had no measurable effect on anything.

TWO CHANGES. The call to action now names the sign the reader is actually reading about, because "Ask
about your own chart" on a page about Vrishchik is a weaker sentence than "Ask about your own Vrishchik
chart". And a visit records which SECTION of this site sent it - the section, never the page, never the
sign, never the query, which is the same arm's length external sources are kept at.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n

client = TestClient(app)

#: EVERY reading page, from the registry. Three hand-typed paths were checked here at first, which is a
#: claim about 180 pages tested on 3 of them - and hand-typed paths are how 10A's title guard came to skip
#: ten pages in silence. The behaviour was right on all 180 when this was widened; the guard was not.
READING_PAGES = [(path, lang, params["rashi"]) for path, key, lang, params in i18n.all_paths()
                 if key == "rashifal-reading"]


def test_the_population_is_every_reading_page():
    assert len(READING_PAGES) == 180, len(READING_PAGES)


@pytest.mark.parametrize("path, lang, rashi", READING_PAGES)
def test_the_astrologer_cta_names_the_sign_being_read(path, lang, rashi):
    import re

    html = client.get(path).text
    found = re.search(r'id="cta-chat">([^<]*)', html)
    assert found, f"{path} has no astrologer call to action"
    expected = i18n.rashi_names(rashi, lang)["rashi"]
    assert expected in found.group(1), f"{path}: generic CTA - {found.group(1)!r}"


@pytest.mark.parametrize("path, lang, rashi", READING_PAGES)
def test_every_reading_page_offers_both_a_chart_and_the_astrologer(path, lang, rashi):
    from app.web import i18n

    html = client.get(path).text
    chat = any(url in html for url in i18n.PAGES["consultation"].values())
    chart = any(url in html for url in i18n.PAGES["kundali"].values())
    assert chat and chart, f"{path}: chat={chat} chart={chart}"


# ---- what the funnel can now see ---------------------------------------------------------------------

@pytest.mark.parametrize("referer, expected", [
    ("https://rashikundli.com/hi/rashifal/vrishchik/masik", "rashifal"),
    ("https://rashikundli.com/horoscope/scorpio/today", "rashifal"),
    ("https://rashikundli.com/mr/rashi-bhavishya/tula", "rashifal"),
    ("https://rashikundli.com/birth-chart", "kundali"),
    ("https://rashikundli.com/about", ""),
    ("https://www.google.com/search?q=x", ""),
    ("", ""),
])
def test_the_section_that_sent_them_is_recognised(referer, expected):
    from app.analytics import internal_origin

    assert internal_origin(referer, host="rashikundli.com") == expected


def test_only_the_section_is_kept_never_the_page():
    """A reading page's URL carries the sign somebody reads about, which is closer to a person than a
    section is. The same arm's length as the external sources."""
    from app.analytics import internal_origin

    assert internal_origin("https://rashikundli.com/hi/rashifal/vrishchik/masik", host="rashikundli.com") == "rashifal"
    assert "vrishchik" not in internal_origin("https://rashikundli.com/hi/rashifal/vrishchik/masik", host="rashikundli.com")


def test_a_journey_from_a_rashifal_page_to_the_chat_is_counted():
    """End to end, through the middleware, the way a reader actually does it."""
    from app import analytics

    agent = "Mozilla/5.0 (Linux; Android 13) Chrome/119 Mobile Safari/537.36"
    reader = TestClient(app, headers={"user-agent": agent})
    reader.get("/hi/rashifal/vrishchik/masik")
    reader.get("/hi/ai-jyotish", headers={"referer": "http://testserver/hi/rashifal/vrishchik/masik"})

    journeys = analytics.internal_journeys(days=1)
    assert any(row["came_from"] == "rashifal" and row["went_to"] == "chat" and row["people"] >= 1
               for row in journeys), f"the journey was not counted: {journeys}"


def test_a_visit_with_no_referrer_starts_no_journey():
    from app import analytics

    agent = "Mozilla/5.0 (Linux; Android 14) Chrome/120 Mobile Safari/537.36"
    TestClient(app, headers={"user-agent": agent}).get("/birth-chart")
    rows = [r for r in analytics.visits_on(analytics.ist_day()) if r["path"] == "/birth-chart"]
    assert rows and rows[-1]["via"] == ""


def test_a_staging_host_is_still_our_own_site():
    """"Internal" means the same host as the request, not a list of names. A hardcoded list files our own
    links as a stranger's everywhere the site is not on its production domain - which is every test, every
    preview and every staging box."""
    from app.analytics import internal_origin

    assert internal_origin("https://staging.example.net/horoscope/scorpio",
                           host="staging.example.net") == "rashifal"
    assert internal_origin("https://someone-else.example/horoscope/scorpio",
                           host="staging.example.net") == ""
