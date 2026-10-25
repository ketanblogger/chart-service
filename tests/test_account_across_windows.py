"""One account, two windows: the same remaining answers, the same chats, the same balance.

THE BUG THIS PINS. The chat lived in `sessionStorage`, which is per-tab and empty in a new window, so
signing in somewhere else showed an empty astrologer offering a fresh start - while the reader's own
consultation sat on the server, correctly keyed to their account, with nothing ever asking for it.

The free count and the paid balance were ALREADY account-scoped, and that is why the earlier tests passed:
they asserted `chat_users.user_id` is the account id, which it is. What none of them did was open a SECOND
cookie jar and compare. A key being right is not the same as every reader of it asking for the right thing.
"""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.ai import chat_store
from app.main import app
from app.web import accounts

EMAIL = "across.windows@gmail.com"
# Built from the address under test rather than written out: a hand-written alias list only aliases the
# ONE address it was written for, and substituting into it silently produced a different account whose
# "same allowance" then meant nothing. Gmail folds dots and +tags; these are one of each, plus the
# address itself as the control.
ALIAS_FORMS = ("plain", "plus-tag", "dotted", "capitalised")


def alias_of(email: str, form: str) -> str:
    local, _, domain = email.partition("@")
    if form == "plain":
        return email
    if form == "plus-tag":
        return f"{local}+shop@{domain}"
    if form == "dotted":
        return f"{local[0]}.{local[1:]}@{domain}"
    return f"{local[0].upper()}{local[1:]}@{domain.upper()}"
BIRTH = {"name": "Asha", "date": "1990-11-09", "time": "16:20", "lat": 18.5204, "lon": 73.8567,
         "timezone": "Asia/Kolkata", "city": "Pune"}


class FakeClient:
    """No model is called. The quota machinery is what is under test, not the astrologer."""

    def generate_chat(self, **kwargs):
        class Result:
            text = "A reply."
            usage, model, request_id, data = {}, "fake", None, None
        return Result()


@pytest.fixture(autouse=True)
def _no_ai(monkeypatch):
    import app.ai.chat as chat

    monkeypatch.setattr(chat, "get_chat_client", lambda: FakeClient())


def jar(email: str) -> TestClient:
    """A browser with nothing but a sign-in cookie: a separate cookie jar, like a second window."""
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.clear()
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(email))
    return client


@pytest.fixture
def used_one(request):
    """One account that has started a consultation and spent one free answer."""
    email = f"{request.node.name[:28]}@gmail.com".replace("_", ".")
    first = jar(email)
    started = first.post("/api/consultation/start", json={**BIRTH, "language": "en"})
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]
    answered = first.post("/api/consultation/message",
                          json={"session_id": session_id, "message": "What does my chart say about work?"})
    assert answered.status_code == 200, answered.text
    return {"email": email, "session_id": session_id, "quota": answered.json()["quota"]}


# ---- the free count ---------------------------------------------------------------------------------


def test_a_second_window_sees_the_same_remaining_free_answers(used_one):
    second = jar(used_one["email"])
    quota = second.post("/api/consultation/start", json={**BIRTH, "language": "en"}).json()["quota"]
    assert quota == used_one["quota"], "a new window handed out a fresh allowance"


@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_the_allowance_does_not_depend_on_the_language_the_window_is_in(language, used_one):
    second = jar(used_one["email"])
    quota = second.post("/api/consultation/start", json={**BIRTH, "language": language}).json()["quota"]
    assert quota["free_left"] == used_one["quota"]["free_left"], language


@pytest.mark.parametrize("form", ALIAS_FORMS)
def test_an_alias_of_the_address_is_the_same_account(form, used_one):
    """Gmail folds dots and +tags into one inbox, and so do we - otherwise one person has as many free
    trials as they can think of punctuation."""
    aliased = alias_of(used_one["email"], form)
    quota = jar(aliased).post("/api/consultation/start", json={**BIRTH, "language": "en"}).json()["quota"]
    assert quota["free_left"] == used_one["quota"]["free_left"], aliased


# ---- the chat history -------------------------------------------------------------------------------


def test_a_second_window_can_see_the_consultations_the_first_one_started(used_one):
    second = jar(used_one["email"])
    listed = second.get("/api/consultation/mine")
    assert listed.status_code == 200, listed.text
    ids = [row["session_id"] for row in listed.json()["sessions"]]
    assert used_one["session_id"] in ids, "the chat did not follow the account into a second window"


def test_both_windows_list_exactly_the_same_chats(used_one):
    first, second = jar(used_one["email"]), jar(used_one["email"])
    assert first.get("/api/consultation/mine").json() == second.get("/api/consultation/mine").json()


@pytest.mark.parametrize("form", ALIAS_FORMS)
def test_an_alias_sees_the_same_chats(form, used_one):
    aliased = alias_of(used_one["email"], form)
    ids = [row["session_id"] for row in jar(aliased).get("/api/consultation/mine").json()["sessions"]]
    assert used_one["session_id"] in ids, aliased


def test_the_list_is_only_ever_the_callers_own(used_one):
    """It takes no id from the query - the account comes from the cookie - so this is about what a DIFFERENT
    signed-in person sees, which is nothing of this one's."""
    stranger = jar("someone.else.entirely@gmail.com")
    ids = [row["session_id"] for row in stranger.get("/api/consultation/mine").json()["sessions"]]
    assert used_one["session_id"] not in ids


def test_a_signed_out_window_is_told_to_sign_in_rather_than_shown_a_list():
    cold = TestClient(app, raise_server_exceptions=False)
    cold.cookies.clear()
    answer = cold.get("/api/consultation/mine")
    assert answer.status_code == 401 and answer.json()["detail"]["login_required"] is True


# ---- the paid balance -------------------------------------------------------------------------------


def test_the_paid_balance_is_the_same_in_both_windows(used_one):
    account = accounts.account_id(used_one["email"])
    with db.transaction() as conn:
        conn.execute("UPDATE chat_users SET paid_balance = 7 WHERE user_id = ?", (account,))
    for _ in range(2):
        quota = jar(used_one["email"]).post("/api/consultation/start",
                                            json={**BIRTH, "language": "en"}).json()["quota"]
        assert quota["paid_left"] == 7


# ---- what a visitor used before signing in ----------------------------------------------------------


def test_answers_used_before_signing_in_are_charged_to_the_account(used_one):
    """DECIDED, and this is the decision: they count. Carried by MAX, never assigned - so a browser that
    has spent answers raises the account's count, and a fresh browser can never LOWER one. Assignment was
    what the original note was afraid of, and it was right to be."""
    account = accounts.account_id(used_one["email"])
    cookie_id = "c" * 32
    with db.transaction() as conn:
        conn.execute("INSERT INTO chat_users (user_id, free_used, paid_balance, busy_until, created_at) "
                     "VALUES (?, 2, 0, 0, 0)", (cookie_id,))
        before = conn.execute("SELECT free_used FROM chat_users WHERE user_id = ?", (account,)).fetchone()
    chat_store.adopt_paid_balance(cookie_id, account)
    with db.transaction(write=False) as conn:
        after = conn.execute("SELECT free_used FROM chat_users WHERE user_id = ?", (account,)).fetchone()
    assert after["free_used"] == max(2, before["free_used"]), "a spent trial did not follow the browser"


def test_a_fresh_browser_can_never_lower_a_count_the_account_already_has(used_one):
    """The failure the original note named: arrive with a clean cookie, get the trial back."""
    account = accounts.account_id(used_one["email"])
    with db.transaction() as conn:
        conn.execute("UPDATE chat_users SET free_used = 2 WHERE user_id = ?", (account,))
    fresh = "f" * 32
    with db.transaction() as conn:
        conn.execute("INSERT INTO chat_users (user_id, free_used, paid_balance, busy_until, created_at) "
                     "VALUES (?, 0, 0, 0, 0)", (fresh,))
    chat_store.adopt_paid_balance(fresh, account)
    with db.transaction(write=False) as conn:
        after = conn.execute("SELECT free_used FROM chat_users WHERE user_id = ?", (account,)).fetchone()
    assert after["free_used"] == 2, "a clean cookie reset the account's trial"


def test_the_paid_move_is_still_a_move_and_still_happens_once():
    """Unchanged on purpose. The free carry rides inside the same claim, so neither can happen twice."""
    account = accounts.account_id("paid.move@gmail.com")
    cookie_id = "p" * 32
    with db.transaction() as conn:
        conn.execute("INSERT INTO chat_users (user_id, free_used, paid_balance, busy_until, created_at) "
                     "VALUES (?, 1, 9, 0, 0)", (cookie_id,))
    assert chat_store.adopt_paid_balance(cookie_id, account) == 9
    assert chat_store.adopt_paid_balance(cookie_id, account) == 0, "the same cookie paid out twice"
    with db.transaction(write=False) as conn:
        source = conn.execute("SELECT paid_balance FROM chat_users WHERE user_id = ?", (cookie_id,)).fetchone()
        target = conn.execute("SELECT free_used, paid_balance FROM chat_users WHERE user_id = ?",
                              (account,)).fetchone()
    assert source["paid_balance"] == 0, "the balance was copied rather than moved"
    assert target["paid_balance"] == 9 and target["free_used"] == 1


# ---- the abuse angle --------------------------------------------------------------------------------


def test_a_new_account_on_a_new_address_still_gets_the_whole_allowance():
    """None of this may make the front door narrower for somebody arriving for the first time."""
    from app.ai.config import get_chat_settings

    fresh = jar("brand.new.reader@gmail.com")
    quota = fresh.post("/api/consultation/start", json={**BIRTH, "language": "en"}).json()["quota"]
    assert quota["free_left"] == get_chat_settings().free_messages


def test_the_limits_themselves_are_untouched():
    """Asserted on the constants, so a quiet loosening shows up here rather than in the logs."""
    from app.web import accounts as acc

    assert acc.CODE_TTL_SECONDS == 600
    assert acc.MAX_ATTEMPTS == 5
    assert acc.RESEND_COOLDOWN_SECONDS == 60
    assert acc.CODES_PER_ADDRESS_PER_HOUR == 3
    assert acc.CODES_PER_IP_PER_HOUR == 20
    assert acc.NEW_ACCOUNTS_PER_IP_PER_DAY == 5


# ---- what the page promises -------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/ai-astrologer", "/hi/ai-jyotish", "/mr/ai-jyotish"])
def test_the_page_does_not_promise_free_answers_to_someone_who_has_none(path, used_one):
    """WHAT IT LOOKED LIKE FROM THE OUTSIDE. The page said "your first 2 questions are free" to a reader
    who had spent both, directly above a card saying they were used - which reads as a fresh allowance
    that then refuses to work, and is the likeliest thing anybody actually saw."""
    import re

    account = accounts.account_id(used_one["email"])
    with db.transaction() as conn:
        conn.execute("UPDATE chat_users SET free_used = 99 WHERE user_id = ?", (account,))
    html = jar(used_one["email"]).get(path).text
    note = re.search(r'<p class="form-note">(.*?)</p>', html, re.S)
    assert note, f"{path}: no form note at all"
    text = note.group(1).strip()
    assert "2" not in text, f"{path}: still offering two free questions: {text!r}"


@pytest.mark.parametrize("path", ["/ai-astrologer", "/hi/ai-jyotish", "/mr/ai-jyotish"])
def test_a_visitor_who_has_not_signed_in_still_gets_the_offer(path):
    """The other half: the offer is true for somebody arriving for the first time, and must not be hidden
    from them by a fix aimed at returning readers."""
    import re

    cold = TestClient(app, raise_server_exceptions=False)
    cold.cookies.clear()
    html = cold.get(path).text
    note = re.search(r'<p class="form-note">(.*?)</p>', html, re.S)
    assert note and note.group(1).strip(), f"{path}: no form note for a visitor"


def test_the_page_count_and_the_api_count_agree(used_one):
    """Two readers of the same number. They disagreed before: the page read a constant and the composer
    read the quota."""
    from app.ai import chat_store

    account = accounts.account_id(used_one["email"])
    page_view = chat_store.quota_for_user(account)
    api_view = jar(used_one["email"]).post("/api/consultation/start",
                                           json={**BIRTH, "language": "en"}).json()["quota"]
    assert page_view["free_left"] == api_view["free_left"]
    assert page_view["paid_left"] == api_view["paid_left"]


# ---- and the browser, which is where it was seen ----------------------------------------------------

from tests.test_rendered_contrast import browser, chromium, live_site  # noqa: E402,F401


@pytest.mark.browser
def test_a_second_browser_window_opens_the_same_consultation(live_site, browser, monkeypatch):
    """THE WHOLE BUG, END TO END. Everything above tests the API, and the API was never the problem: the
    sessions were keyed to the account all along. What was wrong lived in the browser, where the session id
    is kept in `sessionStorage` - per tab, empty in a new window - so a second window asked for nothing and
    was given a fresh start.

    Two separate browser CONTEXTS, which is what an incognito window is: separate storage, same sign-in.
    """
    import app.ai.chat as chat

    monkeypatch.setattr(chat, "get_chat_client", lambda: FakeClient())
    email = "browser.two.windows@gmail.com"

    seeded = jar(email)
    started = seeded.post("/api/consultation/start", json={**BIRTH, "language": "en"})
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]
    answer = seeded.post("/api/consultation/message",
                         json={"session_id": session_id, "message": "What does my chart say about work?"})
    assert answer.status_code == 200, answer.text

    cookie = {"name": accounts.COOKIE_NAME, "value": accounts.sign(email),
              "domain": "127.0.0.1", "path": "/"}
    seen = []
    for _ in range(2):                       # two windows, neither of which has ever had this tab's storage
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        try:
            context.add_cookies([cookie])
            page = context.new_page()
            page.goto(f"{live_site}/ai-astrologer", wait_until="networkidle")
            page.wait_for_timeout(1500)
            body = page.inner_text("body").lower()
            seen.append("a reply." in body)
        finally:
            context.close()
    assert all(seen), f"a fresh window did not open the account's consultation: {seen}"


def test_with_the_sign_in_switched_off_nothing_here_changes(monkeypatch):
    """`CHAT_LOGIN=off` is the rollback, and it has to roll back to the OLD behaviour exactly: the cookie
    is the identity again, so the list is the cookie's own consultations and the page shows the offer.
    A fix for signed-in readers must not leave the rollback half-applied."""
    from app.web import site

    monkeypatch.setattr(site, "CHAT_LOGIN", False)
    cold = TestClient(app, raise_server_exceptions=False)
    cold.cookies.clear()
    listed = cold.get("/api/consultation/mine")
    assert listed.status_code == 200, "with the gate off, the list is the cookie's and needs no account"
    assert listed.json()["sessions"] == []

    import re

    note = re.search(r'<p class="form-note">(.*?)</p>', cold.get("/ai-astrologer").text, re.S)
    assert note and "free" in note.group(1).lower(), "the offer disappeared when the gate was switched off"
