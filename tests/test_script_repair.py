"""A Roman-locked chat should not lose an answer because the model slipped into Devanagari mid-word.

WHAT THE DASHBOARD SHOWED. System health, week of 19 October: about twelve answers rejected twice and replaced by the
fallback, nearly all of them Roman-script chats, with reasons naming the offending word - 'chintित',
'dhैर्य', 'rashीत'. The checker was right: those words are in no script. The generation was wrong, and the
customer paid for it with a non-answer.

The drafts themselves are not stored anywhere - only the REASON is, which is why the words above are what
there is to work from. `scripts/replay_rejected.py` replays the real recorded set on the VPS.

The fix is to repair before regenerating: a mixed word in a Roman chat is a transliteration problem, and
transliteration is deterministic. Regenerating is for when the draft is actually wrong.
"""
from __future__ import annotations

import pytest

#: The exact words from the System health page, with the chats they came from. Each is Latin and
#: Devanagari fused into one word - the shape the model produces when it half-switches script.
FROM_THE_LOG = [
    ("1FP51D8_", "chintित", "chintit"),
    ("yt6wHkKo", "dhैर्य", "dhairya"),
    ("nz8Db7nr", "rashीत", "rashit"),
]

#: Whole Devanagari words that turned up inside otherwise-Roman drafts.
STRAY_WORDS = [
    ("5OcuPm_9", "Aapki kundali mein शनि strong hai.", "shani"),
    ("EKwvFFeA", "Guru ki dasha अच्छी chal rahi hai.", "achchhi"),
    ("g-gUUBwd", "Thoda धैर्य rakhiye, sab theek hoga.", "dhairya"),
    ("xp_tArcw", "Aapke 7वें bhav mein Shukra hai.", "7ven"),
]


@pytest.mark.parametrize("chat, word, expected", FROM_THE_LOG)
def test_a_mixed_word_is_repaired_not_regenerated(chat, word, expected):
    from app.ai.chat_style import repair

    draft = f"Aap thode {word} feel kar rahe hain, lekin yeh phase nikal jayega."
    fixed, changed = repair(draft, "hi-Latn")
    assert changed, f"{chat}: nothing was repaired"
    assert expected in fixed, f"{chat}: {word!r} became {fixed!r}, expected {expected!r} in it"


@pytest.mark.parametrize("chat, draft, expected", STRAY_WORDS)
def test_a_whole_devanagari_word_is_transliterated(chat, draft, expected):
    from app.ai.chat_style import repair

    fixed, changed = repair(draft, "mr-Latn")
    assert changed, f"{chat}: nothing was repaired"
    assert expected in fixed.lower(), f"{chat}: got {fixed!r}, expected {expected!r} in it"


@pytest.mark.parametrize("chat, word, _expected", FROM_THE_LOG)
def test_every_repaired_draft_passes_the_check_that_rejected_it(chat, word, _expected):
    """THE CLAIM THAT MATTERS: after repair the draft is clean, so no regeneration is needed at all."""
    from app.ai.chat_style import repair, script_problems

    draft = f"Aap thode {word} feel kar rahe hain, lekin yeh phase nikal jayega."
    assert script_problems(draft, "hi-Latn"), f"{chat}: the draft was not a problem to begin with"
    fixed, _ = repair(draft, "hi-Latn")
    assert not script_problems(fixed, "hi-Latn"), f"{chat}: still broken after repair: {fixed!r}"


def test_repair_leaves_a_clean_roman_draft_exactly_alone():
    from app.ai.chat_style import repair

    clean = "Aapki Chandra mahadasha 4 April 2027 tak hai, aur Guru 11 December 2026 ko margi hoga."
    fixed, changed = repair(clean, "hi-Latn")
    assert not changed and fixed == clean


def test_repair_does_not_touch_a_devanagari_chat_that_is_merely_quoting_a_date():
    from app.ai.chat_style import repair

    clean = "तुमच्या कुंडलीत चंद्र महादशा 4 April 2027 पर्यंत आहे."
    fixed, changed = repair(clean, "mr")
    assert not changed and fixed == clean


def test_a_devanagari_chat_only_has_mixed_words_repaired_not_its_english_terms():
    """In a Devanagari chat the rule is narrower, by the brief: only Latin fused INSIDE a word."""
    from app.ai.chat_style import repair

    draft = "तुमच्या rashीत शनी आहे, Swiss Ephemeris नुसार."
    fixed, changed = repair(draft, "mr")
    assert changed
    assert "Swiss Ephemeris" in fixed, "a legitimate English term was transliterated away"
    assert "rashीत" not in fixed


@pytest.mark.parametrize("deva, roman", [
    ("नमस्कार", "namaskar"),
    ("कुंडली", "kundali"),
    ("शनि", "shani"),
    ("धैर्य", "dhairya"),
    ("राशी", "rashi"),
    ("ग्रह", "grah"),
    ("महादशा", "mahadasha"),
    ("तुमच्या", "tumchya"),
    ("आहे", "ahe"),
    ("मंगळ", "mangal"),
])
def test_the_transliteration_is_the_hinglish_people_actually_write(deva, roman):
    """Not ITRANS, not IAST: no diacritics, no doubled vowels - what a person types on a phone."""
    from app.ai.chat_style import to_roman

    assert to_roman(deva) == roman


# ---- a refusal should explain itself ------------------------------------------------------------------

#: Questions the HARD screen does not catch - so the model is really called, really refuses, and the new
#: path is really the one under test. "how long will I live?" and "mala cancer hoil ka?" are caught before
#: any model is asked, so they prove nothing here: with the fix reverted they still pass, which is exactly
#: what trying it showed.
@pytest.mark.parametrize("question, language, must_contain", [
    ("meri lifespan kitni hai?", "hi-Latn", "bhavishyavani"),
    ("mere paas kitne saal bache hain?", "hi-Latn", "bhavishyavani"),
    ("mala kaunsi bimari hoil?", "mr-Latn", "doctor"),
])
def test_a_model_refusal_about_lifespan_explains_rather_than_malfunctioning(
        question, language, must_contain, monkeypatch):
    """What the live chats showed: a question the model declined came back as "I couldn't put together a reliable
    answer", which reads as a breakage when it was a decision - and tells the reader nothing about what
    this service will help with. The subject has its own explanation already; it just was not reached.
    """
    from fastapi.testclient import TestClient

    import app.ai.chat as chat
    from app.ai.client import AIBadOutput
    from app.main import app
    from app.web import accounts

    class Refuses:
        calls = 0

        def generate_chat(self, **kwargs):
            Refuses.calls += 1
            raise AIBadOutput("the model declined to answer")

    monkeypatch.setattr(chat, "get_chat_client", lambda: Refuses())
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(f"refuse.{language}@gmail.com"))
    session_id = client.post("/api/consultation/start", json={
        "name": "Asha", "date": "1990-04-12", "time": "09:15", "lat": 18.5204, "lon": 73.8567,
        "timezone": "Asia/Kolkata", "city": "Pune", "language": language.split("-")[0]}).json()["session_id"]

    from app.ai.chat_safety import screen_input

    assert screen_input(question) is None, (
        f"{question!r} is caught by the hard screen, so this test would pass without the fix - "
        "pick a question that actually reaches the model")

    reply = chat.send_message(session_id, question, unlimited=True)["reply"]
    assert Refuses.calls > 0, "the model was never called, so no refusal was under test"
    assert reply["kind"] == "safe", f"a refused topic came back as {reply['kind']}"
    assert "couldn" not in reply["content"] and "तयार करता" not in reply["content"], \
        "the reader got the generic fallback for a question we decline on purpose"
    assert must_contain.lower() in reply["content"].lower()


def test_an_ordinary_question_the_model_refuses_still_gets_the_plain_fallback(monkeypatch):
    """The looser topic read must not turn every failure into a lecture about death."""
    from fastapi.testclient import TestClient

    import app.ai.chat as chat
    from app.ai.client import AIBadOutput
    from app.main import app
    from app.web import accounts

    class Refuses:
        def generate_chat(self, **kwargs):
            raise AIBadOutput("truncated")

    monkeypatch.setattr(chat, "get_chat_client", lambda: Refuses())
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign("refuse.plain@gmail.com"))
    session_id = client.post("/api/consultation/start", json={
        "name": "Asha", "date": "1990-04-12", "time": "09:15", "lat": 18.5204, "lon": 73.8567,
        "timezone": "Asia/Kolkata", "city": "Pune", "language": "en"}).json()["session_id"]
    reply = chat.send_message(session_id, "how is my career this year?", unlimited=True)["reply"]
    assert reply["kind"] == "fallback"


# ---- 1d: a fallback is a failure, and Usage must say so ----------------------------------------------

def test_a_fallback_is_recorded_as_a_failure_with_its_reason(monkeypatch):
    """Usage said "Nothing failed" in a week when about twelve people asked a question and got "I
    couldn't put together a reliable answer". The event was written with ok=True, so the one number that
    would have shown it was the one number that could not."""
    import uuid

    from fastapi.testclient import TestClient

    import app.ai.chat as chat
    from app import analytics
    from app.main import app
    from app.web import accounts

    class Mixes:
        def generate_chat(self, **kwargs):
            class Result:
                pass

            Result.text = "aapki dasha \u0633\u0644\u0627\u0645 badlegi"   # a third script: unrepairable
            Result.usage = {"input_tokens": 3000, "output_tokens": 200}
            Result.model, Result.request_id, Result.data = "claude-sonnet-5", None, None
            return Result

    monkeypatch.setattr(chat, "get_chat_client", lambda: Mixes())
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(f"fail{uuid.uuid4().hex[:6]}@gmail.com"))
    session_id = client.post("/api/consultation/start", json={
        "name": "Asha", "date": "1990-04-12", "time": "09:15", "lat": 18.5204, "lon": 73.8567,
        "timezone": "Asia/Kolkata", "city": "Pune", "language": "hi"}).json()["session_id"]

    reply = chat.send_message(session_id, "meri dasha kab badlegi?", unlimited=True)["reply"]
    assert reply["kind"] == "fallback"

    event = analytics.recent_events(5)[0]
    assert event["feature"] == "chat" and event["action"] == "question"
    assert not event["ok"], "the reader got a non-answer and it was recorded as a success"
    assert event["detail"], "the failure was recorded with no reason"
    assert event["cost_inr"] > 0, "a fallback costs real money and must be counted"


def test_an_answered_question_is_recorded_as_a_success_with_its_cost(monkeypatch):
    import uuid

    from fastapi.testclient import TestClient

    import app.ai.chat as chat
    from app import analytics
    from app.main import app
    from app.web import accounts

    class Answers:
        def generate_chat(self, **kwargs):
            class Result:
                pass

            Result.text = "Aapki dasha theek chal rahi hai, dhairya rakhiye."
            Result.usage = {"input_tokens": 4000, "output_tokens": 300}
            Result.model, Result.request_id, Result.data = "claude-sonnet-5", None, None
            return Result

    monkeypatch.setattr(chat, "get_chat_client", lambda: Answers())
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(f"okq{uuid.uuid4().hex[:6]}@gmail.com"))
    session_id = client.post("/api/consultation/start", json={
        "name": "Asha", "date": "1990-04-12", "time": "09:15", "lat": 18.5204, "lon": 73.8567,
        "timezone": "Asia/Kolkata", "city": "Pune", "language": "hi"}).json()["session_id"]
    chat.send_message(session_id, "meri dasha kaisi hai?", unlimited=True)

    event = analytics.recent_events(5)[0]
    assert event["ok"] and event["cost_inr"] > 0, "a real answer was recorded as free"
