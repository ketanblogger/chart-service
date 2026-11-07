"""What the dashboard says a thing cost must be what it cost.

WHAT THE DASHBOARD SHOWED. Usage reported Rs 0.00 for every chat question and every report, so Margin was
Revenue - while the Generation page, reading the same calls from a different table, showed Rs 6-13 each.
One of the two pages was lying and it was not the one with the detail on it.

The cause was a single line: `_count_question` read `meta["cost_estimate_inr"]`, which is the name the
REPORT pipeline gives its own field and which the chat never writes. The read returned None, `float(None
or 0.0)` turned that into 0.00, and a column of zeroes is indistinguishable from a free service.

So the second claim here matters as much as the first: an event whose cost is NOT KNOWN must say so. If
"unknown" and "zero" look the same on the page, this bug can happen again and nobody will see it.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app import analytics
from app.main import app
from app.web import accounts

BIRTH = {"name": "Asha", "date": "1990-04-12", "time": "09:15", "lat": 18.5204, "lon": 73.8567,
         "timezone": "Asia/Kolkata", "city": "Pune", "language": "en"}


class Answers:
    """A model with a price in our table, so a real cost can be worked out."""

    model = "claude-sonnet-5"

    def generate_chat(self, **kwargs):
        class Result:
            pass

        Result.text = "Your Guru period runs on for a while yet; keep your routine steady."
        Result.usage = {"input_tokens": 4000, "output_tokens": 300}
        Result.model, Result.request_id, Result.data = self.model, None, None
        return Result


def ask(monkeypatch, client_cls=Answers, language="en"):
    import app.ai.chat as chat

    monkeypatch.setattr(chat, "get_chat_client", lambda: client_cls())
    http = TestClient(app, raise_server_exceptions=False)
    http.cookies.set(accounts.COOKIE_NAME, accounts.sign(f"cost{uuid.uuid4().hex[:8]}@gmail.com"))
    session_id = http.post("/api/consultation/start",
                           json={**BIRTH, "language": language}).json()["session_id"]
    chat.send_message(session_id, "how is my career?", unlimited=True)
    return analytics.recent_events(5)[0]


def test_a_chat_answer_records_what_it_actually_cost(monkeypatch):
    event = ask(monkeypatch)
    assert event["feature"] == "chat" and event["action"] == "question"
    assert event["cost_inr"] > 0, "the dashboard was told this answer was free"
    assert event["cost_known"], "the cost was recorded but not marked as known"


def test_the_cost_matches_the_tokens_at_the_ledgers_own_rate(monkeypatch):
    """Not just "greater than zero" - the NUMBER, so the two pages cannot drift apart again."""
    from app.admin.ledger import usd_inr
    from app.ai.config import estimate_cost_usd

    event = ask(monkeypatch)
    expected = estimate_cost_usd("claude-sonnet-5", {"input_tokens": 4000, "output_tokens": 300}) * usd_inr()
    assert event["cost_inr"] == pytest.approx(expected, rel=0.01), (
        f"usage says {event['cost_inr']}, the tokens say {expected}")


def test_an_unpriced_model_is_not_recorded_as_free(monkeypatch):
    """The failure mode this whole file is about: silence that reads as zero."""

    class Unpriced(Answers):
        model = "claude-some-model-we-have-not-priced"

    event = ask(monkeypatch, Unpriced)
    assert not event["cost_known"], "an unpriced model was recorded as costing nothing"


def test_the_margin_says_so_when_some_costs_are_missing():
    """A margin computed over events with no cost is an over-statement, and the page must admit it."""
    analytics.record_event("chat", "question", cost_inr=None, revenue_inr=0.0)
    summary = analytics.summary(days=1)
    assert summary["cost_unknown"] >= 1


def test_every_model_the_service_is_configured_to_use_has_a_price():
    """The guard for the door this could come back through: set CHAT_MODEL to something unpriced and the
    costs quietly become unknown again. Better to fail here than to discover it on the dashboard."""
    from app.ai.config import PRICES_PER_MTOK, get_chat_settings

    assert get_chat_settings().model in PRICES_PER_MTOK, (
        f"CHAT_MODEL is {get_chat_settings().model!r}, which has no price in PRICES_PER_MTOK - "
        "every chat answer would be recorded with no cost")
