"""/ai-astrologer: what it is, questions to copy, what the two tiers cost, and what it will not do.

WHAT WAS ALREADY THERE: four sections and eight FAQs, 751 words, with the prices as placeholders filled
from the catalogue rather than typed in - so the page could not drift from what is charged.

WHAT WAS MISSING. The page listed TOPICS - "career and work", "timing" - and a first-time visitor still
had to invent a sentence; "what should I ask an astrologer" is itself a query. And the two tiers were two
sentences that each restated what they share, where what a reader wants is the one row that differs. The
title was 73 characters and the meta 187, so both were cut off in the result for the page's own query.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n, pages

client = TestClient(app)
PATH = i18n.url_for("consultation", "en")


def test_the_title_and_meta_fit_in_a_search_result():
    copy = pages.get("consultation", "en")
    assert len(copy.title) <= 60, f"{len(copy.title)}: {copy.title}"
    assert len(copy.meta_description) <= 160, len(copy.meta_description)


def test_the_title_still_carries_the_phrase_the_page_exists_to_win():
    """Shortening a title is only a gain if the query survives it. The 10E matching title lost
    "horoscope matching" the first time it was cut, which is the mistake this guards against here."""
    assert re.search(r"ai astrolog", pages.get("consultation", "en").title, re.I)


def test_there_are_questions_a_visitor_can_copy():
    """Not topics. A visitor who does not know what to ask gets sentences, and a sentence naming a part of
    life and a stretch of time gets a far better answer than "what does my future hold"."""
    html = client.get(PATH).text
    questions = [q for q in re.findall(r"<li>([^<]*)</li>", html) if q.strip().endswith("?")]
    assert len(questions) >= 8, f"only {len(questions)} example questions: {questions}"
    assert any("career" in q.lower() for q in questions)
    assert any("marriage" in q.lower() or "partner" in q.lower() for q in questions)
    assert any("dasha" in q.lower() for q in questions)


def test_the_example_questions_are_about_a_chart_and_not_about_fortune_telling():
    """The page's own section says what it will not do. The examples must not invite the thing it
    refuses, or the two halves of the page contradict each other."""
    html = client.get(PATH).text
    questions = [q.lower() for q in re.findall(r"<li>([^<]*\?)</li>", html)]
    # `not any(... for ... in [])` is True, so without this line the safety check went green the moment
    # the questions stopped rendering - which is exactly when it would matter.
    assert len(questions) >= 8, f"nothing to check: {len(questions)} questions found"
    for banned in ("when will i die", "will i die", "cancer", "accident", "lottery"):
        assert not any(banned in q for q in questions), banned


def test_the_two_tiers_are_a_table_that_shows_what_differs():
    html = client.get(PATH).text
    table = re.search(r'<table class="copy-table">(.*?)</table>', html, re.S)
    assert table, "no price table"
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(1), re.S)
    assert len(rows) >= 4, len(rows)
    headers = re.findall(r"<th>([^<]*)</th>", rows[0])
    assert sum(1 for h in headers if "₹" in h) == 2, headers


def test_the_prices_on_the_page_are_the_prices_in_the_catalogue():
    """The one thing on this page that must never be typed in. A page that advertises a price the
    checkout does not charge is the worst defect available to it."""
    html = client.get(PATH).text
    offers = pages.purchase_offers("consultation", pages.get("consultation", "en"))
    table = re.search(r'<table class="copy-table">(.*?)</table>', html, re.S).group(1)
    shown = {int(n) for n in re.findall(r"₹(\d+)", table)}
    assert shown == {offer["price_inr"] for offer in offers}, (shown, offers)


def test_no_price_is_hard_coded_in_the_copy_source():
    """The placeholders are what keep the page honest when a price moves."""
    raw = pages.raw("consultation", "en")
    source = " ".join(text for section in raw.sections for block in section.blocks
                      for text in pages.block_strings(block))
    for price in ("119", "349", "49"):
        assert f"₹{price}" not in source, f"₹{price} typed into the copy"


def test_what_it_will_not_do_is_still_on_the_page():
    """Added sections must not push the refusal off the page: it is the reason the rest can be trusted."""
    html = client.get(PATH).text
    assert "never predicts death" in html
    assert "qualified professional" in html


@pytest.mark.parametrize("phrase", ["Swiss Ephemeris", "Lahiri"])
def test_it_says_what_computes_the_chart(phrase):
    assert phrase in client.get(PATH).text, phrase


def test_the_body_is_deep_enough_to_rank_for_its_own_query():
    """751 words before, against competitors with pages of it. The count is the floor, not the goal."""
    copy = pages.get("consultation", "en")
    words = sum(len(text.split()) for section in copy.sections for block in section.blocks
                for text in pages.block_strings(block))
    words += sum(len((q + " " + a).split()) for q, a in copy.faqs)
    assert words >= 900, words
