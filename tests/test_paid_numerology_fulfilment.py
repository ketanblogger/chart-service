"""A paid numerology order is fulfilled: webhook -> report -> PDF -> e-mail.

WHY THIS FILE EXISTS. On 5 November a real customer paid Rs 199 for a Marathi numerology report.
Fulfilment failed five times with "numerology-report needs `numerology_facts` - it is written from
them", and no retry could ever have worked: the order stored `subject`, a one-way digest of the
numbers, and nothing to rebuild them from. The customer's order page said "generating, 5-10 min"
for three hours.

Every test we had stopped at Razorpay's door. The browser check drove the buy panel and asserted
the order was created - and then deliberately blocked checkout.js, so not one step after payment
had ever run for this product. The suite was green the whole time.

So these tests start where the old ones stopped: a signed webhook, then the real fulfilment path,
and they assert a PDF on disk and an e-mail queued, in all three languages.
"""
import datetime as dt
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.payments import catalogue, razorpay, service, store

KEY_ID, KEY_SECRET, WEBHOOK_SECRET = "rzp_test_fulfil", "secret", "whsecret"
BORN, NAME = "1990-05-14", "Asha Kulkarni"          # invented, as every fixture here is


@pytest.fixture
def live(tmp_path, monkeypatch):
    """Payments configured, Razorpay faked, a database of this test's own, and no real mail."""
    # APP_DB, REPORTS_DIR and PDFS_DIR are already pointed at this test's tmp_path by the autouse
    # fixture in conftest.py. Setting APP_DB again here gave the app one database and this test
    # another, so every lookup came back None.
    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(200, json={"id": "order_Fulfil001", "entity": "order",
                                         "amount": body["amount"], "amount_paid": 0,
                                         "amount_due": body["amount"], "currency": body["currency"],
                                         "receipt": body["receipt"], "status": "created",
                                         "attempts": 0, "notes": body["notes"]})

    monkeypatch.setattr(razorpay, "_transport", httpx.MockTransport(handler))
    sent: list[dict] = []
    monkeypatch.setattr(service, "_email_order_link", lambda order: sent.append(order))
    # Fulfilment runs off the payment path in a daemon thread; _spawn is the seam its own docstring
    # offers for exactly this. Inline, so the assertions below see a finished job rather than a
    # race - and so a failure is this test's failure, not a flake.
    monkeypatch.setattr(service, "_spawn", lambda fn, *args: fn(*args))
    # The report itself is the AI's job and costs money; the point here is the PLUMBING, so the
    # writer is replaced and everything around it is real.
    import app.ai.report as report_module

    def fake_generate(product, language, births, *, as_of=None, numerology_facts=None, **kw):
        assert product == "numerology-report"
        # THE ASSERTION THE OUTAGE WAS ABOUT: fulfilment must hand the numbers over.
        assert numerology_facts and numerology_facts.get("mulank"), (
            "fulfilment called the writer with no numerology_facts - the 5 November failure")
        rid = report_module.report_id(product, language, [], as_of,
                                      report_module.facts_digest(numerology_facts))
        built = {"id": rid, "product": product, "language": language, "as_of": as_of.isoformat(),
                 "sections": [{"key": "your_numbers", "title": "Your numbers", "body": "Text."}],
                 "disclaimer": "For guidance only.", "meta": {"model": "fake"}}
        report_module._save_report(built)
        return built

    monkeypatch.setattr(service, "generate_report", fake_generate)
    with TestClient(app) as client:
        yield client, sent


def _webhook(client, order_id: str, amount: int):
    payload = {"entity": "event", "account_id": "acc_Test", "event": "payment.captured",
               "contains": ["payment"], "created_at": 1790000000,
               "payload": {"payment": {"entity": {"id": "pay_Fulfil01", "entity": "payment",
                                                  "amount": amount, "currency": "INR",
                                                  "status": "captured", "order_id": order_id,
                                                  "captured": True, "email": "buyer@example.invalid"}}}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    return client.post("/api/payments/webhook", content=body, headers={
        "Content-Type": "application/json",
        "X-Razorpay-Event-Id": f"evt_{order_id}",
        "X-Razorpay-Signature": hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()})


def _buy(client, language: str) -> dict:
    """Buy, and return the created order ROW - the response does not expose the Razorpay id, and the
    webhook is looked up by exactly that."""
    reply = client.post("/api/payments/order", json={
        "product": "numerology-report", "language": language, "name": NAME, "born": BORN,
        "email": "buyer@example.invalid", "place_of_supply": "27"})
    assert reply.status_code == 200, reply.text[:300]
    # `order_id` in the response is RAZORPAY's id - it is what Checkout needs and what the webhook
    # is looked up by. Our own id is order["id"]. I had those the wrong way round.
    return store.by_razorpay_id(reply.json()["order_id"])


# ---- the order must carry what its report is written from ----------------------------------------

@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_the_order_stores_the_name_and_date_not_only_their_digest(live, language):
    """`subject` is one-way. An order carrying only that can never be fulfilled, which is exactly
    what happened: the inputs were gone the moment the order was written."""
    client, _ = live
    order = _buy(client, language)
    stored = order["request"]["numerology"]
    assert stored == {"name": NAME, "born": BORN}
    assert order["request"]["subject"], "the digest is still stored, for the id it was sold under"


# ---- past payment: the path that had never run ---------------------------------------------------

@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_a_paid_numerology_order_is_fulfilled_end_to_end(live, language):
    client, sent = live
    created = _buy(client, language)
    assert _webhook(client, created["razorpay_order_id"], 19900).json() == {"status": "ok"}

    order = store.get_order(created["id"])
    assert order["status"] == "paid"
    assert order["fulfilment"] == "ready", f"fulfilment {order['fulfilment']}: {order.get('error')}"
    assert not order.get("error"), order.get("error")
    assert [o["id"] for o in sent] == [created["id"]], "no e-mail was queued"


@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_the_pdf_is_rendered_for_a_paid_numerology_order(live, language):
    """The customer's deliverable is a PDF, so "fulfilled" has to mean one exists."""
    from app.pdf.service import ensure_pdf

    client, _ = live
    created = _buy(client, language)
    _webhook(client, created["razorpay_order_id"], 19900)
    order = store.get_order(created["id"])

    from app.ai.report import load_report

    report = load_report(order["report_id"])
    assert report, "the generated report was not saved"
    pdf = ensure_pdf(report, order.get("names"))
    assert pdf.exists() and pdf.stat().st_size > 1000, pdf


def test_fulfilment_refuses_to_write_a_different_persons_report(live):
    """The order's digest is checked against the numbers rebuilt from its stored inputs. If they
    ever disagree, failing is right: generating somebody else's report under a paid order's id is
    the one outcome worse than this outage."""
    client, _ = live
    order = _buy(client, "en")
    tampered = dict(order)
    tampered["request"] = {**order["request"], "numerology": {"name": "Someone Else", "born": "1971-01-01"}}
    with pytest.raises(RuntimeError, match="refusing to generate a different report"):
        service._numerology_facts(tampered)


def test_an_order_placed_before_the_fix_says_how_to_re_run_it(live):
    """The 5 November order has no stored inputs at all. The error must say what to do, not just
    fail again."""
    client, _ = live
    order = _buy(client, "mr")
    old = dict(order)
    old["request"] = {"births": [], "subject": order["request"]["subject"]}
    with pytest.raises(ValueError, match="fulfil_order.py"):
        service._numerology_facts(old)


# ---- the chat tiers go through the same door -----------------------------------------------------

@pytest.mark.parametrize("product", catalogue.NUMEROLOGY_PACKS)
def test_a_paid_numerology_pack_is_fulfilled(live, product):
    """A pack credits questions rather than generating a report, so it must NOT go near the writer -
    and it must still come out fulfilled rather than stuck."""
    client, sent = live
    from app.ai import chat

    session = chat.start_session("u1", "b1", "ip1", {"date": BORN}, NAME, "en", numerology=True)
    item = catalogue.sellable(product)
    created = client.post("/api/payments/order", json={
        "product": product, "session_id": session["session_id"],
        "email": "buyer@example.invalid", "place_of_supply": "27"}).json()
    assert _webhook(client, created["order_id"], item.price_inr * 100).json() == {"status": "ok"}
    order = store.by_razorpay_id(created["order_id"])
    assert order["status"] == "paid"
    assert order["fulfilment"] == "ready", f"{order['fulfilment']}: {order.get('error')}"
    assert not order.get("report_id"), "a questions-only pack must not own a report"


# ---- repairing an order placed before the fix ----------------------------------------------------

def test_an_old_order_can_be_repaired_and_fulfilled(live, monkeypatch):
    """THE 5 NOVEMBER ORDER. It stored no name and no date, so nothing can rebuild its report -
    scripts/fulfil_order.py --born writes them on after checking they reproduce the digest the
    customer's report id was computed from."""
    from scripts.fulfil_order import _supply_numerology_inputs

    client, sent = live
    order = _buy(client, "mr")
    _webhook(client, order["razorpay_order_id"], 19900)

    # put it back into the broken shape: digest only, no inputs
    broken = {"births": [], "subject": order["request"]["subject"]}
    store.set_request(order["id"], broken)
    assert store.get_order(order["id"])["request"].get("numerology") is None

    repaired = _supply_numerology_inputs(store.get_order(order["id"]), BORN, NAME)
    assert repaired is not None
    assert repaired["request"]["numerology"] == {"name": NAME, "born": BORN}
    service.fulfil(repaired, sync=True, force=True)
    assert store.get_order(order["id"])["fulfilment"] == "ready"


def test_the_repair_refuses_a_date_that_does_not_match_the_purchase(live, capsys):
    """A wrong date would deliver a stranger's reading under a paid order. Refusing is the only
    safe answer, and the message has to say why."""
    from scripts.fulfil_order import _supply_numerology_inputs

    client, _ = live
    order = _buy(client, "en")
    assert _supply_numerology_inputs(order, "1971-01-01", NAME) is None
    assert "REFUSED" in capsys.readouterr().out


def test_the_repair_refuses_a_product_it_is_not_for(live, capsys):
    from scripts.fulfil_order import _supply_numerology_inputs

    client, _ = live
    order = _buy(client, "en")
    order = {**order, "product": "kundali-report"}
    assert _supply_numerology_inputs(order, BORN, NAME) is None
    assert "only for numerology-report" in capsys.readouterr().out


# ---- the customer was told the wrong thing, and nobody was told anything -------------------------

JS = (__import__("pathlib").Path(__file__).resolve().parents[1] / "app/static/js/pay.js").read_text(encoding="utf-8")


def test_a_numerology_order_is_not_described_as_a_chart_while_it_waits():
    """The customer watched "your report is being written from your exact kundali" for three hours,
    with stages about a chart and a life timeline their report does not contain."""
    assert JS.count("numerologyPreparingText:") == 3, "one per language"
    assert JS.count("numerologyStages:") == 3
    assert "isNumerology(view) && T.numerologyPreparingText" in JS
    assert "isNumerology(view) && T.numerologyStages" in JS
    assert 'view.product === "numerology-report"' in JS


def test_a_final_failure_says_what_happened_and_what_we_will_do():
    """It used to say only that things were "taking longer than they should" and promise completion.
    After the retries are exhausted the customer is owed the truth and a way out."""
    for phrase in ("Something went wrong", "we will e-mail you", "refund you in full"):
        assert phrase in JS, phrase
    assert "taking longer than it should; we will complete it" not in JS


def test_the_honest_failure_message_is_in_all_three_languages():
    for marker in ("काहीतरी चुकले", "कुछ गड़बड़ हो गई"):
        assert marker in JS, marker
    for marker in ("परतावा", "पैसा वापस"):          # refund, mr and hi
        assert marker in JS, marker


def test_a_failed_paid_order_is_actually_alerted_on_a_schedule():
    """THE ALERT EXISTED AND NOTHING RAN IT. late_and_failed_orders() has raised a critical alert
    since it was written; the only alert-adjacent timer was the daily digest, which reports a
    COUNT. A critical alert nobody has scheduled is a comment."""
    import pathlib

    deploy = pathlib.Path(__file__).resolve().parents[1] / "deploy/systemd"
    service = (deploy / "alerts.service").read_text(encoding="utf-8")
    timer = (deploy / "alerts.timer").read_text(encoding="utf-8")
    assert "-m app.admin.alerts" in service and "--digest" not in service, (
        "the digest is not the alert path; fire_due is")
    assert "OnUnitActiveSec" in timer and "WantedBy=timers.target" in timer


def test_the_daily_digest_names_undelivered_orders_rather_than_counting_them():
    from app.admin import alerts

    source = __import__("inspect").getsource(alerts.digest_body)
    assert "_failed_order_lines" in source
    helper = __import__("inspect").getsource(alerts._failed_order_lines)
    assert "unfinished_paid" in helper and "fulfil_order.py" in helper


def test_the_deploy_line_installs_the_new_units():
    """A unit that is written but never copied to the server is a unit that does not run - which is
    the whole shape of this outage, one level down."""
    import pathlib

    runbook = pathlib.Path(__file__).resolve().parents[1] / "docs/DEPLOY.md"
    if not runbook.exists():
        pytest.skip("the deploy runbook is not in this checkout")
    assert "alerts." in runbook.read_text(encoding="utf-8")
