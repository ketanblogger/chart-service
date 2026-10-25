"""The result cards show their working, link to the number's own page, and carry what the reader
typed into the paid report form. Items 8, 9 and 11 of the QA round.
"""
import datetime as dt
import html
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.numerology import core


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _result(client, body="name=Asha+Vernekar&day=29&month=3&year=1988"):
    return client.post("/numerology-calculator", content=body,
                       headers={"content-type": "application/x-www-form-urlencoded"}).text


# ---- item 9: the working -------------------------------------------------------------------------

@pytest.mark.parametrize("total, expected", [
    (29, ["2+9=11", "1+1=2"]),
    (11, ["1+1=2"]),
    (5, []),
    (19, ["1+9=10", "1+0=1"]),
])
def test_the_reduction_is_written_out(total, expected):
    assert core.steps(total) == expected


def test_a_single_digit_needs_no_working():
    """Born on the 5th: there is no sum to show, and inventing one ("5=5") would be noise."""
    assert core.steps(5) == []
    assert core.profile("Asha", dt.date(1988, 3, 5))["mulank_working"] == []


def test_the_bhagyank_chain_starts_from_the_digits_it_adds():
    """Its first step must be the sum ITSELF, or the chain begins at a number nothing on the page
    explains - a reader would see "4+0=4" and have no idea where 40 came from."""
    working = core.profile("Asha", dt.date(1988, 3, 29))["bhagyank_working"]
    assert working[0] == "2+9+0+3+1+9+8+8=40"
    assert working[-1].endswith("=4")


def test_every_working_chain_ends_at_the_number_the_card_shows():
    """THE PROPERTY, not one example. The working is only worth showing if it arrives at the answer,
    and a chain that ends somewhere else is worse than no chain at all."""
    for day in range(1, 32):
        for month in (1, 2, 3, 11, 12):
            try:
                born = dt.date(1991, month, day)
            except ValueError:
                continue
            p = core.profile("Asha", born)
            for key, number in (("mulank", p["mulank"]), ("bhagyank", p["bhagyank"])):
                chain = p[f"{key}_working"]
                if chain:
                    assert chain[-1].endswith(f"={number}"), (born, key, chain)
                else:
                    assert number == born.day, (born, key)


def test_the_page_shows_the_working(client):
    body = _result(client)
    shown = [" ".join(x.split()) for x in
             re.findall(r'class="quiet num-card__working">(.*?)</p>', body, re.S)]
    assert len(shown) == 2, shown
    assert "2+9=11" in shown[0] and "1+1=2" in shown[0]
    assert "2+9+0+3+1+9+8+8=40" in shown[1] and "4+0=4" in shown[1]


def test_each_card_links_to_that_number_page(client):
    """The cards gave a digit and no way to read what it means; the nine pages were reachable only
    from the strip at the bottom."""
    body = _result(client)
    linked = re.findall(r'num-card__value">\s*<a href="(/mulank-\d)"', body)
    assert len(linked) == 3, linked
    assert linked[0] == "/mulank-2" and linked[1] == "/mulank-4"  # mulank 2, bhagyank 4


def test_an_unusable_name_card_has_no_link(client):
    """A name in Devanagari has no Chaldean value, so that card says so instead of showing a 0 -
    and must not link to /mulank-0, which does not exist."""
    body = _result(client, "name=%E0%A4%86%E0%A4%B6%E0%A4%BE&day=29&month=3&year=1988")
    assert "/mulank-0" not in body
    assert len(re.findall(r'num-card__value">\s*<a href="/mulank-\d"', body)) == 2


# ---- item 8: the chips have a label --------------------------------------------------------------

@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_chip_strip_says_what_it_is(client, lang):
    """It was a bare row of nine digits under aria-label="1-9", which tells a screen-reader user the
    range and not the purpose, and told a sighted reader nothing at all."""
    from app.web import i18n

    body = client.get(i18n.url_for("numerology", lang)).text
    assert 'aria-labelledby="mulank-chips-label"' in body
    assert 'id="mulank-chips-label"' in body
    assert 'aria-label="1-9"' not in body


def test_every_chip_names_its_own_destination(client):
    body = client.get("/numerology-calculator").text
    labelled = re.findall(r'<a href="/mulank-(\d)"\s+aria-label="([^"]+)"', body)
    assert len(labelled) == 9, labelled
    for number, label in labelled:
        assert label.endswith(f" {number}"), label
        assert ":" not in label, f"the trailing colon of the visible label leaked into {label!r}"


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_the_label_is_translated(client, lang):
    """The paths come from i18n, not from me: I guessed /hi/ank-jyotish-calculator and got three
    404s, which is the "read the index, do not guess the URL" trap in my own notes."""
    from app.numerology.copy import PAGE
    from app.web import i18n

    label = PAGE[lang]["mulank_chips_label"]
    assert label and label != PAGE["en"]["mulank_chips_label"]
    assert label in client.get(i18n.url_for("numerology", lang)).text


# ---- item 11: the report form is prefilled -------------------------------------------------------

def _report_form(body):
    """The card's form: (action, {field: value}). It was a link with a query string until the
    privacy fix - see tests/test_numerology_report_card.py for why that had to stop."""
    found = re.search(r'<form class="report-card__form"[^>]*action="([^"]+)"(.*?)</form>', body, re.S)
    return (found.group(1), dict(re.findall(r'name="(\w+)" value="([^"]*)"', found.group(2)))) if found else (None, {})


def test_the_report_cta_carries_the_name_and_date(client):
    """Still carried - just not in the URL any more."""
    action, fields = _report_form(_result(client))
    assert action == "/numerology-report" and "?" not in action
    assert fields == {"name": "Asha Vernekar", "day": "29", "month": "3", "year": "1988"}


def test_following_it_lands_on_a_filled_form(client):
    """The whole point of item 11, now reached by POST: nobody types their own name and birthday
    twice to buy a report about themselves."""
    action, fields = _report_form(_result(client))
    body = client.post(action, data=fields,
                       headers={"content-type": "application/x-www-form-urlencoded"}).text
    assert 'value="Asha Vernekar"' in body
    for part in ('<option value="29" selected>', '<option value="3" selected>',
                 '<option value="1988" selected>'):
        assert part in body, part


def test_the_prefilled_form_is_ready_to_buy(client):
    action, fields = _report_form(_result(client))
    body = client.post(action, data=fields,
                       headers={"content-type": "application/x-www-form-urlencoded"}).text
    assert "numerology-report" in body and "btn--cta" in body


def test_a_prefill_never_shows_an_error(client):
    """An error on arrival would be about the link, not about anything the reader did. An old-style
    query string with an impossible date still fills nothing and still says nothing."""
    body = client.get("/numerology-report?name=Asha&day=31&month=2&year=1988").text
    assert 'class="num-error"' not in body
    assert '<option value="31" selected>' not in body
    assert 'value="Asha"' in body, "the name is still worth keeping"


def test_the_mulank_pages_carry_nothing(client):
    """They have no calculator, so there is nothing to carry - and a form with no fields to post is
    just a slower link, so the card renders a plain link there."""
    body = client.get("/mulank-2").text
    assert "report-card__form" not in body
    assert f'href="/numerology-report"' in body


def test_the_bare_report_page_is_unchanged(client):
    body = client.get("/numerology-report").text
    assert 'value=""' in body or 'value="{{' not in body
    assert "selected" not in body, "something is pre-selected with no query string"
