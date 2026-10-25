"""WhatsApp share: what the link carries, and the one thing it must never carry.

A WHATSAPP MESSAGE IS FORWARDED ONWARD by people who never saw the original. So a birth detail in a
share URL does not stay between two people - it ends up in strangers' chat history, attached to a name.

That is the whole rule, and it divides the two buttons. A rashifal page is the same page for everybody
born under that sign, so its own link is safe to send. A kundli RESULT is one person's chart, computed
from their date, time and place - so the button there shares the TOOL, not the result.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import sharing

client = TestClient(app)

#: Anything that would identify a birth. Checked against the whole decoded share URL.
BIRTH_SHAPED = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),            # a date
    re.compile(r"\b\d{1,2}:\d{2}\b"),                # a time
    re.compile(r"[?&](date|time|tob|dob|lat|lon|city|place|name)="),
)


def share_urls(html: str) -> list[str]:
    """What the page would share, assembled the way analytics.js assembles it at the tap.

    THE PAGE ITSELF CARRIES NO wa.me URL - four guards in this repository forbid a third-party URL in
    markup, and the first version of this feature broke all four. The data attributes are what the
    page holds; this builds the link from them so the test still checks the thing that reaches
    WhatsApp."""
    out = []
    for text, url in re.findall(r'data-share-text="([^"]*)"\s+data-share-url="([^"]*)"', html):
        out.append(unquote(sharing.whatsapp_url(html_unescape(text), html_unescape(url))))
    return out


def html_unescape(value: str) -> str:
    import html as html_module

    return html_module.unescape(value)


@pytest.mark.parametrize("path", [
    "/hi/rashifal/tula/aaj", "/mr/rashi-bhavishya/mesh/aaj", "/horoscope/libra/today",
    "/birth-chart", "/kundli", "/hi/kundli", "/mr/kundali",
])
def test_no_share_link_carries_anything_about_a_birth(path):
    """THE RULE, checked on the rendered page rather than on the helper - a template could always add
    a parameter the helper never saw."""
    for url in share_urls(client.get(path).text):
        for pattern in BIRTH_SHAPED:
            assert not pattern.search(url), f"{path}: {pattern.pattern} appears in {url}"


def test_the_kundli_page_offers_a_share():
    html = client.get("/birth-chart").text
    assert 'data-share="kundli"' in html
    assert share_urls(html), "the kundli page has no WhatsApp link"


def test_no_page_contains_a_third_party_url():
    """THE REASON THE LINK IS BUILT AT THE TAP. Four separate guards here forbid a third-party URL in
    markup - this feature broke all four, and needing the same exception four times was the design
    being wrong rather than the guards being fussy."""
    for path in ("/birth-chart", "/kundli", "/hi/rashifal/tula/aaj"):
        assert "wa.me" not in client.get(path).text, f"{path} renders a wa.me URL"


def test_the_button_is_revealed_by_script_and_absent_without_it():
    """The honest no-JavaScript path: no button at all, rather than one that cannot open anything."""
    html = client.get("/birth-chart").text
    button = re.search(r"<button[^>]*data-share=\"kundli\"[^>]*>", html)
    assert button and " hidden" in button.group(0)
    script = Path("app/static/js/analytics.js").read_text(encoding="utf-8")
    assert "hidden = false" in script


def test_the_rashifal_share_appears_only_where_there_is_a_reading():
    """A page whose reading has not been generated has nothing worth forwarding, and a share link to an
    empty page is worse than no share link. The block sits inside the reading's own condition, which is
    why it is absent on a tree with no readings in it."""
    body = Path("app/web/templates/_rashifal_reading_body.html").read_text(encoding="utf-8")
    opens = body.index("{% if reading %}")
    assert opens < body.index('data-share="rashifal"'), "the share is outside the reading block"


def test_the_rashifal_share_renders_when_a_reading_exists():
    made = sharing.share("/hi/rashifal/tula/aaj", "rashifal", "hi", title="तुला राशिफल")
    assert made and "/hi/rashifal/tula/aaj" in made["url"]
    assert sharing.whatsapp_url(made["text"], made["url"]).startswith("https://wa.me/?text=")


def test_the_kundli_button_shares_the_tool_and_not_a_result():
    """A result cannot be shared without sharing the birth that produced it."""
    urls = share_urls(client.get("/birth-chart").text)
    assert urls and "/birth-chart" in urls[0]
    assert "Swiss Ephemeris" in urls[0], "the shared sentence is not about the tool"


def test_every_share_link_is_tagged_so_arrivals_can_be_counted():
    rendered = share_urls(client.get("/birth-chart").text)
    made = sharing.share("/hi/rashifal/tula/aaj", "rashifal", "hi", title="T")
    built = [unquote(sharing.whatsapp_url(made["text"], made["url"]))]
    for url in rendered + built:
        inner = url.split("\n")[-1]
        query = parse_qs(urlparse(inner).query)
        assert query.get("utm_source") == ["whatsapp"]
        assert query.get("utm_content"), "nothing says which page it was shared from"


def test_the_tag_is_read_back_as_a_source():
    """The other half: an arrival through one of these links is counted as whatsapp, by the classifier
    that already exists. Otherwise the tag would be decoration."""
    from app import analytics

    source, campaign = analytics.classify_source(None, "utm_source=whatsapp&utm_content=rashifal")
    assert source == "whatsapp"


def test_a_tap_is_counted_and_only_a_known_source_is_stored():
    """`source` becomes a row in the events table, so a crafted URL must not be able to put a string of
    its own choosing in it."""
    from app import analytics

    before = len([e for e in analytics.recent_events(200) if e.get("feature") == "share"])
    assert client.post("/api/share?source=rashifal").status_code == 204
    assert client.post("/api/share?source=something-else").status_code == 204
    after = [e for e in analytics.recent_events(200) if e.get("feature") == "share"]
    assert len(after) == before + 1, "an unknown source was stored, or a known one was not"
    assert after[0]["detail"] in sharing.SOURCES


def test_counting_never_costs_the_reader_the_share():
    """Every path through the endpoint answers 204 - a counter is not a reason to fail a request."""
    assert client.post("/api/share").status_code == 204
    assert client.post("/api/share?source=" + "x" * 40).status_code in (204, 422)


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_language_has_its_own_words(lang):
    made = sharing.share("/x", "rashifal", lang, title="T")
    assert made and made["label"].strip()
    if lang != "en":
        assert made["label"] != sharing.share("/x", "rashifal", "en", title="T")["label"]


def test_an_unknown_source_builds_no_link_at_all():
    assert sharing.share("/x", "facebook", "en") is None
