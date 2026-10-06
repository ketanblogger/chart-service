"""The muhurta feature as a visitor meets it: the flag, the pages, the search, the chat and the purchase."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import site

PUNE = {"lat": 18.5204, "lon": 73.8567, "city": "Pune"}
SEARCH = {"purpose": "griha-pravesh", "from_date": "2027-03-01", "to_date": "2027-03-31", **PUNE}
PAGES = ("/muhurta", "/hi/muhurta", "/mr/muhurta")


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(site, "MUHURTA", True)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def off(monkeypatch):
    monkeypatch.setattr(site, "MUHURTA", False)
    return TestClient(app, raise_server_exceptions=False)


# ---- the flag --------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", PAGES)
def test_the_pages_are_not_there_at_all_when_the_flag_is_off(path, off):
    assert off.get(path).status_code == 404


def test_the_search_is_not_there_either_when_the_flag_is_off(off):
    """The page being hidden is not the feature being off. An endpoint left answering is the feature on."""
    assert off.post("/api/muhurta/search", json=SEARCH).status_code == 404


# ---- the pages -------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", PAGES)
def test_each_tree_has_the_page_and_keeps_it_out_of_the_index(path, on):
    response = on.get(path)
    assert response.status_code == 200
    assert 'name="robots" content="noindex, nofollow"' in response.text
    assert 'class="design-v2"' in response.text, "a new page carries the current design"


@pytest.mark.parametrize("path, word", [(PAGES[0], "Find an Auspicious Date (Muhurat)"),
                                        (PAGES[1], "शुभ मुहूर्त खोजें"), (PAGES[2], "शुभ मुहूर्त शोधा")])
def test_each_tree_is_in_its_own_language(path, word, on):
    assert word in on.get(path).text


@pytest.mark.parametrize("path", PAGES)
def test_every_page_says_it_is_arithmetic_and_not_a_guarantee(path, on):
    """Asked for on every result. It is the honest description of what is being sold, so it is not small
    print at the bottom of one page."""
    text = on.get(path).text
    assert any(phrase in text for phrase in ("arithmetic, not a guarantee", "गणित है, कोई गारंटी नहीं",
                                             "गणित आहे, हमी नाही"))


@pytest.mark.parametrize("path", PAGES)
def test_the_page_offers_every_purpose_the_engine_knows(path, on):
    from app.engine import muhurta

    text = on.get(path).text
    for key in muhurta.purposes():
        assert f'value="{key}"' in text, f"{path}: {key} is missing from the form"


def test_the_page_is_not_in_the_sitemap_while_it_is_behind_its_flag(on):
    """The registry drives the sitemap and the hreflang alternates. A page in the sitemap that 404s when
    the flag goes off is a crawler invited to a missing room, so this one is deliberately outside it."""
    sitemap = on.get("/sitemap.xml").text
    for path in PAGES:
        assert f"<loc>https://rashikundli.com{path}</loc>" not in sitemap


# ---- the search ------------------------------------------------------------------------------------


def test_the_search_answers_with_days_that_carry_their_reasons(on):
    body = on.post("/api/muhurta/search", json={**SEARCH, "language": "en"}).json()
    assert body["found"] == len(body["days"])
    assert body["searched_days"] == 31
    assert "arithmetic, not a guarantee" in body["basis"]
    for day in body["days"]:
        assert day["date"] and day["sunrise"] and day["tithi"] and day["nakshatra"]
        assert "-" in day["rahu_kaal"]


def test_the_search_says_how_many_rather_than_padding(on):
    """A single rikta day: the honest answer is none, and none is what comes back."""
    body = on.post("/api/muhurta/search",
                   json={**SEARCH, "from_date": "2027-03-12", "to_date": "2027-03-12"}).json()
    assert body["found"] == 0 and body["days"] == [] and body["searched_days"] == 1


@pytest.mark.parametrize("bad", [
    {"purpose": "surgery"},                                   # not a purpose at all
    {"from_date": "2027-03-31", "to_date": "2027-03-01"},     # backwards
    {"from_date": "2027-01-01", "to_date": "2029-01-01"},     # longer than a year
    {"lat": 999},
])
def test_the_search_refuses_what_it_should(bad, on):
    assert on.post("/api/muhurta/search", json={**SEARCH, **bad}).status_code == 422


def test_the_search_is_in_the_readers_language(on):
    body = on.post("/api/muhurta/search", json={**SEARCH, "language": "mr"}).json()
    assert body["found"], "this range has days; the language check needs one"
    assert any("ऀ" <= ch <= "ॿ" for ch in body["days"][0]["nakshatra"])
    assert "गणित आहे" in body["basis"]


# ---- the purchase ----------------------------------------------------------------------------------


def test_two_different_searches_are_two_different_reports():
    """The id is what the duplicate check, the entitlement and the PDF path all work on. If a purpose or a
    range did not reach it, a second purchase would silently hand over the first one's report."""
    from app.ai import muhurta_report

    base = ("griha-pravesh", "en", dt.date(2027, 3, 1), dt.date(2027, 3, 31), PUNE)
    first = muhurta_report.report_id(*base)
    assert first != muhurta_report.report_id("vehicle", *base[1:])
    assert first != muhurta_report.report_id(base[0], "hi", *base[2:])
    assert first != muhurta_report.report_id(*base[:3], dt.date(2027, 4, 30), PUNE)
    assert first != muhurta_report.report_id(*base[:4], {"lat": 19.07, "lon": 72.88, "city": "Mumbai"})
    assert first == muhurta_report.report_id(*base)


def test_the_report_is_built_without_a_model_and_carries_the_basis_line():
    from app.ai import muhurta_report

    report = muhurta_report.build("griha-pravesh", "hi", dt.date(2027, 3, 1), dt.date(2027, 3, 31), PUNE)
    assert report["meta"]["model"] is None and report["meta"]["engine_only"] is True
    assert report["meta"]["cost_estimate_inr"] == 0.0
    assert "गणित है, कोई गारंटी नहीं" in report["disclaimer"]
    assert [section["id"] for section in report["sections"]] == ["dates", "how", "panchang", "backups"]
    assert report["sections"][0]["table"]["rows"], "the dates section has no dates in it"


# ---- who can use it --------------------------------------------------------------------------------


@pytest.mark.parametrize("path", PAGES)
def test_a_visitor_with_no_cookie_at_all_can_use_the_finder(path, on):
    """The finder is FREE and needs no account: it is panchang, not a reading. The sign-in exists for the
    astrologer, and a free tool that asks for an account is a free tool nobody uses."""
    cold = TestClient(app, raise_server_exceptions=False)
    cold.cookies.clear()
    assert cold.get(path).status_code == 200
    answer = cold.post("/api/muhurta/search", json={**SEARCH, "language": "en"})
    assert answer.status_code == 200 and answer.json()["found"] >= 0
    assert not answer.cookies, "the finder set a cookie on a visitor who needed none"


@pytest.mark.parametrize("path", PAGES)
def test_a_signed_in_reader_sees_the_same_finder(path, on):
    from app.web import accounts

    signed = TestClient(app, raise_server_exceptions=False)
    signed.cookies.set(accounts.COOKIE_NAME, accounts.sign("muhurta.reader@gmail.com"))
    assert signed.get(path).status_code == 200
    assert signed.post("/api/muhurta/search", json={**SEARCH, "language": "en"}).status_code == 200


def test_the_pdf_of_a_muhurta_report_actually_renders(on):
    """The product is a PDF. A report dict that the PDF pipeline cannot render is not a product."""
    from app.ai import muhurta_report
    from app.pdf import browser as pdf_browser
    from app.pdf import service as pdf_service

    ok, reason = pdf_browser.chromium_available()
    if not ok:
        pytest.skip(f"headless Chromium cannot launch here: {reason}")
    report = muhurta_report.build("griha-pravesh", "mr", dt.date(2027, 3, 1), dt.date(2027, 3, 31), PUNE)
    path = pdf_service.ensure_pdf(report)
    assert path.exists() and path.stat().st_size > 20_000, f"{path} is {path.stat().st_size} bytes"
    assert path.read_bytes()[:5] == b"%PDF-"


def test_the_pdf_does_not_call_itself_a_kundali_report_or_a_reading(on):
    """It is a date table. A running head saying "Kundali Report" and a part headed "Your reading" are both
    claims about what the buyer got, and both were wrong until they were looked at."""
    from app.ai import muhurta_report
    from app.pdf import book as pdf_book
    from app.pdf import labels as pdf_labels

    for lang, wrong, right in (("en", "Kundali Report", "Muhurta Report"),
                               ("mr", "कुंडली अहवाल", "मुहूर्त अहवाल"),
                               ("hi", "कुंडली रिपोर्ट", "मुहूर्त रिपोर्ट")):
        L = pdf_labels.Labels(lang)
        assert L["muhurta_running_title"] == right and L["running_title"] == wrong
    report = muhurta_report.build("vehicle", "mr", dt.date(2027, 5, 1), dt.date(2027, 6, 30), PUNE)
    assert report["product"] == "muhurta-report"
    # The part id the book builder picks for this product, which is what chooses the heading.
    assert pdf_labels.PART_LABELS["muhurta"] == ("The dates", "तिथियाँ", "तारखा")


def test_there_is_a_way_to_reach_the_finder_from_an_ordinary_page(on):
    """A FEATURE NOBODY CAN FIND IS A FEATURE NOBODY USES - which is exactly what the sign-in was until
    this week, when it existed only inside the AI astrologer. The finder is not a NAV_KEY, because it is
    outside the URL registry, so it has its own entry in the nav and this is what says it is there."""
    for path, expected in (("/", "/muhurta"), ("/hi/", "/hi/muhurta"), ("/mr/", "/mr/muhurta")):
        html = on.get(path).text
        assert 'class="site-nav__extra"' in html, f"{path}: no way to reach the muhurta finder"
        assert f'href="{expected}"' in html, f"{path}: the link does not stay in the reader's language"
    # ...and the rashifal pages, which have their own responder and were the one place the account control
    # went missing for exactly this reason.
    assert 'class="site-nav__extra"' in on.get("/mr/rashi-bhavishya/mesh").text


def test_the_entry_point_disappears_with_the_flag(off):
    for path in ("/", "/hi/", "/mr/", "/mr/rashi-bhavishya/mesh"):
        assert 'class="site-nav__extra"' not in off.get(path).text


# ---- free, and it has to stay that way --------------------------------------------------------------


# MONEY, not commerce-shaped words. "Buying a vehicle" and "वाहन खरीद" are PURPOSES - things a reader
# wants a date for - and a check that flagged those would have to be weakened the first time it ran, which
# is how a check stops meaning anything. These are the marks that can only be about being charged.
PRICE_MARKS = ("₹", "&#8377;", "Rs.", "INR", "rupee", "price", "payment", "checkout", "razorpay",
               "मूल्य", "कीमत", "भुगतान", "किंमत", "पैसे")


@pytest.mark.parametrize("path", PAGES)
def test_no_muhurta_page_mentions_a_price_or_a_purchase(path, on):
    """IT IS FREE, and a free thing that talks about money is not experienced as free. The product is out
    of the catalogue, so there is nothing to charge for - this is about what the page SAYS."""
    import re

    html = on.get(path).text
    body = html.split("<main", 1)[-1].split("</main>", 1)[0]
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", body)
    found = [mark for mark in PRICE_MARKS if mark.lower() in text.lower()]
    assert not found, f"{path} mentions {found}"
    assert "data-product" not in body, f"{path} still carries a purchase hook"


def test_the_product_is_not_in_the_catalogue_at_all():
    """Not flag-gated, not retired-but-resolvable: gone. Nothing can create an order for it."""
    from app.payments import catalogue

    assert catalogue.item("muhurta-report") is None
    assert catalogue.sellable("muhurta-report") is None
    assert "muhurta-report" not in catalogue.prices_inr()
    from app.ai.products import PRODUCTS

    assert "muhurta-report" not in PRODUCTS


def test_an_order_for_it_is_refused():
    from app.payments.routes import OrderRequest

    with pytest.raises(Exception):
        OrderRequest(product="muhurta-report", email="a@b.co", place_of_supply="27")


def test_the_pdf_says_nothing_about_money_either():
    from app.ai import muhurta_report
    from app.pdf.render import render_report_html

    for lang in ("en", "hi", "mr"):
        report = muhurta_report.build("griha-pravesh", lang, dt.date(2027, 3, 1), dt.date(2027, 3, 31), PUNE)
        text = render_report_html(report)
        for mark in ("₹", "&#8377;", "INR"):
            assert mark not in text, f"{lang} PDF mentions {mark}"


def test_a_cold_visitor_with_no_cookie_gets_the_pdf(on):
    """NOTHING IS ASKED FOR: no payment, no account, no e-mail. This is the whole claim of the feature, so
    it is made by a client with an empty cookie jar rather than by one the fixture prepared."""
    cold = TestClient(app, raise_server_exceptions=False)
    cold.cookies.clear()
    search = cold.post("/api/muhurta/search", json={**SEARCH, "language": "en"})
    assert search.status_code == 200 and search.json()["token"]

    got = cold.post("/api/muhurta/pdf", json={**SEARCH, "language": "en", "token": search.json()["token"]})
    assert got.status_code == 200, got.text
    assert got.headers["content-type"] == "application/pdf" and got.content[:5] == b"%PDF-"
    for word in ("login", "sign in", "sign-in", "payment", "402", "401"):
        assert word not in got.text[:0] + str(got.status_code), word


@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_the_whole_flow_works_cold_in_every_language(language, on):
    cold = TestClient(app, raise_server_exceptions=False)
    cold.cookies.clear()
    page = cold.get(PAGES[("en", "hi", "mr").index(language)])
    assert page.status_code == 200
    search = cold.post("/api/muhurta/search", json={**SEARCH, "language": language})
    assert search.status_code == 200 and search.json()["found"] >= 0
    pdf = cold.post("/api/muhurta/pdf", json={**SEARCH, "language": language,
                                              "token": search.json()["token"]})
    assert pdf.status_code == 200, f"{language}: {pdf.text[:200]}"


@pytest.mark.parametrize("chat_login", [True, False])
def test_neither_state_of_the_sign_in_flag_changes_any_of_this(chat_login, monkeypatch, on):
    """The muhurta finder does not use the sign-in at all, so CHAT_LOGIN must make no difference to it -
    in either direction. A feature that quietly depends on another feature's flag is a feature that breaks
    when that flag moves."""
    monkeypatch.setattr(site, "CHAT_LOGIN", chat_login)
    cold = TestClient(app, raise_server_exceptions=False)
    cold.cookies.clear()
    search = cold.post("/api/muhurta/search", json={**SEARCH, "language": "en"})
    assert search.status_code == 200
    pdf = cold.post("/api/muhurta/pdf", json={**SEARCH, "language": "en", "token": search.json()["token"]})
    assert pdf.status_code == 200, f"CHAT_LOGIN={chat_login}: {pdf.text[:200]}"


# ---- what stands in for an account ------------------------------------------------------------------


def test_the_pdf_cannot_be_asked_for_without_a_token_from_a_real_search(on):
    """THE BOT ANSWER, and it is not a CAPTCHA. A script that wants PDFs has to walk the flow - run the
    search, take its token, send it back - rather than hammering one endpoint with fresh cookies."""
    cold = TestClient(app, raise_server_exceptions=False)
    cold.cookies.clear()
    assert cold.post("/api/muhurta/pdf", json=SEARCH).status_code == 422          # no token at all
    for bad in ("", "nonsense", "0.0", "9999999999.deadbeefdeadbeefdeadbeefdeadbeef"):
        answer = cold.post("/api/muhurta/pdf", json={**SEARCH, "token": bad})
        assert answer.status_code in (409, 422), f"{bad!r} was accepted"


def test_a_token_is_only_good_for_the_search_it_was_issued_for(on):
    """Otherwise one token is a key to every PDF on the site, and the flow it proves means nothing."""
    from app.web.muhurta_routes import SearchRequest, issue_token, token_is_good

    asked = SearchRequest(**{**SEARCH, "language": "en"})
    token = issue_token(asked)
    assert token_is_good(token, asked)

    for change in ({"purpose": "vehicle"}, {"to_date": "2027-04-30"}, {"lat": 19.07},
                   {"language": "mr"}):
        other = SearchRequest(**{**SEARCH, "language": "en", **change})
        assert not token_is_good(token, other), f"the token survived a change of {list(change)[0]}"


def test_a_token_goes_stale(on):
    from app.web.muhurta_routes import TOKEN_TTL_SECONDS, SearchRequest, issue_token, token_is_good

    asked = SearchRequest(**{**SEARCH, "language": "en"})
    issued_at = 1_800_000_000
    token = issue_token(asked, now=issued_at)
    assert token_is_good(token, asked, now=issued_at + TOKEN_TTL_SECONDS - 5)
    assert not token_is_good(token, asked, now=issued_at + TOKEN_TTL_SECONDS + 5)
    assert not token_is_good(token, asked, now=issued_at - 60), "a token from the future was accepted"


def test_a_cross_origin_script_is_turned_away(on):
    """Cheap, and it costs an old browser nothing: a MISSING Sec-Fetch-Site is allowed through, because
    breaking an old Safari to inconvenience a curl loop is a bad trade."""
    cold = TestClient(app, raise_server_exceptions=False)
    cold.cookies.clear()
    token = cold.post("/api/muhurta/search", json={**SEARCH, "language": "en"}).json()["token"]
    body = {**SEARCH, "language": "en", "token": token}
    assert cold.post("/api/muhurta/pdf", json=body,
                     headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert cold.post("/api/muhurta/pdf", json=body,
                     headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_the_daily_caps_are_inside_the_existing_abuse_machinery():
    """Counted by `chat_store.check_rate`, like every other limit, so they are visible in one place."""
    from app.web import muhurta_routes

    assert muhurta_routes.PDFS_PER_COOKIE_PER_DAY == 10
    assert muhurta_routes.PDFS_PER_IP_PER_DAY == 30


def test_the_pdf_cache_is_pruned_rather_than_kept_for_ever():
    """A paid report is an archive; a free one anybody can ask for is a CACHE. Every distinct purpose,
    range, place and language is a different document, so one that is never pruned has no ceiling."""
    from app.pdf import service as pdf_service

    assert pdf_service.DEFAULT_MUHURTA_CACHE_MAX == 300
    assert pdf_service.muhurta_dir().name == "muhurta"


# ---- the caps, exercised rather than asserted -------------------------------------------------------


def _fresh_search(client, *, purpose="griha-pravesh", month=3):
    """A DIFFERENT search each time, so every call is a cache MISS and therefore really charges a slot.
    Asking for the same dates twice is a cache hit by design and must not count - which is exactly why a
    cap test that repeated one search would pass while capping nothing."""
    body = {**SEARCH, "purpose": purpose, "language": "en",
            "from_date": f"2027-{month:02d}-01", "to_date": f"2027-{month:02d}-28"}
    token = client.post("/api/muhurta/search", json=body).json()["token"]
    return {**body, "token": token}


def test_the_per_cookie_cap_bites(on, monkeypatch):
    from app.web import muhurta_routes

    monkeypatch.setattr(muhurta_routes, "PDFS_PER_COOKIE_PER_DAY", 2)
    monkeypatch.setattr(muhurta_routes, "PDFS_PER_IP_PER_DAY", 99)
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.clear()
    codes = [client.post("/api/muhurta/pdf", json=_fresh_search(client, month=month)).status_code
             for month in (4, 5, 6)]
    assert codes[:2] == [200, 200], codes
    assert codes[2] == 429, f"the third went through: {codes}"
    refused = client.post("/api/muhurta/pdf", json=_fresh_search(client, month=7))
    assert refused.json()["detail"]["code"] == "pdf_limit"
    # WHAT THE READER IS TOLD: the dates are still there, and none of this ever cost money.
    assert "still on the page" in refused.json()["detail"]["message"]
    assert "costs money" in refused.json()["detail"]["message"]


def test_a_cleared_cookie_gets_past_the_soft_cap_and_the_network_cap_still_holds(on, monkeypatch):
    """SAID OUT LOUD because it is true: the cookie cap is soft. Clearing a cookie gets another ten, and
    that is fine - it is there to stop ordinary repeated clicking. The network cap is what holds."""
    from app.web import muhurta_routes

    monkeypatch.setattr(muhurta_routes, "PDFS_PER_COOKIE_PER_DAY", 1)
    monkeypatch.setattr(muhurta_routes, "PDFS_PER_IP_PER_DAY", 3)
    client = TestClient(app, raise_server_exceptions=False)

    codes = []
    for month in (8, 9, 10, 11):
        client.cookies.clear()                       # a brand-new visitor, every time
        codes.append(client.post("/api/muhurta/pdf", json=_fresh_search(client, month=month)).status_code)
    assert codes[:3] == [200, 200, 200], f"the soft cap stopped a cleared cookie: {codes}"
    assert codes[3] == 429, f"the network cap did not hold: {codes}"


def test_breaking_the_network_cap_is_what_this_test_would_catch(on, monkeypatch):
    """The cap is read at request time, so this proves the route consults it rather than a copy taken at
    import. Raise it and the fourth request goes through."""
    from app.web import muhurta_routes

    monkeypatch.setattr(muhurta_routes, "PDFS_PER_COOKIE_PER_DAY", 1)
    monkeypatch.setattr(muhurta_routes, "PDFS_PER_IP_PER_DAY", 99)
    client = TestClient(app, raise_server_exceptions=False)
    codes = []
    for month in (1, 2, 3, 4):
        client.cookies.clear()
        codes.append(client.post("/api/muhurta/pdf",
                                 json=_fresh_search(client, purpose="vehicle", month=month)).status_code)
    assert codes == [200, 200, 200, 200], codes


def test_asking_twice_for_the_same_dates_costs_nothing(on, monkeypatch):
    """A cache hit must not spend a reader's daily allowance - they have not used two of anything."""
    from app.web import muhurta_routes

    monkeypatch.setattr(muhurta_routes, "PDFS_PER_COOKIE_PER_DAY", 1)
    monkeypatch.setattr(muhurta_routes, "PDFS_PER_IP_PER_DAY", 1)
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.clear()
    body = _fresh_search(client, purpose="business", month=12)
    assert client.post("/api/muhurta/pdf", json=body).status_code == 200
    assert client.post("/api/muhurta/pdf", json=body).status_code == 200, \
        "the second ask for the same dates was charged, though it was served from the cache"


# ---- the browser, which is where the flow actually happens ------------------------------------------

from tests.test_rendered_contrast import browser, chromium, live_site  # noqa: E402,F401


@pytest.mark.browser
@pytest.mark.parametrize("path, language", [("/muhurta", "en"), ("/mr/muhurta", "mr")])
def test_a_cold_browser_downloads_the_pdf_without_signing_in(path, language, live_site, browser, monkeypatch):
    """THE ONE THAT MATTERS, because the API tests all passed while this failed.

    The token is signed over the search INCLUDING its language, and the page stored the search without
    one - so the PDF was asked for in English with a token issued in Marathi, and correctly refused. The
    token was right; the page was wrong, and only a browser could say so.

    A fresh context each time: separate storage, no cookies, nobody signed in.
    """
    monkeypatch.setattr(site, "MUHURTA", True)
    context = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    try:
        assert context.cookies() == []
        page = context.new_page()
        page.goto(f"{live_site}{path}", wait_until="networkidle")
        page.fill("#m-city", "Pune")
        page.wait_for_timeout(900)
        page.locator("#m-city-list li").first.click()
        page.fill("#m-from", "2027-03-01")
        page.fill("#m-to", "2027-03-31")
        page.click("#m-submit")
        page.wait_for_timeout(2500)
        assert page.locator("#m-table tbody tr").count() > 0, f"{language}: no dates came back"

        with page.expect_download(timeout=40000) as download:
            page.click("#m-pdf-btn")
        saved = download.value.path()
        assert saved.stat().st_size > 20_000, f"{language}: {saved.stat().st_size} bytes"
        assert saved.read_bytes()[:5] == b"%PDF-"
        assert "/login" not in page.url, "the reader was sent to a sign-in"
    finally:
        context.close()


@pytest.mark.browser
@pytest.mark.parametrize("path", ["/muhurta", "/hi/muhurta", "/mr/muhurta"])
@pytest.mark.parametrize("width", [1280, 390])
def test_clicking_the_button_downloads_a_pdf(path, width, live_site, browser, monkeypatch):
    """CLICKED, in a browser, at both widths and in all three trees - not fetched by a script.

    The smoke check fetched the PDF with a request and passed while the BUTTON did nothing for anybody who
    had the page open under the previous deploy. A request is not a click: a click goes through the markup,
    the script that was actually loaded, and whatever the browser decided to keep from last time.
    """
    monkeypatch.setattr(site, "MUHURTA", True)
    context = browser.new_context(viewport={"width": width, "height": 860}, accept_downloads=True)
    try:
        assert context.cookies() == []
        page = context.new_page()
        page.goto(f"{live_site}{path}", wait_until="networkidle")
        page.fill("#m-city", "Pune")
        page.wait_for_timeout(900)
        page.locator("#m-city-list li").first.click()
        page.fill("#m-from", "2027-03-01")
        page.fill("#m-to", "2027-03-31")
        page.click("#m-submit")
        page.wait_for_timeout(2300)
        assert page.locator("#m-table tbody tr").count() > 0, f"{path}: no dates"

        with page.expect_download(timeout=40000) as download:
            page.click("#m-pdf-btn")
        saved = download.value
        assert saved.suggested_filename.endswith(".pdf"), saved.suggested_filename
        body = saved.path().read_bytes()
        assert body[:5] == b"%PDF-" and len(body) > 20_000, f"{len(body)} bytes"
    finally:
        context.close()


@pytest.mark.browser
def test_a_browser_holding_yesterdays_script_is_not_left_with_a_dead_button(live_site, browser, monkeypatch):
    """THE BUG ITSELF, reproduced and then prevented.

    `muhurta.js` was the one script on the site loaded without `?v={{ static_version }}`, so it was served
    `max-age=3600` at a URL that never changed. A reader who had opened the page under the previous deploy
    kept yesterday's script for an hour - and yesterday's script wires a button id that today's HTML does
    not have. The button did nothing, silently.

    This serves the page with a script that has the old id in it, which is exactly what a cache does, and
    asserts the page the SERVER sends asks for a versioned URL - the thing that stops a browser doing this.
    """
    monkeypatch.setattr(site, "MUHURTA", True)
    context = browser.new_context(viewport={"width": 1280, "height": 860}, accept_downloads=True)
    try:
        page = context.new_page()
        page.goto(f"{live_site}/mr/muhurta", wait_until="networkidle")
        asked = page.evaluate(
            "() => [...document.querySelectorAll('script[src]')].map(s => s.getAttribute('src'))")
        muhurta_src = [src for src in asked if "muhurta.js" in src]
        assert muhurta_src, "the page does not load muhurta.js at all"
        assert "?v=" in muhurta_src[0], (
            f"muhurta.js is asked for as {muhurta_src[0]!r} - with no version a browser keeps it for an "
            f"hour after a deploy, and that is how the button came to do nothing")
    finally:
        context.close()
