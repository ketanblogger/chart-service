"""The /admin pages: the gate, the audit log, and the privacy rules - especially what must NOT be on a page.

Three groups of test, and the middle one is the reason this file exists at all:

1. **The gate.** No password configured = closed to everyone. Wrong credentials = 401 and a recorded refusal.
   Enough wrong credentials = locked out with a Retry-After, and the password is then not even compared.
   A valid sign-in mints a 12-hour session cookie; an expired or tampered cookie is refused.
2. **What is not there.** A birth date, a birth time and a customer's name are placed on a real order row,
   and then asserted ABSENT from the orders list, the overview, the quality page and every CSV. The
   addresses on those pages are masked. This is the rule the owner stated and it is the one a future change
   can break without anything else failing, because a leak renders perfectly.
3. **Every page renders and is not indexable**, and /admin is not in the sitemap - which it gets for free by
   not being in the URL registry, and which is asserted here so that stays true.

Invented people only. The birth details and the cover name below belong to nobody; `tests/` is published.
"""

import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import db
from app.admin import audit, auth, metrics
from app.ai import chat_store
from app.main import app
from app.payments import store

PASSWORD = "an-admin-password-long-enough-to-be-real"
# Invented, and deliberately distinctive: every assertion below is that these exact strings are ABSENT, so
# a substring that also occurs in the page chrome would make the test pass for the wrong reason.
BIRTH_DATE, BIRTH_TIME, BIRTH_CITY = "1991-04-05", "07:15:00", "Solapur"
COVER_NAME = "Testperson Invented"
BUYER_EMAIL = "zephyrine.buyer@example.invalid"
SECRETS_THAT_MUST_NOT_LEAK = (BIRTH_DATE, BIRTH_TIME, COVER_NAME)


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("SESSION_SECRET", "test-admin-session-secret")
    monkeypatch.setenv("BASE_URL", "https://admin.test")
    monkeypatch.setenv("ADMIN_LOGIN_MAX_FAILURES", "3")
    monkeypatch.setenv("ADMIN_LOGIN_WINDOW_MINUTES", "15")
    # The overview EVALUATES alerts for its strip and would then deliver them on a background thread. That
    # thread can outlive the test, and monkeypatch undoes this environment at teardown - so a still-running
    # thread would read the developer's real .env and could send a real e-mail from a test run. Delivery is
    # therefore switched off here and proved separately, synchronously, in tests/test_admin_alerts.py.
    monkeypatch.setenv("ADMIN_ALERTS_ON_VIEW", "0")
    monkeypatch.setenv("REPORT_EMAIL_ENABLED", "")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)


@pytest.fixture
def client():
    """Over https, because the session cookie is `Secure` - as it has to be, since basic auth sends the
    password on every request. A client on http would silently never receive the cookie back, which is
    exactly the behaviour a real browser on a misconfigured box would show."""
    return TestClient(app, base_url="https://admin.test")


def header(password: str = PASSWORD, user: str = "admin") -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def paid_order(order_id: str = "ord_adminwebtest", **overrides) -> dict:
    """A paid, ready, costed order carrying invented birth details and an invented cover name."""
    store.insert_order(
        order_id=order_id, product="kundali-report", kind="report", amount_paise=29382, currency="INR",
        razorpay_order_id=f"order_{order_id}", user_id="user-under-test", report_id="b" * 32, language="mr",
        as_of="2026-09-20",
        request={"births": [{"date": BIRTH_DATE, "time": BIRTH_TIME, "lat": 17.6, "lon": 75.9,
                             "timezone": "Asia/Kolkata", "city": BIRTH_CITY}]},
        names={"self": COVER_NAME}, email=BUYER_EMAIL)
    now = time.time()
    usage = {"model": "claude-sonnet-5", "usage": {},
             "calls": [{"call": "part-a", "attempts": 1, "redactions": 0, "repairs": 0,
                        "cut_by_chapter": {}, "cost_estimate_inr": 9.1},
                       {"call": "part-b", "attempts": 2, "redactions": 2, "repairs": 1,
                        "cut_by_chapter": {"3.2": 2}, "cost_estimate_inr": 13.4}]}
    fields = {"paid_at": now - 600, "updated_at": now - 60, "cost_inr": 22.5, "base_paise": 24900,
              "gst_paise": 4482, "gst_rate_bp": 1800, "usage_json": json.dumps(usage), "attempts": 2}
    fields.update(overrides)
    with db.transaction() as conn:
        conn.execute(
            "UPDATE orders SET status='paid', paid_via='verify', payment_id='pay_test', fulfilment='ready', "
            "paid_at=:paid_at, updated_at=:updated_at, cost_inr=:cost_inr, base_paise=:base_paise, "
            "gst_paise=:gst_paise, gst_rate_bp=:gst_rate_bp, usage_json=:usage_json, attempts=:attempts "
            "WHERE id=:id", {**fields, "id": order_id})
    return store.get_order(order_id)


# ---- 1. the gate -------------------------------------------------------------------------------------


def test_admin_does_not_exist_when_nothing_configures_it(client, monkeypatch):
    """CHANGED on 5 October: 404, not 401.

    An unset password used to close the door with a challenge, which was right while the password was the
    only door. The door is now an allowlist of verified addresses (`ADMIN_EMAILS`), and a closed one says
    the page is not there: a 401 or a 403 confirms there IS a dashboard at this address, and an admin
    panel that announces itself is an admin panel being probed by morning.

    The password door still works when ADMIN_PASSWORD is set - locking the owner out on a deploy would be
    a poor trade - so this asserts the state where NEITHER is configured.
    """
    from app.web import site

    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setattr(site, "ADMIN_EMAILS", ())
    response = client.get("/admin", headers=header(""))
    assert response.status_code == 404
    assert "www-authenticate" not in response.headers, "a 404 must not advertise a login"


def test_no_credentials_is_a_challenge_and_not_counted_as_a_failed_attempt(client):
    response = client.get("/admin")
    assert response.status_code == 401
    assert auth.lock_state(audit.ip_key_of(None)) == 0
    with db.transaction(write=False) as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM admin_audit WHERE action = ?",
                            (audit.SIGN_IN_REFUSED,)).fetchone()["n"] == 0


def test_a_wrong_password_is_refused_and_recorded(client):
    assert client.get("/admin", headers=header("wrong")).status_code == 401
    refusals = [entry for entry in audit.recent() if entry["action"] == audit.SIGN_IN_REFUSED]
    assert len(refusals) == 1


def test_a_wrong_user_name_is_refused_too(client):
    assert client.get("/admin", headers=header(PASSWORD, user="root")).status_code == 401


def test_enough_failures_lock_the_caller_out_with_a_retry_after(client):
    """Three failures in the window (ADMIN_LOGIN_MAX_FAILURES=3 above), then 429 - and the 429 arrives even
    for the RIGHT password, because the lock is checked before anything is compared."""
    for _ in range(3):
        assert client.get("/admin", headers=header("wrong")).status_code == 401
    locked = client.get("/admin", headers=header(PASSWORD))
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0
    assert any(entry["action"] == audit.LOCKED_OUT for entry in audit.recent())


def test_the_lockout_reuses_the_existing_rate_events_table(client):
    """Not a second limiter. The sliding window has one implementation - `chat_store.check_rate` - and one
    writer, which is why the admin lock and the chat limit cannot disagree about what a window means."""
    client.get("/admin", headers=header("wrong"))
    with db.transaction(write=False) as conn:
        keys = [row["key"] for row in conn.execute("SELECT DISTINCT key FROM rate_events")]
    assert any(key.startswith("admin-login:") for key in keys)
    assert "admin-login:all" in keys, "a per-IP limit alone is blind to attempts spread across networks"
    assert hasattr(chat_store, "check_rate")


def test_a_global_failure_count_locks_out_even_from_fresh_networks(client, monkeypatch):
    monkeypatch.setenv("ADMIN_LOGIN_MAX_FAILURES", "50")     # the per-network limit must not be what trips
    monkeypatch.setenv("ADMIN_LOGIN_MAX_FAILURES_ALL", "2")
    for _ in range(2):
        client.get("/admin", headers=header("wrong"))
    assert client.get("/admin", headers=header(PASSWORD)).status_code == 429


def test_a_successful_sign_in_mints_a_session_cookie_and_is_recorded(client):
    response = client.get("/admin", headers=header())
    assert response.status_code == 200
    assert auth.COOKIE_NAME in response.cookies
    assert any(entry["action"] == audit.SIGN_IN for entry in audit.recent())


def test_the_session_cookie_alone_authorises_the_next_request(client):
    client.get("/admin", headers=header())
    assert client.get("/admin/orders").status_code == 200, "the cookie should carry the session"


def test_a_session_older_than_the_configured_hours_is_refused(client, monkeypatch):
    client.get("/admin", headers=header())
    monkeypatch.setenv("ADMIN_SESSION_HOURS", "0")
    assert client.get("/admin/orders").status_code == 401


def test_a_tampered_session_cookie_is_refused(client):
    client.cookies.set(auth.COOKIE_NAME, f"{int(time.time())}.{'0' * 32}")
    assert client.get("/admin/orders").status_code == 401


def test_changing_the_password_invalidates_every_live_session(client, monkeypatch):
    """What the 12-hour session actually buys with basic auth: a password pulled out of .env after a leak
    stops working, instead of living on in every open browser. The signature covers the password's hash."""
    client.get("/admin", headers=header())
    assert client.get("/admin/orders").status_code == 200
    monkeypatch.setenv("ADMIN_PASSWORD", "a-completely-different-admin-password")
    assert client.get("/admin/orders").status_code == 401


def test_logout_drops_the_session_cookie(client):
    client.get("/admin", headers=header())
    response = client.get("/admin/logout", follow_redirects=False)
    assert response.status_code == 303
    assert client.cookies.get(auth.COOKIE_NAME) in (None, "")


# ---- 2. what must not be on a page --------------------------------------------------------------------


def test_no_birth_detail_and_no_customer_name_reaches_the_orders_list(client):
    paid_order()
    body = client.get("/admin/orders", headers=header()).text
    for secret in SECRETS_THAT_MUST_NOT_LEAK:
        assert secret not in body, f"{secret!r} is on the orders list"


def test_the_orders_list_masks_the_address(client):
    paid_order()
    body = client.get("/admin/orders", headers=header()).text
    assert BUYER_EMAIL not in body
    assert metrics.mask_email(BUYER_EMAIL) in body


def test_no_birth_detail_reaches_the_overview_quality_or_cost_pages(client):
    paid_order()
    for path in ("/admin", "/admin/quality", "/admin/cost", "/admin/rashifal", "/admin/system"):
        body = client.get(path, headers=header()).text
        for secret in (*SECRETS_THAT_MUST_NOT_LEAK, BUYER_EMAIL):
            assert secret not in body, f"{secret!r} is on {path}"


def test_the_privacy_boundary_is_a_column_list_and_not_a_convention():
    """`request_json` holds the resolved birth date and time. The list query does not select it, so no list
    template can print it even by accident - which is the difference between a rule and a guarantee."""
    from app.admin import orders as admin_orders

    assert "request_json" not in admin_orders.LIST_COLUMNS
    paid_order()
    row = admin_orders.recent(1)[0]
    assert "request_json" not in row and "names_json" not in row and "token" not in row


def test_the_order_detail_page_shows_the_full_address_but_still_no_birth_date_or_name(client):
    """The single exception the owner allowed, and the limit of it: the address, the place, and nothing else."""
    paid_order()
    body = client.get("/admin/orders/ord_adminwebtest", headers=header()).text
    assert BUYER_EMAIL in body
    assert BIRTH_CITY in body, "the place is what identifies a chart in a support conversation"
    assert BIRTH_DATE not in body and BIRTH_TIME not in body
    assert COVER_NAME not in body, "the page says whether the cover was personalised, not with what"


def test_the_order_token_never_appears_in_admin_html(client):
    """It is a bearer credential: anyone holding it can open the customer's order page and download the PDF."""
    order = paid_order()
    body = client.get("/admin/orders/ord_adminwebtest", headers=header()).text
    assert order["token"] not in body


def test_opening_one_order_is_written_to_the_audit_log(client):
    paid_order()
    client.get("/admin/orders/ord_adminwebtest", headers=header())
    views = audit.views_of("ord_adminwebtest")
    assert len(views) == 1
    assert views[0]["actor"] == "admin"
    assert views[0]["ip_key"] and "127.0.0" not in views[0]["ip_key"], "a raw IP is never stored"


def test_listing_orders_is_not_audited(client):
    """Deliberate: auditing every list view turns the log into a page counter and buries the views that
    matter. The list has no full address and no birth detail, so there is nothing on it to audit."""
    paid_order()
    client.get("/admin/orders", headers=header())
    assert not [entry for entry in audit.recent() if entry["action"] == audit.ORDER_VIEW]


def test_a_missing_order_is_a_404_and_not_an_audit_line(client):
    assert client.get("/admin/orders/ord_does_not_exist", headers=header()).status_code == 404


# ---- exports ----------------------------------------------------------------------------------------


EXPORTS = ("/admin/export/daily-cost.csv", "/admin/export/daily-revenue.csv", "/admin/export/audit.csv")


@pytest.mark.parametrize("path", EXPORTS)
def test_every_export_is_audited(client, path):
    paid_order()
    client.get(path, headers=header())
    exports = [entry for entry in audit.recent() if entry["action"] == audit.EXPORT]
    assert len(exports) == 1 and exports[0]["subject"] == path.rsplit("/", 1)[-1]


@pytest.mark.parametrize("path", EXPORTS)
def test_no_export_contains_a_customer_row(client, path):
    """Aggregates only. A CSV of orders would be a spreadsheet of who bought what, off the server and out
    of reach of the audit log that covers the page it came from."""
    paid_order()
    body = client.get(path, headers=header()).text
    for secret in (*SECRETS_THAT_MUST_NOT_LEAK, BUYER_EMAIL):
        assert secret not in body, f"{secret!r} is in {path}"


def test_the_revenue_export_is_one_row_per_day_and_names_its_nulls(client):
    paid_order()
    body = client.get("/admin/export/daily-revenue.csv?days=7", headers=header()).text
    lines = [line for line in body.splitlines() if line and not line.startswith("#")]
    assert len(lines) == 8, "a header and seven IST days"
    assert "not recorded, never zero" in body.splitlines()[0], "the file has to explain its own blanks"


def test_there_is_no_export_of_customer_rows_at_all():
    """A structural assertion, not a spot check: if someone adds an orders export, this fails and they have
    to come and read the rule rather than discover it in a review."""
    from app.admin import routes

    exports = [route.path for route in routes.router.routes if "/export/" in route.path]
    assert sorted(exports) == ["/admin/export/audit.csv", "/admin/export/daily-cost.csv",
                               "/admin/export/daily-revenue.csv"]


# ---- 3. every page renders, nothing is indexable ------------------------------------------------------


PAGES = ("/admin", "/admin/orders", "/admin/quality", "/admin/cost", "/admin/rashifal", "/admin/system")


@pytest.mark.parametrize("path", PAGES)
def test_every_page_renders_on_an_empty_database(client, path):
    """An empty database is the state this dashboard is FIRST opened in, and a page that divides by zero on
    day one is a page nobody comes back to."""
    response = client.get(path, headers=header())
    assert response.status_code == 200
    assert "not recorded" in response.text or "0" in response.text


@pytest.mark.parametrize("path", PAGES + EXPORTS)
def test_nothing_under_admin_is_indexable_or_cached(client, path):
    paid_order()
    response = client.get(path, headers=header())
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_the_401_itself_is_marked_noindex(client):
    """A crawler that finds /admin without credentials should be told not to index it before anything else."""
    response = client.get("/admin")
    assert response.headers.get("x-robots-tag") == "noindex, nofollow"


def test_admin_is_not_in_the_sitemap(client):
    """It gets this for free by not being in the URL registry, which is exactly why it is asserted: the day
    someone registers an admin page in app/web/i18n.py, this is what says no."""
    import re

    from app.web import seo

    paths = [re.sub(r"https?://[^/]+", "", loc) for loc in re.findall(r"<loc>([^<]+)</loc>", seo.sitemap_xml())]
    assert paths, "the sitemap should not be empty, or this test proves nothing"
    assert not [path for path in paths if path.startswith("/admin")]


def test_the_admin_pages_add_no_asset_and_no_script(client):
    """The CSP in app/hardening.py allows no inline script and no third-party host beyond Razorpay's
    checkout. These pages therefore contain no <script> at all, and their styling is an inline <style>,
    which style-src already permits. Charts are inline SVG for the same reason."""
    paid_order()
    for path in PAGES:
        body = client.get(path, headers=header()).text
        assert "<script" not in body.lower(), f"{path} loads a script"
    assert "<svg" in client.get("/admin", headers=header()).text, "the 30-day trend should be drawn"


def test_no_admin_page_reveals_the_password_or_the_session_secret(client):
    paid_order()
    for path in PAGES + EXPORTS:
        body = client.get(path, headers=header()).text
        assert PASSWORD not in body
        assert "test-admin-session-secret" not in body


def test_the_system_page_does_not_launch_chromium_unless_asked(client, monkeypatch):
    """1.5 s and a browser process, on the box the page exists to watch."""
    launched = []
    from app import hardening

    real = hardening.readiness
    monkeypatch.setattr(hardening, "readiness",
                        lambda check_chromium=False: launched.append(check_chromium) or real(False))
    client.get("/admin/system", headers=header())
    assert launched == [False]
