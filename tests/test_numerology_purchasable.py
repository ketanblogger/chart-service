"""The Rs 199 numerology report can actually be bought.

FIVE INDEPENDENT FAULTS stood between the button and an order, and any ONE of them was enough to
stop the sale. The product has been listed, priced and linked from every numerology page, and it
has never been purchasable. A browser check found them one at a time, each hidden behind the last:

  1. app.js registered its [data-product] click hook INSIDE the tool-page closure, which returns
     early when there is no #tool-form. The report page has none, so clicking the button dispatched
     nothing at all.
  2. the report page's pay.js tag carried neither data-pay nor data-enabled, so pay.js never
     registered its purchase handler either.
  3. pay.js opened its panel only for a detail carrying a `request`; a numerology order has none,
     by design, because it is not about a chart.
  4. the page omitted #pay-state-options, so the REQUIRED "State (for GST)" select held nothing but
     its placeholder and the panel could never be submitted.
  5. OrderRequest.births() dereferenced self.birth unconditionally - on the one product whose
     validator REFUSES a birth - so the request raised AttributeError and returned 500.

And behind all five, a sixth that no browser could have shown: report_id had nothing about the
person in it for a product with no birth details, so two buyers in one language on one day shared
an id - the second matching the first as "already paid", and the cache serving them a stranger's
reading.
"""
import datetime as dt
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = ROOT / "app/static/js"
TEMPLATES = ROOT / "app/web/templates"


# ---- 1. the payment hook is not trapped behind the tool form -------------------------------------

def test_the_payment_hook_is_outside_the_tool_form_closure():
    """It must be registered on every page that has a [data-product] button, not only on the tool
    pages. The marker is that the hook appears AFTER the tool-page closure has ended."""
    source = (JS / "app.js").read_text(encoding="utf-8")
    guard = source.index('var form = document.getElementById("tool-form");')
    early_return = source.index("if (!R || !form) return;", guard)
    hook = source.index('closest("[data-product]")')
    assert hook > early_return, "the payment hook is inside the closure that returns without a tool form"
    # and it must not assume a form exists
    tail = source[source.index("THE PAID PRODUCT HOOK"):]
    assert "form ? form.getAttribute" in tail and "form ? form._astroLast" in tail


def test_there_is_exactly_one_payment_hook():
    """Two copies of this would drift; one of them would be the one not fixed."""
    source = (JS / "app.js").read_text(encoding="utf-8")
    assert source.count('closest("[data-product]")') == 1
    assert source.count('new CustomEvent("product:purchase"') == 1


# ---- 2 and 4. every selling page carries what pay.js needs ---------------------------------------

SELLING_PAGES = ["numerology_report.html", "consultation.html", "order.html", "order_v2.html"]


@pytest.mark.parametrize("name", SELLING_PAGES)
def test_a_page_that_loads_pay_js_declares_it_properly(name):
    """Without data-pay, pay.js finds no script tag, `enabled` stays false and it registers nothing
    - so the page loads the payment script and the buy button does nothing."""
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    if "pay.js" not in text:
        pytest.skip(f"{name} does not load pay.js")
    tag = re.search(r"<script[^>]*pay\.js[^>]*>", text, re.S)
    assert tag, name
    assert "data-pay" in tag.group(0), f"{name}: pay.js is loaded without data-pay"
    assert "data-enabled" in tag.group(0), f"{name}: pay.js is loaded without data-enabled"


def test_the_state_list_lives_in_one_place():
    """It was inline in two templates when a third page needed it. Two copies of one list is how
    they drift; the partial is the single source."""
    partial = TEMPLATES / "_pay_state_options.html"
    assert partial.exists()
    assert "ui.states" in partial.read_text(encoding="utf-8")
    inline = [p.name for p in TEMPLATES.glob("*.html")
              if 'id="pay-state-options"' in p.read_text(encoding="utf-8") and p.name != partial.name]
    assert not inline, f"these still inline the state list instead of including the partial: {inline}"


# ---- 3. pay.js opens its panel for a product that is not about a chart ---------------------------

def test_pay_js_opens_the_panel_for_a_numerology_order():
    source = (JS / "pay.js").read_text(encoding="utf-8")
    assert "detail.request || detail.numerology" in source, (
        "pay.js opens its panel only for a detail with a `request`, which a numerology order never has")
    # it has always known how to build the body; nothing ever reached it
    assert "detail.numerology" in source and "body.born = detail.numerology.born" in source


# ---- 5. the order request survives a product with no birth details -------------------------------

def _request(**kw):
    """email and place_of_supply are required on every order - the invoice needs both."""
    from app.payments.routes import OrderRequest

    kw.setdefault("email", "nobody@example.invalid")
    kw.setdefault("place_of_supply", "27")
    return OrderRequest(**kw)


def test_a_numerology_order_has_no_births_and_does_not_raise():
    body = _request(product="numerology-report", name="Asha Vernekar", born=dt.date(1988, 3, 29))
    assert body.births() == [], "the generator asks for zero births for this product"
    assert body.names() == {"self": "Asha Vernekar"}


def test_a_chart_order_still_needs_its_birth():
    with pytest.raises(ValueError):
        _request(product="kundali-report-simple")


def test_the_subject_identifies_the_buyer_and_only_for_numerology():
    a = _request(product="numerology-report", name="Asha Vernekar", born=dt.date(1988, 3, 29))
    b = _request(product="numerology-report", name="Devdatta Rane", born=dt.date(1991, 7, 14))
    same = _request(product="numerology-report", name="Asha Vernekar", born=dt.date(1988, 3, 29))
    assert a.subject() and a.subject() != b.subject(), "two buyers share one report id"
    assert a.subject() == same.subject(), "the same person must get the same report"
    assert "Asha" not in a.subject(), "the id goes in a filename and a URL; a name does not"


# ---- 6. the report id tells two buyers apart ------------------------------------------------------

def test_two_numerology_buyers_get_different_report_ids():
    from app.ai.report import facts_digest, report_id
    from app.numerology import core

    day = dt.date(2026, 11, 4)
    first = report_id("numerology-report", "en", [], day,
                      facts_digest(core.for_chat(dt.date(1988, 3, 29), "Asha Vernekar")))
    second = report_id("numerology-report", "en", [], day,
                       facts_digest(core.for_chat(dt.date(1991, 7, 14), "Devdatta Rane")))
    assert first != second, (
        "same product, same language, same day - without a subject these collide, and the second "
        "buyer is served the first buyer's reading")


def test_every_other_products_report_id_is_unchanged():
    """A changed id would orphan the cache entry of a report somebody has already paid for, so the
    subject is added to the payload ONLY when there is one."""
    import hashlib
    import json

    from app.ai.report import CACHE_VERSION, report_id

    day = dt.date(2026, 11, 4)
    payload = {"v": CACHE_VERSION, "product": "kundali-report-simple", "language": "en",
               "as_of": day.isoformat(), "births": []}
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:32]
    assert report_id("kundali-report-simple", "en", [], day) == expected


def test_the_generator_and_the_order_agree_on_the_subject():
    """They must derive it the same way, or the report that is generated is not the one that was
    sold and the buyer pays for a cache miss forever."""
    import inspect

    from app.ai import report as report_module
    from app.payments import routes

    assert "facts_digest(numerology_facts)" in inspect.getsource(report_module.generate_report)
    assert "facts_digest(core.for_chat(" in inspect.getsource(routes.OrderRequest.subject)
