"""The one-tap rating on the order page, and the line it must not cross.

THE SHAPE OF THE PROBLEM: three paid orders exist. A written-review form would collect nothing for
months, and a page showing "no reviews yet" sells worse than a page showing nothing. One tap, on the page
somebody is already on, the moment after they downloaded what they bought, is the only version of this
that gets answered at that volume.

WHAT IT MUST NEVER DO is turn three orders into social proof. The public threshold is five real ratings
and the public display does not exist yet - the admin can see them, and that is all. These tests pin the
gate, because "we have a 5-star average" from one rating is the kind of claim that is easy to ship and
impossible to take back.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.payments import ratings, service, store

# The payment fixtures live in tests/test_payments.py and are imported rather than rebuilt: a paid order
# here must be paid the way the site pays for one, through the same stubbed Razorpay and the same verify
# call, or this file would be testing a row it wrote itself.
from tests.test_payments import (  # noqa: E402
    cache_fixture_report, jobs, report_order, rzp, verify_body)

__all__ = ["jobs", "rzp"]  # imported for pytest to find them as fixtures, not used directly


@pytest.fixture()
def delivered(rzp, jobs):
    """A real paid order, through the real payment path - not a row written straight into the table."""
    client = TestClient(app)
    cache_fixture_report()
    created = report_order(client)
    paid = client.post("/api/payments/verify", json=verify_body(created["order_id"]))
    assert paid.status_code == 200, paid.text
    order = store.by_razorpay_id(created["order_id"])
    return client, order


def test_a_delivered_order_can_be_rated_once_and_corrected(delivered):
    client, order = delivered
    token = order["token"]
    assert client.post("/api/payments/order/rating", json={"token": token, "score": 5}).status_code == 200
    assert ratings.for_order(order["id"])["score"] == 5
    # corrected while the page is open, not appended: one answer per order
    assert client.post("/api/payments/order/rating", json={"token": token, "score": 3}).status_code == 200
    assert ratings.for_order(order["id"])["score"] == 3
    assert ratings.summary()["counts"][5] == 0


def test_an_unknown_token_is_refused_the_same_way_a_wrong_one_is(delivered):
    """Otherwise the endpoint answers "does this token exist", which is exactly what a token must not say."""
    client, _ = delivered
    response = client.post("/api/payments/order/rating", json={"token": "z" * 40, "score": 5})
    assert response.status_code == 404


def test_an_unpaid_order_cannot_be_rated(rzp):
    """A rating on an undelivered order is an opinion about a document nobody has - and it would move the
    one figure here that is meant to say something about the product."""
    client = TestClient(app)
    cache_fixture_report()
    created = report_order(client)
    order = store.by_razorpay_id(created["order_id"])
    assert order["status"] != "paid"
    assert client.post("/api/payments/order/rating", json={"token": order["token"], "score": 5}).status_code == 404
    assert ratings.for_order(order["id"]) is None


@pytest.mark.parametrize("score", [0, 6, -1, 99])
def test_a_score_off_the_scale_is_refused(delivered, score):
    client, order = delivered
    assert client.post("/api/payments/order/rating", json={"token": order["token"], "score": score}).status_code == 422


def test_nothing_is_public_below_the_threshold():
    """THE GATE. Five real ratings before anything is shown, whatever the average is."""
    assert ratings.PUBLIC_THRESHOLD == 5
    for n in range(1, ratings.PUBLIC_THRESHOLD):
        ratings.record(f"gate-order-{n}", 5)
        assert ratings.summary()["public"] is False, f"{n} rating(s) declared public"
    ratings.record(f"gate-order-{ratings.PUBLIC_THRESHOLD}", 5)
    assert ratings.summary()["public"] is True


@pytest.mark.parametrize("fulfilment, rated", [("ready", True), ("pending", False), ("failed", False)])
def test_the_widget_appears_exactly_where_the_download_does(monkeypatch, fulfilment, rated):
    """ONLY WHERE THERE IS SOMETHING TO RATE. The rating hangs off the same `view.pdf_url` as the
    download, so it cannot appear beside a payment that is still being processed - a rating on an
    undelivered order is an opinion about a document nobody has.

    Driven the way tests/test_order_page_web.py drives this page, because the delivered-order fixture
    goes through Razorpay and does not by itself produce a ready fulfilment."""
    from app.payments import store as payments_store

    token = "T" * 32
    order = {"id": "order_Rate000001", "status": "paid", "language": "en", "amount_paise": 4900,
             "created_at": 0, "paid_at": 0, "product": "kundali-report-simple", "kind": "report",
             "report_id": "r1", "token": token}
    view = {"kind": "report", "fulfilment": fulfilment, "retrying": False, "messages": 0,
            "order_id": "order_Rate000001", "status": "paid", "product_name": "report",
            "includes_report": True, "amount_inr": 49.0,
            "pdf_url": "/api/report/r1/pdf?token=x" if fulfilment == "ready" else None}
    monkeypatch.setattr(payments_store, "by_token", lambda t: order if t == token else None)
    monkeypatch.setattr(service, "status", lambda found, reveal_token=False: view)

    html = TestClient(app).get(f"/order/{token}").text
    assert ('id="rating"' in html) is rated, f"{fulfilment}: rating block present={not rated}"
    assert ('pay-status__download' in html) is rated, "the download and the rating disagree"


def test_the_rating_collects_no_free_text():
    """A comment box is somewhere for a customer to type their name, their birth details or their phone
    number. The simplest way not to hold any of those is to have nowhere to put them."""
    body = Path("app/web/templates/_order_body.html").read_text(encoding="utf-8")
    block = body[body.index('id="rating"'):]
    block = block[:block.index("</div>", block.index("rating__scores"))]
    assert "<textarea" not in block and 'type="text"' not in block

    columns = {"order_id", "score", "language", "rated_at"}
    source = Path("app/payments/ratings.py").read_text(encoding="utf-8")
    created = source[source.index("CREATE TABLE"):source.index(")\n\"\"\"")]
    found = set(re.findall(r"^\s{4}(\w+)\s", created, flags=re.M))
    assert found == columns, f"the ratings table holds {found - columns} beyond a score"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_language_has_the_rating_copy(lang):
    from app.payments import order_page

    for key in ("rate_prompt", "rate_thanks", "rate_failed", "rate_aria"):
        assert order_page.LABELS[lang][key].strip(), f"{lang} is missing {key}"


def test_no_script_reads_the_dom_at_the_top_level():
    """THE FAILURE THAT HAPPENED TWICE IN ONE BATCH. render.js and pay.js are both evaluated by
    py_mini_racer - a bare JS VM with no `document` - to check their text tables against the server's. A
    top-level DOM read fails the whole file, and every test that evaluates it then reports a
    JSEvalException about something unrelated. 50 tests went red the first time."""
    for name in ("pay.js", "render.js"):
        source = Path("app/static/js") / name
        text = source.read_text(encoding="utf-8")
        assert 'typeof document === "undefined"' in text, f"{name} has no DOM-less guard"
