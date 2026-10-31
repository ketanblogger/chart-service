"""Checkout asks a signed-in customer for less, and never puts their address in a page.

WHAT WAS ASKED FOR: e-mail, the e-mail again, phone, state, and the report language. Five fields, of
which two were the same address typed twice.

THE CONFIRM FIELD IS NOT SUPERSTITION - a typo sends a paid report to a stranger, and there is no way
back from that. But it is only a risk for an address typed INTO this form. The address somebody signed
in with had a code sent to it which they read; it is already proved. So when the server knows it, it is
filled in and the second field goes away.

AND IT IS FETCHED, NOT RENDERED. Tool pages carry no Cache-Control of their own, so an address printed
into one could be held by a shared cache and handed to the next person through it. The account chrome
has always shown only the part before the @ for the same reason.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import accounts, site

PAY_JS = Path("app/static/js/pay.js").read_text(encoding="utf-8")
ADDRESS = "buyer@example.com"


@pytest.fixture()
def signed_in():
    client = TestClient(app)
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(ADDRESS))
    return client


def test_the_endpoint_answers_only_the_cookie_that_asked(signed_in):
    assert signed_in.get("/api/account/email").json() == {"email": ADDRESS}
    assert TestClient(app).get("/api/account/email").json() == {"email": None}


def test_the_address_is_never_cached_by_anything_in_between(signed_in):
    """A shared cache holding this answer would hand one person's address to the next."""
    response = signed_in.get("/api/account/email")
    assert response.headers["cache-control"] == "private, no-store"


def test_a_signed_out_visitor_is_not_an_error():
    """Checkout works without an account and must keep working: the panel asks for the address, as it
    always did. A 401 here would turn a signed-out purchase into a broken one."""
    response = TestClient(app).get("/api/account/email")
    assert response.status_code == 200 and response.json()["email"] is None


@pytest.mark.parametrize("path", ["/birth-chart", "/kundli", "/hi/kundli", "/mr/kundali", "/kundli-pdf"])
def test_a_page_carrying_an_address_is_never_cacheable_by_anything_shared(signed_in, path):
    """FOUND WHILE JUSTIFYING THE ENDPOINT, and it was already true of every page on the site.

    The account menu shows the part before the @ and puts the WHOLE address in the title attribute, so
    it can be read on hover. Those pages were served with no Cache-Control at all and a Vary of
    "Accept-Encoding" - which does not mention Cookie, so a CDN or a corporate proxy had no reason to
    tell two readers apart, and one person's address could be stored and handed to the next.

    So the rule is not "no page may carry an address" - one already does, deliberately - it is that a
    page which carries one may never be held by a shared cache."""
    response = signed_in.get(path)
    if ADDRESS not in response.text:
        return
    assert response.headers.get("cache-control") == "private, no-store", path
    assert "Cookie" in response.headers.get("vary", ""), f"{path} does not vary on the cookie"


@pytest.mark.parametrize("path", ["/birth-chart", "/kundli-pdf", "/"])
def test_a_signed_out_page_is_as_cacheable_as_it_ever_was(path):
    """The fix must not make the whole site uncacheable for the visitors who are not signed in - which
    is most of them, and the ones whose page speed the rest of this batch has been measuring."""
    response = TestClient(app).get(path)
    assert ADDRESS not in response.text
    assert response.headers.get("cache-control") in (None, "", "public, max-age=86400")


def test_the_panel_fills_the_address_and_drops_the_second_field():
    block = PAY_JS[PAY_JS.index('fetch("/api/account/email"'):]
    block = block[:block.index(".catch(")]
    assert "email.value = known" in block
    assert "confirmRow" in block and "hidden = true" in block


def test_a_filled_address_is_never_overwritten():
    """Somebody who typed an address before the answer arrived must keep it - the request is slower than
    a fast typist, and silently replacing what they entered would send the report elsewhere."""
    block = PAY_JS[PAY_JS.index('fetch("/api/account/email"'):]
    block = block[:block.index(".catch(")]
    assert "if (!known || email.value) return;" in block


def test_the_customer_can_still_use_another_address():
    """A report bought as a gift, or an account signed in on someone else's phone. The link brings both
    fields back exactly as they were, including the confirm."""
    block = PAY_JS[PAY_JS.index('fetch("/api/account/email"'):]
    block = block[:block.index(".catch(")]
    assert 'email.value = ""' in block and 'emailConfirm.value = ""' in block
    assert "hidden = false" in block


def test_a_failed_lookup_costs_nothing():
    """Offline, signed out, or refused: the panel was built before the request and is already correct."""
    assert ".catch(function () {" in PAY_JS[PAY_JS.index('fetch("/api/account/email"'):]


def test_every_language_says_where_the_report_is_going():
    """All three trees, and each must NAME the address - "sending to your e-mail" tells somebody buying
    on a shared phone nothing about which account they are signed into.

    Counted rather than sliced per language: the three tables are indented differently in this file and
    a slice that assumed otherwise failed on Hindi while the copy was sitting there correctly."""
    known = re.findall(r'emailKnown: "([^"]*)"', PAY_JS)
    change = re.findall(r'emailChange: "([^"]*)"', PAY_JS)
    assert len(known) == 3, f"prefill copy in {len(known)} languages, expected 3"
    assert len(change) == 3
    for text in known:
        assert "{email}" in text, f"this language does not name the address: {text}"
    assert len(set(known)) == 3 and len(set(change)) == 3, "two languages share a string"
