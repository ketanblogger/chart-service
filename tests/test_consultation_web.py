"""Phase 5: the AI consultation page (/ai-astrologer, /hi/ai-jyotish, /mr/ai-jyotish) and its JavaScript (pure parts run
in an embedded V8, as in test_web.py)."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.ai import chat, chat_store
from app.main import app
from app.web import STATIC_DIR, i18n, pages, site
from tests.reference_charts import CITY_REFERENCES
from tests.test_consultation import FakeChat, GOOD_REPLY, MIRAJ
from tests.test_web import _Page

client = TestClient(app)


def catalogue_prices() -> dict[str, int]:
    from app.payments import catalogue

    return catalogue.prices_inr()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("CHAT_RATE_PER_MINUTE", "100")


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_consultation_page_seo_structure_and_hooks(lang):
    path = i18n.url_for("consultation", lang)
    response = client.get(path)
    assert response.status_code == 200
    html, page, config = response.text, _Page(response.text), pages.get("consultation", lang)

    assert page.title == f"{config.title} | {site.SITE_NAME}" and page.h1 == [config.h1]
    assert page.meta["description"] == config.meta_description and 70 <= len(config.meta_description) <= 220
    assert page.links["canonical"] == f"http://localhost:8000{path}" == page.meta["og:url"]
    assert page.meta["viewport"]

    form = page.ids["tool-form"]  # the shared birth form, wired by app.js; the session starts in the page language
    assert form["data-endpoint"] == "/api/consultation/start" and form["data-renderer"] == "consultation"
    assert form["data-lang"] == lang
    for field in ("name", "date", "time", "city"):
        assert f"self-{field}" in page.ids
    assert page.ids["self-city"]["role"] == "combobox"
    for element in ("result", "result-body", "chat", "chat-log", "chat-form", "chat-input", "chat-typing",
                    "chat-error", "chat-quota", "chat-paywall", "chat-reset", "cta-notice"):
        assert element in page.ids, element
    assert page.ids["chat-input"]["maxlength"] == "1000"
    assert "hidden" in page.ids["chat-paywall"] and "hidden" in page.ids["result"]
    # analytics.js and the Google loader come from base.html and lead every page's list; pay.js is inert without keys.
    assert [src.split("?")[0] for src in page.scripts] == ["/static/js/analytics.js",
                                                           "https://www.googletagmanager.com/gtag/js",
                                                           "/static/js/nav.js", "/static/js/render.js",
                                                           "/static/js/app.js", "/static/js/chat.js",
                                                           "/static/js/pay.js"]

    # paywall card: same purchase hook as the tool pages. Both tiers are ALWAYS N questions + a Kundali PDF; what
    # differs is which report comes with them, so the buyer can see what the extra rupees buy.
    offer = pages.chat_offer()
    prices = catalogue_prices()
    assert [(p["data-product"], p["data-price-inr"]) for p in page.products] == \
        [("consultation-basic", str(offer["price_inr"])), ("consultation-premium", str(prices["consultation-premium"]))]
    assert page.ids["chat-buy"]["data-product"] == pages.CONSULTATION_PRODUCT  # chat.js / the browser checks use the id
    for button in page.products:  # every tier fires the same purchase hook, with the same "coming soon" note
        assert button["data-notice"] == config.extra["paywall_notice"]
    # the page sells a consultation TIER from the catalogue; `chat.PRODUCT` is what the 402 quotes, and
    # app/ai/chat.py still names the id the single bundle was sold under (reported to the lead)
    from app.payments import catalogue

    assert catalogue.sellable(pages.CONSULTATION_PRODUCT) is not None
    assert chat.PRODUCT.startswith("consultation-")
    paywall = html.split('id="chat-paywall"', 1)[1].split("</aside>", 1)[0]
    assert f"₹{offer['price_inr']}" in paywall and str(offer["pack_messages"]) in paywall and "PDF" in paywall
    assert f"₹{prices['consultation-premium']}" in paywall  # both prices are on the card, never typed into copy
    for key in ("basic", "premium"):  # a label and a one-line "what you get" per tier
        assert config.extra[f"buy_{key}"] in paywall and config.extra[f"gets_{key}"] in paywall
    assert config.extra["buy_basic"] != config.extra["buy_premium"]
    for text in (config.extra["paywall_heading"], config.extra["input_placeholder"],
                 config.extra["typing"], config.extra["reset"], config.extra["chat_disclaimer"]):
        assert text in html or text.replace("'", "&#39;") in html, text

    faq = next(block for block in page.json_ld if block["@type"] == "FAQPage")
    assert [q["name"] for q in faq["mainEntity"]] == [question for question, _ in config.faqs]
    assert 4 <= len(config.faqs) <= 8
    for question, _ in config.faqs:
        assert f"<summary>{question}</summary>" in html or f"<summary>{question}</summary>".replace("'", "&#39;") in html
    if lang == "en":
        assert "faith-based" in html and "health, legal or financial" in html  # fixed disclaimer under the chat + footer
        assert "10 questions" in html
    for url in re.findall(r'(?:src|href)="([^"]+)"', html):  # no external assets
        assert url.startswith(("/", "#", "https://www.googletagmanager.com/gtag/js?id=")) \
            or url.startswith(site.base_url()), url  # the analytics tag in base.html is the one exception


def test_page_offer_matches_backend():
    """The paywall card and the API's 402 payload (CHAT_PACK_PRICE_INR / CHAT_PACK_MESSAGES) must agree."""
    offer = pages.chat_offer()
    assert offer["price_inr"] == chat.paywall()["price_inr"] == 99
    assert offer["pack_messages"] == chat.paywall()["messages"] == 10 and offer["free_messages"] == 2


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_consultation_is_linked_from_every_page_of_its_language(lang):
    target = i18n.url_for("consultation", lang)
    for key in ("home", *i18n.TOOL_KEYS, "consultation", "rashifal-hub"):
        html = client.get(i18n.url_for(key, lang)).text
        assert f'href="{target}"' in html, key
    assert f'href="{target}" aria-current="page"' in client.get(target).text


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_consultation_starts_in_the_page_language(lang, monkeypatch):
    """app.js adds `language` = the form's data-lang to POST /api/consultation/start."""
    app_js = (STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert 'if (rendererKey === "consultation") request.language = lang;' in app_js
    monkeypatch.setattr(chat, "get_chat_client", lambda: FakeChat())
    started = TestClient(app).post("/api/consultation/start", json={**MIRAJ, "language": lang})
    assert started.status_code == 200 and started.json()["language"] == lang


def test_chat_js_only_talks_to_the_consultation_api():
    source = (STATIC_DIR / "js" / "chat.js").read_text(encoding="utf-8")
    assert client.get("/static/js/chat.js").status_code == 200
    assert set(re.findall(r'"(/api/[^"]*)"', source)) == {"/api/consultation/session/", "/api/consultation/message"}
    assert "http://" not in source and "https://" not in source and "innerHTML = C.messagesHtml" in source
    assert "product:purchase" in (STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")


# ---------- the page's own JavaScript, in V8 ----------


@pytest.fixture(scope="module")
def js():
    mini_racer = pytest.importorskip("py_mini_racer")
    ctx = mini_racer.MiniRacer()
    ctx.eval((STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8"))
    ctx.eval((STATIC_DIR / "js" / "chat.js").read_text(encoding="utf-8"))  # the DOM half must not run without a document

    def call(expression: str, **variables):
        names = ", ".join(variables)
        args = ", ".join(json.dumps(value, ensure_ascii=False) for value in variables.values())
        return json.loads(ctx.eval(f"JSON.stringify((function({names}) {{ return {expression}; }})({args}))"))

    return call


def test_full_flow_with_the_real_api_third_message_shows_the_paywall(js, monkeypatch):
    fake = FakeChat()
    monkeypatch.setattr(chat, "get_chat_client", lambda: fake)
    http = TestClient(app)

    # 1. what app.js does with the birth form. The combobox can only offer a city, so the form step uses
    # the one published chart that can be given as a city (reference_charts.CITY_REFERENCES); the
    # conversation then runs on PRIMARY, the chart the fake reply in tests/test_consultation.py is
    # written for (it names a real placement, and the reply validator checks that against the chart).
    from_city = CITY_REFERENCES[0].city_request()
    values = {"self": {"name": "Test <b>User</b>", **from_city}}
    assert js("AstroRender.validate('single', values, '2026-01-01')", values=values) == []
    body = js("AstroRender.buildPayload('single', values)", values=values)
    assert body == from_city  # the form sends exactly what the API asks for
    assert http.post("/api/consultation/start", json=body).status_code == 200

    started = http.post("/api/consultation/start", json=MIRAJ)
    assert started.status_code == 200
    summary = started.json()["summary"]
    header = js("AstroRender.renderers.consultation(data, ctx)", data=started.json(), ctx={"name": "Test <b>User</b>"})
    for expected in (summary["lagna"]["sign"]["name"], summary["moon_rashi"]["name"],
                     summary["janma_nakshatra"]["name"], summary["dasha"]["mahadasha"]["lord"]["name"], "until"):
        assert expected in header, expected
    assert "<b>User</b>" not in header and "&lt;b&gt;User" in header
    for junk in ("undefined", "NaN", "[object", ">null<"):
        assert junk not in header

    # 2. what chat.js does with each message
    state = js("AstroChat.stateFromSession(view)", view=started.json())
    assert state["paywall"] is None and js("AstroChat.quotaLabel(s)", s=state) == "2 free questions left"
    assert "Namaste" in js("AstroChat.messagesHtml(s)", s=state)

    for question, label in [("How is my career?", "1 free question left"), ("<script>alert(1)</script> marriage?", "")]:
        assert js("AstroChat.validateMessage(s, t)", s=state, t=question) is None
        state = js("AstroChat.withPending(s, t)", s=state, t=question)
        assert state["pending"] and js("AstroChat.validateMessage(s, 'again')", s=state)  # no double send
        response = http.post("/api/consultation/message", json={"session_id": state["sessionId"], "message": question})
        state = js("AstroChat.applyResponse(s, status, body)", s=state, status=response.status_code, body=response.json())
        assert not state["pending"] and state["error"] is None and js("AstroChat.quotaLabel(s)", s=state) == label

    html = js("AstroChat.messagesHtml(s)", s=state)
    assert html.count("chat__msg--user") == 2 and html.count("chat__msg--assistant") == 2
    assert "<script>" not in html and "&lt;script&gt;" in html and GOOD_REPLY.split(",")[0] in html
    assert state["paywall"]["price_inr"] == chat.paywall()["price_inr"]  # after the 2nd free reply the input is replaced by the paywall card
    assert js("AstroChat.validateMessage(s, 'third')", s=state) == "Your free questions are used."

    # 3. a 3rd message anyway (e.g. another tab): HTTP 402 -> paywall state, the question is not lost, no AI call
    state["paywall"] = None
    state = js("AstroChat.withPending(s, 'third question')", s=state)
    third = http.post("/api/consultation/message", json={"session_id": state["sessionId"], "message": "third question"})
    assert third.status_code == 402
    state = js("AstroChat.applyResponse(s, status, body)", s=state, status=402, body=third.json())
    # the 402 names a consultation product; which tier it quotes is app/ai/chat.py's to say
    assert state["paywall"]["product"].startswith("consultation-") and state["paywall"]["session_id"] == state["sessionId"]
    assert state["draft"] == "third question" and len(state["messages"]) == 4 and len(fake.calls) == 2

    # 4. Phase 6 credits the pack -> `consultation:credited` -> chat.js reloads the session
    chat_store.credit_session(state["sessionId"], 10, reference="pay_1")
    reloaded = js("AstroChat.stateFromSession(view)", view=http.get(f"/api/consultation/session/{state['sessionId']}").json())
    assert reloaded["paywall"] is None and len(reloaded["messages"]) == 4
    assert js("AstroChat.quotaLabel(s)", s=reloaded) == "10 questions left"


def test_chat_state_error_handling(js):
    state = {"sessionId": "s", "messages": [], "quota": {"free_left": 2, "paid_left": 0, "messages_left": 2},
             "paywall": None, "pending": False, "error": None}
    assert js("AstroChat.validateMessage(s, '   ')", s=state) == "Please type a question."
    assert "under 1000" in js("AstroChat.validateMessage(s, t)", s=state, t="x" * 1001)
    pending = js("AstroChat.withPending(s, ' hello ')", s=state)
    assert pending["messages"] == [{"role": "user", "content": "hello", "kind": "pending"}]

    for status, body, expected in [
        (503, {"detail": {"code": "ai_unavailable", "message": "The astrologer is unavailable right now."}}, "The astrologer is unavailable right now."),
        (429, {"detail": {"code": "rate_limited", "message": "Please wait a moment."}}, "Please wait a moment."),
        (0, None, "Could not reach the server"), (500, None, "Something went wrong"), (404, {"detail": {}}, "expired"),
    ]:
        after = js("AstroChat.applyResponse(s, status, body)", s=pending, status=status, body=body)
        assert expected in after["error"] and after["messages"] == [] and not after["pending"] and after["draft"] == "hello"
    assert js("AstroChat.applyResponse(s, 404, b)", s=pending, b={"detail": {}})["expired"] is True

    safe = js("AstroChat.applyResponse(s, 200, b)", s=pending, b={
        "reply": {"role": "assistant", "content": "line one\n\nline two\nline three", "kind": "safe"},
        "quota": {"free_left": 2, "paid_left": 0, "messages_left": 2}, "paywall": None})
    assert [m["kind"] for m in safe["messages"]] == ["safe", "safe"] and safe["draft"] == ""
    assert "<p>line one</p><p>line two<br>line three</p>" in js("AstroChat.messagesHtml(s)", s=safe)
    mixed = dict(state, quota={"free_left": 1, "paid_left": 10, "messages_left": 11})
    assert js("AstroChat.quotaLabel(s)", s=mixed) == "1 free + 10 paid questions left"


def test_start_errors_reach_the_form(js):
    limited = {"detail": {"code": "rate_limited", "message": "You are sending messages very quickly."}}
    assert js("AstroRender.parseApiError(429, body, 'single')", body=limited) == [
        {"person": None, "field": None, "message": "You are sending messages very quickly."}]


# ---------- a lost response is not proof that nothing happened ----------
#
# POST /api/consultation/message is a SYNC route, so a client that disconnects does not cancel it: the
# server finishes, spends the message credit and stores both the question and the reply. chat.js used to
# treat any failure as "nothing was delivered" and put the question back in the box, which invites the
# reader to buy the same answer a second time. On a status of 0 it now re-reads the session first.
#
# These two tests are the two sides of that decision, and both are taken against real server state rather
# than against a list this file builds. That matters for the second one: if the "delivered" side were made
# by appending to a local array, the assertion would be about arithmetic done here, and the mutant worth
# catching - comparing against the length AFTER the pending question was appended - would survive because
# the condition would never be constructed. So the message really is sent, the server really records it,
# the credit really is spent, and only the response is treated as lost. At the API level that is exactly
# what an aborted response leaves behind.


def test_a_lost_response_recovers_the_answer_instead_of_charging_for_it_twice(js, monkeypatch):
    """The one that counts: one mid-send failure spends one credit and the answer comes back."""
    fake = FakeChat()
    monkeypatch.setattr(chat, "get_chat_client", lambda: fake)
    http = TestClient(app)

    started = http.post("/api/consultation/start", json=MIRAJ)
    assert started.status_code == 200
    state = js("AstroChat.stateFromSession(view)", view=started.json())
    left_before = state["quota"]["messages_left"]
    delivered = len(state["messages"])          # what chat.js counts BEFORE withPending appends
    pending = js("AstroChat.withPending(s, t)", s=state, t="How is my career?")

    sent = http.post("/api/consultation/message",
                     json={"session_id": state["sessionId"], "message": "How is my career?"})
    assert sent.status_code == 200 and len(fake.calls) == 1, "precondition: the server must have done the work"

    # The client heard nothing. The handler's status-0 branch re-reads the session instead of believing that.
    view = http.get(f"/api/consultation/session/{state['sessionId']}").json()
    recovered = js("AstroChat.recoverFromSession(view, n)", view=view, n=delivered)

    assert recovered, (
        "a reply the customer has already been charged for was not recovered. The old behaviour put their "
        "question back in the box, so the obvious next action buys the same answer again.")
    assert len(recovered["messages"]) == delivered + 2, "the question and its reply should both be back"
    assert GOOD_REPLY.split(",")[0] in js("AstroChat.messagesHtml(s)", s=recovered)
    assert recovered["quota"]["messages_left"] == left_before - 1, (
        f"one question should cost one credit: {left_before} -> {recovered['quota']['messages_left']}")
    assert len(fake.calls) == 1, "recovering an answer asked the AI for it a second time"
    assert not recovered["pending"] and not recovered["error"] and not recovered.get("draft"), (
        "the recovered state still looks like a send in progress, so the reader would be invited to resend")

    # I expected to be able to assert here that the count MUST be the one taken before withPending appended
    # the pending question, and that passing the post-pending length would recover nothing. That assertion
    # failed, and it deserved to: measured, a recorded turn adds TWO messages while withPending adds one,
    # so both counts clear the comparison and the off-by-one is absorbed. The pre-pending count is the
    # right one to pass because it is the quantity the comparison is about, not because the other is
    # broken - and the comment in chat.js now says that instead of overstating it.
    assert len(pending["messages"]) == delivered + 1 and len(recovered["messages"]) == delivered + 2

    # What IS worth pinning is that the comparison is a real comparison rather than a truthiness check: a
    # session holding nothing the caller had not already seen is not a recovery.
    assert js("AstroChat.recoverFromSession(view, n)", view=view, n=len(recovered["messages"])) is None
    assert js("AstroChat.recoverFromSession(view, n)", view=view, n=len(recovered["messages"]) + 5) is None


def test_a_failure_the_server_never_saw_still_gives_the_question_back(js, monkeypatch):
    """The other side. Nothing was delivered, so nothing is suppressed - and no credit was spent."""
    fake = FakeChat()
    monkeypatch.setattr(chat, "get_chat_client", lambda: fake)
    http = TestClient(app)

    started = http.post("/api/consultation/start", json=MIRAJ)
    state = js("AstroChat.stateFromSession(view)", view=started.json())
    left_before = state["quota"]["messages_left"]
    delivered = len(state["messages"])
    pending = js("AstroChat.withPending(s, t)", s=state, t="How is my career?")

    # The request never arrived: the session is untouched.
    view = http.get(f"/api/consultation/session/{state['sessionId']}").json()
    assert js("AstroChat.recoverFromSession(view, n)", view=view, n=delivered) is None, (
        "a session with nothing new in it was treated as a recovery, which would swallow a question that "
        "was never asked and leave the reader with no way to ask it")

    # So the handler falls through to exactly the behaviour that shipped: the question goes back in the box.
    after = js("AstroChat.applyResponse(s, status, body)", s=pending, status=0, body=None)
    assert after["draft"] == "How is my career?" and "Could not reach the server" in after["error"]
    assert len(fake.calls) == 0
    assert js("AstroChat.stateFromSession(v)", v=view)["quota"]["messages_left"] == left_before, (
        "a message that never reached the server cost a credit")

    # Unreadable or empty answers from the re-read are failures, not recoveries.
    assert js("AstroChat.recoverFromSession(v, 0)", v=None) is None
    assert js("AstroChat.recoverFromSession(v, 0)", v={}) is None
