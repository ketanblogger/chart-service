"""Many conversations per account, each about a different person - and ONE allowance across all of them.

THE CLAIM THAT MATTERS. A chat is about one person's chart, so a reader needs several. The free answers
are the ACCOUNT's, so opening another chat must never hand out more - otherwise the allowance is a
formality and the sign-in that was built to enforce it was built for nothing.
"""

import pytest
from fastapi.testclient import TestClient

from app.ai import chat_store
from app.main import app
from app.web import accounts, site

BIRTH = {"name": "Asha", "date": "1990-04-12", "time": "09:15", "lat": 18.5204, "lon": 73.8567,
         "timezone": "Asia/Kolkata", "city": "Pune", "language": "en"}
OTHER = {**BIRTH, "name": "Meera", "date": "1992-08-03", "time": "14:40"}


class FakeClient:
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
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.clear()
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(email))
    return client


def start(client, **extra) -> str:
    answer = client.post("/api/consultation/start", json={**BIRTH, **extra})
    assert answer.status_code == 200, answer.text
    return answer.json()["session_id"]


def chats(client, archived: bool = False) -> list[dict]:
    path = "/api/consultation/mine" + ("?archived=1" if archived else "")
    answer = client.get(path)
    assert answer.status_code == 200, answer.text
    return answer.json()["sessions"]


# ---- the allowance is the account's ------------------------------------------------------------------


def test_a_new_chat_does_not_hand_out_new_free_answers(request):
    """THE WHOLE POINT. Spend them in one conversation, open another, and there are still none."""
    email = f"{request.node.name[:26]}@gmail.com".replace("_", ".")
    client = jar(email)
    first = start(client)
    spent = 0
    for _ in range(10):
        answer = client.post("/api/consultation/message",
                             json={"session_id": first, "message": "What about my work this year?"})
        if answer.status_code == 402:
            break
        assert answer.status_code == 200, answer.text
        spent += 1
    assert spent > 0, "the account never had any free answers to spend"

    second = start(client, **OTHER)
    assert second != first
    refused = client.post("/api/consultation/message",
                          json={"session_id": second, "message": "And what about her work?"})
    assert refused.status_code == 402, (
        f"a brand-new chat was given a fresh allowance: {refused.status_code}")


def test_the_quota_on_a_new_chat_reports_what_is_actually_left(request):
    email = f"{request.node.name[:26]}@gmail.com".replace("_", ".")
    client = jar(email)
    first = start(client)
    client.post("/api/consultation/message", json={"session_id": first, "message": "One question please?"})
    before = client.post("/api/consultation/start", json=BIRTH).json()["quota"]
    second = client.post("/api/consultation/start", json=OTHER).json()["quota"]
    assert second == before, "the second chart's chat reported a different allowance"


# ---- many chats, each about somebody ------------------------------------------------------------------


def test_two_people_get_two_chats_that_stay_apart(request):
    email = f"{request.node.name[:26]}@gmail.com".replace("_", ".")
    client = jar(email)
    mine = start(client, subject="me")
    hers = start(client, **OTHER, subject="wife")

    listed = {row["session_id"]: row for row in chats(client)}
    assert mine in listed and hers in listed
    assert listed[mine]["subject"] == "me" and listed[hers]["subject"] == "wife"

    # ...and the histories do not mix.
    client.post("/api/consultation/message", json={"session_id": mine, "message": "Ask about my career?"})
    one = client.get(f"/api/consultation/session/{mine}").json()
    two = client.get(f"/api/consultation/session/{hers}").json()
    assert one["messages"] and not two["messages"], "the second chat inherited the first one's history"


def test_the_title_comes_from_the_first_question_and_can_be_changed(request):
    email = f"{request.node.name[:26]}@gmail.com".replace("_", ".")
    client = jar(email)
    chat_id = start(client)
    client.post("/api/consultation/message",
                json={"session_id": chat_id, "message": "Will I change jobs this year?"})
    titled = [row for row in chats(client) if row["session_id"] == chat_id][0]
    assert "change jobs" in titled["title"].lower()

    assert client.post("/api/consultation/edit", json={"session_id": chat_id, "title": "Career, 2026"}).status_code == 200
    renamed = [row for row in chats(client) if row["session_id"] == chat_id][0]
    assert renamed["title"] == "Career, 2026"

    # ...and a later question does not overwrite the name the reader chose.
    client.post("/api/consultation/message", json={"session_id": chat_id, "message": "And my health?"})
    assert [row for row in chats(client) if row["session_id"] == chat_id][0]["title"] == "Career, 2026"


def test_archiving_hides_a_chat_without_losing_it(request):
    email = f"{request.node.name[:26]}@gmail.com".replace("_", ".")
    client = jar(email)
    chat_id = start(client)
    assert client.post("/api/consultation/edit", json={"session_id": chat_id, "archived": True}).status_code == 200
    assert chat_id not in [row["session_id"] for row in chats(client)]
    assert chat_id in [row["session_id"] for row in chats(client, archived=True)]
    assert client.get(f"/api/consultation/session/{chat_id}").status_code == 200, "archiving deleted it"


def test_deleting_a_chat_really_deletes_its_messages(request):
    """Not a flag. Somebody who deletes a conversation about their marriage has asked for it to be gone."""
    from app import db

    email = f"{request.node.name[:26]}@gmail.com".replace("_", ".")
    client = jar(email)
    chat_id = start(client)
    client.post("/api/consultation/message", json={"session_id": chat_id, "message": "A question to store?"})
    with db.transaction(write=False) as conn:
        before = conn.execute("SELECT COUNT(*) AS n FROM chat_messages WHERE session_id = ?",
                              (chat_id,)).fetchone()["n"]
    assert before > 0

    assert client.delete(f"/api/consultation/session/{chat_id}").status_code == 200
    with db.transaction(write=False) as conn:
        after = conn.execute("SELECT COUNT(*) AS n FROM chat_messages WHERE session_id = ?",
                             (chat_id,)).fetchone()["n"]
        session_row = conn.execute("SELECT 1 FROM chat_sessions WHERE session_id = ?", (chat_id,)).fetchone()
    assert after == 0 and session_row is None
    assert client.get(f"/api/consultation/session/{chat_id}").status_code == 404


def test_a_stranger_cannot_rename_archive_or_delete_somebody_elses_chat(request):
    email = f"{request.node.name[:26]}@gmail.com".replace("_", ".")
    owner = jar(email)
    chat_id = start(owner)
    stranger = jar("passing.by@gmail.com")
    assert stranger.post("/api/consultation/edit", json={"session_id": chat_id, "title": "mine now"}).status_code == 404
    assert stranger.post("/api/consultation/edit", json={"session_id": chat_id, "archived": True}).status_code == 404
    assert stranger.delete(f"/api/consultation/session/{chat_id}").status_code == 404
    assert owner.get(f"/api/consultation/session/{chat_id}").status_code == 200, "it survived"


def test_the_cap_is_explained_rather_than_just_refused(request, monkeypatch):
    monkeypatch.setattr(chat_store, "MAX_CHATS_PER_ACCOUNT", 3)
    email = f"{request.node.name[:26]}@gmail.com".replace("_", ".")
    client = jar(email)
    for _ in range(3):
        start(client)
    refused = client.post("/api/consultation/start", json=BIRTH)
    assert refused.status_code == 409
    message = refused.json()["detail"]["message"]
    assert "archive" in message.lower(), f"the message does not say what to do: {message!r}"
    assert "nothing is lost" in message.lower()
    # ...and archiving one does NOT free a slot, because an archived chat is still kept.
    first = chats(client)[0]["session_id"]
    client.post("/api/consultation/edit", json={"session_id": first, "archived": True})
    assert client.post("/api/consultation/start", json=BIRTH).status_code == 409
    # Deleting one does.
    client.delete(f"/api/consultation/session/{first}")
    assert client.post("/api/consultation/start", json=BIRTH).status_code == 200


# ---- everything already fixed stays fixed --------------------------------------------------------------


def test_the_list_is_the_same_in_a_second_window_and_for_an_alias(request):
    email = f"{request.node.name[:26]}@gmail.com".replace("_", ".")
    local, _, domain = email.partition("@")
    owner = jar(email)
    first = start(owner, subject="me")
    for other in (jar(email), jar(f"{local}+tag@{domain}"), jar(f"{local[0]}.{local[1:]}@{domain}")):
        ids = [row["session_id"] for row in chats(other)]
        assert first in ids, "the chat did not follow the account"


@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_the_sidebar_is_rendered_in_every_tree(language):
    path = {"en": "/ai-astrologer", "hi": "/hi/ai-jyotish", "mr": "/mr/ai-jyotish"}[language]
    html = jar("sidebar.reader@gmail.com").get(path).text
    for required in ('id="chat-list-panel"', 'id="chat-new"', 'id="chat-list-toggle"'):
        assert required in html, f"{language}: {required} missing"
    # The words come from the server, in the reader's language, on data attributes - never an inline
    # <script>, which the CSP would block.
    assert 'data-rename=' in html and 'data-archive=' in html
    assert '<script' not in html.split('chat-list-panel')[1].split('</nav>')[0]


def test_with_the_sign_in_off_nothing_here_demands_an_account(monkeypatch):
    """`CHAT_LOGIN=off` is the rollback and must roll back completely: the cookie is the identity again."""
    monkeypatch.setattr(site, "CHAT_LOGIN", False)
    cold = TestClient(app, raise_server_exceptions=False)
    cold.cookies.clear()
    assert cold.get("/api/consultation/mine").status_code == 200


# ---- the browser, where a sidebar either works or does not ---------------------------------------------

from tests.test_rendered_contrast import browser, chromium, live_site  # noqa: E402,F401


@pytest.mark.browser
def test_two_chats_stay_apart_in_a_real_browser(live_site, browser, monkeypatch):
    """Two people, two charts, two histories - and switching between them shows the right one.

    The API tests above prove the data is separate. This proves the PAGE is: the sidebar lists both, a
    click opens one, and the conversation that appears is that chat's and not the other's.
    """
    import app.ai.chat as chat

    monkeypatch.setattr(chat, "get_chat_client", lambda: FakeClient())
    email = "browser.two.chats@gmail.com"
    seeded = jar(email)
    mine = start(seeded, subject="me")
    hers = start(seeded, **OTHER, subject="wife")
    seeded.post("/api/consultation/message",
                json={"session_id": mine, "message": "A question about MY career?"})
    seeded.post("/api/consultation/message",
                json={"session_id": hers, "message": "A question about HER marriage?"})

    cookie = {"name": accounts.COOKIE_NAME, "value": accounts.sign(email),
              "domain": "127.0.0.1", "path": "/"}
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        context.add_cookies([cookie])
        page = context.new_page()
        page.goto(f"{live_site}/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(1500)

        titles = page.locator(".v2-chats__title")
        assert titles.count() >= 2, f"the sidebar lists {titles.count()} chats"
        listed = [titles.nth(n).inner_text() for n in range(titles.count())]
        assert any("MY career" in text for text in listed), listed
        assert any("HER marriage" in text for text in listed), listed

        # Open the one about her, and check the conversation that appears is hers.
        for n in range(titles.count()):
            if "HER marriage" in titles.nth(n).inner_text():
                titles.nth(n).click()
                break
        page.wait_for_timeout(1500)
        body = page.inner_text("body")
        assert "HER marriage" in body
        assert "MY career" not in page.inner_text("#chat-log"), "the other chat's history leaked in"
    finally:
        context.close()


@pytest.mark.browser
def test_the_same_list_appears_after_a_refresh_and_in_a_second_window(live_site, browser, monkeypatch):
    import app.ai.chat as chat

    monkeypatch.setattr(chat, "get_chat_client", lambda: FakeClient())
    email = "browser.list.persists@gmail.com"
    seeded = jar(email)
    start(seeded, subject="me")
    seeded.post("/api/consultation/message",
                json={"session_id": chats(seeded)[0]["session_id"], "message": "A question to title it?"})

    cookie = {"name": accounts.COOKIE_NAME, "value": accounts.sign(email),
              "domain": "127.0.0.1", "path": "/"}
    seen = []
    for _ in range(2):                      # a fresh context each time: a second window, not a reload
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        try:
            context.add_cookies([cookie])
            page = context.new_page()
            page.goto(f"{live_site}/ai-astrologer", wait_until="networkidle")
            page.wait_for_timeout(1500)
            seen.append(page.locator(".v2-chats__title").count())
        finally:
            context.close()
    assert seen[0] >= 1 and seen[0] == seen[1], f"the list differed between windows: {seen}"


@pytest.mark.browser
def test_the_list_is_a_drawer_on_a_phone_and_a_column_on_a_desktop(live_site, browser, monkeypatch):
    """One list, two shapes. On a phone it must not be sitting on top of the conversation by default."""
    import app.ai.chat as chat

    monkeypatch.setattr(chat, "get_chat_client", lambda: FakeClient())
    email = "browser.drawer@gmail.com"
    start(jar(email), subject="me")
    cookie = {"name": accounts.COOKIE_NAME, "value": accounts.sign(email),
              "domain": "127.0.0.1", "path": "/"}
    for width, drawer in ((390, True), (1280, False)):
        context = browser.new_context(viewport={"width": width, "height": 860})
        try:
            context.add_cookies([cookie])
            page = context.new_page()
            page.goto(f"{live_site}/ai-astrologer", wait_until="networkidle")
            page.wait_for_timeout(1200)
            toggle_shown = page.locator("#chat-list-toggle").is_visible()
            assert toggle_shown == drawer, f"{width}px: toggle visible={toggle_shown}"
            if drawer:
                box = page.locator("#chat-list-panel").bounding_box()
                assert box is None or box["x"] < 0, f"{width}px: the drawer is open over the page"
                page.click("#chat-list-toggle")
                page.wait_for_timeout(400)
                opened = page.locator("#chat-list-panel").bounding_box()
                assert opened and opened["x"] >= -1, "the drawer did not open"
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), \
                f"{width}px: the page scrolls sideways"
        finally:
            context.close()


def test_the_sidebar_is_given_a_rashi_and_not_a_chart():
    """The list query now carries `summary_json` so the rashi costs no extra read. That row holds the
    whole chart - every degree, every position - and the sidebar needs two strings from it. If the
    payload is ever built by spreading the row instead of naming its fields, this is what notices."""
    client = jar("sidebar.payload@gmail.com")
    client.post("/api/consultation/start", json=BIRTH)
    rows = client.get("/api/consultation/mine").json()["sessions"]
    assert rows, "no chat to inspect"
    row = rows[0]
    assert row.get("rashi") and row.get("rashi_glyph"), "the sidebar lost the rashi"
    for leak in ("summary_json", "summary", "context_json", "facts_json", "birth_json", "houses"):
        assert leak not in row, f"the sidebar is being sent {leak}"


def test_a_chat_saved_before_the_kundali_existed_still_gets_one():
    """Every conversation on the live site was stored before the panel drew a chart, so their summaries
    have no `houses`. Reopening one must top it up - otherwise the feature works only for chats started
    after the deploy, and the people with the most history see the least.

    And it must NOT re-date the transits while doing it: a conversation being read is not a conversation
    being continued, and silently moving `as_of` would change what the next answer is built on.
    """
    import json

    from app import db

    client = jar("old.chat@gmail.com")
    session_id = client.post("/api/consultation/start", json=BIRTH).json()["session_id"]
    with db.transaction() as conn:
        row = conn.execute("SELECT summary_json, as_of FROM chat_sessions WHERE session_id = ?",
                           (session_id,)).fetchone()
        as_of_before = row["as_of"]
        stored = json.loads(row["summary_json"])
        stored.pop("houses", None)
        stored.pop("grahas", None)
        conn.execute("UPDATE chat_sessions SET summary_json = ? WHERE session_id = ?",
                     (json.dumps(stored), session_id))

    view = client.get(f"/api/consultation/session/{session_id}").json()
    assert len(view["summary"].get("houses") or []) == 12, "an old chat got no chart"
    assert view["summary"]["houses"][0]["sign"], "the houses carry no signs"

    with db.transaction(write=False) as conn:
        after = conn.execute("SELECT as_of FROM chat_sessions WHERE session_id = ?",
                             (session_id,)).fetchone()["as_of"]
    assert after == as_of_before, "topping up the summary moved the transit date"
