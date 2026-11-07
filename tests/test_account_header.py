"""The account control in the header, on every page.

The gap this closes: the sign-in existed only inside the AI astrologer, so a visitor who HAD an account had
no way to reach it - or their own orders - from anywhere else on the site. A sign-in nobody can find is a
sign-in nobody uses.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import accounts, site
# The browser fixtures live with the contrast file; importing them keeps ONE server-and-browser harness
# rather than a second copy that could drift from it.
from tests.test_rendered_contrast import browser, chromium, live_site  # noqa: F401

PAGES = ["/", "/hi/", "/mr/", "/birth-chart", "/hi/kundli", "/mr/kundali",
         "/horoscope/libra/today", "/privacy", "/ai-astrologer", "/login"]
TREES = {"/": "en", "/hi/": "hi", "/mr/": "mr"}


def cold() -> TestClient:
    """A visitor with no cookies at all. The state the gap was found in."""
    return TestClient(app)


def signed_in(email: str = "ashav@gmail.com") -> TestClient:
    client = TestClient(app)
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(email))
    return client


@pytest.mark.parametrize("path", PAGES)
def test_a_signed_out_visitor_can_reach_the_sign_in_from_every_page(path):
    html = cold().get(path).text
    assert "site-account__in" in html, f"{path} has no way to sign in"
    assert "/login" in html


@pytest.mark.parametrize("path", PAGES)
def test_a_signed_in_visitor_gets_an_account_menu_on_every_page(path):
    html = signed_in().get(path).text
    assert "site-account__menu" in html, f"{path} has no account menu"
    assert "site-account__in" not in html, f"{path} offers a sign-in to somebody already signed in"
    assert "/orders" in html and 'id="sign-out"' in html


@pytest.mark.parametrize("path,lang", TREES.items())
def test_the_menu_links_stay_in_the_readers_language(path, lang):
    html = signed_in().get(path).text
    expected_orders = "/orders" if lang == "en" else f"/{lang}/orders"
    assert f'href="{expected_orders}"' in html, f"{path} links to another tree's orders page"

    cold_html = cold().get(path).text
    expected_login = "/login" if lang == "en" else f"/{lang}/login"
    assert f'href="{expected_login}?next=' in cold_html


def test_the_menu_shows_who_is_signed_in_without_printing_the_whole_address():
    """Enough to tell two accounts apart on a shared machine; not the whole address in the chrome of every
    page, where it would be read by whoever is looking over the reader's shoulder."""
    html = signed_in("ashavernekar@gmail.com").get("/").text
    assert "ashavernekar" in html
    menu = re.search(r'<span class="site-account__who"[^>]*>([^<]*)</span>', html)
    assert menu and "@" not in menu.group(1), "the header prints the full e-mail address"


@pytest.mark.parametrize("path", ["/", "/hi/", "/birth-chart"])
def test_signing_in_returns_the_visitor_to_the_page_they_were_on(path):
    html = cold().get(path).text
    assert f"?next={path}" in html, f"{path}: signing in would not come back here"


def test_a_signed_out_visit_to_my_orders_goes_to_sign_in_and_then_back():
    """IT RAISED A 500 BEFORE. Not here - this redirect always worked - but the page behind it did; see
    tests/test_orders_page.py. This pins the round trip."""
    for path in ("/orders", "/hi/orders", "/mr/orders"):
        response = cold().get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"] == f"{path.replace('/orders', '')}/login?next={path}" \
            or response.headers["location"].endswith(f"?next={path}"), response.headers["location"]


def test_the_header_follows_the_sign_in_flag(monkeypatch):
    """With `CHAT_LOGIN` off there is no account to reach, so the header shows NOTHING about accounts - a
    link to a page that would only turn the visitor away is worse than no link. Defined and tested, rather
    than left to whatever happens."""
    monkeypatch.setattr(site, "CHAT_LOGIN", False)
    for path in ("/", "/hi/", "/birth-chart"):
        html = cold().get(path).text
        assert "site-account__in" not in html, f"{path} offers a sign-in with the flag off"
        assert "site-account__menu" not in html

    monkeypatch.setattr(site, "CHAT_LOGIN", True)
    assert "site-account__in" in cold().get("/").text


def test_the_sign_in_page_says_that_registering_is_the_same_thing():
    """A form headed "Sign in" with no mention of creating an account reads, to somebody who has never been
    here, as a door they do not have the key to."""
    for path, lang in TREES.items():
        login = "/login" if lang == "en" else f"/{lang}/login"
        assert "v2-auth__new" in cold().get(login).text, login


def test_none_of_this_changed_the_limits():
    """The abuse protections are untouched by the header: same cooldown, same per-address and per-IP caps,
    same attempt count. Asserted on the constants so a 'small tweak' to them shows up here."""
    assert accounts.CODE_TTL_SECONDS == 600
    assert accounts.MAX_ATTEMPTS == 5
    assert accounts.RESEND_COOLDOWN_SECONDS == 60
    assert accounts.CODES_PER_ADDRESS_PER_HOUR == 3
    assert accounts.CODES_PER_IP_PER_HOUR == 20
    assert accounts.NEW_ACCOUNTS_PER_IP_PER_DAY == 5


# ---- one route to the account, never two ------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/hi/", "/mr/", "/horoscope/libra/today"])
def test_a_phone_reaches_the_account_through_the_menu_that_already_exists(path):
    """THE HEADER HAS A BUDGET. The chip costs a whole extra row at phone width - measured at 158px against
    the 140px that tests/test_layout_widths.py sets deliberately, with a note that it is not a target to
    grow into. So on a phone the account lives in the nav disclosure, which costs nothing, and the chip is
    hidden by CSS; above the breakpoint it is the other way round.

    Both are in the DOCUMENT on every page - that is what lets CSS choose - so what is asserted here is that
    each route exists and that the nav's own item count is untouched by it."""
    html = cold().get(path).text
    assert 'class="site-nav__accountlist"' in html, f"{path}: a phone has no route to the account"
    assert '<li class="site-nav__account">' in html
    assert "site-account__in" in html, f"{path}: a desktop has no route to the account"

    nav = re.search(r'<ul id="site-nav-list">(.*?)</ul>', html, re.S)
    assert nav and "site-nav__account" not in nav.group(1), \
        "the account entries are inside the nav list, where they count as nav items that do not render"


def test_the_phone_menu_offers_orders_and_sign_out_when_signed_in():
    html = signed_in().get("/").text
    entries = re.findall(r'<li class="site-nav__account">(.*?)</li>', html, re.S)
    assert len(entries) == 2, f"expected My orders + Sign out, got {len(entries)}"
    assert "/orders" in entries[0]
    assert 'id="sign-out-nav"' in entries[1]


def test_the_account_css_is_in_the_shared_stylesheet_not_the_prototypes():
    """base.html renders this for BOTH designs. Styled in design-v2.css it was unstyled - and un-hidden on a
    phone - wherever the previous design serves, which is what broke the header budget."""
    import pathlib

    assert "site-account__in" in pathlib.Path("app/static/css/site.css").read_text()
    assert "site-account__in" not in pathlib.Path("app/static/css/design-v2.css").read_text()


@pytest.mark.browser
def test_only_one_route_to_the_account_is_ever_VISIBLE(live_site, browser):
    """PRESENT IS NOT VISIBLE, and the test above only ever checked present.

    Both routes are in the document on purpose - that is what lets CSS choose between them - so asserting
    the markup proved nothing about what a reader sees. It saw nothing wrong while every desktop page in
    all three languages showed "Sign in" twice, because `.site-nav ul { display: flex }` is more specific
    than the class that was supposed to hide the menu copy. This asks the browser.
    """
    for width in (390, 760, 1024, 1440):
        page = browser.new_page(viewport={"width": width, "height": 900})
        try:
            for lang in ("", "/hi", "/mr"):
                page.goto(f"{live_site}{lang}/", wait_until="networkidle")
                chip = page.locator(".site-account").is_visible()
                entry = page.locator(".site-nav__accountlist").is_visible()
                assert not (chip and entry), \
                    f"{width}px {lang or '/'}: the account is offered twice at once"
                if width > 760:
                    assert chip, f"{width}px {lang or '/'}: no way to reach the account at all"
                else:
                    # On a phone it lives inside the menu, so it is reachable once that is opened.
                    assert not chip
                    page.click(".site-nav__toggle")
                    page.wait_for_timeout(120)
                    assert page.locator(".site-nav__accountlist").is_visible(), \
                        f"{width}px {lang or '/'}: the menu opens and the account is still not in it"
        finally:
            page.close()
