"""The numerology consultation: a name and a date of birth, and no chart.

WHAT THIS REPLACES was a dead end on every numerology CTA. "Start the consultation" and the four
question chips all went to the chart chat, which asked for a birth time and a city the reader had
never been asked for, and dropped their numbers and their chosen question on the way.
"""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.ai import chat, chat_identity as identity, chat_prompts, chat_store as store
from app.main import app
from app.web import site


@pytest.fixture(autouse=True)
def _own_db_and_no_login(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "chat.db"))
    monkeypatch.setattr(site, "CHAT_LOGIN", False)


@pytest.fixture
def client():
    return TestClient(app)


def _start(client, **over):
    body = {"date": "1988-03-11", "name": "Asha Vernekar", "language": "en"}
    body.update(over)
    return client.post("/api/consultation/start-numerology", json=body)


# ---- it starts from a date alone -----------------------------------------------------------------

def test_a_date_is_enough_to_start():
    """No clock time, no city. Being asked for either is the bug."""
    with TestClient(app) as client:
        assert _start(client).status_code == 200
        assert client.post("/api/consultation/start-numerology",
                           json={"date": "1988-03-11"}).status_code == 200


@pytest.mark.parametrize("body, why", [
    ({}, "no date at all"),
    ({"date": "1988-02-31"}, "31 February is not a date"),
    ({"date": "not-a-date"}, "not a date"),
])
def test_an_unusable_date_is_refused(client, body, why):
    assert client.post("/api/consultation/start-numerology", json=body).status_code == 422, why


def test_the_chosen_question_comes_back_as_a_prefill_and_not_a_message(client):
    """The chip the reader tapped opens the input box; it is not sent until they press send."""
    started = _start(client, question="  Which career suits my mulank?  ").json()
    assert started["prefill"] == "Which career suits my mulank?"
    assert started["kind"] == "numerology"
    # Nothing has been asked yet, so no reply has been spent.
    assert started.get("messages") in (None, [], 0) or not started.get("history")


def test_no_question_means_no_prefill(client):
    assert _start(client).json()["prefill"] is None


# ---- there is no chart, and nothing pretends there is --------------------------------------------

def test_the_session_carries_numbers_and_no_chart():
    context, summary, facts = chat._session_data({"date": "1988-03-11"}, dt.date(2026, 11, 3),
                                                 numerology_for="Asha Vernekar")
    assert sorted(context) == ["numerology"], "a chart block has appeared in a chartless session"
    assert context["numerology"]["mulank"] == 2 and context["numerology"]["bhagyank"] == 4
    assert summary == {"kind": "numerology"}
    # EMPTY FACTS ARE THE POINT: the validator then has nothing to confirm a sign, house or dasha
    # against, so any such claim in a reply is flagged as unsupported.
    assert all(not value for value in facts.values())


def test_the_readers_name_never_reaches_the_model():
    """The chat's standing rule. core.for_chat returns the number a name adds up to, not the name."""
    context, _, _ = chat._session_data({"date": "1988-03-11"}, dt.date(2026, 11, 3),
                                       numerology_for="Asha Vernekar")
    assert "Asha" not in str(context) and "Vernekar" not in str(context)
    assert context["numerology"]["name_number"]


def test_nothing_is_synthesised_to_make_a_chart_build():
    """A default hour and a default city would produce a REAL chart from invented data, and the
    model would then answer from placements nobody gave it - worse than having no chart."""
    context, _, _ = chat._session_data({"date": "1988-03-11"}, dt.date(2026, 11, 3),
                                       numerology_for="")
    assert "chart" not in context and "transits" not in context and "dasha" not in context


def test_the_prompt_says_there_is_no_chart_and_forbids_asking_for_a_time():
    blocks = chat_prompts.build_system({"numerology": {"mulank": 2}}, first_reply=True)
    joined = "\n".join(b["text"] for b in blocks)
    assert "NO BIRTH CHART" in joined
    assert "NEVER ASK FOR A BIRTH TIME" in joined
    assert not any(b["text"].lstrip().startswith("<chart_data>") for b in blocks)
    assert any("<numerology>" in b["text"] for b in blocks)


def test_the_chart_chat_is_untouched():
    """Its system prompt is the cached prefix of every conversation on this site."""
    blocks = chat_prompts.build_system({"chart": {"lagna": 1}}, first_reply=True)
    joined = "\n".join(b["text"] for b in blocks)
    assert any(b["text"].lstrip().startswith("<chart_data>") for b in blocks)
    assert "NO BIRTH CHART" not in joined, "the numerology rules leaked into the chart chat"


# ---- the free replies are the same two ------------------------------------------------------------

def test_the_numerology_bucket_is_stable_and_distinct():
    a = identity.numerology_bucket("1988-03-11", "ip1")
    assert a == identity.numerology_bucket("1988-03-11", "ip1")
    assert a != identity.numerology_bucket("1988-03-12", "ip1")
    assert a != identity.numerology_bucket("1988-03-11", "ip2")
    assert a != identity.birth_bucket("1988-03-11", "19:30", 16.8, 74.6, "ip1")


def test_a_free_reply_spent_on_the_chart_chat_is_gone_from_numerology_too(client, monkeypatch):
    """THE ALLOWANCE IS PER USER, NOT PER BUCKET. chat_store._quota takes max(the user's free_used,
    the bucket's), so two free questions is two in total - not two here and two there. Asserted
    because a separate bucket makes a second allowance look plausible, and that would be a leak."""
    from app.ai.config import get_chat_settings

    free = get_chat_settings().free_messages
    started = _start(client).json()
    user_id = store.get_session(started["session_id"])["user_id"]

    from app import db

    store.ensure_user(user_id)
    with db.transaction() as conn:
        conn.execute("UPDATE chat_users SET free_used = ? WHERE user_id = ?", (free, user_id))

    again = _start(client).json()
    # UNCONDITIONAL. The first version of this guarded the assertion with `if quota is not None`,
    # which would have passed silently had the accessor been named anything else - the same way of
    # passing with nothing to check that has bitten me three times in this project.
    numerology_quota = store.quota(user_id, identity.numerology_bucket("1988-03-11", "zz"), "zz")
    assert numerology_quota["free_left"] == 0, (
        "the numerology path handed out a second free allowance on top of the chart chat's")
    assert again["session_id"] != started["session_id"]


def test_the_two_paths_read_the_same_user_allowance(client):
    """The other direction: spend it on numerology, and the chart chat has none left either."""
    from app.ai.config import get_chat_settings
    from app import db

    free = get_chat_settings().free_messages
    started = _start(client).json()
    user_id = store.get_session(started["session_id"])["user_id"]
    with db.transaction() as conn:
        conn.execute("UPDATE chat_users SET free_used = ? WHERE user_id = ?", (free, user_id))

    chart_bucket = identity.birth_bucket("1988-03-11", "19:30", 16.8, 74.6, "zz")
    assert store.quota(user_id, chart_bucket, "zz")["free_left"] == 0


# ---- the page the CTAs land on -------------------------------------------------------------------

CONSULTATION = {"en": "/ai-astrologer", "hi": "/hi/ai-jyotishi", "mr": "/mr/ai-jyotishi"}


def _page(client, query=""):
    from app.web import i18n

    return client.get(i18n.url_for("consultation", "en") + query)


def test_arriving_from_a_numerology_page_asks_for_a_name_and_a_date_only(client):
    """THE DEAD END, FROM THE OTHER SIDE. The reader came from a calculator that never asked for a
    birth time or a city, so this page must not either."""
    body = _page(client, "?numerology=1&name=Asha+Vernekar&date=1988-03-11").text
    assert 'data-mode="numerology"' in body
    assert 'data-endpoint="/api/consultation/start-numerology"' in body
    assert 'id="self-city"' not in body, "the city field is still on the page"
    assert 'id="self-time"' not in body and 'name="hour"' not in body, "a birth time is still asked"


def test_the_name_and_date_arrive_prefilled(client):
    body = _page(client, "?numerology=1&name=Asha+Vernekar&date=1988-03-11").text
    assert 'value="Asha Vernekar"' in body
    for part in ('value="11"', 'value="3"', 'value="1988"'):
        assert part in body, part


def test_an_impossible_date_in_the_url_leaves_the_fields_empty(client):
    """A hand-edited ?date= should not prefill something that cannot exist - the reader fills it in
    instead. The date is validated here rather than trusted into the form."""
    import re

    body = _page(client, "?numerology=1&date=1988-02-31").text
    assert 'data-mode="numerology"' in body
    # SCOPED TO THE DAY FIELD. My first version asserted that value="31" was absent from the whole
    # page, which it never is: the state dropdown has Lakshadweep at value="31".
    day = re.search(r'<input[^>]*id="num-chat-day"[^>]*>', body)
    assert day, "the day field is missing"
    assert 'value=""' in day.group(0) or "value=" not in day.group(0), day.group(0)


def test_the_plain_consultation_page_is_unchanged(client):
    """The chart chat is a live paid feature. Without ?numerology it must be exactly what it was."""
    body = _page(client).text
    assert 'data-mode="birth"' in body
    assert 'id="self-city"' in body
    assert 'data-numerology="1"' not in body


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_tree_has_the_numerology_mode(lang):
    from app.web import i18n

    with TestClient(app) as client:
        body = client.get(i18n.url_for("consultation", lang) + "?numerology=1&date=1988-03-11").text
        assert 'data-mode="numerology"' in body, lang


def test_the_script_is_on_both_shells():
    """consultation_v2.html is the live default and consultation.html is a documented rollback; a
    rollback that silently drops a fix is the worst moment to find it missing."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app/web/templates"
    for shell in ("consultation.html", "consultation_v2.html"):
        assert "numerology-chat.js" in (root / shell).read_text(encoding="utf-8"), shell


def test_the_script_only_acts_in_numerology_mode():
    """It returns immediately unless the form says so, which is what keeps it off the chart chat."""
    import pathlib

    js = (pathlib.Path(__file__).resolve().parents[1]
          / "app/static/js/numerology-chat.js").read_text(encoding="utf-8")
    assert 'getAttribute("data-numerology") !== "1"' in js and "return;" in js
    # It must reuse the event chat.js already listens for rather than reimplement the chat.
    assert '"tool:result"' in js
    # And it checks the date rather than letting Date() roll 31 February into 2 March.
    assert "getUTCDate() !== day" in js
