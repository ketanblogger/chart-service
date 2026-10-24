"""Visitors to paying customers, step by step - and every step able to move.

WHY THE SHAPE OF THIS FILE. A funnel step that can never fire is worse than one that is missing: it reads
as an answer. The first version of this had "reached the login page", counting visits to /sign-in - a page
this site does not have, because the sign-in form is inline on whatever page the reader is already on. It
would have reported 0 for ever and been believed. So the one test that matters here walks a visitor
through all eight steps and insists each one moves.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app import analytics
from app.main import app
from app.web import accounts

AGENT = "Mozilla/5.0 (Linux; Android 13) Chrome/119 Mobile Safari/537.36"
BIRTH = {"name": "Asha", "date": "1990-04-12", "time": "09:15", "lat": 18.5204, "lon": 73.8567,
         "timezone": "Asia/Kolkata", "city": "Pune"}


class Answers:
    def generate_chat(self, **kwargs):
        class Result:
            pass

        Result.text = "Your Guru period runs on for a while; keep your routine steady."
        Result.usage = {"input_tokens": 3000, "output_tokens": 200}
        Result.model, Result.request_id, Result.data = "claude-sonnet-5", None, None
        return Result


@pytest.fixture
def walked(monkeypatch):
    """One person, all the way through, using the routes a browser uses."""
    import app.ai.chat as chat

    monkeypatch.setattr(chat, "get_chat_client", lambda: Answers())
    monkeypatch.setenv("MAIL_TEST_MODE", "1")

    email = f"funnel{uuid.uuid4().hex[:8]}@gmail.com"
    client = TestClient(app, headers={"user-agent": AGENT}, raise_server_exceptions=False)
    client.get("/", headers={"referer": "https://www.google.com/"})
    client.get("/ai-astrologer")
    client.post("/api/chart", json=BIRTH)
    client.post("/api/auth/request-code", json={"email": email, "name": "Asha", "language": "en"})
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(email))
    analytics.record_event("auth", "sign-up", account_id=accounts.account_id(email), cost_inr=0.0)

    session_id = client.post("/api/consultation/start",
                             json={**BIRTH, "language": "en"}).json()["session_id"]
    for _ in range(3):                       # enough to run the free allowance out and reach the paywall
        client.post("/api/consultation/message",
                    json={"session_id": session_id, "message": "how is my career?"})
    analytics.record_event("report", "sold", account_id=accounts.account_id(email),
                           revenue_inr=119.0, cost_inr=7.0, source="google")
    return {"email": email, "client": client}


def test_every_step_of_the_funnel_can_actually_move(walked):
    """THE TEST THIS FILE EXISTS FOR. Not that the numbers are right - that none of them is structurally
    stuck at zero because it counts something that never happens."""
    steps = {step["key"]: step for step in analytics.funnel(days=1)}
    assert set(steps) == {key for key, _, _, _ in analytics.FUNNEL}
    stuck = [key for key, step in steps.items() if step["people"] == 0]
    assert not stuck, f"these steps did not move for somebody who walked the whole funnel: {stuck}"


def test_the_funnel_counts_people_not_events(walked):
    """One person asking three questions is one person. Counting events would make the middle of the
    funnel wider than its top, which is not a funnel."""
    steps = {step["key"]: step for step in analytics.funnel(days=1)}
    assert steps["first_q"]["people"] == 1, "three questions from one person counted more than once"
    assert steps["first_q"]["people"] <= steps["visitors"]["people"]


def test_the_chat_paths_come_from_the_registry_that_defines_them():
    """Spelled out by hand they drift the day a URL changes, and the step reads zero for ever."""
    from app.web import i18n

    assert set(analytics._consultation_paths()) == set(i18n.PAGES["consultation"].values())


def test_somebody_who_signed_up_and_never_asked_is_listed():
    """The list is the point, not the count: each row did the hard part and then stopped."""
    email = f"quiet{uuid.uuid4().hex[:8]}@gmail.com"
    analytics.record_event("auth", "sign-up", account_id=accounts.account_id(email), cost_inr=0.0)
    quiet = analytics.accounts_that_never_asked(days=1)
    assert any(row["account_id"] == accounts.account_id(email) for row in quiet)


def test_somebody_who_did_ask_is_not_listed(walked):
    quiet = analytics.accounts_that_never_asked(days=1)
    asked = accounts.account_id(walked["email"])
    assert all(row["account_id"] != asked for row in quiet), "a person who asked was listed as silent"


def test_the_list_holds_no_address(walked):
    """It is read on a page and exported; an account id is a hash and must stay one."""
    for row in analytics.accounts_that_never_asked(days=1):
        assert "@" not in str(row), f"an address reached the never-asked list: {row}"
