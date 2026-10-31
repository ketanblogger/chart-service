"""/order/{token} is rendered in the ORDER's language (words: app/payments/order_page.py, platform) inside the matching
language tree's layout. The payment flow itself is tested in tests/test_payments.py; here the route + template."""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.payments import order_page as order_text
from app.payments import service, store
from app.web import i18n
from tests.test_web import _Page

client = TestClient(app)
TOKEN = "T" * 32


def _serve(monkeypatch, lang: str, kind: str, fulfilment: str):
    order = {"status": "paid", "language": lang, "paid_at": 1790000000, "product": "consultation-pack" if kind == "pack" else "kundali-report",
             "kind": kind, "report_id": "r1", "token": TOKEN}
    view = {"kind": kind, "fulfilment": fulfilment, "retrying": False, "messages": 10 if kind == "pack" else 0,
            "includes_report": True, "order_id": "order_Web0000001", "amount_inr": 99.0 if kind == "pack" else 49.0,
            "product_name": "fallback name", "pdf_url": "/api/report/r1/pdf?token=x" if fulfilment == "ready" else None}
    monkeypatch.setattr(store, "by_token", lambda token: order if token == TOKEN else None)
    monkeypatch.setattr(service, "status", lambda found, reveal_token=False: view)
    response = client.get(f"/order/{TOKEN}")
    assert response.status_code == 200
    return response, order_text.context(order, view)


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("kind, fulfilment", [("report", "ready"), ("report", "generating"), ("pack", "ready"), ("pack", "failed")])
def test_order_page_speaks_the_orders_language(monkeypatch, lang, kind, fulfilment):
    response, expected = _serve(monkeypatch, lang, kind, fulfilment)
    html, page = response.text, _Page(response.text)
    labels = expected["labels"]

    assert f'<html lang="{lang}">' in html and response.headers["content-language"] == lang
    assert page.title.startswith(labels["title"]) and page.h1 == [labels["heading"]]
    assert page.meta["description"] == labels["description"]
    for text in (labels["purchase"], labels["amount"], labels["paid_on"], labels["reference"].strip(), labels["keep"],
                 expected["product_name"], expected["paid_on"], expected["info"]["title"], expected["info"]["text"]):
        assert text in html or text.replace("'", "&#39;") in html, text
    assert "fallback name" not in html and ("₹99" if kind == "pack" else "₹49") in html
    if lang != "en":
        body = re.sub(r"<[^>]+>", " ", html.split("<main", 1)[1].split("</main>", 1)[0])
        for english in ("Your order", "Purchase", "Paid on", "Order reference", "Download your PDF", "Bookmark"):
            assert english not in body, english

    # never indexable, never cached, no referrer - and outside the registry: no hreflang
    assert "noindex" in page.meta["robots"] and response.headers["x-robots-tag"] == "noindex, nofollow"
    assert response.headers["cache-control"] == "private, no-store" and response.headers["referrer-policy"] == "no-referrer"
    assert 'rel="alternate"' not in html

    # hooks of pay.js / scripts/browser_check_payments.py
    status = page.ids["order-status"]
    assert status["data-order-id"] == "order_Web0000001" and status["data-order-token"] == TOKEN
    assert status["data-state"] == expected["info"]["state"] and status["data-poll"] == ("0" if expected["info"]["done"] else "1")
    assert f'pay-status--{expected["info"]["state"]}' in status["class"]
    assert ('class="btn btn--cta pay-status__download"' in html) == (fulfilment == "ready")
    if fulfilment == "ready":
        assert f">{labels['download']}</a>" in html
    assert any(src.startswith("/static/js/pay.js") for src in page.scripts) and "data-pay" in html

    # a consultation purchase leads back to the consultation in the order's language; header / footer follow it too
    target = f'href="{i18n.url_for("consultation", lang)}">{labels["continue"]}</a>'
    assert (target in html) == (kind == "pack")
    assert f'href="{i18n.url_for("kundali", lang)}"' in html and f'class="brand" href="{i18n.url_for("home", lang)}"' in html


def test_bundle_first_paint_mentions_the_questions_and_the_pdf(monkeypatch):
    response, expected = _serve(monkeypatch, "en", "pack", "generating")
    assert expected["info"]["state"] == "preparing" and "10 questions added" in response.text and "Kundali PDF" in response.text


def test_unknown_order_language_falls_back_to_english_and_bad_tokens_are_404(monkeypatch):
    response, _ = _serve(monkeypatch, "fr", "report", "ready")
    assert '<html lang="en">' in response.text and "Your report is ready" in response.text
    assert client.get("/order/" + "A" * 32).status_code == 404 and client.get("/order/short").status_code == 404
